# tests/test_stage_e_data_feed.py
# SAMSUNG V4 — NEW STRATEGY ENGINE. STAGE E.
# Тесты HistoricalDataFeed: хронологический порядок, некорректные данные,
# пропущенные свечи, отсутствие доступа к будущим данным (ТЗ Stage E §9).
# Offline-only.

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from historical_engine import (
    Candle,
    DataFeedError,
    EngineConfigError,
    HistoricalDataFeed,
)
from tests.stage_e_tools import (
    TEST_FIGI,
    flat_candles,
    make_candles,
    make_engine_config,
)


def _feed(candles, **cfg_overrides):
    cfg = make_engine_config(**cfg_overrides)
    return HistoricalDataFeed.from_candles(candles, engine_config=cfg)


# --- хронологический порядок -------------------------------------------------

def test_chronological_order_accepted_and_length_preserved():
    candles = flat_candles(10)
    feed = _feed(candles)
    assert feed.length == 10
    assert feed.candle(0).timestamp < feed.candle(9).timestamp


def test_non_chronological_candles_rejected():
    candles = flat_candles(3)
    reordered = [candles[1], candles[0], candles[2]]
    with pytest.raises(DataFeedError):
        _feed(reordered)


def test_duplicate_timestamps_rejected():
    candles = flat_candles(3)
    duplicated = [candles[0], candles[1], candles[1]]
    with pytest.raises(DataFeedError):
        _feed(duplicated)


def test_naive_timestamp_rejected():
    naive = datetime(2024, 1, 2, 10, 0)   # без часового пояса
    with pytest.raises(DataFeedError):
        Candle(timestamp=naive, open=100.0, high=101.0, low=99.0,
               close=100.5, volume=10.0)


# --- некорректные данные -------------------------------------------------------

@pytest.mark.parametrize("field,value", [
    ("open", 0.0), ("high", -1.0), ("low", float("nan")),
    ("close", float("inf")), ("volume", -5.0),
])
def test_invalid_ohlc_values_rejected(field, value):
    kwargs = dict(timestamp=datetime(2024, 1, 2, tzinfo=timezone.utc),
                  open=100.0, high=101.0, low=99.0, close=100.5, volume=10.0)
    kwargs[field] = value
    with pytest.raises(DataFeedError):
        Candle(**kwargs)


def test_broken_ohlc_geometry_rejected():
    base = datetime(2024, 1, 2, 10, 0, tzinfo=timezone.utc)
    # high ниже close — геометрия свечи нарушена
    with pytest.raises(DataFeedError):
        Candle(timestamp=base, open=100.0, high=100.2, low=99.0,
               close=100.5, volume=10.0)
    # low выше open — геометрия свечи нарушена
    with pytest.raises(DataFeedError):
        Candle(timestamp=base, open=100.0, high=101.0, low=100.1,
               close=100.0, volume=10.0)


def test_empty_series_rejected():
    with pytest.raises(DataFeedError):
        _feed([])


def test_bool_price_rejected():
    base = datetime(2024, 1, 2, 10, 0, tzinfo=timezone.utc)
    with pytest.raises(DataFeedError):
        Candle(timestamp=base, open=True, high=101.0, low=99.0,
               close=100.5, volume=10.0)


# --- пропущенные свечи -----------------------------------------------------------

def test_gap_detection_report_policy():
    candles = flat_candles(3)
    gapped = [candles[0], candles[1],
              Candle(timestamp=candles[1].timestamp + timedelta(seconds=180),
                     open=candles[1].close, high=candles[1].close + 1,
                     low=candles[1].close - 1, close=candles[1].close,
                     volume=1000.0)]
    feed = _feed(gapped, expected_candle_interval_seconds=60,
                 gap_policy="REPORT")
    assert len(feed.gaps) == 1
    expected_ts, actual_ts = feed.gaps[0]
    assert expected_ts == (candles[1].timestamp
                           + timedelta(seconds=60)).isoformat()
    assert actual_ts == (candles[1].timestamp
                         + timedelta(seconds=180)).isoformat()


def test_gap_policy_strict_rejects_series_with_gap():
    candles = flat_candles(3)
    gapped = [candles[0], candles[1],
              Candle(timestamp=candles[1].timestamp + timedelta(seconds=120),
                     open=candles[1].close, high=candles[1].close + 1,
                     low=candles[1].close - 1, close=candles[1].close,
                     volume=1000.0)]
    with pytest.raises(DataFeedError):
        _feed(gapped, expected_candle_interval_seconds=60,
              gap_policy="STRICT")


def test_no_gaps_reported_for_regular_series():
    feed = _feed(flat_candles(5), expected_candle_interval_seconds=60)
    assert feed.gaps == ()


def test_gap_control_disabled_is_explicit_configuration():
    # None (умолчание движка) — ЯВНОЕ решение: контроль только хронологии.
    feed = _feed(flat_candles(5))
    assert feed.gaps == ()


# --- отсутствие доступа к будущим данным ------------------------------------------

def test_view_upto_never_returns_future_candles():
    candles = flat_candles(8)
    feed = _feed(candles)
    for index in range(8):
        view = feed.view_upto(index)
        assert len(view) == index + 1
        assert view[-1].timestamp == candles[index].timestamp
    with pytest.raises(DataFeedError):
        feed.view_upto(8)          # будущей свечи не существует
    with pytest.raises(DataFeedError):
        feed.view_upto(-1)


def test_entry_dataframe_upto_is_defensive_copy():
    candles = flat_candles(5)
    feed = _feed(candles)
    frame = feed.entry_dataframe_upto(3)
    assert len(frame) == 4
    assert list(frame.columns) == ["open", "high", "low", "close", "volume"]
    # Защитная копия: мутации кадра не влияют на данные кормушки.
    frame.loc[frame.index[-1], "close"] = 999999.0
    assert feed.candle(3).close == candles[3].close
    fresh = feed.entry_dataframe_upto(3)
    assert float(fresh["close"].iloc[-1]) == candles[3].close


def test_dataframe_without_tz_rejected():
    base = datetime(2024, 1, 2, 10, 0)
    naive_index = pd.DatetimeIndex([base, base + timedelta(minutes=1)])
    frame = pd.DataFrame({"open": [1.0, 1.0], "high": [1.0, 1.0],
                          "low": [1.0, 1.0], "close": [1.0, 1.0],
                          "volume": [1.0, 1.0]}, index=naive_index)
    with pytest.raises(DataFeedError):
        HistoricalDataFeed.from_dataframe(
            frame, engine_config=make_engine_config())


def test_dataframe_missing_columns_rejected():
    aware_index = pd.DatetimeIndex(
        [datetime(2024, 1, 2, 10, 0, tzinfo=timezone.utc)])
    frame = pd.DataFrame({"open": [1.0], "high": [1.0]}, index=aware_index)
    with pytest.raises(DataFeedError):
        HistoricalDataFeed.from_dataframe(
            frame, engine_config=make_engine_config())


# --- детерминированный отпечаток данных ---------------------------------------------

def test_data_sha256_is_stable_and_content_sensitive():
    candles = flat_candles(4)
    feed_a = _feed(candles)
    feed_b = _feed(list(candles))
    assert feed_a.data_sha256 == feed_b.data_sha256
    other = flat_candles(4, price=101.0)
    feed_c = _feed(other)
    assert feed_a.data_sha256 != feed_c.data_sha256


def test_engine_config_rejects_invalid_risk_fractions():
    with pytest.raises(EngineConfigError):
        make_engine_config(risk_per_trade_fraction=0.0)
    with pytest.raises(EngineConfigError):
        make_engine_config(stop_loss_fraction=1.5)
    with pytest.raises(EngineConfigError):
        make_engine_config(lot_size=0)
    with pytest.raises(EngineConfigError):
        make_engine_config(commission_rate=float("nan"))


def test_engine_config_requires_stop_loss_for_stage_d_sizing():
    # Формула Stage D требует protective_stop_price: конфигурация без
    # стопа отклоняется сразу (fail-closed), а не блокирует входы молча.
    with pytest.raises(EngineConfigError):
        make_engine_config(stop_loss_fraction=None)


def test_test_figi_is_safe_key():
    # FIGI тестов проходит правила Stage B (safe string) — косвенно
    # проверено каждым прогоном; прямой контроль символов:
    assert TEST_FIGI.isalnum()
