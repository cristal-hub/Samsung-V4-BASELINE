# historical_engine/__init__.py
# SAMSUNG V4 — NEW STRATEGY ENGINE. STAGE E.
# ДЕТЕРМИНИРОВАННЫЙ ИСТОРИЧЕСКИЙ СИМУЛЯТОР (STRICT RESEARCH ONLY).
#
# Только исторические данные, только виртуальная симуляция; никаких
# реальных ордеров, Sandbox/LIVE, брокерских SDK и сетевых запросов.
# Модуль не изменяет Stage A/B/C/D и legacy Samsung V4.
#
# Компоненты (ТЗ Stage E §3):
#   HistoricalDataFeed            — хронологическая подача закрытых свечей,
#                                   контроль пропусков, без будущего;
#   EventEngine                   — детерминированные фазы обработки;
#   StrategyRunner                — вызов контрактов Stage A/C;
#   HistoricalExecutionSimulator  — виртуальное исполнение, издержки;
#   RiskIntegration               — размер позиции СТРОГО через Stage D;
#   PortfolioLedger               — виртуальный портфель и PnL;
#   BacktestReport                — детерминированный отчёт + SHA-256.

from .models import (
    AMBIGUITY_SL_TP_SAME_CANDLE,
    Candle,
    CandleSeries,
    DataFeedError,
    ENGINE_VERSION,
    EngineConfig,
    EngineConfigError,
    ExecutionError,
    HistoricalEngineError,
    JournalEvent,
    LedgerError,
    LedgerOperation,
    SegmentSpec,
)
from .data_feed import HistoricalDataFeed
from .ledger import ClosedTrade, OpenPosition, PortfolioLedger
from .risk_integration import RiskIntegration
from .execution import HistoricalExecutionSimulator
from .strategy_runner import StrategyRunner
from .event_engine import EventEngine
from .report import BacktestReportBuilder
from .engine import BacktestEngine

__all__ = [
    "AMBIGUITY_SL_TP_SAME_CANDLE",
    "BacktestEngine",
    "BacktestReportBuilder",
    "Candle",
    "CandleSeries",
    "ClosedTrade",
    "DataFeedError",
    "ENGINE_VERSION",
    "EngineConfig",
    "EngineConfigError",
    "EventEngine",
    "ExecutionError",
    "HistoricalDataFeed",
    "HistoricalEngineError",
    "HistoricalExecutionSimulator",
    "JournalEvent",
    "LedgerError",
    "LedgerOperation",
    "OpenPosition",
    "PortfolioLedger",
    "RiskIntegration",
    "SegmentSpec",
    "StrategyRunner",
]
