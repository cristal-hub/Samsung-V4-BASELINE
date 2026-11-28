# tests/test_stage_e_engine_decisions.py
# SAMSUNG V4 — NEW STRATEGY ENGINE. STAGE E.
# Тесты EventEngine/StrategyRunner: отсутствие look-ahead bias, модель
# «сигнал на закрытии i -> исполнение на открытии i+1», детерминизм
# повторного запуска, интеграция со Stage D, изоляция стратегий,
# IS/VALIDATION/OOS, неразрешённые решения на границе сегмента.
# Offline-only.

from __future__ import annotations

from datetime import timedelta

import pytest

from historical_engine import (
    BacktestEngine,
    HistoricalDataFeed,
    SegmentSpec,
)
from strategy_api import SignalDirection
from strategy_risk import SizingOutcome

from tests.stage_e_tools import (
    AlwaysBuyStrategy,
    LookAheadSpyStrategy,
    ScriptedSignalStrategy,
    make_candles,
    make_engine_config,
    make_strategy_config,
)


def _engine(strategy, candles, **cfg_overrides):
    config = make_strategy_config(strategy, {"warmup": 1, "rises": 2,
                                             "rises_declared": 2})
    engine_config = make_engine_config(**cfg_overrides)
    feed = HistoricalDataFeed.from_candles(candles,
                                           engine_config=engine_config)
    return BacktestEngine(strategy=strategy, strategy_config=config,
                          engine_config=engine_config, feed=feed), feed


# --- look-ahead bias -------------------------------------------------------------

def test_strategy_never_sees_future_candles():
    inner = AlwaysBuyStrategy()
    spy = LookAheadSpyStrategy(delegate=inner)
    candles = make_candles([
        {"o": 100.0, "h": 100.1, "l": 99.9, "c": 100.0},
        {"o": 100.0, "h": 100.1, "l": 99.9, "c": 100.0},
        {"o": 100.0, "h": 100.1, "l": 99.9, "c": 100.0},
        {"o": 100.0, "h": 100.1, "l": 99.9, "c": 100.0},
    ])
    engine, _feed = _engine(spy, candles)
    engine.run_full()
    # Вызов стратегии на каждой свече k (0..3): срез ровно k+1 свечей,
    # последняя метка среза == метка свечи k (будущие не попадают).
    assert len(spy.calls) == 4
    for k, call in enumerate(spy.calls):
        assert call["slice_length"] == k + 1
        assert call["last_timestamp"] == str(candles[k].timestamp)
        assert call["last_price"] == candles[k].close


def test_signal_after_close_executes_next_open_not_signal_close():
    # Сигнал BUY на закрытии свечи 0 по цене close=100.0; если бы
    # исполнение происходило «задним числом» по сигнальной свече,
    # цена входа была бы 100.0 — проверяем, что вход идёт по open(+slip)
    # СЛЕДУЮЩЕЙ свечи, недоступной на момент решения.
    candles = make_candles([
        {"o": 100.0, "h": 100.1, "l": 99.9, "c": 100.0},  # сигнал здесь
        {"o": 105.0, "h": 105.2, "l": 104.8, "c": 105.0},  # гэп вверх
    ])
    strategy = AlwaysBuyStrategy()
    engine, _ = _engine(strategy, candles)
    report = engine.run_full()
    op_entry = [op for op in report["ledger_operations"]
                if op["kind"] == "ENTRY_EXECUTED"]
    assert len(op_entry) == 1
    assert op_entry[0]["timestamp_iso"] == candles[1].timestamp.isoformat()
    assert op_entry[0]["price"] == 105.0 * 1.0005
    assert op_entry[0]["price"] != 100.0   # НЕ цена сигнальной свечи


def test_no_execution_on_decision_candle_close():
    # Исполнение всегда на следующей свече: у сделки вход i+1, выход —
    # на открытии свечи ПОСЛЕ решения, никогда в момент решения.
    script = {0: SignalDirection.BUY, 2: SignalDirection.SELL}
    strategy = ScriptedSignalStrategy(script)
    candles = make_candles([
        {"o": 100.0, "h": 100.2, "l": 99.8, "c": 100.0},
        {"o": 100.0, "h": 100.2, "l": 99.8, "c": 100.0},
        {"o": 100.0, "h": 100.2, "l": 99.8, "c": 100.0},  # SELL на закрытии
        {"o": 101.0, "h": 101.2, "l": 100.8, "c": 101.0},  # исполнение
    ])
    engine, _ = _engine(strategy, candles)
    report = engine.run_full()
    trade = report["trades"][0]
    assert trade["entry_candle_index"] == 1
    assert trade["exit_candle_index"] == 3
    assert trade["entry_timestamp_iso"] == candles[1].timestamp.isoformat()
    assert trade["exit_timestamp_iso"] == candles[3].timestamp.isoformat()


# --- детерминизм -------------------------------------------------------------------

def test_rerun_produces_identical_report_and_hash():
    strategy = AlwaysBuyStrategy()
    candles = make_candles([
        {"o": 100.0, "h": 100.2, "l": 99.8, "c": 100.0},
        {"o": 100.5, "h": 100.7, "l": 100.3, "c": 100.5},
        {"o": 99.0, "h": 99.4, "l": 98.2, "c": 98.5},
        {"o": 99.0, "h": 100.0, "l": 98.9, "c": 99.5},
        {"o": 101.0, "h": 101.4, "l": 100.9, "c": 101.2},
    ])
    engine, _ = _engine(strategy, candles)
    report_a = engine.run_full()
    report_b = engine.run_full()
    assert report_a["report_sha256"] == report_b["report_sha256"]
    assert report_a == report_b


def test_run_id_derives_from_data_config_and_segment():
    strategy = AlwaysBuyStrategy()
    candles_a = make_candles([
        {"o": 100.0, "h": 100.1, "l": 99.9, "c": 100.0},
        {"o": 100.0, "h": 100.1, "l": 99.9, "c": 100.0},
    ])
    candles_b = make_candles([
        {"o": 100.0, "h": 100.1, "l": 99.9, "c": 100.0},
        {"o": 101.0, "h": 101.1, "l": 100.9, "c": 101.0},   # другие данные
    ])
    engine_a, _ = _engine(strategy, candles_a)
    engine_b, _ = _engine(strategy, candles_b)
    report_a = engine_a.run_full()
    report_b = engine_b.run_full()
    assert report_a["metadata"]["run_id"] != \
        report_b["metadata"]["run_id"]      # разные данные -> другой run_id
    assert report_a["metadata"]["run_id"] == \
        engine_a.run_full()["metadata"]["run_id"]   # стабильный при повторе


def test_report_sha_covers_engine_config_change():
    strategy = AlwaysBuyStrategy()
    candles = make_candles([
        {"o": 100.0, "h": 100.1, "l": 99.9, "c": 100.0},
        {"o": 100.0, "h": 100.1, "l": 99.9, "c": 100.0},
        {"o": 100.0, "h": 100.1, "l": 99.9, "c": 100.0},
    ])
    engine_a, _ = _engine(strategy, candles, commission_rate=0.001)
    engine_b, _ = _engine(strategy, candles, commission_rate=0.002)
    report_a = engine_a.run_full()
    report_b = engine_b.run_full()
    assert report_a["metadata"]["engine_config_sha256"] != \
        report_b["metadata"]["engine_config_sha256"]


# --- интеграция со Stage D ------------------------------------------------------------

def test_stage_d_sized_quantity_is_used_for_entry():
    candles = make_candles([
        {"o": 100.0, "h": 100.1, "l": 99.9, "c": 100.0},
        {"o": 100.0, "h": 100.1, "l": 99.9, "c": 100.0},
    ])
    strategy = AlwaysBuyStrategy()
    engine, _ = _engine(strategy, candles)
    report = engine.run_full()
    op_entry = [op for op in report["ledger_operations"]
                if op["kind"] == "ENTRY_EXECUTED"][0]
    # Размер рассчитан Stage D: кратен лоту и совпадает с точным расчётом
    # (см. test_lot_flooring_quantity_multiple_of_lot: 450 единиц).
    assert op_entry["quantity"] == 450
    assert op_entry["quantity"] % 10 == 0
    assert op_entry["details"]["lot_count"] == 45
    assert len(op_entry["details"]["risk_policy_hash"]) == 64


def test_stage_d_attribution_mismatch_blocks_entry():
    # Подмена конфигурации на расчёте: политика привязана к другой
    # паре (strategy_id, config_hash) -> Stage D отклоняет расчёт
    # (ATTRIBUTION_MISMATCH), движок НЕ открывает позицию.
    strategy = AlwaysBuyStrategy()
    config = make_strategy_config(strategy, {"warmup": 1})
    engine_config = make_engine_config()
    feed = HistoricalDataFeed.from_candles(
        make_candles([
            {"o": 100.0, "h": 100.1, "l": 99.9, "c": 100.0},
            {"o": 100.0, "h": 100.1, "l": 99.9, "c": 100.0},
        ]), engine_config=engine_config)
    other_config = make_strategy_config(strategy, {"warmup": 1})
    # Конфигурация другой СТРАТЕГИИ (другой strategy_id/config_hash):
    from tests.stage_e_tools import TEST_FIGI
    class ForeignStrategy(AlwaysBuyStrategy):
        strategy_id = "stage_e_foreign"
    foreign_config = make_strategy_config(ForeignStrategy(), {"warmup": 1})
    risk = __import__("historical_engine").RiskIntegration(
        engine_config=engine_config, strategy_config=config)
    result = risk.size_entry(execution_price=100.05, cash=100000.0,
                             config=foreign_config)
    assert result.outcome is SizingOutcome.ATTRIBUTION_MISMATCH
    assert result.quantity == 0


def test_sizing_result_not_mutated_by_engine():
    # Результат Stage D передаётся движку как есть: исход SIZED —
    # единственный источник положительного объёма; блокирующий результат
    # никогда не превращается в позицию.
    strategy = AlwaysBuyStrategy()
    candles = make_candles([
        {"o": 100.0, "h": 100.1, "l": 99.9, "c": 100.0},
        {"o": 100.0, "h": 100.1, "l": 99.9, "c": 100.0},
    ])
    engine, _ = _engine(strategy, candles, initial_cash=500.0)
    report = engine.run_full()
    assert report["trades"] == []
    assert report["account"]["final_cash"] == 500.0


# --- изоляция стратегий ----------------------------------------------------------------

def test_strategy_isolation_no_state_bleed():
    strategy = AlwaysBuyStrategy()
    candles = make_candles([
        {"o": 100.0, "h": 100.2, "l": 99.8, "c": 100.0},
        {"o": 100.0, "h": 100.2, "l": 99.8, "c": 100.0},
        {"o": 99.0, "h": 99.4, "l": 98.2, "c": 98.5},
    ])
    engine_a, _ = _engine(strategy, candles)
    report_a_before = engine_a.run_full()
    engine_b, _ = _engine(strategy, candles,
                          commission_rate=0.002)   # другой прогон
    report_b = engine_b.run_full()
    report_a_after = engine_a.run_full()
    assert report_a_before == report_a_after   # прогон A не изменён прогоном B
    assert report_a_before["report_sha256"] != report_b["report_sha256"]


def test_engine_rejects_foreign_strategy_config():
    class OtherStrategy(AlwaysBuyStrategy):
        strategy_id = "stage_e_other"
    other = OtherStrategy()
    other_config = make_strategy_config(other, {"warmup": 1})
    engine_config = make_engine_config()
    feed = HistoricalDataFeed.from_candles(
        make_candles([
            {"o": 100.0, "h": 100.1, "l": 99.9, "c": 100.0}]),
        engine_config=engine_config)
    with pytest.raises(Exception):
        BacktestEngine(strategy=AlwaysBuyStrategy(),
                       strategy_config=other_config,
                       engine_config=engine_config, feed=feed)


# --- IS / VALIDATION / OOS ---------------------------------------------------------------

def test_is_validation_oos_segments_run_independently():
    strategy = AlwaysBuyStrategy()
    candles = make_candles([
        {"o": 100.0, "h": 100.1, "l": 99.9, "c": 100.0},
        {"o": 100.0, "h": 100.1, "l": 99.9, "c": 100.0},
        {"o": 100.0, "h": 100.1, "l": 99.9, "c": 100.0},
        {"o": 100.0, "h": 100.1, "l": 99.9, "c": 100.0},
        {"o": 100.0, "h": 100.1, "l": 99.9, "c": 100.0},
        {"o": 100.0, "h": 100.1, "l": 99.9, "c": 100.0},
    ])
    engine, _ = _engine(strategy, candles)
    bundle = engine.run_segments([
        SegmentSpec(label="IS", start_index=0, end_index=3),
        SegmentSpec(label="VALIDATION", start_index=3, end_index=5),
        SegmentSpec(label="OOS", start_index=5, end_index=6),
    ])
    assert [r["metadata"]["segment_label"] for r in bundle["reports"]] == \
        ["IS", "VALIDATION", "OOS"]
    # Независимость: тот же сегмент отдельно даёт ИДЕНТИЧНЫЙ отчёт.
    alone = engine.run_segment(SegmentSpec(label="OOS", start_index=5,
                                           end_index=6))
    assert alone["report_sha256"] == bundle["reports"][2]["report_sha256"]
    # Одна конфигурация на все сегменты: никаких параметров из отчётов.
    hashes = {r["metadata"]["engine_config_sha256"]
              for r in bundle["reports"]}
    assert len(hashes) == 1


def test_oos_results_cannot_change_parameters_structural():
    # Структурная гарантия ТЗ §8: движок не возвращает параметров и не
    # принимает «подстроенных» параметров из отчётов: отчёт не содержит
    # полей оптимизации, фасад не имеет методов подстройки.
    strategy = AlwaysBuyStrategy()
    candles = make_candles([
        {"o": 100.0, "h": 100.1, "l": 99.9, "c": 100.0},
        {"o": 100.0, "h": 100.1, "l": 99.9, "c": 100.0},
    ])
    engine, _ = _engine(strategy, candles)
    report = engine.run_full()
    assert "optimized_params" not in report
    assert "parameter_updates" not in report
    assert not hasattr(engine, "optimize")
    assert not hasattr(engine, "tune_parameters")
    assert not hasattr(engine, "apply_oos_feedback")


# --- неразрешённые решения на границе сегмента ---------------------------------------------

def test_pending_exit_unresolved_at_segment_end():
    # SELL на закрытии ПОСЛЕДНЕЙ свечи: решение остаётся неисполненным
    # (задним числом исполнять запрещено) и фиксируется в отчёте.
    script = {0: SignalDirection.BUY, 2: SignalDirection.SELL}
    strategy = ScriptedSignalStrategy(script)
    candles = make_candles([
        {"o": 100.0, "h": 100.2, "l": 99.8, "c": 100.0},
        {"o": 100.0, "h": 100.2, "l": 99.8, "c": 100.0},
        {"o": 100.0, "h": 100.2, "l": 99.8, "c": 100.0},  # SELL на закрытии
    ])
    engine, _ = _engine(strategy, candles)
    report = engine.run_full()
    assert report["trades"] == []
    assert report["unresolved_decisions"]["exit_pending_at_segment_end"] \
        is True
    assert report["account"]["open_position_at_end"] is not None


def test_sell_signal_when_flat_is_not_an_entry():
    script = {0: SignalDirection.SELL}
    strategy = ScriptedSignalStrategy(script)
    candles = make_candles([
        {"o": 100.0, "h": 100.2, "l": 99.8, "c": 100.0},
        {"o": 100.0, "h": 100.2, "l": 99.8, "c": 100.0},
    ])
    engine, _ = _engine(strategy, candles)
    report = engine.run_full()
    assert report["trades"] == []
    assert report["account"]["final_cash"] == 100000.0
    assert report["reasons"]["entry_decision_reasons"].get(
        "ENTRY_FORBIDDEN_SELL") == 1
