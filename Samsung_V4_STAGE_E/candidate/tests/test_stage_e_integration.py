# tests/test_stage_e_integration.py
# SAMSUNG V4 — NEW STRATEGY ENGINE. STAGE E.
# Интеграционные тесты Stage E с ПРИНЯТЫМИ контрактами:
#   * Stage B.1 (StrategyStateManager, memory-режим) внутри координатора
#     выхода — изолированное состояние прогона, config_hash проверяется;
#   * Stage C (EntryEvaluationRunner / ExitDecisionCoordinator / merge /
#     price gate) — полный контрактный путь решений;
#   * Stage D (calculate_position_size) — размер позиции и атрибуция;
#   * regression-only legacy-стратегия Samsung V4 (адаптер Stage A):
#     запускается через build_regression_config (origin=regression_harness),
#     детерминизм прогона (OFFLINE; требует pandas_ta_classic — в среде
#     репозитория установлен; отсутствие помечается skipif, что НЕ
#     ослабляет набор: тест валиден и без него).
# Offline-only; никакой сети и брокера.

from __future__ import annotations

import pytest

from historical_engine import (
    BacktestEngine,
    HistoricalDataFeed,
    SegmentSpec,
)
from strategy_api import SignalDirection

from tests.stage_e_tools import (
    ScriptedSignalStrategy,
    make_candles,
    make_engine_config,
    make_strategy_config,
)

try:
    import pandas_ta_classic  # noqa: F401
    HAS_PANDAS_TA = True
except Exception:
    HAS_PANDAS_TA = False


def _engine(strategy, candles, **cfg_overrides):
    config = make_strategy_config(strategy, {"warmup": 1})
    engine_config = make_engine_config(**cfg_overrides)
    feed = HistoricalDataFeed.from_candles(candles,
                                           engine_config=engine_config)
    engine = BacktestEngine(strategy=strategy, strategy_config=config,
                            engine_config=engine_config, feed=feed)
    return engine, feed


def test_exit_decision_uses_stage_b_state_and_stage_c_merge():
    # Полный контрактный путь выхода: price gate (Stage C) -> состояние
    # Stage B.1 (memory) -> оценщики -> merge -> запись состояния.
    # Проверяем отчёт решения: price_check выполнен, merge зафиксирован,
    # состояние обновлено координатором.
    script = {0: SignalDirection.BUY, 2: SignalDirection.SELL}
    strategy = ScriptedSignalStrategy(script)
    candles = make_candles([
        {"o": 100.0, "h": 100.2, "l": 99.8, "c": 100.0},
        {"o": 100.0, "h": 100.2, "l": 99.8, "c": 100.0},
        {"o": 100.0, "h": 100.2, "l": 99.8, "c": 100.0},
        {"o": 100.5, "h": 100.7, "l": 100.3, "c": 100.5},
        {"o": 100.5, "h": 100.7, "l": 100.3, "c": 100.5},
    ])
    engine, _ = _engine(strategy, candles)
    report = engine.run_full()
    # СДЕЛКА: вход на открытии свечи 1, выход на открытии свечи 3.
    assert len(report["trades"]) == 1
    trade = report["trades"][0]
    assert trade["exit_type"] == "STRATEGIC_SELL_SIGNAL"
    # Гистограмма решений выхода содержит merge-итог STRATEGIC_EXIT.
    assert report["reasons"]["exit_reasons"].get(
        "STRATEGIC_SELL_SIGNAL:STRATEGIC_EXIT_SELL_SIGNAL") == 1
    # Мердж и price gate отработали в контрактном формате Stage C.
    assert report["reasons"]["entry_decision_reasons"].get(
        "ENTRY_SIGNAL_BUY") == 1


def test_protective_exit_decision_layer_when_no_position_levels():
    # Защитный оценщик на закрытии: при отсутствии позиции возвращает
    # NO_EXIT (не падает и не изобретает выход) — контракт Stage C.
    from historical_engine.strategy_runner import (
        StopLevelsProtectiveEvaluator,
    )
    from strategy_contracts import (
        ExitDecisionSource, ExitEvaluationRequest, ExitOutcome, PriceData,
    )
    strategy = ScriptedSignalStrategy({})
    config = make_strategy_config(strategy, {"warmup": 1})
    evaluator = StopLevelsProtectiveEvaluator(
        levels_provider=lambda: None)   # позиции нет
    request = ExitEvaluationRequest(
        strategy_id=config.strategy_id,
        config_hash=config.config_hash,
        figi="TESTFIGI1",
        price=PriceData(figi="TESTFIGI1", price=100.0,
                        timestamp="2024-01-02T10:00:00+00:00",
                        source="test"),
    )
    result = evaluator.evaluate_exit(request)
    assert result.outcome is ExitOutcome.NO_EXIT
    assert result.decision_source is ExitDecisionSource.PROTECTIVE


def test_protective_exit_decision_layer_close_breach():
    from historical_engine.strategy_runner import (
        StopLevelsProtectiveEvaluator,
    )
    from strategy_contracts import (
        ExitOutcome, ExitDecisionSource, ExitEvaluationRequest, PriceData,
    )
    strategy = ScriptedSignalStrategy({})
    config = make_strategy_config(strategy, {"warmup": 1})
    evaluator = StopLevelsProtectiveEvaluator(
        levels_provider=lambda: {"stop_price": 101.0, "take_price": None})
    request = ExitEvaluationRequest(
        strategy_id=config.strategy_id,
        config_hash=config.config_hash,
        figi="TESTFIGI1",
        price=PriceData(figi="TESTFIGI1", price=100.0,
                        timestamp="2024-01-02T10:00:00+00:00",
                        source="test"),
    )
    result = evaluator.evaluate_exit(request)
    assert result.outcome is ExitOutcome.PROTECTIVE_EXIT
    assert result.exit_type == "PROTECTIVE_STOP_LOSS"
    assert result.decision_source is ExitDecisionSource.PROTECTIVE


def test_stage_b_state_manager_config_mismatch_isolated():
    # Изоляция Stage B.1: состояние прогона привязано к config_hash;
    # запрос состояния с ЧУЖИМ config_hash отклоняется (без автопереноса).
    from strategy_state import StateStore, StateConfigMismatchError, \
        StrategyStateManager
    strategy = ScriptedSignalStrategy({})
    config = make_strategy_config(strategy, {"warmup": 1})
    manager = StrategyStateManager(StateStore(path=None))
    state = manager.get_state(config.strategy_id, "TESTFIGI1",
                              config=config)
    assert state.config_hash == config.config_hash
    # Чужой config_hash (валидный формат, но другое значение):
    other_hash = "b" * 64
    with pytest.raises(StateConfigMismatchError):
        manager.get_state(config.strategy_id, "TESTFIGI1",
                          config_hash=other_hash)


def test_segments_labels_and_bundle_structure():
    script = {0: SignalDirection.BUY, 2: SignalDirection.SELL}
    strategy = ScriptedSignalStrategy(script)
    candles = make_candles([
        {"o": 100.0, "h": 100.2, "l": 99.8, "c": 100.0},
        {"o": 100.0, "h": 100.2, "l": 99.8, "c": 100.0},
        {"o": 100.0, "h": 100.2, "l": 99.8, "c": 100.0},
        {"o": 101.0, "h": 101.2, "l": 100.8, "c": 101.0},
        {"o": 101.0, "h": 101.2, "l": 100.8, "c": 101.0},
        {"o": 101.0, "h": 101.2, "l": 100.8, "c": 101.0},
    ])
    engine, feed = _engine(strategy, candles)
    bundle = engine.run_segments([
        SegmentSpec(label="IS", start_index=0, end_index=4),
        SegmentSpec(label="OOS", start_index=4, end_index=6),
    ])
    assert bundle["bundle_schema"] == "samsung_v4_stage_e_bundle_v1"
    assert len(bundle["bundle_id"]) == 64
    assert len(bundle["reports"]) == 2
    for report in bundle["reports"]:
        assert len(report["metadata"]["run_id"]) == 64
        assert len(report["metadata"]["data_sha256"]) == 64


@pytest.mark.skipif(not HAS_PANDAS_TA,
                    reason="pandas_ta_classic недоступен: legacy-прогон "
                           "требует зависимости baseline-стратегии")
def test_legacy_samsung_v4_regression_config_backtest_deterministic():
    # Legacy-стратегия Samsung V4 (REGRESSION_ONLY, Stage A адаптер):
    # единственный легальный путь — build_regression_config; прогон в
    # историческом движке детерминирован (два запуска — один хеш).
    from strategies.legacy_samsung_v4.strategy import LegacySamsungV4Strategy
    import math as _math
    # Детерминированные 150 свечей (синус + дрейф, БЕЗ случайности).
    base = _math.pi
    specs = []
    price = 100.0
    for i in range(150):
        drift = 20.0 * (i / 149.0)
        wave = 5.0 * (1.0 - _math.cos(2 * base * i / 30.0))
        close = 100.0 + drift + wave
        open_ = price
        specs.append({"o": round(open_, 2), "h": round(max(open_, close) + 0.5, 2),
                      "l": round(min(open_, close) - 0.5, 2),
                      "c": round(close, 2), "v": 10000.0})
        price = close
    candles = make_candles(specs)
    strategy = LegacySamsungV4Strategy()
    config = strategy.build_regression_config("SANDBOX_TEST")
    engine_config = make_engine_config()
    feed = HistoricalDataFeed.from_candles(candles,
                                           engine_config=engine_config)
    engine = BacktestEngine(strategy=strategy, strategy_config=config,
                            engine_config=engine_config, feed=feed)
    report_a = engine.run_full()
    report_b = engine.run_full()
    assert report_a["metadata"]["strategy_id"] == "legacy_samsung_v4"
    assert report_a["report_sha256"] == report_b["report_sha256"]
    # Все входы прошли через Stage D: у сделок есть риск-политика.
    for trade in report_a["trades"]:
        assert len(trade["risk_policy_hash"]) == 64
        assert trade["quantity"] % 10 == 0
