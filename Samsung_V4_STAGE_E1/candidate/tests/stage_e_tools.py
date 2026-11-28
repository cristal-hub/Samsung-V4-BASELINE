# tests/stage_e_tools.py
# SAMSUNG V4 — NEW STRATEGY ENGINE. STAGE E.
# Вспомогательный модуль ТЕСТОВ ЭТАПА E (не production-код, не test_*):
#   * детерминированные тестовые стратегии контракта Stage A
#     (AlwaysBuy, ScriptedSignal, RisingCloses);
#   * построители детерминированных серий свечей;
#   * сборщик стандартной конфигурации симуляции.
# Все данные — офлайн, синтетика; никакой сети и брокера.

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Mapping, Optional, Tuple

import strategy_api
from strategy_api import (
    EntrySignalInput,
    ParamSpec,
    ParamType,
    Signal,
    SignalDirection,
    Strategy,
    StrategyConfig,
    compute_config_hash,
)

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from historical_engine import (  # noqa: E402
    BacktestEngine,
    Candle,
    EngineConfig,
    HistoricalDataFeed,
)

TEST_FIGI = "TESTFIGI1"
TEST_TICKER = "TEST"


def make_candles(specs: List[Mapping[str, float]],
                 *,
                 start: Optional[datetime] = None,
                 interval_seconds: int = 60) -> List[Candle]:
    """Свечи из явных спецификаций {o, h, l, c, v} (детерминированные)."""
    base = start or datetime(2024, 1, 2, 10, 0, tzinfo=timezone.utc)
    candles: List[Candle] = []
    for i, spec in enumerate(specs):
        candles.append(Candle(
            timestamp=base + timedelta(seconds=i * interval_seconds),
            open=float(spec["o"]),
            high=float(spec["h"]),
            low=float(spec["l"]),
            close=float(spec["c"]),
            volume=float(spec.get("v", 1000.0)),
        ))
    return candles


def flat_candles(count: int, *, price: float = 100.0) -> List[Candle]:
    """Ровная серия без касания стопов/целей (для управляемых сценариев)."""
    half = price * 0.001
    return make_candles([
        {"o": price, "h": price + half, "l": price - half,
         "c": price, "v": 1000.0}
        for _ in range(count)])


class AlwaysBuyStrategy(Strategy):
    """Детерминированная стратегия: всегда BUY (для сценариев входа)."""

    strategy_id = "stage_e_always_buy"
    strategy_version = "1.0.0"

    def param_specs(self) -> Tuple[ParamSpec, ...]:
        return (ParamSpec(name="warmup", param_type=ParamType.INT,
                          minimum=1),)

    def evaluate_entry(self, signal_input: EntrySignalInput,
                       config: StrategyConfig) -> Signal:
        return Signal(strategy_id=self.strategy_id,
                      config_hash=config.config_hash,
                      direction=SignalDirection.BUY,
                      reason="TEST_ALWAYS_BUY",
                      figi=signal_input.figi,
                      ticker=signal_input.ticker)


class ScriptedSignalStrategy(Strategy):
    """Сценарная стратегия: направление задаётся по ИНДЕКСУ СВЕЧИ.

    script — отображение индекса свечи (0-based) в направление;
    на индексах вне сценария — HOLD. Используется для управляемых
    проверок вход/выход; доступ к будущим данным не требуется.
    """

    strategy_id = "stage_e_scripted"
    strategy_version = "1.0.0"

    def __init__(self, script: Mapping[int, SignalDirection]) -> None:
        self._script = dict(script)

    def param_specs(self) -> Tuple[ParamSpec, ...]:
        return (ParamSpec(name="warmup", param_type=ParamType.INT,
                          minimum=1),)

    def evaluate_entry(self, signal_input: EntrySignalInput,
                       config: StrategyConfig) -> Signal:
        candles = signal_input.candles
        index = len(candles) - 1
        direction = self._script.get(index, SignalDirection.HOLD)
        return Signal(strategy_id=self.strategy_id,
                      config_hash=config.config_hash,
                      direction=direction,
                      reason=f"TEST_SCRIPTED_{direction.value}",
                      figi=signal_input.figi,
                      ticker=signal_input.ticker)


class RisingClosesStrategy(Strategy):
    """BUY после N подряд строго растущих закрытий; иначе HOLD.

    Считает ТОЛЬКО по переданному срезу (последние N close) — никакой
    внутренней истории между вызовами, доступ к будущему не нужен.
    """

    strategy_id = "stage_e_rising_closes"
    strategy_version = "1.0.0"

    def __init__(self, *, rises: int) -> None:
        self._rises = int(rises)

    def param_specs(self) -> Tuple[ParamSpec, ...]:
        return (
            ParamSpec(name="rises", param_type=ParamType.INT, minimum=1),
            ParamSpec(name="rises_declared", param_type=ParamType.INT,
                      minimum=1),
        )

    def evaluate_entry(self, signal_input: EntrySignalInput,
                       config: StrategyConfig) -> Signal:
        closes = list(signal_input.candles["close"])
        n = self._rises
        buy = len(closes) > n
        for k in range(1, n + 1):
            if not closes[-k] > closes[-k - 1]:
                buy = False
                break
        direction = SignalDirection.BUY if buy else SignalDirection.HOLD
        return Signal(strategy_id=self.strategy_id,
                      config_hash=config.config_hash,
                      direction=direction,
                      reason="TEST_RISING_CLOSES_BUY" if buy
                      else "TEST_RISING_CLOSES_HOLD",
                      figi=signal_input.figi,
                      ticker=signal_input.ticker)


class LookAheadSpyStrategy(Strategy):
    """Шпион look-ahead: записывает каждый вызов и размер переданного
    среза; опционально падает, если срез длиннее ожидаемого."""

    strategy_id = "stage_e_spy"
    strategy_version = "1.0.0"

    def __init__(self, *, delegate: Strategy) -> None:
        self._delegate = delegate
        self.calls: List[Dict[str, Any]] = []

    def param_specs(self) -> Tuple[ParamSpec, ...]:
        return self._delegate.param_specs()

    def evaluate_entry(self, signal_input: EntrySignalInput,
                       config: StrategyConfig) -> Signal:
        candles = signal_input.candles
        self.calls.append({
            "slice_length": len(candles),
            "last_timestamp": str(candles.index[-1]),
            "last_price": float(signal_input.last_price),
        })
        return self._delegate.evaluate_entry(signal_input, config)


def make_strategy_config(strategy: Strategy, params: Mapping[str, Any],
                         *, origin: str = "engine") -> StrategyConfig:
    """Валидированная StrategyConfig с корректным config_hash."""
    normalized = strategy.normalize_params(params)
    return StrategyConfig(
        strategy_id=strategy.strategy_id,
        strategy_version=strategy.strategy_version,
        params=normalized,
        config_hash=compute_config_hash(
            strategy.strategy_id, strategy.strategy_version, normalized),
        origin=origin,
    )


def make_engine_config(**overrides: Any) -> EngineConfig:
    """Стандартная конфигурация симуляции тестов (детерминированная)."""
    values: Dict[str, Any] = dict(
        figi=TEST_FIGI,
        ticker=TEST_TICKER,
        initial_cash=100000.0,
        commission_rate=0.001,
        slippage_rate=0.0005,
        stop_loss_fraction=0.02,
        take_profit_fraction=None,
        lot_size=10,
        contract_multiplier=1.0,
        risk_per_trade_fraction=0.01,
        max_position_notional_fraction=0.5,
    )
    values.update(overrides)
    return EngineConfig(**values)


def build_engine(strategy: Strategy, engine_config: EngineConfig,
                 candles: List[Candle], *,
                 strategy_config: Optional[StrategyConfig] = None):
    """Собранный (feed, engine) с валидированной конфигурацией."""
    config = strategy_config or make_strategy_config(
        strategy, {"warmup": 1, "rises": 2, "rises_declared": 2})
    feed = HistoricalDataFeed.from_candles(candles,
                                           engine_config=engine_config)
    engine = BacktestEngine(strategy=strategy,
                            strategy_config=config,
                            engine_config=engine_config,
                            feed=feed)
    return feed, engine, config
