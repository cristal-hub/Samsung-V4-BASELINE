# tests/test_stage_e_execution_ledger.py
# SAMSUNG V4 — NEW STRATEGY ENGINE. STAGE E.
# Тесты модели исполнения и виртуального портфеля: slippage, комиссии,
# Stop Loss, Take Profit, конфликт SL/TP внутри одной свечи, гэпы,
# размер лота, недостаточный капитал / покупательная способность,
# инварианты PortfolioLedger, LONG/SHORT (ТЗ Stage E §9). Offline-only.

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from historical_engine import (
    BacktestEngine,
    Candle,
    EngineConfigError,
    LedgerError,
    PortfolioLedger,
    RiskIntegration,
    AMBIGUITY_SL_TP_SAME_CANDLE,
)
from historical_engine.execution import HistoricalExecutionSimulator
from strategy_api import compute_config_hash, SignalDirection
from strategy_risk import SizingOutcome, TradeSide

from tests.stage_e_tools import (
    AlwaysBuyStrategy,
    ScriptedSignalStrategy,
    flat_candles,
    make_candles,
    make_engine_config,
    make_strategy_config,
)

SLIP = 0.0005
COMM = 0.001
SL = 0.02
TP = 0.03


def _run(candles, **cfg_overrides):
    strategy = AlwaysBuyStrategy()
    config = make_strategy_config(strategy, {"warmup": 1})
    engine_config = make_engine_config(**cfg_overrides)
    from historical_engine import HistoricalDataFeed
    feed = HistoricalDataFeed.from_candles(candles,
                                           engine_config=engine_config)
    engine = BacktestEngine(strategy=strategy, strategy_config=config,
                            engine_config=engine_config, feed=feed)
    return engine.run_full()


# --- slippage и диапазон свечи --------------------------------------------------

def test_buy_slippage_adverse_and_bounded_by_high():
    candles = flat_candles(4, price=100.0)
    report = _run(candles, take_profit_fraction=None)
    entry = report["trades"][0] if report["trades"] else None
    # Позиция не закрывается (AlwaysBuy) — берём из операций.
    op_entry = [op for op in report["ledger_operations"]
                if op["kind"] == "ENTRY_EXECUTED"][0]
    expected_exec = 100.0 * (1.0 + SLIP)
    assert expected_exec <= candles[1].high
    assert op_entry["price"] == expected_exec
    assert op_entry["price"] <= candles[1].high


def test_buy_slippage_capped_by_candle_high():
    # open=100, но high=100.02 < open*(1+slip)=100.05: исполнение по high.
    candles = make_candles([
        {"o": 100.0, "h": 100.05, "l": 99.95, "c": 100.0},
        {"o": 100.0, "h": 100.02, "l": 99.9, "c": 100.0},
        {"o": 100.0, "h": 100.05, "l": 99.95, "c": 100.0},
    ])
    report = _run(candles)
    op_entry = [op for op in report["ledger_operations"]
                if op["kind"] == "ENTRY_EXECUTED"][0]
    assert op_entry["price"] == 100.02   # cap по high, не выше диапазона


def test_sell_slippage_adverse_and_bounded_by_low():
    script = {0: SignalDirection.BUY, 3: SignalDirection.SELL}
    strategy = ScriptedSignalStrategy(script)
    config = make_strategy_config(strategy, {"warmup": 1})
    candles = make_candles([
        {"o": 100.0, "h": 100.1, "l": 99.9, "c": 100.0},
        {"o": 100.0, "h": 100.1, "l": 99.9, "c": 100.0},
        {"o": 100.0, "h": 100.1, "l": 99.9, "c": 100.0},
        {"o": 100.0, "h": 100.1, "l": 99.9, "c": 100.0},   # SELL на закрытии
        {"o": 100.0, "h": 100.04, "l": 99.97, "c": 100.0},  # исполнение
    ])
    engine_config = make_engine_config()
    from historical_engine import HistoricalDataFeed
    feed = HistoricalDataFeed.from_candles(candles,
                                           engine_config=engine_config)
    engine = BacktestEngine(strategy=strategy, strategy_config=config,
                            engine_config=engine_config, feed=feed)
    report = engine.run_full()
    assert len(report["trades"]) == 1
    trade = report["trades"][0]
    # open=100.0; sell: 100.0*(1-slip)=99.95 > low=99.97? НЕТ: 99.95 < 99.97
    # -> cap снизу: исполнение по low=99.97 (внутри диапазона свечи).
    assert trade["exit_exec_price"] == 99.97
    assert trade["exit_type"] == "STRATEGIC_SELL_SIGNAL"


# --- комиссии ---------------------------------------------------------------------

def test_commissions_charged_on_both_sides():
    script = {0: SignalDirection.BUY, 3: SignalDirection.SELL}
    strategy = ScriptedSignalStrategy(script)
    config = make_strategy_config(strategy, {"warmup": 1})
    candles = make_candles([
        {"o": 100.0, "h": 100.2, "l": 99.8, "c": 100.0},
        {"o": 100.0, "h": 100.2, "l": 99.8, "c": 100.0},
        {"o": 100.0, "h": 100.2, "l": 99.8, "c": 100.0},
        {"o": 100.0, "h": 100.2, "l": 99.8, "c": 100.0},
        {"o": 100.0, "h": 100.2, "l": 99.8, "c": 100.0},
    ])
    engine_config = make_engine_config()
    from historical_engine import HistoricalDataFeed
    feed = HistoricalDataFeed.from_candles(candles,
                                           engine_config=engine_config)
    engine = BacktestEngine(strategy=strategy, strategy_config=config,
                            engine_config=engine_config, feed=feed)
    report = engine.run_full()
    trade = report["trades"][0]
    exec_entry = 100.0 * (1.0 + SLIP)
    exec_exit = max(100.0 * (1.0 - SLIP), 99.8)   # cap свечи не срабатывает
    quantity = trade["quantity"]
    # Зеркальные формулы движка (тот же порядок float-операций):
    entry_notional = exec_entry * quantity
    exit_notional = exec_exit * quantity
    expected_entry_comm = COMM * entry_notional
    expected_exit_comm = COMM * exit_notional
    assert trade["entry_commission"] == expected_entry_comm
    assert trade["exit_commission"] == expected_exit_comm
    assert report["costs"]["total_commission"] == \
        trade["entry_commission"] + trade["exit_commission"]
    assert report["costs"]["total_slippage_cost"] == \
        trade["entry_slippage_cost"] + trade["exit_slippage_cost"]
    expected_net = (exit_notional - expected_exit_comm) \
        - (entry_notional + expected_entry_comm)
    assert trade["pnl_net"] == expected_net


# --- Stop Loss / Take Profit --------------------------------------------------------

def test_stop_loss_exit_at_stop_price_with_slippage():
    candles = make_candles([
        {"o": 100.0, "h": 100.1, "l": 99.9, "c": 100.0},
        {"o": 100.0, "h": 100.1, "l": 99.9, "c": 100.0},   # вход по open
        {"o": 99.0, "h": 99.5, "l": 97.0, "c": 97.5},      # low <= стоп
    ])
    report = _run(candles)
    assert len(report["trades"]) == 1
    trade = report["trades"][0]
    exec_entry = 100.0 * (1.0 + SLIP)
    stop = exec_entry * (1.0 - SL)
    expected_exit = max(stop * (1.0 - SLIP), 97.0)  # cap свечи не срабатывает
    assert trade["exit_type"] == "PROTECTIVE_STOP_LOSS"
    assert trade["exit_exec_price"] == expected_exit
    assert trade["pnl_net"] < 0.0
    assert trade["entry_candle_index"] == 1
    assert trade["exit_candle_index"] == 2


def test_stop_loss_gap_through_stop_executes_at_open():
    candles = make_candles([
        {"o": 100.0, "h": 100.1, "l": 99.9, "c": 100.0},
        {"o": 100.0, "h": 100.1, "l": 99.9, "c": 100.0},
        {"o": 95.0, "h": 96.0, "l": 94.5, "c": 95.5},  # open ниже стопа
    ])
    report = _run(candles)
    trade = report["trades"][0]
    exec_entry = 100.0 * (1.0 + SLIP)
    stop = exec_entry * (1.0 - SL)
    assert stop > 95.0            # гэп вниз за стоп
    expected_exit = max(95.0 * (1.0 - SLIP), 94.5)  # cap не срабатывает
    assert trade["exit_type"] == "PROTECTIVE_STOP_LOSS"
    assert trade["exit_exec_price"] == expected_exit
    assert trade["exit_exec_price"] < stop   # хуже стопа: честный гэп
    assert trade["exit_reason_code"] == "SL_GAP_THROUGH_STOP"


def test_take_profit_exit_at_target_price_with_slippage():
    candles = make_candles([
        {"o": 100.0, "h": 100.1, "l": 99.9, "c": 100.0},
        {"o": 100.0, "h": 100.1, "l": 99.9, "c": 100.0},
        {"o": 102.0, "h": 104.0, "l": 101.5, "c": 103.2},  # high >= цель
    ])
    report = _run(candles, take_profit_fraction=TP)
    trade = report["trades"][0]
    exec_entry = 100.0 * (1.0 + SLIP)
    target = exec_entry * (1.0 + TP)
    expected_exit = max(target * (1.0 - SLIP), 101.5)  # cap не срабатывает
    assert trade["exit_type"] == "PROTECTIVE_TAKE_PROFIT"
    assert trade["exit_exec_price"] == expected_exit
    assert trade["pnl_net"] > 0.0


def test_sl_and_tp_same_candle_conservative_sl_wins():
    candles = make_candles([
        {"o": 100.0, "h": 100.1, "l": 99.9, "c": 100.0},
        {"o": 100.0, "h": 100.1, "l": 99.9, "c": 100.0},
        # и low <= стоп (98.049), и high >= цель (103.0515)
        {"o": 101.0, "h": 104.0, "l": 97.5, "c": 100.0},
    ])
    report = _run(candles, take_profit_fraction=TP)
    trade = report["trades"][0]
    exec_entry = 100.0 * (1.0 + SLIP)
    stop = exec_entry * (1.0 - SL)
    target = exec_entry * (1.0 + TP)
    assert stop > 97.5 and target < 104.0   # оба уровня в свече
    assert trade["exit_type"] == "PROTECTIVE_STOP_LOSS"
    assert AMBIGUITY_SL_TP_SAME_CANDLE in trade["ambiguity_flags"]
    assert report["ambiguity_incidents"] == 1


def test_no_stop_touch_no_exit():
    candles = make_candles([
        {"o": 100.0, "h": 100.1, "l": 99.9, "c": 100.0},
        {"o": 100.0, "h": 100.1, "l": 99.9, "c": 100.0},
        {"o": 99.5, "h": 100.0, "l": 99.0, "c": 99.5},  # low > стопа
    ])
    report = _run(candles)
    assert len(report["trades"]) == 0
    assert report["account"]["open_position_at_end"] is not None


# --- размер лота и границы лимитов (через Stage D) ------------------------------------

def _sizing_for(cash, **cfg_overrides):
    engine_config = make_engine_config(**cfg_overrides)
    strategy = AlwaysBuyStrategy()
    config = make_strategy_config(strategy, {"warmup": 1})
    risk = RiskIntegration(engine_config=engine_config,
                           strategy_config=config)
    entry_price = 100.0 * (1.0 + SLIP)
    return risk, risk.size_entry(execution_price=entry_price, cash=cash)


def test_lot_flooring_quantity_multiple_of_lot():
    risk, result = _sizing_for(100000.0)
    assert result.outcome is SizingOutcome.SIZED
    assert result.quantity % 10 == 0
    assert result.quantity == 450
    assert result.lot_count == 45


def test_risk_budget_exactly_one_lot_sized():
    # equity=2200: budget=22; risk/unit=2.199099 -> 10 единиц -> ровно 1 лот
    risk, result = _sizing_for(2200.0)
    assert result.outcome is SizingOutcome.SIZED
    assert result.quantity == 10
    assert result.lot_count == 1


def test_risk_budget_slightly_below_one_lot_zero_size():
    # equity=2190: budget=21.9 -> 9 единиц -> меньше лота -> ZERO_SIZE
    risk, result = _sizing_for(2190.0)
    assert result.outcome is SizingOutcome.ZERO_SIZE
    assert result.quantity == 0
    assert result.reason_code == "RISK_BUDGET_BELOW_ONE_LOT"


def test_notional_cap_boundary_exactly_one_lot():
    # cap = 2100*0.5 = 1050; 1050/100.05 -> 10 единиц -> 1 лот
    risk, result = _sizing_for(2100.0, risk_per_trade_fraction=0.05)
    assert result.outcome is SizingOutcome.SIZED
    assert result.quantity == 10
    diagnostics = dict(result.diagnostics)
    assert diagnostics["units_by_notional"] == 10


def test_notional_cap_slightly_below_one_lot_zero_size():
    # cap = 2090*0.5 = 1045; 1045/100.05 -> 10.44 -> 10? НЕТ:
    # floor(1045/100.05) = 10 -> 1 лот; берём 2000: 1000/100.05 -> 9
    risk, result = _sizing_for(2000.0, risk_per_trade_fraction=0.05)
    assert result.outcome is SizingOutcome.ZERO_SIZE
    assert result.reason_code == "NOTIONAL_CAP_BELOW_ONE_LOT"


def test_buying_power_boundary_exactly_one_lot():
    # cash=1002: 1002/(100.05*1.001) -> 10.005 -> 10 единиц -> 1 лот
    risk, result = _sizing_for(1002.0, risk_per_trade_fraction=0.05,
                               max_position_notional_fraction=1.0)
    assert result.outcome is SizingOutcome.SIZED
    assert result.quantity == 10


def test_buying_power_slightly_below_one_lot_zero_size():
    # cash=1001: 1001/100.15005 -> 9.99 -> 9 единиц -> ZERO_SIZE
    risk, result = _sizing_for(1001.0, risk_per_trade_fraction=0.05,
                               max_position_notional_fraction=1.0)
    assert result.outcome is SizingOutcome.ZERO_SIZE
    assert result.reason_code == "BUYING_POWER_BELOW_ONE_LOT"


def test_buying_power_is_limiting_constraint_when_cap_is_full():
    risk, result = _sizing_for(100000.0, risk_per_trade_fraction=0.05,
                               max_position_notional_fraction=1.0)
    assert result.outcome is SizingOutcome.SIZED
    diagnostics = dict(result.diagnostics)
    units = min(diagnostics["units_by_risk"], diagnostics["units_by_notional"],
                diagnostics["units_by_buying_power"])
    assert diagnostics["units_by_buying_power"] == units
    assert result.quantity == units - units % 10


# --- недостаточный капитал / покупательная способность (движок) -------------------------

def test_insufficient_capital_blocks_entry_and_keeps_cash():
    candles = flat_candles(4, price=100.0)
    report = _run(candles, initial_cash=500.0)
    assert report["trades"] == []
    assert report["account"]["final_cash"] == 500.0
    # Решение о входе принимается на каждой свече при отсутствии позиции:
    # в серии из 4 свечей это 3 блокировки (индексы 0, 1, 2).
    assert report["reasons"]["blocked_entry_reasons"].get(
        "RISK_BUDGET_BELOW_ONE_LOT") == 3
    assert report["account"]["open_position_at_end"] is None


def test_insufficient_buying_power_blocks_entry():
    # cash=1001: Stage D возвращает ZERO_SIZE по покупательной способности
    candles = flat_candles(4, price=100.0)
    report = _run(candles, initial_cash=1001.0,
                  risk_per_trade_fraction=0.05,
                  max_position_notional_fraction=1.0)
    assert report["trades"] == []
    assert report["account"]["final_cash"] == 1001.0
    assert report["reasons"]["blocked_entry_reasons"].get(
        "BUYING_POWER_BELOW_ONE_LOT") == 3


def test_ledger_refuses_overdraft_fail_closed():
    ledger = PortfolioLedger(initial_cash=100.0, figi="TESTFIGI1")
    from historical_engine.ledger import OpenPosition
    position = OpenPosition(
        figi="TESTFIGI1", quantity=10, lot_size=10, lot_count=1,
        entry_exec_price=100.0, entry_raw_price=100.0,
        entry_timestamp_iso="2024-01-02T10:00:00+00:00",
        stop_price=98.0, take_price=None, entry_notional=1000.0,
        entry_commission=1.0, entry_slippage_cost=0.0,
        risk_policy_hash="a" * 64, sizing_reason_code="SIZED_LONG",
        contract_multiplier=1.0, decision_candle_index=0,
        entry_candle_index=1)
    with pytest.raises(LedgerError):
        ledger.open_position(position=position,
                             timestamp_iso="2024-01-02T10:01:00+00:00")
    assert ledger.cash == 100.0
    assert ledger.position is None


# --- инварианты PortfolioLedger --------------------------------------------------------

def test_ledger_cash_conservation_multiple_trades():
    ledger = PortfolioLedger(initial_cash=10000.0, figi="TESTFIGI1")
    from historical_engine.ledger import OpenPosition
    # Сделка 1: вход 100 x10, выход 110 -> +100 - комиссии (0 rate здесь)
    ledger.open_position(position=OpenPosition(
        figi="TESTFIGI1", quantity=10, lot_size=10, lot_count=1,
        entry_exec_price=100.0, entry_raw_price=100.0,
        entry_timestamp_iso="t1", stop_price=98.0, take_price=None,
        entry_notional=1000.0, entry_commission=0.0,
        entry_slippage_cost=0.0, risk_policy_hash="a" * 64,
        sizing_reason_code="SIZED_LONG", contract_multiplier=1.0,
        decision_candle_index=0, entry_candle_index=1),
        timestamp_iso="t1")
    ledger.close_position(exit_exec_price=110.0, exit_raw_price=110.0,
                          exit_commission=0.0, exit_slippage_cost=0.0,
                          exit_type="PROTECTIVE_TAKE_PROFIT",
                          exit_reason_code="TP",
                          exit_timestamp_iso="t2", exit_candle_index=3)
    # Сделка 2: вход 100 x10, выход 96 -> -40
    ledger.open_position(position=OpenPosition(
        figi="TESTFIGI1", quantity=10, lot_size=10, lot_count=1,
        entry_exec_price=100.0, entry_raw_price=100.0,
        entry_timestamp_iso="t3", stop_price=98.0, take_price=None,
        entry_notional=1000.0, entry_commission=0.0,
        entry_slippage_cost=0.0, risk_policy_hash="a" * 64,
        sizing_reason_code="SIZED_LONG", contract_multiplier=1.0,
        decision_candle_index=4, entry_candle_index=5),
        timestamp_iso="t3")
    trade = ledger.close_position(
        exit_exec_price=96.0, exit_raw_price=96.0,
        exit_commission=0.0, exit_slippage_cost=0.0,
        exit_type="PROTECTIVE_STOP_LOSS", exit_reason_code="SL",
        exit_timestamp_iso="t4", exit_candle_index=7)
    assert ledger.verify_cash_conservation() is None
    assert ledger.cash == 10000.0 + 100.0 - 40.0
    assert trade.pnl_net == -40.0
    assert len(ledger.closed_trades) == 2


def test_ledger_no_negative_cash_during_engine_run():
    candles = flat_candles(6, price=100.0)
    report = _run(candles, initial_cash=3000.0)
    for op in report["ledger_operations"]:
        assert op["cash_after"] >= 0.0


# --- LONG/SHORT -------------------------------------------------------------------------

def test_engine_requests_long_only_and_short_is_never_requested():
    engine_config = make_engine_config()
    strategy = AlwaysBuyStrategy()
    config = make_strategy_config(strategy, {"warmup": 1})
    risk = RiskIntegration(engine_config=engine_config,
                           strategy_config=config)
    # В конфигурации движка НЕТ параметра направления: long-only по
    # построению; Stage D подтверждает поддержку только LONG.
    assert not hasattr(engine_config, "side")
    assert TradeSide.SHORT in TradeSide.__members__.values()
    from strategy_risk import SUPPORTED_TRADE_SIDES
    assert SUPPORTED_TRADE_SIDES == (TradeSide.LONG,)


def test_short_sizing_request_explicitly_blocked_by_stage_d():
    # Прямая проверка: если бы SHORT был запрошен, Stage D вернул бы
    # блокирующий исход UNSUPPORTED_SIDE (движок никогда его не строит).
    from strategy_risk import SizingInput, calculate_position_size, \
        RiskPolicy
    from attribution import AttributionContext
    engine_config = make_engine_config()
    strategy = AlwaysBuyStrategy()
    config = make_strategy_config(strategy, {"warmup": 1})
    policy = RiskPolicy(strategy_id=config.strategy_id,
                        config_hash=config.config_hash,
                        risk_per_trade_fraction=0.01,
                        max_position_notional_fraction=0.5)
    sizing_input = SizingInput(
        attribution=AttributionContext.from_config(config),
        figi=engine_config.figi, side=TradeSide.SHORT,
        available_equity=100000.0, buying_power_limit=100000.0,
        entry_price=100.0, protective_stop_price=98.0, lot_size=10,
        contract_multiplier=1.0, entry_cost_per_unit=0.1,
        stop_exit_cost_per_unit=0.1)
    result = calculate_position_size(policy=policy, config=config,
                                     sizing_input=sizing_input)
    assert result.outcome is SizingOutcome.UNSUPPORTED_SIDE
    assert result.quantity == 0


def test_engine_config_invalid_values_rejected():
    with pytest.raises(EngineConfigError):
        make_engine_config(slippage_rate=1.0)
    with pytest.raises(EngineConfigError):
        make_engine_config(gap_policy="SILENT")
    with pytest.raises(EngineConfigError):
        make_engine_config(take_profit_fraction=0.0)
