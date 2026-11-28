# tests/test_stage_c_exit_service.py — SAMSUNG V4 — STAGE C.
#
# Координатор выхода (ExitDecisionCoordinator) и интеграция с
# StrategyStateManager Stage B.1. Покрытие обязательных сценариев
# ТЗ Stage C §6:
#   §6.9  отсутствие цены (координатор: оценщики не вызываются);
#   §6.10 некорректная цена (координатор: fail-closed, нулевая цена
#         невозможна, чужой FIGI не проходит);
#   §6.11 устаревшая цена (координатор: PRICE_STALE, состояние не
#         изменяется);
#   §6.12 отсутствие фиктивного исполнения при ошибке оценки;
#   §6.13 сохранение состояния при неудачной оценке выхода;
#   §6.14 корректная атрибуция strategy_id/config_hash/FIGI;
#   §6.15 изоляция состояний нескольких стратегий;
#   §6.16 изоляция нескольких FIGI;
#   §6.17 конкурентное обновление состояния через Stage B.1;
#   плюс: ошибки состояния не маскируются; подмена config_hash
#   отклоняется (Stage A.2.1 перепроверка); подклассы не проходят.
#
# STAGE C.1 (исправление дефекта порядка операций): price gate СТРОГО
#   ДО доступа к состоянию. manager.get_state Stage B.1 создаёт запись
#   при отсутствии, поэтому блокирующая цена (отсутствующая/
#   некорректная/устаревшая) не должна оставлять в хранилище НИКАКИХ
#   следов. Проверяется ФАКТИЧЕСКОЕ состояние StateStore (публичный
#   StateStore.get_state() и файлы хранилища), а не только
#   report.state_updated.
#
# Все тесты offline, без сети и брокера; никаких заявок; старые файлы
# Samsung не затрагиваются.

import json
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import pytest

from strategy_api import StrategyConfig, compute_config_hash
import strategy_state as ss
from strategy_contracts import (
    CoordinatorViolationError,
    ExitDecisionCoordinator,
    ExitDecisionSource,
    ExitEvaluation,
    ExitEvaluationRequest,
    ExitMergeOutcome,
    ExitOutcome,
    PriceCheckOutcome,
    PriceData,
)
from strategy_state import (
    StateConfigMismatchError,
    StateCorruptionError,
    StateStore,
    StrategyStateManager,
)


NOW = datetime(2026, 11, 28, 12, 0, 0, tzinfo=timezone.utc)
FIXED_CLOCK = "2026-11-28T12:00:00.000000+00:00"


def make_config(strategy_id="alpha", params=None):
    params = {"n": 3} if params is None else params
    return StrategyConfig(
        strategy_id=strategy_id,
        strategy_version="1.0.0",
        params=params,
        config_hash=compute_config_hash(strategy_id, "1.0.0", params),
    )


def make_price(figi="FIGI1", price=100.0, offset_seconds=-30.0):
    ts = NOW + timedelta(seconds=offset_seconds)
    return PriceData(
        figi=figi, price=price,
        timestamp=ts.isoformat(timespec="microseconds")
        .replace("+00:00", "Z"),
        source="test-feed")


class CountingEvaluator:
    """Оценщик со счётчиком вызовов (проверка «оценщики не вызывались»)."""

    def __init__(self, source, behavior="no_exit"):
        self.source = source
        self.behavior = behavior
        self.calls = 0

    def evaluate_exit(self, request):
        self.calls += 1
        if self.behavior == "no_exit":
            return ExitEvaluation.no_exit(
                request.strategy_id, request.config_hash, request.figi,
                self.source, "NO_EXIT_RULES")
        if self.behavior == "strategic_exit":
            return ExitEvaluation.strategic_exit(
                request.strategy_id, request.config_hash, request.figi,
                "TAKE_PROFIT", "TAKE_PROFIT_HIT")
        if self.behavior == "protective_exit":
            return ExitEvaluation.protective_exit(
                request.strategy_id, request.config_hash, request.figi,
                "STOP_LOSS", "STOP_LOSS_HIT")
        if self.behavior == "raise":
            raise RuntimeError("protective layer crashed")
        if self.behavior == "garbage":
            return {"outcome": "PROTECTIVE_EXIT"}
        raise AssertionError(f"unknown behavior {self.behavior}")


def make_coord(manager, strategic="no_exit", protective="no_exit",
               clock=FIXED_CLOCK):
    strategic_eval = CountingEvaluator(ExitDecisionSource.STRATEGIC,
                                       strategic)
    protective_eval = CountingEvaluator(ExitDecisionSource.PROTECTIVE,
                                        protective)
    coordinator = ExitDecisionCoordinator(
        manager=manager,
        strategic_evaluator=strategic_eval,
        protective_evaluator=protective_eval,
        clock=(lambda: clock) if clock else None,
    )
    return coordinator, strategic_eval, protective_eval


def run(coordinator, config, figi="FIGI1", price=..., price_required=True,
        max_age=120.0, now=NOW):
    """Помощник прогона: по умолчанию — ВАЛИДНАЯ цена под заданный figi;
    price=None передаётся ЯВНО для сценариев блокировки."""
    kwargs = {}
    if price is not ...:
        kwargs["price"] = price
    elif price_required:
        kwargs["price"] = make_price(figi=figi)  # валидная цена по умолчанию
    return coordinator.evaluate_and_record(
        config=config, figi=figi, price_required=price_required,
        price_max_age_seconds=max_age, now=now, **kwargs)


# ===========================================================================
# Базовые циклы координатора
# ===========================================================================

class TestCoordinatorHappyPaths:
    def test_no_exit_recorded_via_atomic_api(self):
        manager = StrategyStateManager(StateStore())
        config = make_config()
        coordinator, strategic, protective = make_coord(manager)
        report = run(coordinator, config)
        assert report.merged.final_outcome is ExitMergeOutcome.NO_EXIT
        assert report.state_updated is True
        assert strategic.calls == 1 and protective.calls == 1
        state = manager.get_state("alpha", "FIGI1",
                                  config_hash=config.config_hash)
        record = state.data["last_exit_evaluation"]
        assert record["outcome"] == "NO_EXIT"
        assert record["strategy_id"] == "alpha"
        assert record["config_hash"] == config.config_hash
        assert record["figi"] == "FIGI1"
        assert record["decided_at"] == FIXED_CLOCK
        assert record["merge_rules_version"] == "exit_merge_rules_v1"

    def test_protective_exit_wins_end_to_end(self):
        manager = StrategyStateManager(StateStore())
        config = make_config()
        coordinator, _, _ = make_coord(manager,
                                       strategic="strategic_exit",
                                       protective="protective_exit")
        report = run(coordinator, config, price=make_price())
        assert report.merged.final_outcome is ExitMergeOutcome.PROTECTIVE_EXIT
        assert report.merged.decision_source is ExitDecisionSource.PROTECTIVE
        assert report.merged.exit_type == "STOP_LOSS"
        assert report.state_updated is True

    def test_strategic_exit_passes_when_protective_says_no(self):
        manager = StrategyStateManager(StateStore())
        config = make_config()
        coordinator, _, _ = make_coord(manager,
                                       strategic="strategic_exit",
                                       protective="no_exit")
        report = run(coordinator, config, price=make_price())
        assert report.merged.final_outcome is ExitMergeOutcome.STRATEGIC_EXIT
        assert report.merged.decision_source is ExitDecisionSource.STRATEGIC

    def test_price_not_required_proceeds_without_price(self):
        manager = StrategyStateManager(StateStore())
        config = make_config()
        coordinator, strategic, protective = make_coord(manager)
        report = run(coordinator, config, price_required=False)
        assert report.price_check.outcome is PriceCheckOutcome.PRICE_MISSING
        assert strategic.calls == 1 and protective.calls == 1
        assert report.merged.final_outcome is ExitMergeOutcome.NO_EXIT


# ===========================================================================
# ТЗ §6.9–§6.11 — fail-closed цена на уровне координатора
# ===========================================================================

class TestCoordinatorPriceGate:
    def test_missing_price_blocks_before_evaluators(self):
        manager = StrategyStateManager(StateStore())
        config = make_config()
        coordinator, strategic, protective = make_coord(manager)
        report = run(coordinator, config, price=None)  # цена не передана
        assert report.merged.final_outcome is \
            ExitMergeOutcome.INCOMPLETE_PRICE_EVALUATION
        assert report.merged.reason_code == "PRICE_MISSING"
        assert report.strategic_result is None
        assert report.protective_result is None
        assert strategic.calls == 0 and protective.calls == 0
        assert report.merged.diagnostics["evaluators_called"] is False

    def test_stale_price_blocks_and_state_untouched(self):
        manager = StrategyStateManager(StateStore())
        config = make_config()
        coordinator, strategic, protective = make_coord(manager)
        stale = make_price(offset_seconds=-600.0)
        report = run(coordinator, config, price=stale, max_age=120.0)
        assert report.merged.reason_code == "PRICE_STALE"
        assert strategic.calls == 0 and protective.calls == 0
        assert report.state_updated is False

    def test_foreign_price_blocks(self):
        manager = StrategyStateManager(StateStore())
        config = make_config()
        coordinator, _, _ = make_coord(manager)
        foreign = make_price(figi="OTHER")
        report = run(coordinator, config, price=foreign)
        assert report.merged.reason_code == "PRICE_FOREIGN_FIGI"
        assert report.merged.final_outcome is \
            ExitMergeOutcome.INCOMPLETE_PRICE_EVALUATION

    def test_price_not_required_but_invalid_price_still_blocks(self):
        """Цена не требуется, но ПЕРЕДАНА некорректная (чужой FIGI):
        мусорные данные не доходят до оценщиков (fail-closed)."""
        manager = StrategyStateManager(StateStore())
        config = make_config()
        coordinator, strategic, protective = make_coord(manager)
        foreign = make_price(figi="OTHER")
        report = run(coordinator, config, price=foreign, price_required=False)
        assert report.merged.reason_code == "PRICE_FOREIGN_FIGI"
        assert strategic.calls == 0 and protective.calls == 0

    def test_invalid_price_object_type_blocked(self):
        manager = StrategyStateManager(StateStore())
        config = make_config()
        coordinator, _, _ = make_coord(manager)
        report = run(coordinator, config, price="100.5")
        assert report.merged.reason_code == "PRICE_WRONG_TYPE"
        assert report.merged.final_outcome is \
            ExitMergeOutcome.INCOMPLETE_PRICE_EVALUATION


# ===========================================================================
# ТЗ §6.12–§6.13 — ошибки оценки: без фиктивного исполнения,
# состояние сохраняется
# ===========================================================================

class TestFailedEvaluationNoFictitiousExecution:
    def test_evaluator_exception_converted_to_blocked(self):
        manager = StrategyStateManager(StateStore())
        config = make_config()
        coordinator, strategic, protective = make_coord(
            manager, strategic="no_exit", protective="raise")
        report = run(coordinator, config, price=make_price())
        assert report.protective_result.outcome is \
            ExitOutcome.EVALUATION_BLOCKED
        assert report.protective_result.reason_code == "EVALUATOR_RAISED"
        assert report.protective_result.decision_source is \
            ExitDecisionSource.PROTECTIVE
        assert report.merged.final_outcome is \
            ExitMergeOutcome.INCOMPLETE_PROTECTIVE_EVALUATION
        assert report.merged.reason_code == "EVALUATOR_RAISED"
        assert report.state_updated is False
        # Никакого «исполненного» выхода в состоянии нет.
        state = manager.get_state("alpha", "FIGI1",
                                  config_hash=config.config_hash)
        assert "last_exit_evaluation" not in state.data

    def test_state_preserved_on_failed_evaluation(self):
        """ТЗ §6.13: при неудачной оценке выхода состояние пары
        сохраняется побайтово (ни changed data, ни updated_at)."""
        manager = StrategyStateManager(StateStore())
        config = make_config()
        # Создаём состояние с содержимым и обновлением.
        manager.update_state("alpha", "FIGI1", config_hash=config.config_hash,
                             data={"position": 10, "avg_price": 99.5})
        before = manager.get_state("alpha", "FIGI1",
                                   config_hash=config.config_hash).to_json()
        coordinator, _, _ = make_coord(manager, protective="raise")
        report = run(coordinator, config, price=make_price())
        assert report.state_updated is False
        after = manager.get_state("alpha", "FIGI1",
                                  config_hash=config.config_hash).to_json()
        assert before == after

    def test_state_preserved_on_price_block(self):
        manager = StrategyStateManager(StateStore())
        config = make_config()
        manager.update_state("alpha", "FIGI1", config_hash=config.config_hash,
                             data={"position": 10})
        before = manager.get_state("alpha", "FIGI1",
                                   config_hash=config.config_hash).to_json()
        coordinator, _, _ = make_coord(manager)
        report = run(coordinator, config, price=None)  # цена не передана
        assert report.state_updated is False
        after = manager.get_state("alpha", "FIGI1",
                                  config_hash=config.config_hash).to_json()
        assert before == after

    def test_garbage_evaluator_result_blocked(self):
        manager = StrategyStateManager(StateStore())
        config = make_config()
        coordinator, _, protective = make_coord(manager,
                                                protective="garbage")
        report = run(coordinator, config, price=make_price())
        assert report.protective_result.outcome is \
            ExitOutcome.EVALUATION_BLOCKED
        assert report.protective_result.reason_code == \
            "INVALID_EVALUATOR_RESULT"
        assert report.merged.final_outcome is \
            ExitMergeOutcome.INCOMPLETE_PROTECTIVE_EVALUATION
        assert report.state_updated is False

    def test_subclass_result_from_evaluator_rejected(self):
        class TamperedExit(ExitEvaluation):
            def __post_init__(self):
                pass

        class ForgingEvaluator:
            def evaluate_exit(self, request):
                return TamperedExit(request.strategy_id, request.config_hash,
                                    request.figi,
                                    ExitOutcome.PROTECTIVE_EXIT,
                                    ExitDecisionSource.PROTECTIVE,
                                    "FORGED", "STOP_LOSS")

        manager = StrategyStateManager(StateStore())
        config = make_config()
        coordinator = ExitDecisionCoordinator(
            manager=manager,
            strategic_evaluator=CountingEvaluator(
                ExitDecisionSource.STRATEGIC),
            protective_evaluator=ForgingEvaluator(),
            clock=lambda: FIXED_CLOCK)
        report = run(coordinator, config, price=make_price())
        assert report.protective_result.reason_code == \
            "INVALID_EVALUATOR_RESULT"
        assert report.state_updated is False

    def test_partial_evaluator_results_impossible_in_report(self):
        report = ExitDecisionCoordinator.__new__(ExitDecisionCoordinator)
        # Прямая проверка инварианта отчёта: один результат без второго
        # невозможен (fail-closed).
        from strategy_contracts import ExitDecisionReport, PriceCheckResult
        price_check = PriceCheckResult(
            outcome=PriceCheckOutcome.PRICE_OK, reason_code="PRICE_OK",
            price=make_price())
        with pytest.raises(Exception):
            ExitDecisionReport(
                strategy_id="alpha", config_hash=make_config().config_hash,
                figi="FIGI1", price_check=price_check,
                merged=ExitDecisionCoordinator.__new__(object) if False
                else _merged_for_report(make_config()),
                strategic_result=None,
                protective_result=_protective(make_config()),
                state_updated=False, decided_at=FIXED_CLOCK)


def _protective(config):
    return ExitEvaluation.protective_exit(
        config.strategy_id, config.config_hash, "FIGI1",
        "STOP_LOSS", "STOP_LOSS_HIT")


def _merged_for_report(config):
    from strategy_contracts import ExitMergeResult, merge_exit_evaluations
    strategic = ExitEvaluation.no_exit(
        config.strategy_id, config.config_hash, "FIGI1",
        ExitDecisionSource.STRATEGIC, "NO_EXIT_RULES")
    protective = _protective(config)
    return merge_exit_evaluations(strategic, protective)


# ===========================================================================
# ТЗ §6.14 — атрибуция и защита от подмены config_hash
# ===========================================================================

class TestCoordinatorAttribution:
    def test_report_attribution_matches_config(self):
        manager = StrategyStateManager(StateStore())
        config = make_config()
        coordinator, _, _ = make_coord(manager)
        report = run(coordinator, config, price=make_price())
        assert report.strategy_id == config.strategy_id
        assert report.config_hash == config.config_hash
        assert report.figi == "FIGI1"
        assert report.strategic_result.strategy_id == config.strategy_id
        assert report.strategic_result.config_hash == config.config_hash
        assert report.protective_result.figi == "FIGI1"

    def test_fabricated_config_hash_rejected_by_stage_a2_1_recheck(self):
        """Подмена config_hash: объект, СОБРАННЫЙ в обход публичного API
        (object.__setattr__ вместо __post_init__) с хешем, не
        соответствующим фактическим параметрам, отклоняется
        ПЕРЕПРОВЕРКОЙ Stage A.2.1 (AttributionContext.from_config)
        до любой оценки. Через публичный API Stage A.2 такой объект
        создать невозможно: StrategyConfig.__post_init__ отвергает
        несовпадающий хеш при создании."""
        manager = StrategyStateManager(StateStore())
        forged = StrategyConfig.__new__(StrategyConfig)
        object.__setattr__(forged, "strategy_id", "alpha")
        object.__setattr__(forged, "strategy_version", "1.0.0")
        object.__setattr__(forged, "params", {"n": 3})
        object.__setattr__(forged, "config_hash",
                           compute_config_hash("alpha", "1.0.0", {"n": 999}))
        object.__setattr__(forged, "origin", "forged")
        object.__setattr__(forged, "metadata", {})
        coordinator, _, _ = make_coord(manager)
        with pytest.raises(CoordinatorViolationError):
            run(coordinator, forged, price=make_price())

    def test_state_config_hash_mismatch_propagates_unmasked(self):
        """Несовпадение config_hash сохранённого состояния:
        StateConfigMismatchError пробрасывается как есть (не маскируется
        пустыми значениями), состояние не переносится."""
        manager = StrategyStateManager(StateStore())
        old_config = make_config(params={"n": 3})
        new_config = make_config(params={"n": 7})
        manager.get_state("alpha", "FIGI1", config_hash=old_config.config_hash)
        coordinator, _, _ = make_coord(manager)
        with pytest.raises(StateConfigMismatchError):
            run(coordinator, new_config, price=make_price())

    def test_corrupted_state_error_propagates_unmasked(self, tmp_path):
        """Повреждённая запись состояния: StateCorruptionError
        пробрасывается из координатора как есть (ошибки состояния
        не маскируются, ТЗ §3.5)."""
        store = StateStore(path=str(tmp_path))
        manager = StrategyStateManager(store)
        config = make_config()
        manager.get_state("alpha", "FIGI1",
                          config_hash=config.config_hash)
        # Повреждаем содержимое файла: подменяем ключ записи чужим.
        names = [n for n in sorted(__import__("os").listdir(tmp_path))
                 if n.endswith(".json")]
        target = tmp_path / names[0]
        payload = json.loads(target.read_text(encoding="utf-8"))
        payload["strategy_id"] = "someone-else"
        payload["figi"] = "FIGI1"
        target.write_text(json.dumps(payload), encoding="utf-8")
        coordinator, _, _ = make_coord(manager)
        with pytest.raises(StateCorruptionError):
            run(coordinator, config, price=make_price())


# ===========================================================================
# ТЗ §6.15–§6.16 — изоляция состояний
# ===========================================================================

class TestStateIsolation:
    def test_two_strategies_same_figi_isolated(self):
        """ТЗ §6.15: состояние стратегии A не влияет на стратегию B."""
        manager = StrategyStateManager(StateStore())
        config_a = make_config(strategy_id="alpha")
        config_b = make_config(strategy_id="beta", params={"n": 5})
        coord_a, _, _ = make_coord(manager)
        coord_b, _, _ = make_coord(manager,
                                   protective="protective_exit")
        run(coord_a, config_a, figi="FIGI1")
        run(coord_b, config_b, figi="FIGI1")
        state_a = manager.get_state("alpha", "FIGI1",
                                    config_hash=config_a.config_hash)
        state_b = manager.get_state("beta", "FIGI1",
                                    config_hash=config_b.config_hash)
        assert state_a.data["last_exit_evaluation"]["outcome"] == "NO_EXIT"
        assert state_b.data["last_exit_evaluation"]["outcome"] == \
            "PROTECTIVE_EXIT"
        assert state_a.strategy_id == "alpha"
        assert state_b.strategy_id == "beta"
        assert manager.list_states() is not None
        keys = {s.key() for s in manager.list_states()}
        assert ("alpha", "FIGI1") in keys and ("beta", "FIGI1") in keys

    def test_same_strategy_two_figi_isolated(self):
        """ТЗ §6.16: состояние инструмента X не влияет на инструмент Y."""
        manager = StrategyStateManager(StateStore())
        config = make_config()
        coord_x, _, _ = make_coord(manager)
        coord_y, _, _ = make_coord(manager, protective="protective_exit")
        run(coord_x, config, figi="FIGI1")
        run(coord_y, config, figi="FIGI2")
        state_x = manager.get_state("alpha", "FIGI1",
                                    config_hash=config.config_hash)
        state_y = manager.get_state("alpha", "FIGI2",
                                    config_hash=config.config_hash)
        assert state_x.data["last_exit_evaluation"]["outcome"] == "NO_EXIT"
        assert state_y.data["last_exit_evaluation"]["outcome"] == \
            "PROTECTIVE_EXIT"
        assert state_x.figi == "FIGI1" and state_y.figi == "FIGI2"

    def test_isolation_persists_in_persistent_store(self, tmp_path):
        """ТЗ §6.15/§6.16 + Stage B: изоляция и запись в persistent-режиме
        (файлы создаются, читаются после «перезапуска»)."""
        store = StateStore(path=str(tmp_path))
        manager = StrategyStateManager(store)
        config_a = make_config(strategy_id="alpha")
        config_b = make_config(strategy_id="beta", params={"n": 5})
        coord_a, _, _ = make_coord(manager)
        coord_b, _, _ = make_coord(manager, protective="protective_exit")
        run(coord_a, config_a, figi="FIGI1")
        run(coord_b, config_b, figi="FIGI2")

        # Новый менеджер на том же пути — состояние восстановлено.
        manager2 = StrategyStateManager(StateStore(path=str(tmp_path)))
        state_a2 = manager2.get_state("alpha", "FIGI1",
                                      config_hash=config_a.config_hash)
        state_b2 = manager2.get_state("beta", "FIGI2",
                                      config_hash=config_b.config_hash)
        assert state_a2.data["last_exit_evaluation"]["outcome"] == "NO_EXIT"
        assert state_b2.data["last_exit_evaluation"]["outcome"] == \
            "PROTECTIVE_EXIT"
        assert ("alpha", "FIGI1") != ("beta", "FIGI2")
        names = sorted(n for n in __import__("os").listdir(tmp_path)
                       if n.endswith(".json"))
        assert len(names) == 2  # ровно две записи, ровно по одной на пару


# ===========================================================================
# ТЗ §6.17 — конкурентное обновление состояния через Stage B.1
# ===========================================================================

class TestConcurrentStateUpdates:
    def test_parallel_managers_shared_store_no_lost_updates(self, tmp_path):
        """ТЗ §6.17: два менеджера на РАЗНЫХ экземплярах StateStore одного
        пути + координаторы — параллельные атомарные read-modify-write не
        теряют обновлений (Stage B.1, общий RLock каталога)."""
        store1 = StateStore(path=str(tmp_path))
        store2 = StateStore(path=str(tmp_path))
        manager1 = StrategyStateManager(store1)
        manager2 = StrategyStateManager(store2)
        config = make_config()
        coord1, _, _ = make_coord(manager1)
        coord2, _, _ = make_coord(manager2, protective="protective_exit")

        # Прогрев: создаём запись состояния пары.
        run(coord1, config, price=make_price())

        increments = {"m1": 40, "m2": 40}
        errors = []

        def worker(manager, label, count):
            for _ in range(count):
                try:
                    manager.update_state(
                        "alpha", "FIGI1",
                        config_hash=config.config_hash,
                        updater=lambda current: {
                            **ss.unfreeze(current.data),
                            "counter":
                                current.data.get("counter", 0) + 1,
                        })
                except Exception as exc:  # pragma: no cover
                    errors.append((label, exc))

        with ThreadPoolExecutor(max_workers=8) as pool:
            futures = []
            for manager, label, count in (
                    (manager1, "m1", increments["m1"]),
                    (manager2, "m2", increments["m2"])):
                for _ in range(4):  # 4 потока на менеджера
                    futures.append(pool.submit(worker, manager, label, 10))
            # Параллельно — координаторные циклы с записью в состояние.
            for i in range(8):
                futures.append(pool.submit(
                    run, coord1 if i % 2 == 0 else coord2, config,
                    price=make_price()))
            for future in futures:
                future.result()

        assert errors == []
        state = manager1.get_state("alpha", "FIGI1",
                                   config_hash=config.config_hash)
        assert state.data["counter"] == \
            increments["m1"] + increments["m2"]
        record = state.data["last_exit_evaluation"]
        assert record["outcome"] in ("NO_EXIT", "PROTECTIVE_EXIT")
        assert record["config_hash"] == config.config_hash

    def test_repeated_concurrent_runs_deterministic_totals(self, tmp_path):
        """ТЗ §6.17 (детерминизм): повторный параллельный прогон с теми же
        параметрами даёт ТОТ же итоговый счётчик (обновления не теряются
        ни в одном прогоне)."""
        totals = []
        for _ in range(3):
            with __import__("tempfile").TemporaryDirectory() as tmp:
                manager = StrategyStateManager(
                    StateStore(path=tmp))
                config = make_config()
                coordinator, _, _ = make_coord(manager)
                with ThreadPoolExecutor(max_workers=6) as pool:
                    futures = [pool.submit(
                        manager.update_state, "alpha", "FIGI1",
                        config_hash=config.config_hash,
                        updater=lambda current: {
                            **ss.unfreeze(current.data),
                            "counter": current.data.get("counter", 0) + 1,
                        }) for _ in range(50)]
                    for future in futures:
                        future.result()
                state = manager.get_state("alpha", "FIGI1",
                                          config_hash=config.config_hash)
                totals.append(state.data["counter"])
        assert totals == [50, 50, 50]


# ===========================================================================
# Контракт использования координатора (misuse — исключения)
# ===========================================================================

class TestCoordinatorMisuse:
    def test_rejects_wrong_manager_type(self):
        with pytest.raises(CoordinatorViolationError):
            ExitDecisionCoordinator(
                manager="not-a-manager",
                strategic_evaluator=CountingEvaluator(
                    ExitDecisionSource.STRATEGIC),
                protective_evaluator=CountingEvaluator(
                    ExitDecisionSource.PROTECTIVE))

    def test_rejects_manager_without_exact_type(self):
        class FakeManager:
            pass
        with pytest.raises(CoordinatorViolationError):
            ExitDecisionCoordinator(
                manager=FakeManager(),
                strategic_evaluator=CountingEvaluator(
                    ExitDecisionSource.STRATEGIC),
                protective_evaluator=CountingEvaluator(
                    ExitDecisionSource.PROTECTIVE))

    def test_rejects_evaluator_without_evaluate_exit(self):
        manager = StrategyStateManager(StateStore())
        with pytest.raises(CoordinatorViolationError):
            ExitDecisionCoordinator(
                manager=manager,
                strategic_evaluator=object(),
                protective_evaluator=CountingEvaluator(
                    ExitDecisionSource.PROTECTIVE))

    def test_rejects_wrong_config_type(self):
        manager = StrategyStateManager(StateStore())
        coordinator, _, _ = make_coord(manager)
        with pytest.raises(CoordinatorViolationError):
            run(coordinator, {"strategy_id": "alpha"})

    def test_rejects_bad_figi(self):
        manager = StrategyStateManager(StateStore())
        config = make_config()
        coordinator, _, _ = make_coord(manager)
        with pytest.raises(CoordinatorViolationError):
            run(coordinator, config, figi="../traversal",
                price_required=False)  # без цены: figi проверяется раньше

    def test_rejects_non_bool_price_required(self):
        manager = StrategyStateManager(StateStore())
        config = make_config()
        coordinator, _, _ = make_coord(manager)
        with pytest.raises(CoordinatorViolationError):
            coordinator.evaluate_and_record(
                config=config, figi="FIGI1", price_required="yes",
                price_max_age_seconds=120.0, price=make_price())

    def test_rejects_bad_max_age(self):
        manager = StrategyStateManager(StateStore())
        config = make_config()
        coordinator, _, _ = make_coord(manager)
        with pytest.raises(CoordinatorViolationError):
            coordinator.evaluate_and_record(
                config=config, figi="FIGI1", price_required=True,
                price_max_age_seconds=-5.0, price=make_price())

    def test_rejects_naive_now(self):
        manager = StrategyStateManager(StateStore())
        config = make_config()
        coordinator, _, _ = make_coord(manager)
        with pytest.raises(CoordinatorViolationError):
            coordinator.evaluate_and_record(
                config=config, figi="FIGI1", price_required=True,
                price_max_age_seconds=120.0, price=make_price(),
                now=datetime(2026, 11, 28, 12, 0, 0))  # naive


# ===========================================================================
# Stage C.1 — price gate СТРОГО ДО доступа к состоянию
#
# Дефект: manager.get_state Stage B.1 создаёт запись при отсутствии,
# поэтому прежний порядок (get_state -> проверка цены) изменял
# хранилище ЕЩЁ ДО блокировки оценки при плохой цене. Исправленный
# порядок: config/FIGI -> проверка цены -> (только после прохождения
# price gate) manager.get_state -> оценщики -> merge -> запись.
#
# Проверяется ФАКТИЧЕСКОЕ состояние хранилища: публичный
# StateStore.get_state(), файлы persistent-хранилища, полный to_json()
# записи (включая updated_at) — а не только report.state_updated.
# ===========================================================================

def _json_file_names(tmp_path):
    """Имена JSON-записей состояния в persistent-хранилище."""
    return sorted(n for n in os.listdir(str(tmp_path))
                  if n.endswith(".json"))


class TestPriceGateBeforeStateAccess:
    """ТЗ Stage C.1 §4: блокирующая цена не трогает StateStore."""

    # --- сценарии 1-3: блокирующая цена + ОТСУТСТВУЮЩАЯ запись -----------

    def test_missing_price_missing_record_no_state_created(self, tmp_path):
        """Сценарий 1: цена отсутствует + записи нет.

        INCOMPLETE_PRICE_EVALUATION; оба оценщика не вызваны;
        StateStore.get_state(...) возвращает None; файл состояния
        НЕ создан."""
        store = StateStore(path=str(tmp_path))
        manager = StrategyStateManager(store)
        config = make_config()
        coordinator, strategic, protective = make_coord(manager)
        report = run(coordinator, config, price=None)
        assert report.merged.final_outcome is \
            ExitMergeOutcome.INCOMPLETE_PRICE_EVALUATION
        assert report.merged.reason_code == "PRICE_MISSING"
        assert report.strategic_result is None
        assert report.protective_result is None
        assert strategic.calls == 0 and protective.calls == 0
        assert report.state_updated is False
        # Публичный StateStore.get_state(): записи НЕТ.
        assert store.get_state("alpha", "FIGI1") is None
        # Файл состояния НЕ создан.
        assert _json_file_names(tmp_path) == []

    def test_stale_price_missing_record_no_state_created(self, tmp_path):
        """Сценарий 2: устаревшая цена + записи нет — те же проверки,
        никаких новых файлов состояния."""
        store = StateStore(path=str(tmp_path))
        manager = StrategyStateManager(store)
        config = make_config()
        coordinator, strategic, protective = make_coord(manager)
        stale = make_price(offset_seconds=-600.0)
        report = run(coordinator, config, price=stale, max_age=120.0)
        assert report.merged.final_outcome is \
            ExitMergeOutcome.INCOMPLETE_PRICE_EVALUATION
        assert report.merged.reason_code == "PRICE_STALE"
        assert strategic.calls == 0 and protective.calls == 0
        assert report.state_updated is False
        assert store.get_state("alpha", "FIGI1") is None
        assert _json_file_names(tmp_path) == []

    def test_foreign_figi_price_missing_record_no_state_created(
            self, tmp_path):
        """Сценарий 3: чужой FIGI у цены + записи нет — те же проверки."""
        store = StateStore(path=str(tmp_path))
        manager = StrategyStateManager(store)
        config = make_config()
        coordinator, strategic, protective = make_coord(manager)
        foreign = make_price(figi="OTHER")
        report = run(coordinator, config, price=foreign)
        assert report.merged.final_outcome is \
            ExitMergeOutcome.INCOMPLETE_PRICE_EVALUATION
        assert report.merged.reason_code == "PRICE_FOREIGN_FIGI"
        assert strategic.calls == 0 and protective.calls == 0
        assert report.state_updated is False
        assert store.get_state("alpha", "FIGI1") is None
        assert _json_file_names(tmp_path) == []

    # --- сценарии 4-5: блокирующая цена + СУЩЕСТВУЮЩАЯ запись ------------

    def test_missing_price_existing_record_untouched(self, tmp_path):
        """Сценарий 4: цена отсутствует + запись существует.

        Исходный to_json() полностью совпадает после вызова;
        updated_at не изменился; данные не изменились; файл записи
        на диске побайтово тот же."""
        store = StateStore(path=str(tmp_path))
        manager = StrategyStateManager(store)
        config = make_config()
        manager.update_state("alpha", "FIGI1",
                             config_hash=config.config_hash,
                             data={"position": 10, "avg_price": 99.5})
        before_state = store.get_state("alpha", "FIGI1")
        before = before_state.to_json()
        before_updated_at = before_state.updated_at
        coordinator, strategic, protective = make_coord(manager)
        report = run(coordinator, config, price=None)
        assert report.merged.final_outcome is \
            ExitMergeOutcome.INCOMPLETE_PRICE_EVALUATION
        assert report.merged.reason_code == "PRICE_MISSING"
        assert strategic.calls == 0 and protective.calls == 0
        assert report.state_updated is False
        after_state = store.get_state("alpha", "FIGI1")
        assert after_state is not None
        # Полное совпадение (данные + updated_at + created_at + хеш).
        assert after_state.to_json() == before
        assert after_state.updated_at == before_updated_at
        assert after_state.data["position"] == 10
        assert after_state.data["avg_price"] == 99.5
        assert "last_exit_evaluation" not in after_state.data
        # Файл записи на диске побайтово не изменился.
        names = _json_file_names(tmp_path)
        assert len(names) == 1
        with open(os.path.join(str(tmp_path), names[0]),
                  "r", encoding="utf-8") as fh:
            assert fh.read() == before

    def test_stale_price_existing_record_untouched(self, tmp_path):
        """Сценарий 5: устаревшая цена + запись существует — те же
        проверки: to_json() совпадает, updated_at не изменился,
        файл побайтово тот же."""
        store = StateStore(path=str(tmp_path))
        manager = StrategyStateManager(store)
        config = make_config()
        manager.update_state("alpha", "FIGI1",
                             config_hash=config.config_hash,
                             data={"position": 3, "mode": "hold"})
        before_state = store.get_state("alpha", "FIGI1")
        before = before_state.to_json()
        before_updated_at = before_state.updated_at
        coordinator, strategic, protective = make_coord(manager)
        stale = make_price(offset_seconds=-600.0)
        report = run(coordinator, config, price=stale, max_age=120.0)
        assert report.merged.final_outcome is \
            ExitMergeOutcome.INCOMPLETE_PRICE_EVALUATION
        assert report.merged.reason_code == "PRICE_STALE"
        assert strategic.calls == 0 and protective.calls == 0
        assert report.state_updated is False
        after_state = store.get_state("alpha", "FIGI1")
        assert after_state is not None
        assert after_state.to_json() == before
        assert after_state.updated_at == before_updated_at
        assert after_state.data["position"] == 3
        assert "last_exit_evaluation" not in after_state.data
        names = _json_file_names(tmp_path)
        assert len(names) == 1
        with open(os.path.join(str(tmp_path), names[0]),
                  "r", encoding="utf-8") as fh:
            assert fh.read() == before

    # --- сценарий 6: price_required=False + price=None -------------------

    def test_price_not_required_none_price_evaluators_called(self):
        """Сценарий 6: цена не требуется и не передана — штатное
        поведение Stage C сохраняется: оценщики вызываются, итог
        записывается в состояние (допустимый исход NO_EXIT)."""
        manager = StrategyStateManager(StateStore())
        config = make_config()
        coordinator, strategic, protective = make_coord(manager)
        report = run(coordinator, config, price=None, price_required=False)
        assert report.price_check.outcome is PriceCheckOutcome.PRICE_MISSING
        assert strategic.calls == 1 and protective.calls == 1
        assert report.merged.final_outcome is ExitMergeOutcome.NO_EXIT
        assert report.state_updated is True
        state = manager.get_state("alpha", "FIGI1",
                                  config_hash=config.config_hash)
        record = state.data["last_exit_evaluation"]
        assert record["outcome"] == "NO_EXIT"
        assert record["strategy_id"] == "alpha"
        assert record["figi"] == "FIGI1"

    # --- сценарий 7: валидная цена ----------------------------------------

    def test_valid_price_state_obtained_and_updated_per_stage_c_rules(self):
        """Сценарий 7: валидная цена — состояние получается штатно,
        оценщики вызываются, существующая запись обновляется ТОЛЬКО по
        правилам Stage C (добавляется last_exit_evaluation, прочие
        данные записи сохраняются)."""
        manager = StrategyStateManager(StateStore())
        config = make_config()
        manager.update_state("alpha", "FIGI1",
                             config_hash=config.config_hash,
                             data={"position": 7, "note": "kept"})
        coordinator, strategic, protective = make_coord(
            manager, protective="protective_exit")
        report = run(coordinator, config, price=make_price())
        assert report.price_check.outcome is PriceCheckOutcome.PRICE_OK
        assert report.price_check.price is not None
        assert strategic.calls == 1 and protective.calls == 1
        assert report.merged.final_outcome is ExitMergeOutcome.PROTECTIVE_EXIT
        assert report.state_updated is True
        state = manager.get_state("alpha", "FIGI1",
                                  config_hash=config.config_hash)
        record = state.data["last_exit_evaluation"]
        assert record["outcome"] == "PROTECTIVE_EXIT"
        assert record["config_hash"] == config.config_hash
        assert record["figi"] == "FIGI1"
        assert record["decided_at"] == FIXED_CLOCK
        # Существующие данные записи сохранены: updater Stage C только
        # добавляет ключ решения выхода.
        assert state.data["position"] == 7
        assert state.data["note"] == "kept"
