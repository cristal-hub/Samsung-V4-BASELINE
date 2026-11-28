# tests/test_stage_e1_slippage.py
# SAMSUNG V4 — NEW STRATEGY ENGINE. STAGE E.1.
# Correction №2 — раздельный учёт проскальзывания и улучшения цены.
#
# 12 обязательных сценариев ТЗ E.1 §4.5 + дополнительные проверки
# обратной совместимости полей отчёта и детерминизма + FINAL CORRECTIONS
# (валидация конечности всех числовых аргументов split_execution_deviation
# через math.isfinite: NaN / ±Infinity / нули / отрицательные отклоняются).
# Только исторические синтетические данные, только оффлайн.

from __future__ import annotations

import math

import pytest

from historical_engine import (
    BacktestEngine,
    Candle,
    ExecutionError,
    HistoricalDataFeed,
    split_execution_deviation,
    SIDE_BUY,
    SIDE_SELL,
)
from tests.stage_e_tools import (
    AlwaysBuyStrategy,
    ScriptedSignalStrategy,
    make_candles,
    make_engine_config,
    make_strategy_config,
)
from strategy_api import SignalDirection

SLIP = 0.0005      # slippage_rate стандартной конфигурации
COMM = 0.001       # commission_rate стандартной конфигурации
SL = 0.02
TP = 0.05


def _run(candles, **cfg_overrides):
    strategy = AlwaysBuyStrategy()
    config = make_strategy_config(strategy, {"warmup": 1})
    engine_config = make_engine_config(**cfg_overrides)
    feed = HistoricalDataFeed.from_candles(candles,
                                           engine_config=engine_config)
    engine = BacktestEngine(strategy=strategy, strategy_config=config,
                            engine_config=engine_config, feed=feed)
    return engine.run_full()


def _run_scripted(candles, script, **cfg_overrides):
    strategy = ScriptedSignalStrategy(script)
    config = make_strategy_config(strategy, {"warmup": 1})
    engine_config = make_engine_config(**cfg_overrides)
    feed = HistoricalDataFeed.from_candles(candles,
                                           engine_config=engine_config)
    engine = BacktestEngine(strategy=strategy, strategy_config=config,
                            engine_config=engine_config, feed=feed)
    return engine.run_full()


def _entry_op(report):
    return [op for op in report["ledger_operations"]
            if op["kind"] == "ENTRY_EXECUTED"][0]


def _exit_op(report):
    return [op for op in report["ledger_operations"]
            if op["kind"] == "EXIT_EXECUTED"][0]


# 1. Неблагоприятное проскальзывание при покупке ------------------------------

def test_adverse_slippage_on_buy():
    candles = make_candles([
        {"o": 100.0, "h": 100.1, "l": 99.9, "c": 100.0},
        {"o": 100.0, "h": 100.1, "l": 99.9, "c": 100.0},   # вход по open
    ])
    report = _run(candles)
    op = _entry_op(report)
    quantity = op["quantity"]
    exec_price = 100.0 * (1.0 + SLIP)
    assert op["price"] == exec_price
    assert op["details"]["reference_price"] == 100.0
    # Порядок float-операций прежней модели сохранён.
    assert op["slippage_cost"] == \
        quantity * 1.0 * (exec_price - 100.0)
    assert op["slippage_cost"] > 0.0
    assert op["price_improvement"] == 0.0
    assert op["commission"] == COMM * (exec_price * quantity)
    assert op["cash_after"] == report["account"]["final_cash"]


# 2. Неблагоприятное проскальзывание при продаже --------------------------------

def test_adverse_slippage_on_sell():
    script = {0: SignalDirection.BUY, 3: SignalDirection.SELL}
    candles = make_candles([
        {"o": 100.0, "h": 100.1, "l": 99.9, "c": 100.0},
        {"o": 100.0, "h": 100.1, "l": 99.9, "c": 100.0},
        {"o": 100.0, "h": 100.1, "l": 99.9, "c": 100.0},
        {"o": 100.0, "h": 100.1, "l": 99.9, "c": 100.0},   # SELL на закрытии
        {"o": 100.0, "h": 100.1, "l": 99.0, "c": 100.0},   # исполнение
    ])
    report = _run_scripted(candles, script)
    op = _exit_op(report)
    trade = report["trades"][0]
    quantity = op["quantity"]
    exec_price = 100.0 * (1.0 - SLIP)     # cap свечи не срабатывает
    assert op["price"] == exec_price
    assert op["details"]["reference_price"] == 100.0
    assert op["slippage_cost"] == \
        quantity * 1.0 * (100.0 - exec_price)
    assert op["slippage_cost"] > 0.0
    assert op["price_improvement"] == 0.0
    assert trade["exit_slippage_cost"] == op["slippage_cost"]


# 3. Улучшение цены при покупке (направление-осознанная формула) ----------------

def test_price_improvement_on_buy_direction_aware_formula():
    # Покупка НИЖЕ reference — улучшение цены; НИЖЕ для продажи было бы
    # проскальзыванием. Формула учитывает направление сделки.
    adverse, improvement = split_execution_deviation(
        side=SIDE_BUY, reference_price=100.0, execution_price=99.9,
        quantity=10, contract_multiplier=1.0)
    assert adverse == 0.0
    assert improvement == pytest.approx(1.0)
    # Зеркальность: та же дельта (exec ниже ref) для ПРОДАЖИ — проскальзывание.
    sell_adverse, sell_improvement = split_execution_deviation(
        side=SIDE_SELL, reference_price=100.0, execution_price=99.9,
        quantity=10, contract_multiplier=1.0)
    assert sell_adverse == pytest.approx(1.0)
    assert sell_improvement == 0.0


# 4. Улучшение цены при продаже ---------------------------------------------------

def test_price_improvement_on_sell_direction_aware_formula():
    adverse, improvement = split_execution_deviation(
        side=SIDE_SELL, reference_price=100.0, execution_price=100.5,
        quantity=10, contract_multiplier=2.0)
    assert adverse == 0.0
    assert improvement == pytest.approx(10.0)
    # Обе величины неотрицательны при любой дельте.
    for side in (SIDE_BUY, SIDE_SELL):
        for ref, exe in ((100.0, 101.0), (100.0, 99.0), (100.0, 100.0)):
            a, i = split_execution_deviation(
                side=side, reference_price=ref, execution_price=exe,
                quantity=3, contract_multiplier=1.5)
            assert a >= 0.0 and i >= 0.0
            assert a == 0.0 or i == 0.0


# 5. Обычное исполнение без улучшения -----------------------------------------------

def test_normal_execution_without_improvement():
    script = {0: SignalDirection.BUY, 3: SignalDirection.SELL}
    candles = make_candles([
        {"o": 100.0, "h": 100.1, "l": 99.9, "c": 100.0},
        {"o": 100.0, "h": 100.1, "l": 99.9, "c": 100.0},
        {"o": 100.0, "h": 100.1, "l": 99.9, "c": 100.0},
        {"o": 100.0, "h": 100.1, "l": 99.9, "c": 100.0},   # SELL на закрытии
        {"o": 100.0, "h": 100.1, "l": 99.0, "c": 100.0},   # исполнение
    ])
    report = _run_scripted(candles, script)
    entry, exit_ = _entry_op(report), _exit_op(report)
    assert entry["price_improvement"] == 0.0
    assert exit_["price_improvement"] == 0.0
    assert entry["slippage_cost"] > 0.0
    assert exit_["slippage_cost"] > 0.0
    assert report["costs"]["total_favorable_price_improvement"] == 0.0


# 6. Исполнение выше TP после гэпа ---------------------------------------------------

def test_execution_above_take_profit_after_gap_up():
    candles = make_candles([
        {"o": 100.0, "h": 100.1, "l": 99.9, "c": 100.0},
        {"o": 100.0, "h": 100.1, "l": 99.9, "c": 100.0},   # вход по open
        # Гэп вверх: вся свеча выше уровня цели (high >= take, low > take).
        {"o": 110.0, "h": 112.0, "l": 109.0, "c": 111.0},
    ])
    report = _run(candles, take_profit_fraction=TP)
    trade = report["trades"][0]
    op = _exit_op(report)
    assert trade["exit_type"] == "PROTECTIVE_TAKE_PROFIT"
    quantity = trade["quantity"]
    entry_exec = 100.0 * (1.0 + SLIP)
    take = entry_exec * (1.0 + TP)
    # Исполнение: max(take*(1-slip), low=109) = 109 — ВЫШЕ цели (гэп).
    exec_price = max(take * (1.0 - SLIP), 109.0)
    assert exec_price == 109.0
    assert op["price"] == exec_price
    assert op["details"]["reference_price"] == take
    # Улучшение цены, а НЕ отрицательное проскальзывание.
    assert op["slippage_cost"] == 0.0
    assert op["price_improvement"] == quantity * 1.0 * (109.0 - take)
    assert op["price_improvement"] > 0.0
    assert trade["exit_slippage_cost"] == 0.0
    assert trade["exit_price_improvement"] == op["price_improvement"]
    # Сводные показатели отчёта разделены.
    costs = report["costs"]
    assert costs["total_favorable_price_improvement"] \
        == trade["exit_price_improvement"]
    assert costs["total_adverse_slippage_cost"] \
        == trade["entry_slippage_cost"]
    assert costs["total_adverse_slippage_cost"] > 0.0


# 7. Исполнение ниже SL после гэпа ----------------------------------------------------

def test_execution_below_stop_loss_after_gap_down():
    candles = make_candles([
        {"o": 100.0, "h": 100.1, "l": 99.9, "c": 100.0},
        {"o": 100.0, "h": 100.1, "l": 99.9, "c": 100.0},   # вход по open
        {"o": 95.0, "h": 96.0, "l": 94.5, "c": 95.5},      # гэп вниз за стоп
    ])
    report = _run(candles)
    trade = report["trades"][0]
    op = _exit_op(report)
    assert trade["exit_type"] == "PROTECTIVE_STOP_LOSS"
    assert trade["exit_reason_code"] == "SL_GAP_THROUGH_STOP"
    quantity = trade["quantity"]
    stop = (100.0 * (1.0 + SLIP)) * (1.0 - SL)
    exec_price = max(95.0 * (1.0 - SLIP), 94.5)
    # Reference = гэповое open (сырая цена операции), НЕ уровень стопа.
    assert op["details"]["reference_price"] == 95.0
    assert op["price"] == exec_price
    # Проскальзывание — только поверх гэпа; потери гэпа (стоп - open) —
    # рыночный риск и в slippage НЕ входят.
    assert op["slippage_cost"] == quantity * 1.0 * \
        (95.0 - exec_price)
    assert op["slippage_cost"] < quantity * 1.0 * (stop - exec_price)
    assert op["price_improvement"] == 0.0
    assert op["slippage_cost"] > 0.0


# 8. Нулевое проскальзывание ------------------------------------------------------------

def test_zero_slippage_configuration():
    script = {0: SignalDirection.BUY, 3: SignalDirection.SELL}
    candles = make_candles([
        {"o": 100.0, "h": 100.1, "l": 99.9, "c": 100.0},
        {"o": 100.0, "h": 100.1, "l": 99.9, "c": 100.0},
        {"o": 100.0, "h": 100.1, "l": 99.9, "c": 100.0},
        {"o": 100.0, "h": 100.1, "l": 99.9, "c": 100.0},   # SELL на закрытии
        {"o": 100.0, "h": 100.1, "l": 99.0, "c": 100.0},   # исполнение
    ])
    report = _run_scripted(candles, script, slippage_rate=0.0)
    entry, exit_ = _entry_op(report), _exit_op(report)
    assert entry["price"] == 100.0
    assert exit_["price"] == 100.0
    assert entry["slippage_cost"] == 0.0
    assert exit_["slippage_cost"] == 0.0
    assert entry["price_improvement"] == 0.0
    assert exit_["price_improvement"] == 0.0
    costs = report["costs"]
    assert costs["total_slippage_cost"] == 0.0
    assert costs["total_adverse_slippage_cost"] == 0.0
    assert costs["total_favorable_price_improvement"] == 0.0
    # Стоимость исполнения = только комиссия (документированное определение).
    assert costs["total_execution_cost"] == costs["total_commission"]
    assert costs["total_commission"] > 0.0


# 9. Корректность комиссии ------------------------------------------------------------------

def test_commission_correct_and_separate():
    script = {0: SignalDirection.BUY, 3: SignalDirection.SELL}
    candles = make_candles([
        {"o": 100.0, "h": 100.1, "l": 99.9, "c": 100.0},
        {"o": 100.0, "h": 100.1, "l": 99.9, "c": 100.0},
        {"o": 100.0, "h": 100.1, "l": 99.9, "c": 100.0},
        {"o": 100.0, "h": 100.1, "l": 99.9, "c": 100.0},   # SELL на закрытии
        {"o": 100.0, "h": 100.1, "l": 99.0, "c": 100.0},   # исполнение
    ])
    report = _run_scripted(candles, script)
    trade = report["trades"][0]
    quantity = trade["quantity"]
    entry_exec = 100.0 * (1.0 + SLIP)
    exit_exec = 100.0 * (1.0 - SLIP)
    # Зеркальные формулы движка (тот же порядок float-операций:
    # notional первым, комиссия от notional).
    entry_notional = entry_exec * quantity
    exit_notional = exit_exec * quantity
    assert trade["entry_commission"] == COMM * entry_notional
    assert trade["exit_commission"] == COMM * exit_notional
    costs = report["costs"]
    assert costs["total_commission"] == \
        trade["entry_commission"] + trade["exit_commission"]
    # Комиссия не смешивается с проскальзыванием/улучшением:
    # раздельные поля, раздельные суммы.
    assert costs["total_execution_cost"] == \
        costs["total_commission"] + costs["total_adverse_slippage_cost"]


# 10. Сохранение денежного инварианта ---------------------------------------------------------

def test_money_invariant_with_price_improvement():
    # Сценарий с улучшением цены (гэп вверх через TP) — инвариант денег.
    candles = make_candles([
        {"o": 100.0, "h": 100.1, "l": 99.9, "c": 100.0},
        {"o": 100.0, "h": 100.1, "l": 99.9, "c": 100.0},
        {"o": 110.0, "h": 112.0, "l": 109.0, "c": 111.0},
    ])
    report = _run(candles, take_profit_fraction=TP)
    trade = report["trades"][0]
    initial_cash = 100000.0
    # cash == initial + реализованный net-PnL закрытых сделок.
    expected_cash = initial_cash + report["statistics"]["total_pnl_net"]
    assert math.isclose(report["account"]["final_cash"], expected_cash,
                        rel_tol=1e-9, abs_tol=1e-9)
    assert math.isclose(report["account"]["final_equity"],
                        report["account"]["final_cash"], rel_tol=1e-9)
    # PnL отражает ФАКТИЧЕСКОЕ улучшенное исполнение (не цель).
    entry_exec = 100.0 * (1.0 + SLIP)
    quantity = trade["quantity"]
    expected_gross = (109.0 - entry_exec) * quantity
    assert math.isclose(trade["pnl_gross"], expected_gross,
                        rel_tol=1e-9, abs_tol=1e-9)


# 11. Корректность итогового PnL ----------------------------------------------------------------

def test_final_pnl_correctness():
    script = {0: SignalDirection.BUY, 3: SignalDirection.SELL}
    candles = make_candles([
        {"o": 100.0, "h": 100.1, "l": 99.9, "c": 100.0},
        {"o": 100.0, "h": 100.1, "l": 99.9, "c": 100.0},
        {"o": 100.0, "h": 100.1, "l": 99.9, "c": 100.0},
        {"o": 100.0, "h": 100.1, "l": 99.9, "c": 100.0},   # SELL на закрытии
        {"o": 100.0, "h": 100.1, "l": 99.0, "c": 100.0},   # исполнение
    ])
    report = _run_scripted(candles, script)
    trade = report["trades"][0]
    quantity = trade["quantity"]
    entry_exec = 100.0 * (1.0 + SLIP)
    exit_exec = 100.0 * (1.0 - SLIP)
    entry_notional = entry_exec * quantity
    exit_notional = exit_exec * quantity
    expected_net = (exit_notional - trade["exit_commission"]) \
        - (entry_notional + trade["entry_commission"])
    assert math.isclose(trade["pnl_net"], expected_net,
                        rel_tol=1e-9, abs_tol=1e-9)
    assert math.isclose(trade["pnl_gross"],
                        (exit_exec - entry_exec) * quantity,
                        rel_tol=1e-9, abs_tol=1e-9)
    assert math.isclose(
        report["statistics"]["total_pnl_net"], trade["pnl_net"],
        rel_tol=1e-9, abs_tol=1e-9)


# 12. Отсутствие отрицательных расходов на проскальзывание -------------------------------

def test_no_negative_slippage_expenses_anywhere():
    # Сценарий SL + сценарий TP-гэпа: во ВСЕХ операциях, сделках и отчётах
    # расходы на проскальзывание неотрицательны; улучшение цены — отдельно.
    sl_candles = make_candles([
        {"o": 100.0, "h": 100.1, "l": 99.9, "c": 100.0},
        {"o": 100.0, "h": 100.1, "l": 99.9, "c": 100.0},
        {"o": 95.0, "h": 96.0, "l": 94.5, "c": 95.5},
    ])
    tp_candles = make_candles([
        {"o": 100.0, "h": 100.1, "l": 99.9, "c": 100.0},
        {"o": 100.0, "h": 100.1, "l": 99.9, "c": 100.0},
        {"o": 110.0, "h": 112.0, "l": 109.0, "c": 111.0},
    ])
    for report in (_run(sl_candles), _run(tp_candles,
                                          take_profit_fraction=TP)):
        for op in report["ledger_operations"]:
            assert op["slippage_cost"] >= 0.0
            assert op["price_improvement"] >= 0.0
            assert op["slippage_cost"] == 0.0 or op["price_improvement"] == 0.0
        for trade in report["trades"]:
            assert trade["entry_slippage_cost"] >= 0.0
            assert trade["exit_slippage_cost"] >= 0.0
            assert trade["entry_price_improvement"] >= 0.0
            assert trade["exit_price_improvement"] >= 0.0
        costs = report["costs"]
        assert costs["total_slippage_cost"] >= 0.0
        assert costs["total_adverse_slippage_cost"] >= 0.0
        assert costs["total_favorable_price_improvement"] >= 0.0
        assert costs["total_execution_cost"] >= 0.0


# --- дополнительные проверки -----------------------------------------------------------------

def test_split_function_validates_fail_closed():
    with pytest.raises(ExecutionError):
        split_execution_deviation(side="LONG", reference_price=100.0,
                                  execution_price=100.0, quantity=1,
                                  contract_multiplier=1.0)
    with pytest.raises(ExecutionError):
        split_execution_deviation(side=SIDE_BUY, reference_price=0.0,
                                  execution_price=100.0, quantity=1,
                                  contract_multiplier=1.0)
    with pytest.raises(ExecutionError):
        split_execution_deviation(side=SIDE_BUY, reference_price=100.0,
                                  execution_price=100.0, quantity=0,
                                  contract_multiplier=1.0)
    with pytest.raises(ExecutionError):
        split_execution_deviation(side=SIDE_BUY, reference_price=100.0,
                                  execution_price=100.0, quantity=1,
                                  contract_multiplier=0.0)


def test_report_costs_backward_compatible():
    """Существующие поля отчёта сохранены; новые — добавлены рядом."""
    script = {0: SignalDirection.BUY, 3: SignalDirection.SELL}
    candles = make_candles([
        {"o": 100.0, "h": 100.1, "l": 99.9, "c": 100.0},
        {"o": 100.0, "h": 100.1, "l": 99.9, "c": 100.0},
        {"o": 100.0, "h": 100.1, "l": 99.9, "c": 100.0},
        {"o": 100.0, "h": 100.1, "l": 99.9, "c": 100.0},   # SELL на закрытии
        {"o": 100.0, "h": 100.1, "l": 99.0, "c": 100.0},   # исполнение
    ])
    report = _run_scripted(candles, script)
    costs = report["costs"]
    # Прежние поля Stage E (имена и семантика суммарных издержек).
    assert "total_commission" in costs
    assert "total_slippage_cost" in costs
    # Новые поля Stage E.1.
    assert "total_adverse_slippage_cost" in costs
    assert "total_favorable_price_improvement" in costs
    assert "total_execution_cost" in costs
    assert "total_execution_cost_definition" in costs
    # Совместимость: прежнее поле == новое раздельное значение.
    assert costs["total_slippage_cost"] == costs["total_adverse_slippage_cost"]
    # Модель исполнения задокументирована в отчёте.
    model = report["execution_model"]
    assert model["slippage_accounting"] == \
        "ADVERSE_COST_AND_FAVORABLE_IMPROVEMENT_SPLIT_DIRECTION_AWARE"
    assert "reference_price_definition" in model


def test_slippage_split_determinism_in_report():
    """Повторный прогон одного сценария даёт идентичные издержки и хеш."""
    script = {0: SignalDirection.BUY, 3: SignalDirection.SELL}
    candles = make_candles([
        {"o": 100.0, "h": 100.1, "l": 99.9, "c": 100.0},
        {"o": 100.0, "h": 100.1, "l": 99.9, "c": 100.0},
        {"o": 100.0, "h": 100.1, "l": 99.9, "c": 100.0},
        {"o": 100.0, "h": 100.1, "l": 99.9, "c": 100.0},   # SELL на закрытии
        {"o": 100.0, "h": 100.1, "l": 99.0, "c": 100.0},   # исполнение
    ])
    first = _run_scripted(candles, script)
    second = _run_scripted(candles, script)
    assert first["report_sha256"] == second["report_sha256"]
    assert first["costs"] == second["costs"]


def test_signed_deviation_identity_adverse_minus_improvement():
    """Документированное соотношение: прежнее знаковое значение =
    adverse - improvement (positive = adverse, negative = improvement)."""
    # Покупка с cap по high (adverse ограничен диапазоном свечи).
    candles = make_candles([
        {"o": 100.0, "h": 100.05, "l": 99.95, "c": 100.0},
        {"o": 100.0, "h": 100.02, "l": 99.9, "c": 100.0},  # cap: exec=high
    ])
    report = _run(candles)
    op = _entry_op(report)
    exec_price = min(100.0 * (1.0 + SLIP), 100.02)
    quantity = op["quantity"]
    assert op["price"] == exec_price
    assert op["details"]["reference_price"] == 100.0   # сырой open
    assert op["slippage_cost"] == \
        quantity * 1.0 * (exec_price - 100.0)
    assert op["price_improvement"] == 0.0


# --- FINAL CORRECTIONS (Correction 2): валидация чисел (math.isfinite) --------
#
# Требование: конечность ВСЕХ числовых аргументов split_execution_deviation()
# проверяется через math.isfinite(); отклоняются NaN, +Infinity, -Infinity,
# нулевые и отрицательные значения там, где они недопустимы. Регрессионная
# основа: прежде +Infinity ПРОХОДИЛ проверку знаком (inf > 0) и заражал
# показатели Inf/NaN; NaN ловился сравнением x != x, Inf — нет.
# Формулы adverse slippage и favorable price improvement НЕ изменены.


def _split(**overrides):
    """Вызов split_execution_deviation со стандартными валидными
    аргументами; overrides замещают отдельные значения."""
    kwargs = dict(side=SIDE_BUY, reference_price=100.0,
                  execution_price=100.5, quantity=10,
                  contract_multiplier=1.0)
    kwargs.update(overrides)
    return split_execution_deviation(**kwargs)


# reference_price: NaN / +Inf / -Inf / ноль / отрицательное --------------------

def test_reference_price_nan_rejected():
    with pytest.raises(ExecutionError):
        _split(reference_price=float("nan"))


def test_reference_price_plus_inf_rejected():
    # Регрессия FINAL CORRECTIONS: прежде +Infinity проходил валидацию.
    with pytest.raises(ExecutionError):
        _split(reference_price=float("inf"))


def test_reference_price_minus_inf_rejected():
    with pytest.raises(ExecutionError):
        _split(reference_price=float("-inf"))


def test_reference_price_zero_rejected():
    with pytest.raises(ExecutionError):
        _split(reference_price=0.0)


def test_reference_price_negative_rejected():
    with pytest.raises(ExecutionError):
        _split(reference_price=-100.0)


# execution_price: NaN / +Inf / -Inf / ноль / отрицательное --------------------

def test_execution_price_nan_rejected():
    with pytest.raises(ExecutionError):
        _split(execution_price=float("nan"))


def test_execution_price_plus_inf_rejected():
    with pytest.raises(ExecutionError):
        _split(execution_price=float("inf"))


def test_execution_price_minus_inf_rejected():
    with pytest.raises(ExecutionError):
        _split(execution_price=float("-inf"))


def test_execution_price_zero_rejected():
    with pytest.raises(ExecutionError):
        _split(execution_price=0.0)


def test_execution_price_negative_rejected():
    with pytest.raises(ExecutionError):
        _split(execution_price=-100.5)


# contract_multiplier: NaN / +Inf / -Inf / ноль / отрицательное ----------------

def test_contract_multiplier_nan_rejected():
    with pytest.raises(ExecutionError):
        _split(contract_multiplier=float("nan"))


def test_contract_multiplier_plus_inf_rejected():
    with pytest.raises(ExecutionError):
        _split(contract_multiplier=float("inf"))


def test_contract_multiplier_minus_inf_rejected():
    with pytest.raises(ExecutionError):
        _split(contract_multiplier=float("-inf"))


def test_contract_multiplier_zero_rejected():
    with pytest.raises(ExecutionError):
        _split(contract_multiplier=0.0)


def test_contract_multiplier_negative_rejected():
    with pytest.raises(ExecutionError):
        _split(contract_multiplier=-1.0)


# quantity: ноль / отрицательное / bool / не-int / NaN/Inf float / переполнение

def test_quantity_zero_rejected():
    with pytest.raises(ExecutionError):
        _split(quantity=0)


def test_quantity_negative_rejected():
    with pytest.raises(ExecutionError):
        _split(quantity=-10)


def test_quantity_bool_rejected():
    with pytest.raises(ExecutionError):
        _split(quantity=True)


def test_quantity_float_non_integer_rejected():
    with pytest.raises(ExecutionError):
        _split(quantity=10.5)


def test_quantity_nan_float_rejected():
    with pytest.raises(ExecutionError):
        _split(quantity=float("nan"))


def test_quantity_inf_float_rejected():
    with pytest.raises(ExecutionError):
        _split(quantity=float("inf"))


def test_quantity_overflow_int_rejected():
    # Целое, не представимое конечным float: math.isfinite() невозможен,
    # fail-closed -> ExecutionError (а не OverflowError наружу).
    with pytest.raises(ExecutionError):
        _split(quantity=10 ** 400)


# Валидные конечные значения: формулы НЕ изменены -------------------------------

def test_finite_valid_arguments_produce_unchanged_formulas():
    # Порядок float-операций сохранён: quantity * multiplier * delta.
    assert _split(side=SIDE_BUY, reference_price=100.0,
                  execution_price=100.5, quantity=10,
                  contract_multiplier=2.0) == (10 * 2.0 * 0.5, 0.0)
    # Зеркальность: та же дельта для продажи — улучшение цены.
    assert _split(side=SIDE_SELL, reference_price=100.0,
                  execution_price=100.5, quantity=10,
                  contract_multiplier=2.0) == (0.0, 10 * 2.0 * 0.5)
    # Точное совпадение цен — обе величины нулевые.
    assert _split(side=SIDE_BUY, reference_price=100.0,
                  execution_price=100.0, quantity=3,
                  contract_multiplier=1.5) == (0.0, 0.0)
    # Целые цены (int) допускаются, как и прежде.
    assert _split(side=SIDE_SELL, reference_price=100,
                  execution_price=99, quantity=2,
                  contract_multiplier=1) == (2.0, 0.0)
