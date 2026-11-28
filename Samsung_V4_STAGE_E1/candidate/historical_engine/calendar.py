# historical_engine/calendar.py
# SAMSUNG V4 — NEW STRATEGY ENGINE. STAGE E.1.
#
# TradingCalendar: календарно-корректное обнаружение пропусков исторических
# свечей (ТЗ Stage E.1, Correction №1).
#
# Дефект, который исправляет компонент: прежний CandleSeries.detect_gaps()
# сравнивал соседние свечи с ФИКСИРОВАННЫМ интервалом и считал пропуском
# ЛЮБОЕ отклонение — из-за этого ложными «пропусками» помечались выходные,
# праздники, ночные перерывы и внутридневные паузы торговой сессии.
#
# Компонент различает:
#   A. CONFIRMED_EXPECTED_CANDLE_MISSING — реальный пропуск ОЖИДАЕМОЙ
#      торговой свечи (ожидаемая метка попадает в торговое время сессии,
#      свеча отсутствует);
#   B. SESSION_BREAK — нормальный внутридневной перерыв сессии;
#   C. NON_TRADING_DAY / NON_TRADING_TIME — отсутствие торгов в выходной/
#      праздничный день или вне окна торговой сессии;
#   D. UNVERIFIED_NO_CALENDAR / UNVERIFIED_OUTSIDE_CALENDAR_COVERAGE —
#      проверить пропуск НЕВОЗМОЖНО: календарь не передан или отклонение
#      лежит вне покрытого календарём диапазона дат.
#
# ПОКРЫТИЕ ВСЕЙ СЕРИИ (Stage E.1 FINAL CORRECTIONS, Correction 1):
#   analyze_series() проверяет покрытие календарём ДЛЯ ВСЕЙ исследуемой
#   серии НЕЗАВИСИМО от наличия обнаруженных отклонений: начало и конец
#   серии проверяются ОТДЕЛЬНО (граничные свечи не входят ни в один
#   межсвечный интервал и прежде не классифицировались вовсе). Если хотя
#   бы часть серии (граница или межсвечное окно) вне покрытия — итоговый
#   статус проверки НЕ МОЖЕТ быть PERFORMED_FULL_CALENDAR_VERIFIED;
#   непокрытые даты НЕ считаются выходными или праздниками. См.
#   data_feed.py: статус PARTIAL при любом инциденте категории D.
#
# КОНТРАКТ КАЛЕНДАРЯ (задокументирован, без предположений):
#   * календарь получает торговые интервалы ИСКЛЮЧИТЕЛЬНО из явно
#     переданных сессий (никакой автозагрузки, никакой сети);
#   * сессии, явно переданные оператором, считаются ПОЛНЫМ авторитетным
#     календарём внутри покрытого диапазона дат [дата первой сессии;
#     дата закрытия последней сессии]: дата внутри диапазона БЕЗ сессии —
#     авторитетно неторговый день (выходной/праздник);
#   * даты ВНЕ покрытого диапазона НЕ оцениваются (категория D) —
#     календарь не подменяет отсутствующие данные предположениями;
#   * метки свечей — tz-aware datetime; все метки сессий — один общий
#     часовой пояс (представление пояса входит в calendar_sha256);
#   * соглашение о метке свечи: timestamp = момент ОТКРЫТИЯ свечи;
#     торговое время сессии — полуинтервал [open_time; close_time).
#
# Только исторические данные, только оффлайн; никаких сетевых запросов,
# брокерских SDK и подмены отсутствующих календарных данных.

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from .models import (
    CALENDAR_SCHEMA,
    CandleSeries,
    DataFeedError,
    GapIncident,
    GAP_CATEGORY_CONFIRMED_EXPECTED_CANDLE_MISSING,
    GAP_CATEGORY_IRREGULAR_SPACING,
    GAP_CATEGORY_NON_TRADING_DAY,
    GAP_CATEGORY_NON_TRADING_TIME,
    GAP_CATEGORY_SESSION_BREAK,
    GAP_CATEGORY_UNVERIFIED_OUTSIDE_CALENDAR_COVERAGE,
    MOMENT_CATEGORY_IN_SESSION_BREAK,
    MOMENT_CATEGORY_IN_TRADING_TIME,
    MOMENT_CATEGORY_NON_TRADING_DAY,
    MOMENT_CATEGORY_NON_TRADING_TIME,
    MOMENT_CATEGORY_OUTSIDE_CALENDAR_COVERAGE,
    canonical_json,
)

__all__ = ["SessionBreak", "TradingSession", "TradingCalendar"]


def _require_aware(value: datetime, name: str) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise DataFeedError(
            f"{name} должен быть tz-aware datetime; получено {value!r}")


def _same_tzinfo(left: datetime, right: datetime, name: str) -> None:
    # Представление часового пояса входит в отпечаток календаря, поэтому
    # смешение поясов внутри одного календаря отклоняется (fail-closed).
    if left.tzinfo != right.tzinfo:
        raise DataFeedError(
            f"{name}: смешение часовых поясов внутри календаря запрещено "
            f"({left.tzinfo!r} != {right.tzinfo!r}); все метки сессий "
            "должны быть в одном поясе")


@dataclass(frozen=True)
class SessionBreak:
    """Внутридневной перерыв торговой сессии (неизменяемый).

    start/end — tz-aware, start < end; перерыв целиком ВНУТРИ сессии
    (проверяется в TradingSession.__post_init__).
    """
    start: datetime
    end: datetime

    def __post_init__(self) -> None:
        _require_aware(self.start, "SessionBreak.start")
        _require_aware(self.end, "SessionBreak.end")
        _same_tzinfo(self.start, self.end, "SessionBreak")
        if self.end <= self.start:
            raise DataFeedError(
                f"SessionBreak: end ({self.end.isoformat()}) должен быть "
                f"строго позже start ({self.start.isoformat()})")

    def contains(self, moment: datetime) -> bool:
        """Полуинтервал [start; end): момент в перерыве."""
        return self.start <= moment < self.end


@dataclass(frozen=True)
class TradingSession:
    """Одна торговая сессия (неизменяемая).

    open_time/close_time — tz-aware границы сессии; торговое время —
    полуинтервал [open_time; close_time). Перерывы — упорядоченные
    непересекающиеся интервалы внутри (open_time; close_time).
    """
    open_time: datetime
    close_time: datetime
    breaks: Tuple[SessionBreak, ...] = ()

    def __post_init__(self) -> None:
        _require_aware(self.open_time, "TradingSession.open_time")
        _require_aware(self.close_time, "TradingSession.close_time")
        _same_tzinfo(self.open_time, self.close_time, "TradingSession")
        if self.close_time <= self.open_time:
            raise DataFeedError(
                f"TradingSession: close_time ({self.close_time.isoformat()}) "
                f"должен быть строго позже open_time "
                f"({self.open_time.isoformat()})")
        breaks = tuple(self.breaks)
        previous_end: Optional[datetime] = None
        for brk in breaks:
            if type(brk) is not SessionBreak:
                raise DataFeedError(
                    "TradingSession.breaks принимает только точный тип "
                    f"SessionBreak; получено {type(brk).__name__}")
            _same_tzinfo(brk.start, self.open_time, "TradingSession.breaks")
            if brk.start <= self.open_time or brk.end >= self.close_time:
                raise DataFeedError(
                    "TradingSession: перерыв "
                    f"[{brk.start.isoformat()}; {brk.end.isoformat()}) "
                    "должен лежать СТРОГО внутри сессии "
                    f"[{self.open_time.isoformat()}; "
                    f"{self.close_time.isoformat()})")
            if previous_end is not None and brk.start < previous_end:
                raise DataFeedError(
                    "TradingSession: перерывы пересекаются или нарушен "
                    f"порядок (предыдущий завершается "
                    f"{previous_end.isoformat()}, следующий начинается "
                    f"{brk.start.isoformat()})")
            previous_end = brk.end
        object.__setattr__(self, "breaks", breaks)


@dataclass(frozen=True)
class TradingCalendar:
    """Календарь торговых сессий из ЯВНО переданных данных (неизменяемый).

    Гарантии:
      * только явно переданные сессии; сети и автозагрузки НЕТ;
      * сессии передаются в порядке возрастания open_time и не
        пересекаются (close_time <= следующего open_time);
      * все метки — один часовой пояс; представление пояса входит в
        calendar_sha256 (календари с одинаковыми моментами, но разным
        представлением пояса — РАЗНЫЕ конфигурации);
      * классификация момента — детерминированная чистая функция данных
        календаря; никакой зависимости от системного времени.

    Покрытие: даты (в поясе календаря) от даты открытия первой сессии до
    даты закрытия последней сессии. Внутри покрытия список сессий —
    авторитетный (дата без сессии = неторговый день). Вне покрытия
    классификация невозможна (OUTSIDE_CALENDAR_COVERAGE) — компонент НЕ
    додумывает отсутствующие календарные данные.
    """
    sessions: Tuple[TradingSession, ...]
    label: str = ""

    def __post_init__(self) -> None:
        sessions = tuple(self.sessions)
        if not sessions:
            raise DataFeedError(
                "TradingCalendar: пустой список сессий запрещён "
                "(fail-closed; календарь без торговых дней не имеет смысла)")
        for session in sessions:
            if type(session) is not TradingSession:
                raise DataFeedError(
                    "TradingCalendar.sessions принимает только точный тип "
                    f"TradingSession; получено {type(session).__name__}")
        for session in sessions:
            _same_tzinfo(session.open_time, sessions[0].open_time,
                         "TradingCalendar.sessions")
        previous: Optional[TradingSession] = None
        for session in sessions:
            if previous is not None \
                    and session.open_time < previous.close_time:
                raise DataFeedError(
                    "TradingCalendar: сессии пересекаются: "
                    f"[{previous.open_time.isoformat()}; "
                    f"{previous.close_time.isoformat()}) пересекается с "
                    f"{session.open_time.isoformat()}")
            previous = session
        if list(sessions) != sorted(sessions, key=lambda s: s.open_time):
            raise DataFeedError(
                "TradingCalendar: сессии должны быть переданы в порядке "
                "возрастания open_time (fail-closed: порядок — часть "
                "детерминизма)")
        if not isinstance(self.label, str):
            raise DataFeedError("TradingCalendar.label должен быть строкой")
        object.__setattr__(self, "sessions", sessions)

    # --- свойства покрытия ---------------------------------------------------

    @property
    def timezone(self) -> Any:
        return self.sessions[0].open_time.tzinfo

    @property
    def coverage_start_date(self) -> date:
        return self.sessions[0].open_time.date()

    @property
    def coverage_end_date(self) -> date:
        return self.sessions[-1].close_time.date()

    @property
    def session_count(self) -> int:
        return len(self.sessions)

    # --- классификация момента -------------------------------------------------

    def classify_moment(self, moment: datetime) -> str:
        """Детерминированная классификация момента времени.

        Возвращает одну из констант MOMENT_CATEGORY_*:
          * IN_TRADING_TIME            — внутри торговой сессии, вне
                                         перерывов (здесь ожидается свеча);
          * IN_SESSION_BREAK           — внутри сессии, но в перерыве;
          * NON_TRADING_TIME           — дата покрыта, сессия на дату есть,
                                         момент вне окна сессии (до
                                         открытия / после закрытия);
          * NON_TRADING_DAY            — дата покрыта, сессий на дату НЕТ
                                         (выходной/праздник);
          * OUTSIDE_CALENDAR_COVERAGE  — дата вне покрытого календарём
                                         диапазона (категория D: проверить
                                         невозможно).
        """
        _require_aware(moment, "TradingCalendar.classify_moment(moment)")
        for session in self.sessions:
            if session.open_time <= moment < session.close_time:
                for brk in session.breaks:
                    if brk.contains(moment):
                        return MOMENT_CATEGORY_IN_SESSION_BREAK
                return MOMENT_CATEGORY_IN_TRADING_TIME
        local_date = moment.astimezone(self.timezone).date()
        if local_date < self.coverage_start_date \
                or local_date > self.coverage_end_date:
            return MOMENT_CATEGORY_OUTSIDE_CALENDAR_COVERAGE
        for session in self.sessions:
            if session.open_time.date() == local_date:
                return MOMENT_CATEGORY_NON_TRADING_TIME
        return MOMENT_CATEGORY_NON_TRADING_DAY

    # --- календарно-корректный анализ серии -------------------------------------

    def analyze_series(self, series: CandleSeries,
                       expected_interval_seconds: int) \
            -> Tuple[GapIncident, ...]:
        """Календарно-корректный анализ серии свечей.

        Возвращает кортеж инцидентов GapIncident в хронологическом
        порядке. Логика для каждой пары соседних свечей (prev, cur):
          * delta == интервал  — отклонений нет;
          * delta <  интервала — подтверждённая аномалия хронологии
            CONFIRMED_IRREGULAR_SPACING (перерыв/выходной не может
            приблизить следующую свечу; никакой календарь это не
            объясняет);
          * delta >  интервала — перечисляются ожидаемые метки
            prev + k*интервал (строго между prev и cur); каждая метка
            классифицируется календарём:
              - IN_TRADING_TIME и свечи нет -> подтверждённый пропуск
                CONFIRMED_EXPECTED_CANDLE_MISSING (по одному инциденту на
                каждую пропущенную ожидаемую торговую свечу);
              - IN_SESSION_BREAK / NON_TRADING_* -> нормальный перерыв
                (сводный инцидент SESSION_BREAK / NON_TRADING_*);
              - OUTSIDE_CALENDAR_COVERAGE -> проверить невозможно
                (UNVERIFIED_OUTSIDE_CALENDAR_COVERAGE); это НЕ пропуск и
                НЕ подтверждение полноты данных, а явная ограниченность
                проверки.

        ПОКРЫТИЕ ВСЕЙ СЕРИИ (Stage E.1 FINAL CORRECTIONS, Correction 1):
        независимо от наличия межсвечных отклонений НАЧАЛО и КОНЕЦ серии
        (метки первой и последней свечи) классифицируются ОТДЕЛЬНО.
        Граничная свеча не входит ни в один межсвечный интервал, поэтому
        прежде серия, все пары которой лежали ровно через интервал, могла
        получить «полное подтверждение» даже при датах ВНЕ покрытия
        календаря. Теперь непокрытая граница даёт инцидент категории D
        (UNVERIFIED_OUTSIDE_CALENDAR_COVERAGE) — статус проверки в
        data_feed не может быть полным. Непокрытые даты НЕ классифицируются
        как выходные или праздники. Достаточность граничной проверки:
        покрытие — НЕПРЕРЫВНЫЙ диапазон дат в поясе календаря, метки серии
        строго возрастают, поэтому локальные даты свечей монотонны; если
        первая и последняя даты внутри диапазона — все промежуточные тоже
        (промежуточные окна дополнительно проверяются попарной логикой
        выше).

        Данные НИКОГДА не интерполируются и не заполняются.
        """
        if not isinstance(expected_interval_seconds, int) \
                or isinstance(expected_interval_seconds, bool) \
                or expected_interval_seconds <= 0:
            raise DataFeedError(
                "expected_interval_seconds должен быть положительным int")
        interval = timedelta(seconds=expected_interval_seconds)
        incidents: List[GapIncident] = []
        for prev, cur in zip(series.candles, series.candles[1:]):
            delta = cur.timestamp - prev.timestamp
            if delta == interval:
                continue
            gap_seconds = int(delta.total_seconds())
            if delta < interval:
                incidents.append(GapIncident(
                    category=GAP_CATEGORY_IRREGULAR_SPACING,
                    expected_timestamp_iso=(
                        prev.timestamp + interval).isoformat(),
                    next_actual_timestamp_iso=cur.timestamp.isoformat(),
                    gap_seconds=gap_seconds,
                    missing_expected_count=0,
                    details={
                        "reason": "candle_arrived_sooner_than_expected_"
                                  "interval_calendar_independent_anomaly",
                        "expected_interval_seconds":
                            str(expected_interval_seconds),
                    },
                ))
                continue
            missing: List[datetime] = []
            counts: Dict[str, int] = {
                MOMENT_CATEGORY_IN_TRADING_TIME: 0,
                MOMENT_CATEGORY_IN_SESSION_BREAK: 0,
                MOMENT_CATEGORY_NON_TRADING_DAY: 0,
                MOMENT_CATEGORY_NON_TRADING_TIME: 0,
                MOMENT_CATEGORY_OUTSIDE_CALENDAR_COVERAGE: 0,
            }
            checked = 0
            step = 1
            while True:
                moment = prev.timestamp + step * interval
                if moment >= cur.timestamp:
                    break
                checked += 1
                category = self.classify_moment(moment)
                counts[category] += 1
                if category == MOMENT_CATEGORY_IN_TRADING_TIME:
                    missing.append(moment)
                step += 1
            details = {
                "checked_expected_moments": str(checked),
                "in_trading_time": str(
                    counts[MOMENT_CATEGORY_IN_TRADING_TIME]),
                "in_session_break": str(
                    counts[MOMENT_CATEGORY_IN_SESSION_BREAK]),
                "non_trading_day": str(
                    counts[MOMENT_CATEGORY_NON_TRADING_DAY]),
                "non_trading_time": str(
                    counts[MOMENT_CATEGORY_NON_TRADING_TIME]),
                "outside_calendar_coverage": str(
                    counts[MOMENT_CATEGORY_OUTSIDE_CALENDAR_COVERAGE]),
            }
            if missing:
                for moment in missing:
                    incidents.append(GapIncident(
                        category=GAP_CATEGORY_CONFIRMED_EXPECTED_CANDLE_MISSING,
                        expected_timestamp_iso=moment.isoformat(),
                        next_actual_timestamp_iso=cur.timestamp.isoformat(),
                        gap_seconds=gap_seconds,
                        missing_expected_count=len(missing),
                        details=details,
                    ))
                if counts[MOMENT_CATEGORY_OUTSIDE_CALENDAR_COVERAGE] > 0:
                    # Часть отклонения проверить невозможно — фиксируем
                    # ограниченность проверки ОТДЕЛЬНО от подтверждённых
                    # пропусков.
                    incidents.append(GapIncident(
                        category=GAP_CATEGORY_UNVERIFIED_OUTSIDE_CALENDAR_COVERAGE,
                        expected_timestamp_iso=(
                            prev.timestamp + interval).isoformat(),
                        next_actual_timestamp_iso=cur.timestamp.isoformat(),
                        gap_seconds=gap_seconds,
                        missing_expected_count=0,
                        details=details,
                    ))
            elif counts[MOMENT_CATEGORY_OUTSIDE_CALENDAR_COVERAGE] > 0:
                incidents.append(GapIncident(
                    category=GAP_CATEGORY_UNVERIFIED_OUTSIDE_CALENDAR_COVERAGE,
                    expected_timestamp_iso=(
                        prev.timestamp + interval).isoformat(),
                    next_actual_timestamp_iso=cur.timestamp.isoformat(),
                    gap_seconds=gap_seconds,
                    missing_expected_count=0,
                    details=details,
                ))
            elif counts[MOMENT_CATEGORY_IN_SESSION_BREAK] > 0:
                incidents.append(GapIncident(
                    category=GAP_CATEGORY_SESSION_BREAK,
                    expected_timestamp_iso=(
                        prev.timestamp + interval).isoformat(),
                    next_actual_timestamp_iso=cur.timestamp.isoformat(),
                    gap_seconds=gap_seconds,
                    missing_expected_count=0,
                    details=details,
                ))
            elif counts[MOMENT_CATEGORY_NON_TRADING_DAY] > 0:
                incidents.append(GapIncident(
                    category=GAP_CATEGORY_NON_TRADING_DAY,
                    expected_timestamp_iso=(
                        prev.timestamp + interval).isoformat(),
                    next_actual_timestamp_iso=cur.timestamp.isoformat(),
                    gap_seconds=gap_seconds,
                    missing_expected_count=0,
                    details=details,
                ))
            else:
                incidents.append(GapIncident(
                    category=GAP_CATEGORY_NON_TRADING_TIME,
                    expected_timestamp_iso=(
                        prev.timestamp + interval).isoformat(),
                    next_actual_timestamp_iso=cur.timestamp.isoformat(),
                    gap_seconds=gap_seconds,
                    missing_expected_count=0,
                    details=details,
                ))
        # --- ПОКРЫТИЕ ВСЕЙ СЕРИИ (Stage E.1 FINAL CORRECTIONS, Correction 1) ---
        # Граничные свечи (первая и последняя) не входят ни в один
        # межсвечный интервал: их классификация выполняется ОТДЕЛЬНО и
        # НЕЗАВИСИМО от наличия обнаруженных выше отклонений. Граница вне
        # покрытия календаря — инцидент категории D (проверить невозможно);
        # непокрытая дата НЕ считается выходным или праздником, а статус
        # проверки в data_feed не может быть PERFORMED_FULL_CALENDAR_VERIFIED.
        for boundary_name, boundary_moment in (
                ("series_start", series.candles[0].timestamp),
                ("series_end", series.candles[-1].timestamp)):
            if self.classify_moment(boundary_moment) \
                    != MOMENT_CATEGORY_OUTSIDE_CALENDAR_COVERAGE:
                continue
            incidents.append(GapIncident(
                category=GAP_CATEGORY_UNVERIFIED_OUTSIDE_CALENDAR_COVERAGE,
                expected_timestamp_iso=boundary_moment.isoformat(),
                next_actual_timestamp_iso=boundary_moment.isoformat(),
                gap_seconds=0,
                missing_expected_count=0,
                details={
                    "reason": "series_boundary_outside_calendar_coverage",
                    "series_boundary": boundary_name,
                    "series_boundary_timestamp_iso":
                        boundary_moment.isoformat(),
                    "calendar_coverage_start_date":
                        self.coverage_start_date.isoformat(),
                    "calendar_coverage_end_date":
                        self.coverage_end_date.isoformat(),
                },
            ))
        return tuple(incidents)

    # --- отпечаток конфигурации ---------------------------------------------------

    def calendar_sha256(self) -> str:
        """Детерминированный SHA-256 отпечатка КОНФИГУРАЦИИ календаря.

        Включает представление часового пояса: календари с одинаковыми
        моментами времени, но разными поясами (например, UTC и UTC+03:00)
        дают РАЗНЫЕ отпечатки — выбор пояса является частью конфигурации
        интерпретации данных и не нормализуется неявно.
        """
        payload = {
            "calendar_schema": CALENDAR_SCHEMA,
            "timezone": str(self.timezone),
            "coverage_start_date": self.coverage_start_date.isoformat(),
            "coverage_end_date": self.coverage_end_date.isoformat(),
            "label": self.label,
            "sessions": [
                {
                    "open_time": session.open_time.isoformat(),
                    "close_time": session.close_time.isoformat(),
                    "breaks": [
                        {"start": brk.start.isoformat(),
                         "end": brk.end.isoformat()}
                        for brk in session.breaks
                    ],
                }
                for session in self.sessions
            ],
        }
        return hashlib.sha256(
            canonical_json(payload).encode("utf-8")).hexdigest()

