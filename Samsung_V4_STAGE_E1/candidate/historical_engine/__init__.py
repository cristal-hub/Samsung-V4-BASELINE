# historical_engine/__init__.py
# SAMSUNG V4 — NEW STRATEGY ENGINE. STAGE E / STAGE E.1.
# ДЕТЕРМИНИРОВАННЫЙ ИСТОРИЧЕСКИЙ СИМУЛЯТОР (STRICT RESEARCH ONLY).
#
# Только исторические данные, только виртуальная симуляция; никаких
# реальных ордеров, Sandbox/LIVE, брокерских SDK и сетевых запросов.
# Модуль не изменяет Stage A/B/C/D и legacy Samsung V4.
#
# Компоненты (ТЗ Stage E §3):
#   HistoricalDataFeed            — хронологическая подача закрытых свечей,
#                                   календарно-корректный контроль
#                                   пропусков (E.1), без будущего;
#   TradingCalendar (E.1)         — явно переданный календарь сессий:
#                                   классификация пропусков/перерывов/
#                                   выходных/праздников;
#   EventEngine                   — детерминированные фазы обработки;
#   StrategyRunner                — вызов контрактов Stage A/C;
#   HistoricalExecutionSimulator  — виртуальное исполнение, раздельный
#                                   учёт slippage/улучшения цены (E.1);
#   RiskIntegration               — размер позиции СТРОГО через Stage D;
#   PortfolioLedger               — виртуальный портфель и PnL;
#   BacktestReport                — детерминированный отчёт + SHA-256.

from .models import (
    AMBIGUITY_SL_TP_SAME_CANDLE,
    CALENDAR_SCHEMA,
    CONFIRMED_GAP_CATEGORIES,
    Candle,
    CandleSeries,
    DataFeedError,
    ENGINE_VERSION,
    EngineConfig,
    EngineConfigError,
    ExecutionError,
    GapIncident,
    GAP_CATEGORY_CONFIRMED_EXPECTED_CANDLE_MISSING,
    GAP_CATEGORY_IRREGULAR_SPACING,
    GAP_CATEGORY_NON_TRADING_DAY,
    GAP_CATEGORY_NON_TRADING_TIME,
    GAP_CATEGORY_SESSION_BREAK,
    GAP_CATEGORY_UNVERIFIED_NO_CALENDAR,
    GAP_CATEGORY_UNVERIFIED_OUTSIDE_CALENDAR_COVERAGE,
    GAP_VERIFICATION_FULL,
    GAP_VERIFICATION_LIMITED_NO_CALENDAR,
    GAP_VERIFICATION_NOT_PERFORMED_INTERVAL_UNSET,
    GAP_VERIFICATION_PARTIAL,
    HistoricalEngineError,
    JournalEvent,
    LedgerError,
    LedgerOperation,
    MOMENT_CATEGORY_IN_SESSION_BREAK,
    MOMENT_CATEGORY_IN_TRADING_TIME,
    MOMENT_CATEGORY_NON_TRADING_DAY,
    MOMENT_CATEGORY_NON_TRADING_TIME,
    MOMENT_CATEGORY_OUTSIDE_CALENDAR_COVERAGE,
    SegmentSpec,
)
from .calendar import SessionBreak, TradingCalendar, TradingSession
from .data_feed import HistoricalDataFeed
from .ledger import ClosedTrade, OpenPosition, PortfolioLedger
from .risk_integration import RiskIntegration
from .execution import (
    SIDE_BUY,
    SIDE_SELL,
    HistoricalExecutionSimulator,
    split_execution_deviation,
)
from .strategy_runner import StrategyRunner
from .event_engine import EventEngine
from .report import BacktestReportBuilder
from .engine import BacktestEngine

__all__ = [
    "AMBIGUITY_SL_TP_SAME_CANDLE",
    "BacktestEngine",
    "BacktestReportBuilder",
    "CALENDAR_SCHEMA",
    "CONFIRMED_GAP_CATEGORIES",
    "Candle",
    "CandleSeries",
    "ClosedTrade",
    "DataFeedError",
    "ENGINE_VERSION",
    "EngineConfig",
    "EngineConfigError",
    "EventEngine",
    "ExecutionError",
    "GapIncident",
    "GAP_CATEGORY_CONFIRMED_EXPECTED_CANDLE_MISSING",
    "GAP_CATEGORY_IRREGULAR_SPACING",
    "GAP_CATEGORY_NON_TRADING_DAY",
    "GAP_CATEGORY_NON_TRADING_TIME",
    "GAP_CATEGORY_SESSION_BREAK",
    "GAP_CATEGORY_UNVERIFIED_NO_CALENDAR",
    "GAP_CATEGORY_UNVERIFIED_OUTSIDE_CALENDAR_COVERAGE",
    "GAP_VERIFICATION_FULL",
    "GAP_VERIFICATION_LIMITED_NO_CALENDAR",
    "GAP_VERIFICATION_NOT_PERFORMED_INTERVAL_UNSET",
    "GAP_VERIFICATION_PARTIAL",
    "HistoricalDataFeed",
    "HistoricalEngineError",
    "HistoricalExecutionSimulator",
    "JournalEvent",
    "LedgerError",
    "LedgerOperation",
    "MOMENT_CATEGORY_IN_SESSION_BREAK",
    "MOMENT_CATEGORY_IN_TRADING_TIME",
    "MOMENT_CATEGORY_NON_TRADING_DAY",
    "MOMENT_CATEGORY_NON_TRADING_TIME",
    "MOMENT_CATEGORY_OUTSIDE_CALENDAR_COVERAGE",
    "OpenPosition",
    "PortfolioLedger",
    "RiskIntegration",
    "SegmentSpec",
    "SessionBreak",
    "SIDE_BUY",
    "SIDE_SELL",
    "StrategyRunner",
    "TradingCalendar",
    "TradingSession",
    "split_execution_deviation",
]
