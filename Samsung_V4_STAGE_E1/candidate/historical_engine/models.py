# historical_engine/models.py
# SAMSUNG V4 — NEW STRATEGY ENGINE. STAGE E.
# ДЕТЕРМИНИРОВАННЫЙ ИСТОРИЧЕСКИЙ СИМУЛЯТОР (RESEARCH ONLY).
#
# Базовые типизированные неизменяемые модели Stage E: свеча, серия свечей,
# конфигурация симуляции, сегменты периодов (IS/VALIDATION/OOS), журнальные
# события. Никакого времени системы, случайности, окружения и сети.
#
# STRATEGY LOGIC: NOT TOUCHED. NO BROKER. NO ORDERS. NO SANDBOX/LIVE.
# OFFLINE ONLY.

from __future__ import annotations

import dataclasses
import hashlib
import json
import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, Mapping, Optional, Tuple

ENGINE_VERSION = "historical_engine_stage_e_v1"

# --- Stage E.1: календарно-корректное обнаружение пропусков (Correction 1) ---

# Схема отпечатка торгового календаря.
CALENDAR_SCHEMA = "samsung_v4_stage_e1_trading_calendar_v1"

# Категории ИНЦИДЕНТОВ анализа пропусков:
#   A — подтверждённый пропуск ожидаемой торговой свечи;
#   B — нормальный внутридневной перерыв сессии;
#   C — нет торгов (выходной/праздник — день целиком; NON_TRADING_TIME —
#       момент вне окна сессии при наличии на дату сессии);
#   D — проверить невозможно (календарь не передан либо отклонение вне
#       покрытого календарём диапазона дат).
GAP_CATEGORY_CONFIRMED_EXPECTED_CANDLE_MISSING = \
    "CONFIRMED_EXPECTED_CANDLE_MISSING"                       # A
GAP_CATEGORY_SESSION_BREAK = "SESSION_BREAK"                  # B
GAP_CATEGORY_NON_TRADING_DAY = "NON_TRADING_DAY"              # C
GAP_CATEGORY_NON_TRADING_TIME = "NON_TRADING_TIME"            # C
GAP_CATEGORY_IRREGULAR_SPACING = "CONFIRMED_IRREGULAR_SPACING"  # A*
GAP_CATEGORY_UNVERIFIED_NO_CALENDAR = \
    "UNVERIFIED_NO_CALENDAR_LIMITED_CHRONOLOGY_CHECK"         # D
GAP_CATEGORY_UNVERIFIED_OUTSIDE_CALENDAR_COVERAGE = \
    "UNVERIFIED_OUTSIDE_CALENDAR_COVERAGE"                    # D

# Подтверждённые категории (единственное основание для STRICT-отказа):
# собственно пропуск ожидаемой торговой свечи и календарно-независимая
# аномалия хронологии (свеча раньше ожидаемого интервала — ни перерыв,
# ни выходной объяснить её не могут).
CONFIRMED_GAP_CATEGORIES = (
    GAP_CATEGORY_CONFIRMED_EXPECTED_CANDLE_MISSING,
    GAP_CATEGORY_IRREGULAR_SPACING,
)

# Категории ОТДЕЛЬНОГО момента времени (результат classify_moment).
MOMENT_CATEGORY_IN_TRADING_TIME = "IN_TRADING_TIME"
MOMENT_CATEGORY_IN_SESSION_BREAK = "IN_SESSION_BREAK"
MOMENT_CATEGORY_NON_TRADING_DAY = "NON_TRADING_DAY"
MOMENT_CATEGORY_NON_TRADING_TIME = "NON_TRADING_TIME"
MOMENT_CATEGORY_OUTSIDE_CALENDAR_COVERAGE = "OUTSIDE_CALENDAR_COVERAGE"

# Статусы верификации полноты серии (явное сообщение движка).
GAP_VERIFICATION_NOT_PERFORMED_INTERVAL_UNSET = \
    "NOT_PERFORMED_INTERVAL_UNSET"
GAP_VERIFICATION_LIMITED_NO_CALENDAR = \
    "LIMITED_NO_CALENDAR_CHRONOLOGY_ONLY"
GAP_VERIFICATION_FULL = "PERFORMED_FULL_CALENDAR_VERIFIED"
GAP_VERIFICATION_PARTIAL = \
    "PERFORMED_PARTIAL_CALENDAR_COVERAGE_INSUFFICIENT"

# Причины блокировки входа, добавленные движком Stage E (в дополнение к
# reason_code Stage D, которые пробрасываются как есть).
REASON_ENTRY_NO_SIGNAL = "ENGINE_NO_ENTRY_SIGNAL"
REASON_ENTRY_FORBIDDEN_BY_STRATEGY = "ENGINE_ENTRY_FORBIDDEN_BY_STRATEGY"
REASON_ENTRY_BLOCKED_SIZING = "ENGINE_ENTRY_BLOCKED_SIZING"
REASON_ENTRY_BLOCKED_INSUFFICIENT_CASH = \
    "ENGINE_ENTRY_BLOCKED_INSUFFICIENT_CASH"
REASON_EXIT_UNRESOLVED_AT_SEGMENT_END = "ENGINE_EXIT_UNRESOLVED_AT_SEGMENT_END"

# Типы защитного выхода на уровне исполнения (брокерская эмуляция стопов).
EXIT_TYPE_STOP_LOSS = "PROTECTIVE_STOP_LOSS"
EXIT_TYPE_TAKE_PROFIT = "PROTECTIVE_TAKE_PROFIT"
# Стратегический выход (отображение SELL-сигнала Stage A, long-only).
EXIT_TYPE_STRATEGIC_SELL = "STRATEGIC_SELL_SIGNAL"

# Флаг неоднозначности SL/TP внутри одной свечи (последовательность
# движения цены неизвестна): консервативная модель — СТОП ЛОСС первым.
AMBIGUITY_SL_TP_SAME_CANDLE = "SL_TP_SAME_CANDLE_SL_PRIORITIZED"


class HistoricalEngineError(Exception):
    """Базовая ошибка исторического движка Stage E (fail-closed)."""


class DataFeedError(HistoricalEngineError):
    """Некорректные исторические данные (порядок, OHLC, NaN, пропуски)."""


class EngineConfigError(HistoricalEngineError):
    """Некорректная конфигурация симуляции (fail-closed, без умолчаний)."""


class LedgerError(HistoricalEngineError):
    """Нарушение инвариантов виртуального портфеля (fail-closed)."""


class ExecutionError(HistoricalEngineError):
    """Нарушение модели исполнения (fail-closed)."""


def canonical_json(payload: Any) -> str:
    """Канонический JSON: sort_keys, компактные разделители, ASCII,
    NaN/Infinity запрещены (детерминированная сериализация отчётов)."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False)


def sha256_hex(text: str) -> str:
    """SHA-256 hexdigest строки UTF-8."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _validate_positive_float(value: Any, name: str,
                             error: type) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise error(f"{name} должен быть числом (bool запрещён); получено "
                    f"{type(value).__name__}")
    result = float(value)
    if not math.isfinite(result) or result <= 0.0:
        raise error(f"{name} должен быть конечным и СТРОГО больше нуля; "
                    f"получено {value!r}")
    return result


def _validate_fraction_01(value: Any, name: str, error: type,
                          *, allow_zero: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise error(f"{name} должен быть числом (bool запрещён); получено "
                    f"{type(value).__name__}")
    result = float(value)
    if not math.isfinite(result):
        raise error(f"{name}: NaN/Infinity запрещены")
    lower_ok = result >= 0.0 if allow_zero else result > 0.0
    if not lower_ok or result > 1.0:
        raise error(f"{name} должен быть в диапазоне "
                    f"({'[0; 1]' if allow_zero else '(0; 1]'}); получено "
                    f"{value!r}")
    return result


@dataclass(frozen=True)
class Candle:
    """Одна ЗАКРЫТАЯ историческая свеча (неизменяемая, валидированная).

    Инварианты (fail-closed при создании):
      * timestamp — осведомлённый datetime (наивные метки отклоняются);
      * open/high/low/close — конечные числа СТРОГО больше нуля;
      * high >= max(open, close); low <= min(open, close);
      * volume — конечное число >= 0.
    """
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float

    def __post_init__(self) -> None:
        if not isinstance(self.timestamp, datetime) \
                or self.timestamp.tzinfo is None:
            raise DataFeedError(
                "Candle.timestamp должен быть tz-aware datetime; получено "
                f"{self.timestamp!r}")
        for name in ("open", "high", "low", "close"):
            _validate_positive_float(getattr(self, name), f"Candle.{name}",
                                     DataFeedError)
        if self.high < max(self.open, self.close) \
                or self.low > min(self.open, self.close):
            raise DataFeedError(
                "Candle: нарушена OHLC-геометрия "
                f"(high={self.high!r}, low={self.low!r}, "
                f"open={self.open!r}, close={self.close!r})")
        if isinstance(self.volume, bool) \
                or not isinstance(self.volume, (int, float)) \
                or not math.isfinite(float(self.volume)) \
                or float(self.volume) < 0.0:
            raise DataFeedError(
                f"Candle.volume должен быть конечным числом >= 0; "
                f"получено {self.volume!r}")
        object.__setattr__(self, "open", float(self.open))
        object.__setattr__(self, "high", float(self.high))
        object.__setattr__(self, "low", float(self.low))
        object.__setattr__(self, "close", float(self.close))
        object.__setattr__(self, "volume", float(self.volume))

    @property
    def timestamp_iso(self) -> str:
        return self.timestamp.isoformat()

    def as_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp_iso,
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
        }


@dataclass(frozen=True)
class GapIncident:
    """Один инцидент календарного анализа пропусков (неизменяемый).

    category — константа GAP_CATEGORY_*; expected_timestamp_iso —
    ожидаемая метка (для подтверждённого пропуска — пропущенная ожидаемая
    торговая свеча; для прочих категорий — первая ожидаемая метка
    отклонения); next_actual_timestamp_iso — следующая фактически
    присутствующая свеча; gap_seconds — фактическое расстояние между
    соседними свечами; missing_expected_count — сколько ожидаемых торговых
    свечей пропущено в этом отклонении (> 0 только для подтверждённых
    пропусков); details — детерминированная текстовая диагностика.
    """
    category: str
    expected_timestamp_iso: str
    next_actual_timestamp_iso: str
    gap_seconds: int
    missing_expected_count: int
    details: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        KNOWN = {
            GAP_CATEGORY_CONFIRMED_EXPECTED_CANDLE_MISSING,
            GAP_CATEGORY_SESSION_BREAK,
            GAP_CATEGORY_NON_TRADING_DAY,
            GAP_CATEGORY_NON_TRADING_TIME,
            GAP_CATEGORY_IRREGULAR_SPACING,
            GAP_CATEGORY_UNVERIFIED_NO_CALENDAR,
            GAP_CATEGORY_UNVERIFIED_OUTSIDE_CALENDAR_COVERAGE,
        }
        if self.category not in KNOWN:
            raise DataFeedError(
                f"GapIncident: неизвестная категория {self.category!r}")
        if isinstance(self.gap_seconds, bool) \
                or not isinstance(self.gap_seconds, int) \
                or self.gap_seconds < 0:
            raise DataFeedError(
                "GapIncident.gap_seconds должен быть int >= 0; получено "
                f"{self.gap_seconds!r}")
        if isinstance(self.missing_expected_count, bool) \
                or not isinstance(self.missing_expected_count, int) \
                or self.missing_expected_count < 0:
            raise DataFeedError(
                "GapIncident.missing_expected_count должен быть int >= 0; "
                f"получено {self.missing_expected_count!r}")
        if self.category == GAP_CATEGORY_CONFIRMED_EXPECTED_CANDLE_MISSING \
                and self.missing_expected_count <= 0:
            raise DataFeedError(
                "GapIncident: подтверждённый пропуск требует "
                "missing_expected_count >= 1")

    def as_dict(self) -> Dict[str, Any]:
        return {
            "category": self.category,
            "expected_timestamp_iso": self.expected_timestamp_iso,
            "next_actual_timestamp_iso": self.next_actual_timestamp_iso,
            "gap_seconds": self.gap_seconds,
            "missing_expected_count": self.missing_expected_count,
            "details": dict(self.details),
        }


@dataclass(frozen=True)
class CandleSeries:
    """Неизменяемая хронологическая серия закрытых свечей.

    Порядок СТРОГО возрастающий по timestamp (дубликаты и нарушения
    порядка отклоняются при создании). Доступ движка к данным — только
    через slice_upto(i): свечи с индексами [0, i] включительно; метод
    физически не может отдать будущие свечи.
    """
    candles: Tuple[Candle, ...]

    def __post_init__(self) -> None:
        candles = tuple(self.candles)
        if not candles:
            raise DataFeedError(
                "CandleSeries не может быть пустой (fail-closed)")
        previous: Optional[datetime] = None
        for candle in candles:
            if type(candle) is not Candle:
                raise DataFeedError(
                    "CandleSeries принимает только точный тип Candle; "
                    f"получено {type(candle).__name__}")
            if previous is not None and candle.timestamp <= previous:
                raise DataFeedError(
                    "CandleSeries: порядок времени нарушен или дубликат: "
                    f"{previous.isoformat()} -> "
                    f"{candle.timestamp.isoformat()}")
            previous = candle.timestamp
        object.__setattr__(self, "candles", candles)

    def __len__(self) -> int:
        return len(self.candles)

    @property
    def first_timestamp(self) -> datetime:
        return self.candles[0].timestamp

    @property
    def last_timestamp(self) -> datetime:
        return self.candles[-1].timestamp

    def slice_upto(self, index: int) -> Tuple[Candle, ...]:
        """Свечи [0, index] включительно (доступ к будущему невозможен)."""
        if not isinstance(index, int) or isinstance(index, bool):
            raise DataFeedError(
                f"CandleSeries.slice_upto: index должен быть int; "
                f"получено {type(index).__name__}")
        if index < 0 or index >= len(self.candles):
            raise DataFeedError(
                f"CandleSeries.slice_upto: index {index} вне диапазона "
                f"[0, {len(self.candles) - 1}]")
        return self.candles[:index + 1]

    def detect_gaps(self, expected_interval_seconds: int) \
            -> Tuple[Tuple[str, str], ...]:
        """Пары (ожидаемая_метка, фактическая_метка) в местах пропусков.

        Пропуск — расстояние между соседними метками, НЕ равное ровно
        одному ожидаемому интервалу. Данные НЕ интерполируются и НЕ
        заполняются (никаких подстановок, ТЗ Stage E §4/§5).
        """
        if not isinstance(expected_interval_seconds, int) \
                or isinstance(expected_interval_seconds, bool) \
                or expected_interval_seconds <= 0:
            raise DataFeedError(
                "expected_interval_seconds должен быть положительным int")
        interval = timedelta(seconds=expected_interval_seconds)
        gaps = []
        for prev, cur in zip(self.candles, self.candles[1:]):
            expected = prev.timestamp + interval
            if cur.timestamp != expected:
                gaps.append((expected.isoformat(), cur.timestamp.isoformat()))
        return tuple(gaps)

    def data_sha256(self) -> str:
        """Детерминированный SHA-256 отпечаток ВСЕЙ серии (repr float)."""
        payload = [
            {"timestamp": c.timestamp_iso,
             "open": repr(c.open), "high": repr(c.high),
             "low": repr(c.low), "close": repr(c.close),
             "volume": repr(c.volume)}
            for c in self.candles
        ]
        return sha256_hex(canonical_json(payload))


@dataclass(frozen=True)
class EngineConfig:
    """Конфигурация симуляции Stage E (неизменяемая, без умолчаний риска).

    Состав — ТОЛЬКО параметры СИМУЛЯЦИИ (исполнение/издержки/риск-лимиты
    для Stage D). Стратегические пороги сюда НЕ входят и не оптимизируются
    (ТЗ Stage E §2: никакой автоподбор параметров).

    Поля:
      figi, ticker                 — инструмент;
      initial_cash                 — стартовый денежный баланс > 0;
      commission_rate              — доля комиссии от notional НА КАЖДУЮ
                                     сторону, [0; 1);
      slippage_rate                — доля неблагоприятного проскальзывания
                                     на каждую сторону, [0; 1);
      stop_loss_fraction           — защитный стоп ниже входа, (0; 1).
                                     ОБЯЗАТЕЛЕН: формула Stage D требует
                                     protective_stop_price, поэтому вход без
                                     определённого стопа блокировался бы
                                     Stage D (MISSING_REQUIRED_DATA) —
                                     конфигурация отклоняется сразу;
      take_profit_fraction         — цель выше входа, (0; 1); None — TP
                                     отключён ЯВНЫМ решением;
      lot_size                     — размер лота, int > 0;
      contract_multiplier          — множитель контракта, > 0 (акции: 1.0);
      risk_per_trade_fraction      — риск на сделку (Stage D), (0; 1];
      max_position_notional_fraction — notional-лимит позиции (Stage D),
                                       (0; 1];
      expected_candle_interval_seconds — ожидаемый интервал свечей (контроль
                                       пропусков); None — контроль
                                       только хронологии (ЯВНОЕ решение);
      gap_policy                   — 'REPORT' (пропуски фиксируются в
                                     отчёте) или 'STRICT' (подтверждённый
                                     пропуск — ошибка сборки серии);
      calendar                     — торговый календарь (Stage E.1,
                                     Correction 1) для календарно-корректной
                                     классификации отклонений интервала;
                                     None — ограниченная проверка
                                     хронологии (отклонения интервала
                                     НЕ классифицируются календарём и
                                     не могут быть подтверждены как
                                     пропуски торговых свечей — режим
                                     ЯВНО отражается в отчёте).
    """
    figi: str
    ticker: str
    initial_cash: float
    commission_rate: float
    slippage_rate: float
    stop_loss_fraction: float
    take_profit_fraction: Optional[float]
    lot_size: int
    contract_multiplier: float
    risk_per_trade_fraction: float
    max_position_notional_fraction: float
    expected_candle_interval_seconds: Optional[int] = None
    gap_policy: str = "REPORT"
    calendar: Optional["TradingCalendar"] = None

    def __post_init__(self) -> None:
        for name in ("figi", "ticker"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise EngineConfigError(
                    f"EngineConfig.{name} должен быть непустой строкой")
        self._positive("initial_cash")
        rate = _validate_fraction_01(self.commission_rate,
                                     "EngineConfig.commission_rate",
                                     EngineConfigError, allow_zero=True)
        if rate >= 1.0:
            raise EngineConfigError(
                "EngineConfig.commission_rate должен быть < 1.0")
        object.__setattr__(self, "commission_rate", rate)
        slip = _validate_fraction_01(self.slippage_rate,
                                     "EngineConfig.slippage_rate",
                                     EngineConfigError, allow_zero=True)
        if slip >= 1.0:
            raise EngineConfigError(
                "EngineConfig.slippage_rate должен быть < 1.0")
        object.__setattr__(self, "slippage_rate", slip)
        stop = _validate_fraction_01(self.stop_loss_fraction,
                                     "EngineConfig.stop_loss_fraction",
                                     EngineConfigError)
        object.__setattr__(self, "stop_loss_fraction", stop)
        if self.take_profit_fraction is not None:
            tp = _validate_fraction_01(self.take_profit_fraction,
                                       "EngineConfig.take_profit_fraction",
                                       EngineConfigError)
            object.__setattr__(self, "take_profit_fraction", tp)
        if isinstance(self.lot_size, bool) or not isinstance(self.lot_size,
                                                             int) \
                or self.lot_size <= 0:
            raise EngineConfigError(
                f"EngineConfig.lot_size должен быть int > 0; получено "
                f"{self.lot_size!r}")
        self._positive("contract_multiplier")
        self._positive("risk_per_trade_fraction")
        self._positive("max_position_notional_fraction")
        if self.expected_candle_interval_seconds is not None:
            interval = self.expected_candle_interval_seconds
            if isinstance(interval, bool) or not isinstance(interval, int) \
                    or interval <= 0:
                raise EngineConfigError(
                    "EngineConfig.expected_candle_interval_seconds должен "
                    f"быть положительным int или None; получено {interval!r}")
        if self.gap_policy not in ("REPORT", "STRICT"):
            raise EngineConfigError(
                "EngineConfig.gap_policy должен быть 'REPORT' или "
                f"'STRICT'; получено {self.gap_policy!r}")
        if self.calendar is not None:
            # Ленивый импорт исключает цикл моделей: calendar.py импортирует
            # константы из models.py.
            from .calendar import TradingCalendar
            if type(self.calendar) is not TradingCalendar:
                raise EngineConfigError(
                    "EngineConfig.calendar должен быть точным типом "
                    "TradingCalendar или None (ЯВНОЕ решение); получено "
                    f"{type(self.calendar).__name__}")

    def _positive(self, name: str) -> None:
        value = getattr(self, name)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise EngineConfigError(
                f"EngineConfig.{name} должен быть числом (bool запрещён); "
                f"получено {type(value).__name__}")
        result = float(value)
        if not math.isfinite(result) or result <= 0.0:
            raise EngineConfigError(
                f"EngineConfig.{name} должен быть конечным и > 0; "
                f"получено {value!r}")
        object.__setattr__(self, name, result)

    def canonical_dict(self) -> Dict[str, Any]:
        """Канонический словарь конфигурации (для хешей и отчёта)."""
        return {
            "figi": self.figi,
            "ticker": self.ticker,
            "initial_cash": repr(self.initial_cash),
            "commission_rate": repr(self.commission_rate),
            "slippage_rate": repr(self.slippage_rate),
            "stop_loss_fraction": repr(self.stop_loss_fraction),
            "take_profit_fraction":
                None if self.take_profit_fraction is None
                else repr(self.take_profit_fraction),
            "lot_size": self.lot_size,
            "contract_multiplier": repr(self.contract_multiplier),
            "risk_per_trade_fraction": repr(self.risk_per_trade_fraction),
            "max_position_notional_fraction":
                repr(self.max_position_notional_fraction),
            "expected_candle_interval_seconds":
                self.expected_candle_interval_seconds,
            "gap_policy": self.gap_policy,
            "calendar_sha256": None if self.calendar is None
                else self.calendar.calendar_sha256(),
        }

    def config_sha256(self) -> str:
        return sha256_hex(canonical_json(self.canonical_dict()))


@dataclass(frozen=True)
class SegmentSpec:
    """Сегмент исторического периода (IS / VALIDATION / OOS / произвольный).

    Границы — индексы свечей: [start_index, end_index) в терминах полной
    серии. Метка — короткий код; каждый сегмент запускается НЕЗАВИСИМО
    (позиции не переносятся через границу — задокументированная модель).
    """
    label: str
    start_index: int
    end_index: int

    def __post_init__(self) -> None:
        if not isinstance(self.label, str) or not self.label.strip():
            raise EngineConfigError(
                "SegmentSpec.label должен быть непустой строкой")
        for name in ("start_index", "end_index"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int):
                raise EngineConfigError(
                    f"SegmentSpec.{name} должен быть int; получено "
                    f"{type(value).__name__}")
        if self.start_index < 0 or self.end_index <= self.start_index:
            raise EngineConfigError(
                "SegmentSpec: требуется 0 <= start_index < end_index; "
                f"получено [{self.start_index}, {self.end_index})")


# ---------------------------------------------------------------------------
# Журнальные события (неизменяемые, JSON-совместимые через as_dict)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LedgerOperation:
    """Одна операция виртуального портфеля (история операций, ТЗ §3.6).

    Stage E.1 (Correction 2): slippage_cost — ТОЛЬКО неблагоприятное
    проскальзывание (>= 0); price_improvement — улучшение цены исполнения
    (>= 0). Показатели раздельные и никогда не взаимно погашаются.
    """
    op_index: int
    kind: str                       # ENTRY_EXECUTED / EXIT_EXECUTED
    timestamp_iso: str
    price: float
    quantity: int
    notional: float
    commission: float
    slippage_cost: float
    cash_after: float
    realized_pnl_net: Optional[float]   # только для EXIT
    details: Mapping[str, Any] = field(default_factory=dict)
    price_improvement: float = 0.0      # улучшение цены, >= 0 (Stage E.1)

    def as_dict(self) -> Dict[str, Any]:
        return dict(dataclasses.asdict(self))


@dataclass(frozen=True)
class JournalEvent:
    """Обобщённое событие журнала прогона (детерминированный порядок)."""
    event_index: int
    event_type: str
    candle_index: int
    timestamp_iso: str
    payload: Mapping[str, Any]

    def as_dict(self) -> Dict[str, Any]:
        return {
            "event_index": self.event_index,
            "event_type": self.event_type,
            "candle_index": self.candle_index,
            "timestamp_iso": self.timestamp_iso,
            "payload": dict(self.payload),
        }
