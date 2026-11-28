# tests/test_stage_e1_calendar.py
# SAMSUNG V4 — NEW STRATEGY ENGINE. STAGE E.1.
# Correction №1 — календарно-корректное обнаружение пропусков свечей.
#
# 12 обязательных сценариев ТЗ E.1 §3.5 + дополнительные проверки
# детерминизма и fail-closed валидации календаря + FINAL CORRECTIONS
# (покрытие ВСЕЙ серии: начало/конец серии проверяются отдельно, статус
# FULL только при действительном покрытии всей серии).
# Только исторические синтетические данные, только оффлайн; никаких
# сетевых запросов и брокерских API для получения календаря.

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from historical_engine import (
    BacktestEngine,
    Candle,
    CandleSeries,
    DataFeedError,
    EngineConfig,
    GapIncident,
    GAP_CATEGORY_CONFIRMED_EXPECTED_CANDLE_MISSING,
    GAP_CATEGORY_NON_TRADING_DAY,
    GAP_CATEGORY_NON_TRADING_TIME,
    GAP_CATEGORY_SESSION_BREAK,
    GAP_CATEGORY_UNVERIFIED_OUTSIDE_CALENDAR_COVERAGE,
    GAP_VERIFICATION_FULL,
    GAP_VERIFICATION_LIMITED_NO_CALENDAR,
    GAP_VERIFICATION_NOT_PERFORMED_INTERVAL_UNSET,
    GAP_VERIFICATION_PARTIAL,
    HistoricalDataFeed,
    MOMENT_CATEGORY_IN_TRADING_TIME,
    MOMENT_CATEGORY_NON_TRADING_TIME,
    MOMENT_CATEGORY_OUTSIDE_CALENDAR_COVERAGE,
    SessionBreak,
    TradingCalendar,
    TradingSession,
)
from tests.stage_e_tools import (
    AlwaysBuyStrategy,
    make_engine_config,
    make_strategy_config,
)

# Фиксированный офсет без DST (полностью детерминированный, без tzdata).
MSK = timezone(timedelta(hours=3))
HOUR = 3600          # expected_candle_interval_seconds
SESSION_OPEN = (10, 0)
SESSION_CLOSE = (18, 45)


def _dt(day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(2024, 1, day, hour, minute, tzinfo=MSK)


def make_calendar(days, *, breaks_for=None, label="test-calendar"):
    """Календарь из ЯВНО перечисленных торговых дней (10:00–18:45).

    days — дни января 2024 с торговыми сессиями; breaks_for —
    отображение {день: (start_hour, start_min, end_hour, end_min)}.
    """
    breaks_for = breaks_for or {}
    sessions = []
    for day in days:
        breaks = ()
        if day in breaks_for:
            b_sh, b_sm, b_eh, b_em = breaks_for[day]
            breaks = (SessionBreak(start=_dt(day, b_sh, b_sm),
                                   end=_dt(day, b_eh, b_em)),)
        sessions.append(TradingSession(
            open_time=_dt(day, *SESSION_OPEN),
            close_time=_dt(day, *SESSION_CLOSE),
            breaks=breaks,
        ))
    return TradingCalendar(sessions=tuple(sessions), label=label)


def hourly_day(day: int, *, hours=range(10, 19), price: float = 100.0):
    """Часовые свечи одного торгового дня (метка = момент открытия)."""
    half = price * 0.001
    return [Candle(timestamp=_dt(day, h),
                   open=price, high=price + half,
                   low=price - half, close=price, volume=1000.0)
            for h in hours]


def make_config(calendar=None, *, policy="REPORT", interval=HOUR,
                **overrides):
    return make_engine_config(
        expected_candle_interval_seconds=interval,
        gap_policy=policy,
        calendar=calendar,
        **overrides)


def make_feed(candles, config):
    return HistoricalDataFeed.from_candles(candles, engine_config=config)


def confirmed_incidents(feed):
    return [i for i in feed.gap_incidents
            if i.category == GAP_CATEGORY_CONFIRMED_EXPECTED_CANDLE_MISSING]


# 1. Обычная последовательность свечей ---------------------------------------

def test_regular_sequence_has_no_incidents():
    calendar = make_calendar([8, 9])
    # Полный набор часовых свечей сессии 10:00–18:45: 10..18 включительно.
    candles = hourly_day(8) + hourly_day(9)
    feed = make_feed(candles, make_config(calendar))
    # Внутрисессионные интервалы точные — подтверждённых пропусков нет;
    # ночное отклонение классифицировано как неторговое время (не пропуск).
    assert confirmed_incidents(feed) == []
    assert feed.gap_verification_status == GAP_VERIFICATION_FULL
    assert feed.gaps == ()
    categories = {i.category for i in feed.gap_incidents}
    assert categories == {GAP_CATEGORY_NON_TRADING_TIME}


# 2. Пропущенная свеча внутри сессии -----------------------------------------

def test_missed_candle_inside_session_is_confirmed_gap():
    calendar = make_calendar([8])
    candles = hourly_day(8, hours=[10, 11, 13, 14])   # 12:00 отсутствует
    feed = make_feed(candles, make_config(calendar))
    confirmed = confirmed_incidents(feed)
    assert len(confirmed) == 1
    assert confirmed[0].expected_timestamp_iso == _dt(8, 12).isoformat()
    assert confirmed[0].next_actual_timestamp_iso == _dt(8, 13).isoformat()
    assert confirmed[0].missing_expected_count == 1
    # Обратная совместимость: пары содержат подтверждённый пропуск.
    assert feed.gaps == ((_dt(8, 12).isoformat(), _dt(8, 13).isoformat()),)
    assert feed.gap_verification_status == GAP_VERIFICATION_FULL


# 3. Переход через ночной перерыв ---------------------------------------------

def test_overnight_break_is_not_a_gap():
    calendar = make_calendar([8, 9])
    candles = hourly_day(8) + hourly_day(9)
    feed = make_feed(candles, make_config(calendar))
    assert confirmed_incidents(feed) == []
    assert feed.gaps == ()
    categories = {i.category for i in feed.gap_incidents}
    assert categories <= {GAP_CATEGORY_NON_TRADING_TIME}


# 4. Переход через выходные -----------------------------------------------------

def test_weekend_transition_is_not_a_gap():
    # Пятница 12.01 -> понедельник 15.01; выходные ВНУТРИ покрытия.
    calendar = make_calendar([12, 15])
    candles = hourly_day(12) + hourly_day(15)
    feed = make_feed(candles, make_config(calendar))
    assert confirmed_incidents(feed) == []
    assert feed.gaps == ()
    categories = {i.category for i in feed.gap_incidents}
    assert GAP_CATEGORY_NON_TRADING_DAY in categories
    assert feed.gap_verification_status == GAP_VERIFICATION_FULL


# 5. Переход через официальный праздничный день ---------------------------------

def test_holiday_transition_is_not_a_gap():
    # Вторник 9.01 — праздничный день: сессий нет, день внутри покрытия.
    calendar = make_calendar([8, 10, 11])
    candles = hourly_day(8) + hourly_day(10)
    feed = make_feed(candles, make_config(calendar))
    assert confirmed_incidents(feed) == []
    assert feed.gaps == ()
    categories = {i.category for i in feed.gap_incidents}
    assert GAP_CATEGORY_NON_TRADING_DAY in categories


# 6. Внутридневной перерыв --------------------------------------------------------

def test_intraday_break_is_not_a_gap():
    calendar = make_calendar([8], breaks_for={8: (14, 0, 14, 10)})
    # Свечи 13:00 и 15:00: ожидаемая метка 14:00 попадает в перерыв.
    candles = hourly_day(8, hours=[10, 11, 12, 13, 15, 16, 17, 18])
    feed = make_feed(candles, make_config(calendar))
    assert confirmed_incidents(feed) == []
    assert feed.gaps == ()
    categories = {i.category for i in feed.gap_incidents}
    assert GAP_CATEGORY_SESSION_BREAK in categories


# 7. Неполный календарь -------------------------------------------------------------

def test_incomplete_calendar_reports_limited_verification():
    # Серия за 8–12.01, календарь покрывает только 11–12.01.
    calendar = make_calendar([11, 12])
    candles = (hourly_day(8) + hourly_day(9) + hourly_day(10)
               + hourly_day(11) + hourly_day(12))
    feed = make_feed(candles, make_config(calendar))
    assert confirmed_incidents(feed) == []
    # ЛОЖНОГО подтверждения полноты НЕТ: статус прямо ограниченный.
    assert feed.gap_verification_status == GAP_VERIFICATION_PARTIAL
    unverified = [i for i in feed.gap_incidents
                  if i.category
                  == GAP_CATEGORY_UNVERIFIED_OUTSIDE_CALENDAR_COVERAGE]
    assert len(unverified) > 0
    # STRICT НЕ отклоняет неподтверждённые отклонения.
    feed_strict = make_feed(candles, make_config(calendar, policy="STRICT"))
    assert feed_strict.gap_verification_status == GAP_VERIFICATION_PARTIAL


# 8. Отсутствующий календарь -----------------------------------------------------------

def test_missing_calendar_is_explicit_limited_chronology_check():
    candles = hourly_day(8) + hourly_day(9)
    feed = make_feed(candles, make_config(calendar=None, policy="REPORT"))
    # Отклонения интервала обнаружены (старый парный формат сохранён),
    # но классифицировать их НЕВОЗМОЖНО — категория D.
    assert len(feed.gaps) == 1        # единственное отклонение: ночь 18->10
    assert feed.gap_verification_status == GAP_VERIFICATION_LIMITED_NO_CALENDAR
    assert all(i.category == "UNVERIFIED_NO_CALENDAR_LIMITED_CHRONOLOGY_CHECK"
               for i in feed.gap_incidents)


# 9. Переход через границу торговой сессии ----------------------------------------------

def test_session_boundary_moments_are_not_trading_time():
    # Короткая сессия 10:00–13:00; метка ровно на закрытии — НЕ торговое
    # время (полуинтервал [open; close)); метка ровно на открытии —
    # торговое время.
    short = TradingCalendar(sessions=(TradingSession(
        open_time=_dt(8, 10), close_time=_dt(8, 13)),), label="short")
    assert short.classify_moment(_dt(8, 10)) == MOMENT_CATEGORY_IN_TRADING_TIME
    assert short.classify_moment(_dt(8, 12, 59)) == \
        MOMENT_CATEGORY_IN_TRADING_TIME
    assert short.classify_moment(_dt(8, 13)) == \
        MOMENT_CATEGORY_NON_TRADING_TIME
    assert short.classify_moment(_dt(8, 14)) == \
        MOMENT_CATEGORY_NON_TRADING_TIME
    # Свечи 10,11,12; следующая свеча — открытие следующей сессии: метка
    # 13:00 (ровно закрытие) НЕ является ожидаемой торговой свечой.
    short_calendar = TradingCalendar(sessions=(
        TradingSession(open_time=_dt(8, 10), close_time=_dt(8, 13)),
        TradingSession(open_time=_dt(9, 10), close_time=_dt(9, 13)),
    ), label="short-two-days")
    candles = (hourly_day(8, hours=[10, 11, 12])
               + hourly_day(9, hours=[10, 11, 12]))
    feed = make_feed(candles, make_config(short_calendar))
    assert confirmed_incidents(feed) == []
    assert feed.gaps == ()
    categories = {i.category for i in feed.gap_incidents}
    assert categories == {GAP_CATEGORY_NON_TRADING_TIME}


# 10. STRICT при реальном пропуске ------------------------------------------------------

def test_strict_rejects_confirmed_gap_with_calendar():
    calendar = make_calendar([8])
    candles = hourly_day(8, hours=[10, 11, 13, 14])
    with pytest.raises(DataFeedError) as exc:
        make_feed(candles, make_config(calendar, policy="STRICT"))
    assert "подтверждённые пропуски" in str(exc.value)


# 11. STRICT при нормальном перерыве ------------------------------------------------------

def test_strict_accepts_normal_breaks_with_calendar():
    calendar = make_calendar([8, 9])
    candles = hourly_day(8) + hourly_day(9)
    feed = make_feed(candles, make_config(calendar, policy="STRICT"))
    assert feed.gap_verification_status == GAP_VERIFICATION_FULL
    assert feed.gaps == ()


# 12. REPORT при реальном пропуске -----------------------------------------------------------

def test_report_records_confirmed_gap_without_rejection():
    calendar = make_calendar([8])
    candles = hourly_day(8, hours=[10, 11, 13, 14])
    feed = make_feed(candles, make_config(calendar, policy="REPORT"))
    assert feed.gap_verification_status == GAP_VERIFICATION_FULL
    assert len(confirmed_incidents(feed)) == 1
    assert feed.gaps == ((_dt(8, 12).isoformat(), _dt(8, 13).isoformat()),)


# --- дополнительные проверки -----------------------------------------------------------------

def test_irregular_spacing_confirmed_even_with_calendar():
    # Свеча РАНЬШЕ ожидаемого интервала: ни перерыв, ни выходной это
    # объяснить не могут — подтверждённая аномалия (календарно-независимая).
    calendar = make_calendar([8])
    candles = hourly_day(8, hours=[10, 11, 12])
    candles.append(Candle(timestamp=_dt(8, 12, 30), open=100.0, high=100.1,
                          low=99.9, close=100.0, volume=1000.0))
    feed = make_feed(candles, make_config(calendar))
    irregular = [i for i in feed.gap_incidents
                 if i.category == "CONFIRMED_IRREGULAR_SPACING"]
    assert len(irregular) == 1
    # irregular — подтверждённая категория: попадает в пары и в STRICT.
    assert len(feed.gaps) == 1
    with pytest.raises(DataFeedError):
        make_feed(candles, make_config(calendar, policy="STRICT"))


def test_calendar_analysis_is_deterministic():
    calendar = make_calendar([8, 9])
    candles = hourly_day(8) + hourly_day(9)
    first = calendar.analyze_series(CandleSeries(tuple(candles)), HOUR)
    second = calendar.analyze_series(CandleSeries(tuple(candles)), HOUR)
    assert first == second
    assert TradingCalendar(sessions=calendar.sessions,
                           label=calendar.label).calendar_sha256() \
        == calendar.calendar_sha256()


def test_calendar_sha256_sensitive_to_timezone_presentation():
    # Одинаковые моменты времени, разные пояса -> РАЗНЫЕ отпечатки.
    utc_calendar = TradingCalendar(sessions=(TradingSession(
        open_time=datetime(2024, 1, 8, 7, 0, tzinfo=timezone.utc),
        close_time=datetime(2024, 1, 8, 15, 45, tzinfo=timezone.utc)),))
    msk_calendar = TradingCalendar(sessions=(TradingSession(
        open_time=_dt(8, 10), close_time=_dt(8, 18, 45)),))
    assert utc_calendar.calendar_sha256() != msk_calendar.calendar_sha256()


def test_calendar_validates_fail_closed():
    # Наивная метка отклоняется.
    with pytest.raises(DataFeedError):
        TradingSession(open_time=datetime(2024, 1, 8, 10, 0),
                       close_time=datetime(2024, 1, 8, 18, 45))
    # Пустой список сессий отклоняется.
    with pytest.raises(DataFeedError):
        TradingCalendar(sessions=())
    # Пересекающиеся сессии отклоняются.
    with pytest.raises(DataFeedError):
        TradingCalendar(sessions=(
            TradingSession(open_time=_dt(8, 10), close_time=_dt(8, 18)),
            TradingSession(open_time=_dt(8, 17), close_time=_dt(8, 19)),
        ))
    # Неупорядоченные сессии отклоняются.
    with pytest.raises(DataFeedError):
        TradingCalendar(sessions=(
            TradingSession(open_time=_dt(9, 10), close_time=_dt(9, 18)),
            TradingSession(open_time=_dt(8, 10), close_time=_dt(8, 18)),
        ))
    # Перерыв вне сессии отклоняется.
    with pytest.raises(DataFeedError):
        TradingSession(
            open_time=_dt(8, 10), close_time=_dt(8, 18),
            breaks=(SessionBreak(start=_dt(8, 17), end=_dt(8, 19)),))
    # Смешение часовых поясов отклоняется.
    with pytest.raises(DataFeedError):
        TradingCalendar(sessions=(
            TradingSession(open_time=_dt(8, 10), close_time=_dt(8, 18)),
            TradingSession(
                open_time=datetime(2024, 1, 9, 10, 0, tzinfo=timezone.utc),
                close_time=datetime(2024, 1, 9, 18, 0, tzinfo=timezone.utc)),
        ))


def test_gap_control_disabled_with_calendar_is_explicit():
    # interval=None — ЯВНОЕ решение: контроль только хронологии; календарь
    # не анализируется (перечислять ожидаемые метки без интервала нельзя).
    calendar = make_calendar([8, 9])
    candles = hourly_day(8) + hourly_day(9)
    feed = make_feed(candles, make_config(calendar, interval=None))
    assert feed.gap_incidents == ()
    assert feed.gap_verification_status == \
        GAP_VERIFICATION_NOT_PERFORMED_INTERVAL_UNSET
    assert feed.gaps == ()


def test_outside_coverage_moment_is_unclassified():
    calendar = make_calendar([8])
    assert calendar.classify_moment(_dt(20, 10)) == \
        MOMENT_CATEGORY_OUTSIDE_CALENDAR_COVERAGE


# --- FINAL CORRECTIONS (Correction 1): покрытие ВСЕЙ серии --------------------
#
# Дефект: analyze_series() классифицировал ТОЛЬКО ожидаемые метки МЕЖДУ
# соседними свечами. Серия, все пары которой лежали ровно через интервал,
# получала статус PERFORMED_FULL_CALENDAR_VERIFIED даже при датах ВНЕ
# покрытия календаря: граничные свечи (первая и последняя) не входят ни в
# один межсвечный интервал и прежде не классифицировались вовсе.
# Исправление: начало и конец серии проверяются ОТДЕЛЬНО и НЕЗАВИСИМО от
# наличия отклонений; непокрытая граница даёт инцидент категории D
# (UNVERIFIED_OUTSIDE_CALENDAR_COVERAGE), статус — PARTIAL; STRICT не
# отклоняет неподтверждённые инциденты; непокрытые даты НЕ считаются
# выходными или праздниками.


def hourly_span(start_day: int, start_hour: int, end_day: int, end_hour: int,
                price: float = 100.0):
    """Непрерывные часовые свечи от start_day:start_hour до
    end_day:end_hour включительно (все межсвечные интервалы РОВНО 1 час —
    попарная проверка отклонений не находит ничего)."""
    moments = []
    current = datetime(2024, 1, start_day, start_hour, tzinfo=MSK)
    final = datetime(2024, 1, end_day, end_hour, tzinfo=MSK)
    while current <= final:
        moments.append(current)
        current += timedelta(hours=1)
    half = price * 0.001
    return [Candle(timestamp=m, open=price, high=price + half,
                   low=price - half, close=price, volume=1000.0)
            for m in moments]


def make_two_day_calendar():
    return make_calendar([11, 12])


def boundary_incidents(feed):
    return [i for i in feed.gap_incidents
            if i.details.get("reason")
            == "series_boundary_outside_calendar_coverage"]


def unverified_incidents(feed):
    return [i for i in feed.gap_incidents
            if i.category
            == GAP_CATEGORY_UNVERIFIED_OUTSIDE_CALENDAR_COVERAGE]


# 1. Вся серия находится вне календарного покрытия ------------------------------

def test_series_entirely_outside_calendar_coverage_reports_partial():
    calendar = make_two_day_calendar()          # покрытие: 11–12.01
    candles = hourly_span(15, 10, 16, 18)       # серия: 15–16.01 (вне покрытия)
    feed = make_feed(candles, make_config(calendar))
    assert confirmed_incidents(feed) == []
    assert feed.gap_verification_status == GAP_VERIFICATION_PARTIAL
    # Обе границы вне покрытия; серия НЕПРЕРЫВНА (все 33 пары ровно 1 час,
    # включая ночные метки) — попарные отклонения отсутствуют, поэтому до
    # исправления инцидентов не было вовсе и статус ошибочно был FULL.
    boundaries = {i.details["series_boundary"] for i in boundary_incidents(feed)}
    assert boundaries == {"series_start", "series_end"}
    assert len(unverified_incidents(feed)) == 2     # только 2 границы
    # Непокрытые даты НЕ считаются выходными или праздниками: ни одного
    # инцидента категорий B/C на непокрытых датах нет.
    assert all(i.details.get("reason")
               == "series_boundary_outside_calendar_coverage"
               for i in feed.gap_incidents)


# 2. Начало серии вне покрытия ----------------------------------------------------

def test_series_start_outside_coverage_reports_partial():
    # Календарь покрывает 11–12.01; серия начинается 10.01 23:00 и идёт
    # БЕЗ ПРОПУСКОВ (все пары ровно 1 час) до 11.01 18:00. Прежде: ни
    # одного попарного отклонения -> ложный статус FULL. Теперь: начало
    # серии (10.01) вне покрытия -> граница даёт инцидент категории D.
    calendar = make_two_day_calendar()
    candles = hourly_span(10, 23, 11, 18)
    feed = make_feed(candles, make_config(calendar))
    assert confirmed_incidents(feed) == []
    assert feed.gaps == ()
    assert feed.gap_verification_status == GAP_VERIFICATION_PARTIAL
    bounds = boundary_incidents(feed)
    assert len(bounds) == 1
    assert bounds[0].details["series_boundary"] == "series_start"
    assert bounds[0].expected_timestamp_iso == _dt(10, 23).isoformat()
    assert bounds[0].details["calendar_coverage_start_date"] == "2024-01-11"


# 3. Конец серии вне покрытия ------------------------------------------------------

def test_series_end_outside_coverage_reports_partial():
    # Серия 11–12.01 внутри покрытия, но продолжается без пропусков на
    # 13.01 00:00–02:00 (вне покрытия). Межсвечные окна 12.01 дают только
    # нормальные NON_TRADING_TIME-инциденты (даты покрыты), поэтому прежде
    # неподтверждённых инцидентов не было и статус ошибочно был FULL.
    calendar = make_two_day_calendar()
    candles = (hourly_span(11, 10, 12, 18) + hourly_span(13, 0, 13, 2))
    feed = make_feed(candles, make_config(calendar))
    assert confirmed_incidents(feed) == []
    assert feed.gap_verification_status == GAP_VERIFICATION_PARTIAL
    bounds = boundary_incidents(feed)
    assert len(bounds) == 1
    assert bounds[0].details["series_boundary"] == "series_end"
    # Граница серии — ПОСЛЕДНЯЯ свеча (13.01 02:00).
    assert bounds[0].expected_timestamp_iso == _dt(13, 2).isoformat()
    assert bounds[0].details["calendar_coverage_end_date"] == "2024-01-12"


# 4. Серия полностью покрыта календарём ----------------------------------------------

def test_series_fully_covered_boundary_check_keeps_full_status():
    # Полное покрытие — статус FULL СОХРАНЯЕТСЯ: граничная проверка не
    # даёт ложных срабатываний на полностью покрытой серии.
    calendar = make_two_day_calendar()
    candles = hourly_day(11) + hourly_day(12)
    feed = make_feed(candles, make_config(calendar))
    assert confirmed_incidents(feed) == []
    assert feed.gap_verification_status == GAP_VERIFICATION_FULL
    assert boundary_incidents(feed) == []
    assert unverified_incidents(feed) == []


# 5. Между свечами нет пропусков, но календарь не покрывает даты серии --------

def test_contiguous_series_without_gaps_but_uncovered_dates_is_partial():
    # КЛЮЧЕВОЙ регрессионный сценарий дефекта: один торговый день целиком
    # вне покрытия, все межсвечные интервалы РОВНО 1 час — прежде ноль
    # инцидентов и ложный FULL; теперь ОБЕ границы дают инцидент D.
    calendar = make_two_day_calendar()
    candles = hourly_span(15, 10, 15, 18)
    assert calendar.classify_moment(candles[0].timestamp) == \
        MOMENT_CATEGORY_OUTSIDE_CALENDAR_COVERAGE
    feed = make_feed(candles, make_config(calendar))
    assert confirmed_incidents(feed) == []
    assert feed.gaps == ()
    assert feed.gap_verification_status == GAP_VERIFICATION_PARTIAL
    bounds = boundary_incidents(feed)
    assert len(bounds) == 2
    assert {i.details["series_boundary"] for i in bounds} \
        == {"series_start", "series_end"}
    assert all(i.gap_seconds == 0 and i.missing_expected_count == 0
               for i in bounds)


# 6. Корректные выходные и перерывы сессий продолжают обрабатываться правильно --

def test_weekends_and_session_breaks_unchanged_after_boundary_check():
    # Выходные 13–14.01 ВНУТРИ покрытия и внутридневной перерыв 12.01
    # (свеча 14:00 отсутствует): классификация B/C не изменилась, ложных
    # границ нет, статус FULL.
    calendar = make_calendar([12, 15], breaks_for={12: (14, 0, 14, 10)})
    candles = (hourly_day(12, hours=[10, 11, 12, 13, 15, 16, 17, 18])
               + hourly_day(15))
    feed = make_feed(candles, make_config(calendar))
    assert confirmed_incidents(feed) == []
    assert feed.gap_verification_status == GAP_VERIFICATION_FULL
    assert boundary_incidents(feed) == []
    categories = {i.category for i in feed.gap_incidents}
    assert GAP_CATEGORY_SESSION_BREAK in categories
    assert GAP_CATEGORY_NON_TRADING_DAY in categories
    assert GAP_CATEGORY_UNVERIFIED_OUTSIDE_CALENDAR_COVERAGE not in categories


# 7. STRICT не отклоняет неподтверждённые инциденты ----------------------------

def test_strict_does_not_reject_series_outside_coverage():
    # Непокрытая граница — НЕ подтверждённый пропуск: STRICT собирает фид
    # без ошибки и честно сообщает ограниченную проверку (PARTIAL).
    calendar = make_two_day_calendar()
    candles = hourly_span(15, 10, 15, 18)
    feed = make_feed(candles, make_config(calendar, policy="STRICT"))
    assert feed.gap_verification_status == GAP_VERIFICATION_PARTIAL
    assert len(boundary_incidents(feed)) == 2
    assert feed.gaps == ()


# 8. Детерминизм граничных инцидентов ------------------------------------------

def test_boundary_coverage_incidents_are_deterministic():
    calendar = make_two_day_calendar()
    candles = hourly_span(10, 23, 11, 18)
    series = CandleSeries(tuple(candles))
    first = calendar.analyze_series(series, HOUR)
    second = calendar.analyze_series(series, HOUR)
    assert first == second
    boundary = [i for i in first if i.details.get("reason")
                == "series_boundary_outside_calendar_coverage"]
    assert len(boundary) == 1
    assert boundary[0].details == {
        "reason": "series_boundary_outside_calendar_coverage",
        "series_boundary": "series_start",
        "series_boundary_timestamp_iso": _dt(10, 23).isoformat(),
        "calendar_coverage_start_date": "2024-01-11",
        "calendar_coverage_end_date": "2024-01-12",
    }


# 9. Статус ограниченной проверки доходит до отчёта прогона ----------------------

def test_report_reflects_partial_status_for_uncovered_series():
    from historical_engine import BacktestEngine
    strategy = AlwaysBuyStrategy()
    config = make_strategy_config(strategy, {"warmup": 1})
    calendar = make_two_day_calendar()
    candles = hourly_span(15, 10, 15, 18)
    engine_config = make_config(calendar)
    feed = make_feed(candles, engine_config)
    engine = BacktestEngine(strategy=strategy, strategy_config=config,
                            engine_config=engine_config, feed=feed)
    report = engine.run_full()
    gv = report["gap_verification"]
    assert gv["status"] == GAP_VERIFICATION_PARTIAL
    assert gv["calendar_present"] is True
    counts = gv["incident_counts"]
    assert counts["unverified_outside_calendar_coverage"] == 2
    assert counts["confirmed_expected_candle_missing"] == 0
    # Полная классификация инцидентов содержит обе границы серии.
    boundary_reasons = [i["details"]["series_boundary"]
                        for i in report["gap_analysis"]
                        if i["details"].get("reason")
                        == "series_boundary_outside_calendar_coverage"]
    assert sorted(boundary_reasons) == ["series_end", "series_start"]


def test_gap_verification_reaches_report():
    """Отчёт прогона явно сообщает статус верификации (без ложного
    подтверждения полноты данных)."""
    from historical_engine import BacktestEngine
    strategy = AlwaysBuyStrategy()
    config = make_strategy_config(strategy, {"warmup": 1})
    calendar = make_calendar([8, 9])
    candles = hourly_day(8) + hourly_day(9)
    engine_config = make_config(calendar)
    feed = make_feed(candles, engine_config)
    engine = BacktestEngine(strategy=strategy, strategy_config=config,
                            engine_config=engine_config, feed=feed)
    report = engine.run_full()
    gv = report["gap_verification"]
    assert gv["status"] == GAP_VERIFICATION_FULL
    assert gv["calendar_present"] is True
    assert gv["calendar_sha256"] == calendar.calendar_sha256()
    assert gv["incident_counts"]["confirmed_expected_candle_missing"] == 0
    # Отчёт без календаря: ограниченная проверка ЯВНО отражена.
    no_cal_config = make_config(None)
    no_cal_feed = make_feed(candles, no_cal_config)
    no_cal_engine = BacktestEngine(strategy=strategy, strategy_config=config,
                                   engine_config=no_cal_config,
                                   feed=no_cal_feed)
    no_cal_report = no_cal_engine.run_full()
    assert no_cal_report["gap_verification"]["status"] == \
        GAP_VERIFICATION_LIMITED_NO_CALENDAR
    assert no_cal_report["gap_verification"]["calendar_present"] is False
