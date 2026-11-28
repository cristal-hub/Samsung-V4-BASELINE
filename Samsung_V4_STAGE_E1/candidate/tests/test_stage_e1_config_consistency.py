# tests/test_stage_e1_config_consistency.py
# SAMSUNG V4 — NEW STRATEGY ENGINE. STAGE E.1.
# Correction №3 — проверка согласованности конфигураций
# HistoricalDataFeed и BacktestEngine (fail-closed, без неявного выбора).
#
# 7 обязательных сценариев ТЗ E.1 §5.3 + дополнительные проверки.
# Только оффлайн, синтетические данные.

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from historical_engine import (
    BacktestEngine,
    Candle,
    DataFeedError,
    EngineConfig,
    EngineConfigError,
    HistoricalDataFeed,
    SessionBreak,
    TradingCalendar,
    TradingSession,
)
from tests.stage_e_tools import (
    AlwaysBuyStrategy,
    flat_candles,
    make_engine_config,
    make_strategy_config,
)

UTC = timezone.utc
MSK = timezone(timedelta(hours=3))


def make_calendar(*, tz=MSK, label="test-calendar"):
    """Календарь двух торговых дней 07:00–15:45 UTC (10:00–18:45 MSK).

    Моменты сессий ОДИНАКОВЫ для любого tz — различается ТОЛЬКО
    представление часового пояса меток.
    """
    utc_day1 = datetime(2024, 1, 8, 7, 0, tzinfo=timezone.utc)
    utc_day2 = datetime(2024, 1, 9, 7, 0, tzinfo=timezone.utc)
    sessions = tuple(
        TradingSession(
            open_time=utc_open.astimezone(tz),
            close_time=(utc_open + timedelta(hours=8, minutes=45))
            .astimezone(tz))
        for utc_open in (utc_day1, utc_day2)
    )
    return TradingCalendar(sessions=sessions, label=label)


def make_candles_msk():
    """Свечи в поясе календаря (MSK): 5 часовых свечей 8–9 января."""
    base = datetime(2024, 1, 8, 10, 0, tzinfo=MSK)
    return [Candle(timestamp=base + timedelta(hours=h, days=d),
                   open=100.0, high=100.1, low=99.9, close=100.0,
                   volume=1000.0)
            for d in (0, 1) for h in range(9)]


def build_feed(config):
    return HistoricalDataFeed.from_candles(make_candles_msk(),
                                           engine_config=config)


def build_engine(feed, strategy_config, engine_config):
    return BacktestEngine(strategy=AlwaysBuyStrategy(),
                          strategy_config=strategy_config,
                          engine_config=engine_config,
                          feed=feed)


# 1. Полное совпадение конфигураций -------------------------------------------

def test_identical_configs_accepted():
    strategy = AlwaysBuyStrategy()
    strategy_config = make_strategy_config(strategy, {"warmup": 1})
    config = make_engine_config(expected_candle_interval_seconds=3600,
                                gap_policy="REPORT")
    feed = build_feed(config)
    # Тот же объект конфигурации — запуск разрешён.
    engine = build_engine(feed, strategy_config, config)
    report = engine.run_full()
    assert report["metadata"]["run_id"]
    # Равные, но РАЗНЫЕ экземпляры (те же значения) — тоже совместимы.
    equal_config = make_engine_config(expected_candle_interval_seconds=3600,
                                      gap_policy="REPORT")
    equal_feed = build_feed(equal_config)
    engine2 = build_engine(equal_feed, strategy_config, config)
    assert engine2.run_full()["report_sha256"] == report["report_sha256"]


# 2. Различие expected_candle_interval_seconds --------------------------------

def test_interval_mismatch_rejected():
    strategy_config = make_strategy_config(AlwaysBuyStrategy(), {"warmup": 1})
    feed_config = make_engine_config(expected_candle_interval_seconds=3600)
    other_config = make_engine_config(expected_candle_interval_seconds=7200)
    feed = build_feed(feed_config)
    with pytest.raises(EngineConfigError) as exc:
        build_engine(feed, strategy_config, other_config)
    message = str(exc.value)
    assert "expected_candle_interval_seconds" in message
    assert "3600" in message and "7200" in message


# 3. Различие gap_policy --------------------------------------------------------

def test_gap_policy_mismatch_rejected():
    strategy_config = make_strategy_config(AlwaysBuyStrategy(), {"warmup": 1})
    feed_config = make_engine_config(expected_candle_interval_seconds=3600,
                                     gap_policy="REPORT")
    other_config = make_engine_config(expected_candle_interval_seconds=3600,
                                      gap_policy="STRICT")
    feed = build_feed(feed_config)
    with pytest.raises(EngineConfigError) as exc:
        build_engine(feed, strategy_config, other_config)
    message = str(exc.value)
    assert "gap_policy" in message
    assert "REPORT" in message and "STRICT" in message


# 4. Различие календарей ------------------------------------------------------------

def test_calendar_mismatch_rejected():
    strategy_config = make_strategy_config(AlwaysBuyStrategy(), {"warmup": 1})
    calendar_a = make_calendar()
    # Другой календарь: иная граница сессии (18:00 вместо 18:45).
    day = datetime(2024, 1, 8, 10, 0, tzinfo=MSK)
    calendar_b = TradingCalendar(
        sessions=(TradingSession(open_time=day,
                                 close_time=day + timedelta(hours=8)),
                  TradingSession(
                      open_time=datetime(2024, 1, 9, 10, 0, tzinfo=MSK),
                      close_time=datetime(2024, 1, 9, 18, 0, tzinfo=MSK))),
        label="other")
    feed_config = make_engine_config(expected_candle_interval_seconds=3600,
                                     calendar=calendar_a)
    other_config = make_engine_config(expected_candle_interval_seconds=3600,
                                      calendar=calendar_b)
    feed = build_feed(feed_config)
    with pytest.raises(EngineConfigError) as exc:
        build_engine(feed, strategy_config, other_config)
    assert "calendar" in str(exc.value)


# 5. Отсутствующий календарь с обеих сторон -------------------------------------------

def test_both_calendars_absent_accepted():
    strategy_config = make_strategy_config(AlwaysBuyStrategy(), {"warmup": 1})
    config = make_engine_config(expected_candle_interval_seconds=3600)
    feed = build_feed(config)
    engine = build_engine(feed, strategy_config, config)
    report = engine.run_full()
    assert report["gap_verification"]["calendar_present"] is False


# 6. Различающиеся timezone settings -----------------------------------------------

def test_timezone_presentation_mismatch_rejected():
    """Одинаковые моменты сессий, РАЗНОЕ представление часового пояса
    (UTC против фиксированного UTC+03:00) — несовместимые конфигурации:
    часовой пояс — часть конфигурации интерпретации данных."""
    strategy_config = make_strategy_config(AlwaysBuyStrategy(), {"warmup": 1})
    utc_calendar = make_calendar(tz=UTC, label="utc")
    msk_calendar = make_calendar(tz=MSK, label="msk")
    # Контроль: моменты сессий совпадают, представление пояса различно.
    assert utc_calendar.sessions[0].open_time == msk_calendar.sessions[0].open_time
    assert utc_calendar.sessions[0].open_time.tzinfo != \
        msk_calendar.sessions[0].open_time.tzinfo
    assert utc_calendar.calendar_sha256() != msk_calendar.calendar_sha256()
    feed_config = make_engine_config(expected_candle_interval_seconds=3600,
                                     calendar=msk_calendar)
    other_config = make_engine_config(expected_candle_interval_seconds=3600,
                                      calendar=utc_calendar)
    feed = build_feed(feed_config)
    with pytest.raises(EngineConfigError) as exc:
        build_engine(feed, strategy_config, other_config)
    assert "calendar" in str(exc.value)


# 7. Проверка отсутствия побочных эффектов при отказе -----------------------------------

def test_no_side_effects_on_rejection():
    strategy = AlwaysBuyStrategy()
    strategy_config = make_strategy_config(strategy, {"warmup": 1})
    feed_config = make_engine_config(expected_candle_interval_seconds=3600)
    other_config = make_engine_config(expected_candle_interval_seconds=7200)
    feed = build_feed(feed_config)
    length_before = feed.length
    data_sha_before = feed.data_sha256
    gaps_before = feed.gaps
    status_before = feed.gap_verification_status
    # Отказ (fail-closed)...
    with pytest.raises(EngineConfigError):
        build_engine(feed, strategy_config, other_config)
    # ...НЕ оставляет побочных эффектов на фиде.
    assert feed.length == length_before
    assert feed.data_sha256 == data_sha_before
    assert feed.gaps == gaps_before
    assert feed.gap_verification_status == status_before
    assert feed.candle(0).timestamp == make_candles_msk()[0].timestamp
    # И на конфигурациях (неизменяемые, значения не тронуты).
    assert feed_config.expected_candle_interval_seconds == 3600
    assert other_config.expected_candle_interval_seconds == 7200
    # Совместимый движок с тем же фидом создаётся и работает после отказа.
    engine = build_engine(feed, strategy_config, feed_config)
    report = engine.run_full()
    assert report["report_sha256"]


# --- дополнительные проверки ----------------------------------------------------------------

def test_calendar_presence_mismatch_rejected():
    """Календарь есть у фида, но отсутствует у движка (и наоборот) —
    несовместимость: классификация пропусков различалась бы."""
    strategy_config = make_strategy_config(AlwaysBuyStrategy(), {"warmup": 1})
    calendar = make_calendar()
    with_calendar = make_engine_config(expected_candle_interval_seconds=3600,
                                       calendar=calendar)
    without_calendar = make_engine_config(expected_candle_interval_seconds=3600)
    feed = build_feed(with_calendar)
    with pytest.raises(EngineConfigError) as exc:
        build_engine(feed, strategy_config, without_calendar)
    assert "feed=PRESENT != engine=ABSENT" in str(exc.value)
    # Зеркальный случай: у фида нет, у движка есть.
    feed2 = build_feed(without_calendar)
    with pytest.raises(EngineConfigError) as exc2:
        build_engine(feed2, strategy_config, with_calendar)
    assert "feed=ABSENT != engine=PRESENT" in str(exc2.value)


def test_calendar_config_plumbed_into_report():
    """Совместимые конфигурации с календарём: отпечаток календаря
    доходит до отчёта и участвует в хеше конфигурации."""
    strategy = AlwaysBuyStrategy()
    strategy_config = make_strategy_config(strategy, {"warmup": 1})
    calendar = make_calendar()
    config = make_engine_config(expected_candle_interval_seconds=3600,
                                calendar=calendar)
    feed = build_feed(config)
    engine = build_engine(feed, strategy_config, config)
    report = engine.run_full()
    assert report["gap_verification"]["calendar_sha256"] \
        == calendar.calendar_sha256()
    assert report["metadata"]["calendar_sha256"] == calendar.calendar_sha256()
    # Конфигурации, различающиеся ТОЛЬКО календарём, дают разные хеши.
    plain_config = make_engine_config(expected_candle_interval_seconds=3600)
    assert config.config_sha256() != plain_config.config_sha256()


def test_mismatch_diagnostic_lists_all_differences():
    """Диагностика перечисляет ВСЕ различающиеся параметры, а не только
    первый найденный."""
    strategy_config = make_strategy_config(AlwaysBuyStrategy(), {"warmup": 1})
    feed_config = make_engine_config(expected_candle_interval_seconds=3600,
                                     gap_policy="REPORT")
    other_config = make_engine_config(expected_candle_interval_seconds=7200,
                                      gap_policy="STRICT")
    feed = build_feed(feed_config)
    with pytest.raises(EngineConfigError) as exc:
        build_engine(feed, strategy_config, other_config)
    message = str(exc.value)
    assert "expected_candle_interval_seconds" in message
    assert "gap_policy" in message


def test_no_calendar_unrelated_parameters_not_compared():
    """Несвязанные параметры (капитал, комиссии, риск-лимиты) НЕ влияют на
    совместимость интерпретации данных."""
    strategy_config = make_strategy_config(AlwaysBuyStrategy(), {"warmup": 1})
    feed_config = make_engine_config(expected_candle_interval_seconds=3600)
    other_config = make_engine_config(
        expected_candle_interval_seconds=3600,
        initial_cash=500000.0,
        commission_rate=0.0005,
        slippage_rate=0.001,
    )
    feed = build_feed(feed_config)
    # Различаются только несвязанные параметры — совместимость ОК.
    engine = build_engine(feed, strategy_config, other_config)
    assert engine.engine_config is other_config
    assert engine.strategy_config is strategy_config
