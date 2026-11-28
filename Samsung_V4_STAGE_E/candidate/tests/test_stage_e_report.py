# tests/test_stage_e_report.py
# SAMSUNG V4 — NEW STRATEGY ENGINE. STAGE E.
# Тесты BacktestReport: итоговая статистика (Win Rate, Profit Factor,
# средняя прибыль/убыток, просадка), суммы издержек, гистограммы причин,
# канонический JSON и стабильный SHA-256 отчёта. Offline-only.

from __future__ import annotations

import json
import math

import pytest

from historical_engine import (
    BacktestEngine,
    BacktestReportBuilder,
    Candle,
    HistoricalDataFeed,
    PortfolioLedger,
)
from historical_engine.ledger import OpenPosition
from strategy_api import SignalDirection

from tests.stage_e_tools import (
    ScriptedSignalStrategy,
    flat_candles,
    make_candles,
    make_engine_config,
    make_strategy_config,
)


def _run(script, candles, **cfg_overrides):
    strategy = ScriptedSignalStrategy(script)
    config = make_strategy_config(strategy, {"warmup": 1})
    engine_config = make_engine_config(**cfg_overrides)
    # Допустимы и готовые Candle, и явные dict-спецификации {o,h,l,c};
    # все dict конвертируются ОДНИМ вызовом (сквозные метки времени).
    if all(isinstance(c, Candle) for c in candles):
        candle_objects = list(candles)
    else:
        candle_objects = make_candles(list(candles))
    feed = HistoricalDataFeed.from_candles(candle_objects,
                                           engine_config=engine_config)
    engine = BacktestEngine(strategy=strategy, strategy_config=config,
                            engine_config=engine_config, feed=feed)
    return engine.run_full()


def _ledger_with_trades(initial_cash: float) -> PortfolioLedger:
    """Ledger с тремя закрытыми сделками и нулевыми издержками:
    +100 (10 x 100 -> 110), -40 (10 x 100 -> 96), +60 (10 x 100 -> 106)."""
    ledger = PortfolioLedger(initial_cash=initial_cash, figi="TESTFIGI1")
    scenarios = [
        (100.0, 110.0),   # +100
        (100.0, 96.0),    # -40
        (100.0, 106.0),   # +60
    ]
    for k, (entry_price, exit_price) in enumerate(scenarios):
        ledger.open_position(position=OpenPosition(
            figi="TESTFIGI1", quantity=10, lot_size=10, lot_count=1,
            entry_exec_price=entry_price, entry_raw_price=entry_price,
            entry_timestamp_iso=f"2024-01-02T10:0{k}:00+00:00",
            stop_price=entry_price * 0.98, take_price=None,
            entry_notional=entry_price * 10, entry_commission=0.0,
            entry_slippage_cost=0.0, risk_policy_hash="a" * 64,
            sizing_reason_code="SIZED_LONG", contract_multiplier=1.0,
            decision_candle_index=2 * k, entry_candle_index=2 * k + 1),
            timestamp_iso=f"2024-01-02T10:0{k}:00+00:00")
        ledger.close_position(
            exit_exec_price=exit_price, exit_raw_price=exit_price,
            exit_commission=0.0, exit_slippage_cost=0.0,
            exit_type="PROTECTIVE_TAKE_PROFIT", exit_reason_code="TP",
            exit_timestamp_iso=f"2024-01-02T10:0{k + 5}:00+00:00",
            exit_candle_index=2 * k + 2)
    return ledger


def _build_report(ledger):
    strategy = ScriptedSignalStrategy({})
    config = make_strategy_config(strategy, {"warmup": 1})
    engine_config = make_engine_config()
    feed = HistoricalDataFeed.from_candles(
        flat_candles(8), engine_config=engine_config)
    run_summary = {
        "equity_curve": [
            {"candle_index": i, "timestamp": feed.candle(i).timestamp_iso,
             "close": feed.candle(i).close,
             "equity": 10120.0 if i == 7 else 10000.0,
             "drawdown_pct": 0.0, "position_open": False}
            for i in range(8)],
        "max_drawdown_pct": 0.0,
        "peak_equity": 10120.0,
        "unresolved_exit_pending": False,
        "unresolved_entry_pending": False,
    }
    builder = BacktestReportBuilder(
        segment_label="TEST", start_index=0, end_index=8, feed=feed,
        engine_config=engine_config, strategy_config=config,
        ledger=ledger, events=[], run_summary=run_summary)
    return builder.build()


# --- итоговая статистика (ручной контроль значений) ----------------------------

def test_profit_factor_win_rate_and_averages():
    ledger = _ledger_with_trades(10000.0)
    report = _build_report(ledger)
    stats = report["statistics"]
    trades = report["trades"]
    assert len(trades) == 3
    assert [t["pnl_net"] for t in trades] == [100.0, -40.0, 60.0]
    assert stats["total_trades"] == 3
    assert stats["winning_trades"] == 2
    assert stats["losing_trades"] == 1
    assert stats["win_rate"] == 2 / 3
    assert stats["gross_profit_net"] == 160.0
    assert stats["gross_loss_net"] == 40.0
    assert stats["profit_factor"] == 160.0 / 40.0
    assert stats["average_win_net"] == 80.0
    assert stats["average_loss_net"] == -40.0
    assert stats["average_trade_pnl_net"] == 40.0
    assert stats["total_pnl_net"] == 120.0
    # Денежный баланс: initial + realized.
    assert report["account"]["final_cash"] == 10120.0
    assert report["account"]["final_equity"] == 10120.0


def test_profit_factor_undefined_without_losing_trades():
    ledger = PortfolioLedger(initial_cash=10000.0, figi="TESTFIGI1")
    ledger.open_position(position=OpenPosition(
        figi="TESTFIGI1", quantity=10, lot_size=10, lot_count=1,
        entry_exec_price=100.0, entry_raw_price=100.0,
        entry_timestamp_iso="2024-01-02T10:00:00+00:00",
        stop_price=98.0, take_price=None, entry_notional=1000.0,
        entry_commission=0.0, entry_slippage_cost=0.0,
        risk_policy_hash="a" * 64, sizing_reason_code="SIZED_LONG",
        contract_multiplier=1.0, decision_candle_index=0,
        entry_candle_index=1), timestamp_iso="2024-01-02T10:00:00+00:00")
    ledger.close_position(exit_exec_price=110.0, exit_raw_price=110.0,
                          exit_commission=0.0, exit_slippage_cost=0.0,
                          exit_type="PROTECTIVE_TAKE_PROFIT",
                          exit_reason_code="TP",
                          exit_timestamp_iso="2024-01-02T10:01:00+00:00",
                          exit_candle_index=2)
    report = _build_report(ledger)
    stats = report["statistics"]
    assert stats["losing_trades"] == 0
    assert stats["profit_factor"] is None
    assert stats["profit_factor_note"] == \
        "PROFIT_FACTOR_UNDEFINED_NO_LOSSING_TRADES"
    assert stats["win_rate"] == 1.0


def test_no_trades_statistics_are_honest_nulls():
    script = {0: SignalDirection.SELL}   # при плече flat: вход запрещён
    candles = make_candles([
        {"o": 100.0, "h": 100.2, "l": 99.8, "c": 100.0},
        {"o": 100.0, "h": 100.2, "l": 99.8, "c": 100.0},
    ])
    report = _run(script, candles)
    stats = report["statistics"]
    assert stats["total_trades"] == 0
    assert stats["win_rate"] is None
    assert stats["profit_factor"] is None
    assert stats["profit_factor_note"] == "PROFIT_FACTOR_UNDEFINED_NO_TRADES"
    assert stats["average_win_net"] is None
    assert stats["average_loss_net"] is None


# --- просадка и доходность -------------------------------------------------------

def test_max_drawdown_consistent_with_equity_curve():
    script = {0: SignalDirection.BUY, 3: SignalDirection.SELL}
    candles = [
        {"o": 100.0, "h": 100.2, "l": 99.8, "c": 100.0},
        {"o": 100.0, "h": 100.2, "l": 99.8, "c": 100.0},
        {"o": 95.0, "h": 95.2, "l": 94.8, "c": 95.0},   # падение отметки
        {"o": 95.0, "h": 95.2, "l": 94.8, "c": 95.0},
        {"o": 96.0, "h": 96.2, "l": 95.8, "c": 96.0},
        {"o": 96.0, "h": 96.2, "l": 95.8, "c": 96.0},
    ]
    report = _run(script, make_candles(candles), commission_rate=0.0,
                  slippage_rate=0.0, stop_loss_fraction=0.5)
    curve = report["equity_curve"]
    assert len(curve) == 6
    peak = curve[0]["equity"]
    max_dd = 0.0
    for point in curve:
        peak = max(peak, point["equity"])
        dd = (peak - point["equity"]) / peak * 100.0 if peak > 0 else 0.0
        max_dd = max(max_dd, dd)
        assert point["drawdown_pct"] == dd
    assert report["account"]["max_drawdown_pct"] == max_dd
    assert report["account"]["max_drawdown_pct"] > 0.0


def test_total_return_and_buy_hold_benchmark_present():
    script = {0: SignalDirection.BUY, 3: SignalDirection.SELL}
    candles = [
        {"o": 100.0, "h": 100.2, "l": 99.8, "c": 100.0},
        {"o": 100.0, "h": 100.2, "l": 99.8, "c": 100.0},
        {"o": 100.0, "h": 100.2, "l": 99.8, "c": 100.0},
        {"o": 100.0, "h": 100.2, "l": 99.8, "c": 100.0},
        {"o": 110.0, "h": 110.2, "l": 109.8, "c": 110.0},
        {"o": 110.0, "h": 110.2, "l": 109.8, "c": 110.0},
    ]
    report = _run(script, make_candles(candles), commission_rate=0.0,
                  slippage_rate=0.0, stop_loss_fraction=0.5)
    final_equity = report["account"]["final_equity"]
    expected_return = (final_equity - 100000.0) / 100000.0 * 100.0
    assert report["account"]["total_return_pct"] == expected_return
    # Buy&hold-бенчмарк по ценам: (110 - 100) / 100 * 100 = 10%
    assert report["account"]["buy_hold_price_return_pct"] == 10.0


# --- причины входов и выходов ------------------------------------------------------

def test_exit_and_entry_reason_histograms():
    script = {0: SignalDirection.BUY}
    candles = [
        {"o": 100.0, "h": 100.2, "l": 99.8, "c": 100.0},
        {"o": 100.0, "h": 100.2, "l": 99.8, "c": 100.0},
        {"o": 99.0, "h": 99.2, "l": 97.0, "c": 97.5},   # SL
    ]
    report = _run(script, make_candles(candles))
    assert report["reasons"]["exit_reasons"].get(
        "PROTECTIVE_STOP_LOSS:SL_TOUCHED") == 1
    assert report["reasons"]["entry_decision_reasons"].get(
        "ENTRY_SIGNAL_BUY") == 1


# --- канонический JSON и SHA-256 ----------------------------------------------------

def test_report_json_is_canonical_and_hash_stable():
    script = {0: SignalDirection.BUY, 2: SignalDirection.SELL}
    candles = [
        {"o": 100.0, "h": 100.2, "l": 99.8, "c": 100.0},
        {"o": 100.0, "h": 100.2, "l": 99.8, "c": 100.0},
        {"o": 100.0, "h": 100.2, "l": 99.8, "c": 100.0},
        {"o": 101.0, "h": 101.2, "l": 100.8, "c": 101.0},
    ]
    report = _run(script, candles)
    from historical_engine.models import canonical_json, sha256_hex
    # Хеш покрывает отчёт БЕЗ полей report_sha256 (зеркало report.py).
    payload = dict(report)
    payload.pop("report_sha256")
    metadata = dict(payload["metadata"])
    metadata.pop("report_sha256")
    payload["metadata"] = metadata
    assert sha256_hex(canonical_json(payload)) == report["report_sha256"]
    # Отчёт сериализуем без NaN/Infinity (allow_nan=False не падает).
    json.loads(canonical_json(report))
    # Повторный прогон — идентичные байты отчёта.
    report_2 = _run(script, candles)
    assert canonical_json(report_2) == canonical_json(report)


def test_report_contains_no_nan_or_infinity():
    script = {0: SignalDirection.BUY, 2: SignalDirection.SELL}
    candles = [
        {"o": 100.0, "h": 100.2, "l": 99.8, "c": 100.0},
        {"o": 100.0, "h": 100.2, "l": 99.8, "c": 100.0},
        {"o": 100.0, "h": 100.2, "l": 99.8, "c": 100.0},
        {"o": 101.0, "h": 101.2, "l": 100.8, "c": 101.0},
    ]
    report = _run(script, candles)
    from historical_engine.models import canonical_json
    payload = canonical_json(report)
    assert "NaN" not in payload
    assert "Infinity" not in payload


# --- атрибуция сделок и история операций ---------------------------------------------

def test_trade_records_carry_attribution_and_costs():
    script = {0: SignalDirection.BUY, 2: SignalDirection.SELL}
    candles = [
        {"o": 100.0, "h": 100.2, "l": 99.8, "c": 100.0},
        {"o": 100.0, "h": 100.2, "l": 99.8, "c": 100.0},
        {"o": 100.0, "h": 100.2, "l": 99.8, "c": 100.0},
        {"o": 101.0, "h": 101.2, "l": 100.8, "c": 101.0},
    ]
    report = _run(script, candles)
    trade = report["trades"][0]
    assert trade["figi"] == "TESTFIGI1"
    assert len(trade["risk_policy_hash"]) == 64
    assert trade["sizing_reason_code"] == "SIZED_LONG"
    assert trade["lot_size"] == 10
    assert trade["lot_count"] == trade["quantity"] // 10
    assert trade["entry_commission"] > 0.0
    assert trade["exit_commission"] > 0.0
    assert trade["entry_slippage_cost"] > 0.0
    assert trade["exit_slippage_cost"] > 0.0
    assert trade["exit_type"] == "STRATEGIC_SELL_SIGNAL"
    metadata = report["metadata"]
    assert metadata["strategy_id"] == "stage_e_scripted"
    assert len(metadata["strategy_config_hash"]) == 64
    assert metadata["engine_version"].startswith("historical_engine_")
    assert report["report_schema"] == "samsung_v4_stage_e_report_v1"
    assert metadata["risk_policy_hash"] == trade["risk_policy_hash"]


def test_ledger_operations_history_recorded():
    script = {0: SignalDirection.BUY, 2: SignalDirection.SELL}
    candles = [
        {"o": 100.0, "h": 100.2, "l": 99.8, "c": 100.0},
        {"o": 100.0, "h": 100.2, "l": 99.8, "c": 100.0},
        {"o": 100.0, "h": 100.2, "l": 99.8, "c": 100.0},
        {"o": 101.0, "h": 101.2, "l": 100.8, "c": 101.0},
    ]
    report = _run(script, candles)
    operations = report["ledger_operations"]
    assert [op["kind"] for op in operations] == \
        ["ENTRY_EXECUTED", "EXIT_EXECUTED"]
    assert operations[0]["op_index"] < operations[1]["op_index"]
    assert operations[1]["realized_pnl_net"] == report["trades"][0]["pnl_net"]
