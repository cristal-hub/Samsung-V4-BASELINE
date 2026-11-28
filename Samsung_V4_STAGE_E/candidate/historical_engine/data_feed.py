# historical_engine/data_feed.py
# SAMSUNG V4 — NEW STRATEGY ENGINE. STAGE E.
#
# HistoricalDataFeed: последовательная подача исторических свечей СТРОГО
# в хронологическом порядке, контроль пропусков и некорректных данных,
# ФИЗИЧЕСКАЯ невозможность доступа к будущим свечам (ТЗ Stage E §3.1, §4).
#
# Данные только исторические, только оффлайн; никаких сетевых запросов.

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Sequence, Tuple

import pandas as pd

from .models import (
    Candle,
    CandleSeries,
    DataFeedError,
    EngineConfig,
    canonical_json,
)

REQUIRED_COLUMNS = ("open", "high", "low", "close", "volume")


class HistoricalDataFeed:
    """Последовательная подача ЗАКРЫТЫХ исторических свечей (fail-closed).

    Гарантии:
      * данные валидируются при сборке: OHLC-геометрия, конечность,
        положительность цен, неотрицательный объём, СТРОГО возрастающие
        tz-aware метки времени (наивные метки и дубликаты отклоняются);
      * контроль пропусков: при заданном expected_candle_interval_seconds
        обнаруживаются свечи, идущие НЕ через ровно один интервал; данные
        НИКОГДА не интерполируются и не заполняются будущими значениями;
        поведение задается gap_policy: 'REPORT' (пропуски фиксируются в
        отчёте) или 'STRICT' (ошибка сборки);
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
        # Контроль пропусков (ТЗ §3.1): если интервал задан — обнаруживаем
        # свечи, идущие не через ровно один интервал.
        self._gaps: Tuple[Tuple[str, str], ...] = ()
        interval = engine_config.expected_candle_interval_seconds
        if interval is not None:
            gaps = series.detect_gaps(interval)
            if gaps and engine_config.gap_policy == "STRICT":
                raise DataFeedError(
                    f"обнаружены пропуски свечей (gap_policy=STRICT): "
                    f"{len(gaps)} шт.; первый: ожидается {gaps[0][0]}, "
                    f"фактически {gaps[0][1]}; данные не интерполируются")
            self._gaps = gaps

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
        """Обнаруженные пропуски (пусто — если пропусков нет)."""
        return self._gaps

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
