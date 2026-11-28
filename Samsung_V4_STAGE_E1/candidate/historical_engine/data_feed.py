# historical_engine/data_feed.py
# SAMSUNG V4 — NEW STRATEGY ENGINE. STAGE E.
#
# HistoricalDataFeed: последовательная подача исторических свечей СТРОГО
# в хронологическом порядке, контроль пропусков и некорректных данных,
# ФИЗИЧЕСКАЯ невозможность доступа к будущим свечам (ТЗ Stage E §3.1, §4).
#
# Данные только исторические, только оффлайн; никаких сетевых запросов.

from __future__ import annotations

from datetime import timedelta
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import pandas as pd

from .models import (
    CONFIRMED_GAP_CATEGORIES,
    Candle,
    CandleSeries,
    DataFeedError,
    EngineConfig,
    GapIncident,
    GAP_CATEGORY_UNVERIFIED_NO_CALENDAR,
    GAP_CATEGORY_UNVERIFIED_OUTSIDE_CALENDAR_COVERAGE,
    GAP_VERIFICATION_FULL,
    GAP_VERIFICATION_LIMITED_NO_CALENDAR,
    GAP_VERIFICATION_NOT_PERFORMED_INTERVAL_UNSET,
    GAP_VERIFICATION_PARTIAL,
    canonical_json,
)

REQUIRED_COLUMNS = ("open", "high", "low", "close", "volume")


class HistoricalDataFeed:
    """Последовательная подача ЗАКРЫТЫХ исторических свечей (fail-closed).

    Гарантии:
      * данные валидируются при сборке: OHLC-геометрия, конечность,
        положительность цен, неотрицательный объём, СТРОГО возрастающие
        tz-aware метки времени (наивные метки и дубликаты отклоняются);
      * контроль пропусков (Stage E.1, Correction 1): при заданном
        expected_candle_interval_seconds обнаруживаются свечи, идущие
        НЕ через ровно один интервал. КЛАССИФИКАЦИЯ отклонений:
          - календарь передан (EngineConfig.calendar) — календарно-
            корректная проверка: выходные, праздники, ночные перерывы и
            внутридневные паузы НЕ считаются пропущенными свечами;
            STRICT отклоняет ТОЛЬКО подтверждённые пропуски ожидаемых
            торговых свечей (и календарно-независимые аномалии
            хронологии); если часть отклонения лежит вне покрытого
            календарём диапазона — движок ЯВНО сообщает об ограниченной
            проверке (status PARTIAL), не выдавая ложного подтверждения
            полноты данных;
          - календарь НЕ передан — ОГРАНИЧЕННАЯ проверка хронологии:
            отклонения интервала фиксируются, но классифицировать их
            невозможно (категория D); STRICT в этом режиме отклоняет
            любое отклонение (fail-closed консервативизм), статус
            ограниченной проверки ЯВНО отражается в отчёте;
        данные НИКОГДА не интерполируются и не заполняются будущими
        значениями; поведение задается gap_policy: 'REPORT' (инциденты
        фиксируются в отчёте) или 'STRICT' (подтверждённый пропуск —
        ошибка сборки);
      * отсутствие доступа к будущим свечам: единственный путь данных к
        стратегии — view_upto(i) / entry_dataframe_upto(i), возвращающие
        свечи [0, i] включительно; в путь принятия решений НЕ существует
        метода, выдающего серию целиком;
      * data_sha256 — детерминированный SHA-256 отпечаток серии
        (входит в run_id и отчёт, ТЗ §7).
    """

    def __init__(self, *,
                 series: CandleSeries,
                 engine_config: EngineConfig) -> None:
        if type(series) is not CandleSeries:
            raise DataFeedError(
                "HistoricalDataFeed требует точный тип CandleSeries; "
                f"получено {type(series).__name__}")
        if type(engine_config) is not EngineConfig:
            raise DataFeedError(
                "HistoricalDataFeed требует точный тип EngineConfig")
        self._series = series
        self._engine_config = engine_config
        # Контроль пропусков (ТЗ Stage E §3.1; Stage E.1 Correction 1):
        # классификация отклонений интервала — календарно-корректная.
        self._gap_incidents: Tuple[GapIncident, ...] = ()
        self._gap_verification_status = \
            GAP_VERIFICATION_NOT_PERFORMED_INTERVAL_UNSET
        interval = engine_config.expected_candle_interval_seconds
        calendar = engine_config.calendar
        if interval is None:
            # ЯВНОЕ решение оператора: контроль только хронологии.
            self._gap_verification_status = \
                GAP_VERIFICATION_NOT_PERFORMED_INTERVAL_UNSET
        elif calendar is None:
            # ОГРАНИЧЕННАЯ проверка хронологии (категория D): отклонения
            # интервала обнаруживаются, но подтвердить пропуск ожидаемой
            # торговой свечи без календаря НЕВОЗМОЖНО; без календаря
            # подтверждения полноты данных НЕ выдаётся. STRICT —
            # fail-closed консервативизм: отклоняется любое отклонение.
            interval_td = timedelta(seconds=interval)
            deviations: List[GapIncident] = []
            for prev, cur in zip(series.candles, series.candles[1:]):
                delta = cur.timestamp - prev.timestamp
                if delta != interval_td:
                    deviations.append(GapIncident(
                        category=GAP_CATEGORY_UNVERIFIED_NO_CALENDAR,
                        expected_timestamp_iso=(
                            prev.timestamp + interval_td).isoformat(),
                        next_actual_timestamp_iso=cur.timestamp.isoformat(),
                        gap_seconds=int(delta.total_seconds()),
                        missing_expected_count=0,
                        details={
                            "reason": "calendar_not_provided_limited_"
                                      "chronology_check",
                        },
                    ))
            self._gap_incidents = tuple(deviations)
            self._gap_verification_status = \
                GAP_VERIFICATION_LIMITED_NO_CALENDAR
            if deviations and engine_config.gap_policy == "STRICT":
                raise DataFeedError(
                    f"обнаружены отклонения интервала свечей "
                    f"(gap_policy=STRICT): {len(deviations)} шт.; первый: "
                    f"ожидается {deviations[0].expected_timestamp_iso}, "
                    f"фактически "
                    f"{deviations[0].next_actual_timestamp_iso}; данные не "
                    "интерполируются; КАЛЕНДАРЬ НЕ ПЕРЕДАН: ограниченная "
                    "проверка хронологии, классификация отклонений "
                    "(выходные/праздники/перерывы) невозможна")
        else:
            # КАЛЕНДАРНО-КОРРЕКТНАЯ проверка (Stage E.1): выходные,
            # праздники, ночные перерывы и внутридневные паузы НЕ являются
            # пропусками; STRICT отклоняет только ПОДТВЕРЖДЁННЫЕ пропуски
            # ожидаемых торговых свечей.
            incidents = calendar.analyze_series(series, interval)
            confirmed = [incident for incident in incidents
                         if incident.category in CONFIRMED_GAP_CATEGORIES]
            unverified = any(
                incident.category
                in (GAP_CATEGORY_UNVERIFIED_OUTSIDE_CALENDAR_COVERAGE,)
                for incident in incidents)
            self._gap_incidents = tuple(incidents)
            if confirmed and engine_config.gap_policy == "STRICT":
                first_confirmed = confirmed[0]
                raise DataFeedError(
                    "подтверждённые пропуски ожидаемых торговых свечей "
                    f"(gap_policy=STRICT, календарная проверка): "
                    f"{len(confirmed)} шт.; первый: ожидается "
                    f"{first_confirmed.expected_timestamp_iso}, следующая "
                    "фактически присутствующая свеча "
                    f"{first_confirmed.next_actual_timestamp_iso}; данные "
                    "не интерполируются")
            self._gap_verification_status = GAP_VERIFICATION_PARTIAL \
                if unverified else GAP_VERIFICATION_FULL

    # --- сборка из источника -----------------------------------------------

    @classmethod
    def from_candles(cls, candles: Iterable[Candle], *,
                     engine_config: EngineConfig) -> "HistoricalDataFeed":
        items: List[Candle] = list(candles)
        if not items:
            raise DataFeedError(
                "HistoricalDataFeed: пустой набор свечей запрещён "
                "(fail-closed)")
        return cls(series=CandleSeries(tuple(items)),
                   engine_config=engine_config)

    @classmethod
    def from_dataframe(cls, frame: Any, *,
                       engine_config: EngineConfig) -> "HistoricalDataFeed":
        """Сборка из pandas.DataFrame (open/high/low/close/volume,
        DatetimeIndex с часовым поясом). Наивные индексы отклоняются:
        без часового пояса метка не может детерминированно сравниваться
        с метками контрактов Stage C."""
        if not isinstance(frame, pd.DataFrame):
            raise DataFeedError(
                "from_dataframe требует pandas.DataFrame; получено "
                f"{type(frame).__name__}")
        missing = [c for c in REQUIRED_COLUMNS
                   if c not in frame.columns]
        if missing:
            raise DataFeedError(
                f"DataFrame не содержит обязательных колонок: {missing}")
        if len(frame) == 0:
            raise DataFeedError("DataFrame пуст (fail-closed)")
        index = frame.index
        if not isinstance(index, pd.DatetimeIndex):
            raise DataFeedError(
                "DataFrame.index должен быть DatetimeIndex; получено "
                f"{type(index).__name__}")
        if index.tz is None:
            raise DataFeedError(
                "DatetimeIndex без часового пояса отклоняется "
                "(наивные метки не сравнимы детерминированно)")
        candles: List[Candle] = []
        for row_ts, row in zip(index, frame.itertuples(index=False)):
            candles.append(Candle(
                timestamp=row_ts.to_pydatetime(),
                open=getattr(row, "open"),
                high=getattr(row, "high"),
                low=getattr(row, "low"),
                close=getattr(row, "close"),
                volume=getattr(row, "volume"),
            ))
        return cls.from_candles(candles, engine_config=engine_config)

    # --- доступ данных (без будущего) --------------------------------------

    @property
    def length(self) -> int:
        return len(self._series)

    @property
    def gaps(self) -> Tuple[Tuple[str, str], ...]:
        """Обнаруженные отклонения интервала в СТАРОМ парном формате
        (expected_iso, actual_iso) — обратная совместимость Stage E.

        Семантика зависит от режима (Stage E.1):
          * календарь задан — ТОЛЬКО подтверждённые пропуски ожидаемых
            торговых свечей (и календарно-независимые аномалии
            хронологии); нормальные перерывы/выходные/праздники сюда НЕ
            попадают (это и есть исправление Correction 1);
          * календарь НЕ задан — все отклонения интервала (как в Stage E),
            каждый из них — неподтверждённый инцидент ограниченной
            проверки.
        Подробная классификация — в gap_incidents / gap_verification.
        """
        return tuple(
            (incident.expected_timestamp_iso,
             incident.next_actual_timestamp_iso)
            for incident in self._gap_incidents
            if self._engine_config.calendar is None
            or incident.category in CONFIRMED_GAP_CATEGORIES
        )

    @property
    def gap_incidents(self) -> Tuple[GapIncident, ...]:
        """Полная классификация инцидентов контроля пропусков (Stage E.1)."""
        return self._gap_incidents

    @property
    def gap_verification_status(self) -> str:
        """Явный статус верификации полноты серии (Stage E.1).

        NOT_PERFORMED_INTERVAL_UNSET — интервал не задан (контроль только
        хронологии); LIMITED_NO_CALENDAR_CHRONOLOGY_ONLY — календарь не
        передан, отклонения не классифицируются;
        PERFORMED_FULL_CALENDAR_VERIFIED — календарная проверка выполнена
        полностью; PERFORMED_PARTIAL_CALENDAR_COVERAGE_INSUFFICIENT —
        часть отклонений вне покрытого календарём диапазона.
        """
        return self._gap_verification_status

    @property
    def calendar_sha256(self) -> Optional[str]:
        """SHA-256 конфигурации календаря (None — календарь не задан)."""
        calendar = self._engine_config.calendar
        return None if calendar is None else calendar.calendar_sha256()

    @property
    def engine_config(self) -> EngineConfig:
        """Конфигурация интерпретации данных, с которой собран фид
        (для явной проверки совместимости с BacktestEngine, Correction 3)."""
        return self._engine_config

    @property
    def data_sha256(self) -> str:
        return self._series.data_sha256()

    def candle(self, index: int) -> Candle:
        if not isinstance(index, int) or isinstance(index, bool) \
                or index < 0 or index >= self.length:
            raise DataFeedError(
                f"HistoricalDataFeed.candle: index {index!r} вне диапазона")
        return self._series.candles[index]

    def view_upto(self, index: int) -> Tuple[Candle, ...]:
        """Свечи [0, index] включительно (ЕДИНСТВЕННЫЙ канал данных к
        стратегии: будущие свечи физически не попадают в срез)."""
        return self._series.slice_upto(index)

    def entry_dataframe_upto(self, index: int) -> pd.DataFrame:
        """Копия pandas-представления свечей [0, index] для контракта
        EntrySignalInput (Stage A). Возвращается ЗАЩИТНАЯ копия: изменение
        кадра стратегией не влияет на данные движка."""
        rows = self.view_upto(index)
        data = {
            "open": [c.open for c in rows],
            "high": [c.high for c in rows],
            "low": [c.low for c in rows],
            "close": [c.close for c in rows],
            "volume": [c.volume for c in rows],
        }
        tz_index = pd.DatetimeIndex([c.timestamp for c in rows])
        return pd.DataFrame(data, index=tz_index, dtype=float)
