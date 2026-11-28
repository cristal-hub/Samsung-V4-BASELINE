# tests/test_stage_c_contracts.py — SAMSUNG V4 — STAGE C.
#
# Типизированные контракты входа/выхода и детерминированное объединение
# выходов. Покрытие обязательных сценариев ТЗ Stage C §6:
#   §6.1  все допустимые состояния Entry contract;
#   §6.2  отклонение некорректного Entry result;
#   §6.3  все допустимые состояния Exit contract;
#   §6.4  отклонение некорректного Exit result;
#   §6.5  защитный выход не подавляется стратегическим;
#   §6.6  стратегический выход не отменяет защитный;
#   §6.7  детерминированность объединения;
#   §6.8  конфликтующие причины выхода;
#   §6.9  отсутствие цены (fail-closed);
#   §6.10 некорректная цена (fail-closed);
#   §6.11 устаревшая цена (fail-closed);
#   §6.14 корректная атрибуция strategy_id/config_hash/FIGI.
#
# Все тесты offline, без сети и брокера; никаких заявок; старые файлы
# Samsung не затрагиваются. Регрессия Stage A.2.1 / Stage B.1 (§6.18–§6.19)
# обеспечивается полным и каноническим прогонами (см. TEST_RESULTS_STAGE_C).

import math
from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from strategy_api import (
    EntrySignalInput,
    Signal,
    SignalDirection,
    Strategy,
    StrategyConfig,
    compute_config_hash,
)
import strategy_contracts as sc
from strategy_contracts import (
    CoordinatorViolationError,
    EntryContractViolationError,
    EntryEvaluation,
    EntryEvaluationRunner,
    EntryOutcome,
    ExitContractViolationError,
    ExitDecisionSource,
    ExitEvaluation,
    ExitEvaluationRequest,
    ExitMergeOutcome,
    ExitMergeViolationError,
    ExitOutcome,
    PriceCheckOutcome,
    PriceData,
    PriceDataViolationError,
    check_price,
    merge_exit_evaluations,
    validate_entry_evaluation,
    validate_exit_evaluation,
)


NOW = datetime(2026, 11, 28, 12, 0, 0, tzinfo=timezone.utc)

STRATEGY_ID = "alpha"
CONFIG_HASH = compute_config_hash(STRATEGY_ID, "1.0.0", {"n": 3})
FIGI = "FIGI1"


def make_config(strategy_id=STRATEGY_ID, params=None):
    params = {"n": 3} if params is None else params
    return StrategyConfig(
        strategy_id=strategy_id,
        strategy_version="1.0.0",
        params=params,
        config_hash=compute_config_hash(strategy_id, "1.0.0", params),
    )


def make_price(figi=FIGI, price=100.0, offset_seconds=-30.0,
               source="test-feed"):
    ts = NOW + timedelta(seconds=offset_seconds)
    return PriceData(
        figi=figi,
        price=price,
        timestamp=ts.isoformat(timespec="microseconds").replace("+00:00",
                                                                "Z"),
        source=source,
    )


# ===========================================================================
# Общая проверка атрибуции контрактов (ТЗ §6.14)
# ===========================================================================

class TestContractAttribution:
    """ТЗ §6.14: каждый результат несёт strategy_id, config_hash, FIGI."""

    def test_entry_evaluation_carries_full_attribution(self):
        result = EntryEvaluation.allowed(STRATEGY_ID, CONFIG_HASH, FIGI,
                                         "ENTRY_SIGNAL_BUY")
        assert result.strategy_id == STRATEGY_ID
        assert result.config_hash == CONFIG_HASH
        assert result.figi == FIGI
        assert result.outcome is EntryOutcome.ENTRY_ALLOWED
        assert result.reason_code == "ENTRY_SIGNAL_BUY"

    def test_exit_evaluation_carries_full_attribution(self):
        result = ExitEvaluation.protective_exit(
            STRATEGY_ID, CONFIG_HASH, FIGI, "STOP_LOSS", "STOP_LOSS_HIT")
        assert result.strategy_id == STRATEGY_ID
        assert result.config_hash == CONFIG_HASH
        assert result.figi == FIGI
        assert result.outcome is ExitOutcome.PROTECTIVE_EXIT
        assert result.decision_source is ExitDecisionSource.PROTECTIVE

    def test_contract_rejects_tampered_config_hash_format(self):
        with pytest.raises(EntryContractViolationError):
            EntryEvaluation.allowed(STRATEGY_ID, "deadbeef", FIGI, "OK_CODE")

    def test_contract_rejects_foreign_figi(self):
        with pytest.raises(ExitContractViolationError):
            ExitEvaluation.strategic_exit(STRATEGY_ID, CONFIG_HASH,
                                          "../evil", "TAKE_PROFIT", "R")

    def test_validator_checks_expected_attribution(self):
        result = ExitEvaluation.no_exit(STRATEGY_ID, CONFIG_HASH, FIGI,
                                        ExitDecisionSource.STRATEGIC,
                                        "NO_EXIT_RULES")
        validated = validate_exit_evaluation(
            result, expected_strategy_id=STRATEGY_ID,
            expected_config_hash=CONFIG_HASH, expected_figi=FIGI)
        assert validated is result
        with pytest.raises(ExitContractViolationError):
            validate_exit_evaluation(result, expected_strategy_id="beta")
        with pytest.raises(ExitContractViolationError):
            validate_exit_evaluation(result, expected_figi="FIGI2")

    def test_entry_validator_checks_expected_attribution(self):
        result = EntryEvaluation.no_signal(STRATEGY_ID, CONFIG_HASH, FIGI,
                                           "NO_SIGNAL_HOLD")
        assert validate_entry_evaluation(result,
                                         expected_strategy_id=STRATEGY_ID) \
            is result
        with pytest.raises(EntryContractViolationError):
            validate_entry_evaluation(result, expected_config_hash="0" * 64)


# ===========================================================================
# ТЗ §6.1 — все допустимые состояния Entry contract
# ===========================================================================

class TestEntryContractStates:
    """ТЗ §6.1: все допустимые состояния Entry contract создаются
    и однозначно различаются; только ENTRY_ALLOWED допускает вход."""

    ENTRY_STATES = [
        (EntryOutcome.ENTRY_ALLOWED, "allowed", "ENTRY_SIGNAL_BUY"),
        (EntryOutcome.NO_SIGNAL, "no_signal", "NO_SIGNAL_HOLD"),
        (EntryOutcome.ENTRY_FORBIDDEN, "forbidden", "ENTRY_FORBIDDEN_SELL"),
        (EntryOutcome.DATA_INSUFFICIENT, "data_insufficient",
         "CANDLES_MISSING"),
        (EntryOutcome.INVALID_STRATEGY_RESULT, "invalid_strategy_result",
         "RESULT_WRONG_TYPE"),
        (EntryOutcome.EVALUATION_ERROR, "evaluation_error",
         "EVALUATOR_RAISED"),
    ]

    @pytest.mark.parametrize("outcome,factory,reason", ENTRY_STATES)
    def test_all_entry_states_constructible(self, outcome, factory, reason):
        result = getattr(EntryEvaluation, factory)(
            STRATEGY_ID, CONFIG_HASH, FIGI, reason,
            {"detail": "test"})
        assert type(result) is EntryEvaluation
        assert result.outcome is outcome
        assert result.reason_code == reason
        assert result.diagnostics["detail"] == "test"
        assert validate_entry_evaluation(result) is result

    def test_only_allowed_state_permits_entry(self):
        """Ни одно состояние, кроме ENTRY_ALLOWED, не может быть
        истолковано как разрешение входа (fail-closed, ТЗ §3.1)."""
        permitting = {EntryOutcome.ENTRY_ALLOWED}
        for outcome in EntryOutcome:
            if outcome in permitting:
                continue
            result = EntryEvaluation(STRATEGY_ID, CONFIG_HASH, FIGI,
                                     outcome, "SOME_REASON")
            assert result.outcome is not EntryOutcome.ENTRY_ALLOWED

    def test_entry_states_are_frozen(self):
        result = EntryEvaluation.allowed(STRATEGY_ID, CONFIG_HASH, FIGI,
                                         "ENTRY_SIGNAL_BUY")
        with pytest.raises(Exception):
            result.reason_code = "CHANGED"
        with pytest.raises(Exception):
            result.diagnostics["injection"] = True


# ===========================================================================
# ТЗ §6.2 — отклонение некорректного Entry result
# ===========================================================================

class TestEntryContractRejections:
    """ТЗ §6.2: некорректные результаты входа отклоняются (fail-closed);
    подклассы не проходят границу потребителя."""

    def test_rejects_string_outcome(self):
        with pytest.raises(EntryContractViolationError):
            EntryEvaluation(STRATEGY_ID, CONFIG_HASH, FIGI, "ENTRY_ALLOWED",
                            "REASON")

    def test_rejects_lowercase_reason_code(self):
        with pytest.raises(EntryContractViolationError):
            EntryEvaluation.allowed(STRATEGY_ID, CONFIG_HASH, FIGI, "oops")

    def test_rejects_empty_reason_code(self):
        with pytest.raises(EntryContractViolationError):
            EntryEvaluation.allowed(STRATEGY_ID, CONFIG_HASH, FIGI, "")

    def test_rejects_non_json_diagnostics(self):
        class NotJSON:
            pass
        with pytest.raises(EntryContractViolationError):
            EntryEvaluation.allowed(STRATEGY_ID, CONFIG_HASH, FIGI, "CODE",
                                    {"object": NotJSON()})

    def test_rejects_nan_diagnostics(self):
        with pytest.raises(EntryContractViolationError):
            EntryEvaluation.allowed(STRATEGY_ID, CONFIG_HASH, FIGI, "CODE",
                                    {"price": float("nan")})

    def test_validator_rejects_wrong_type_and_none(self):
        for bad in (None, "ENTRY_ALLOWED", {"outcome": "ENTRY_ALLOWED"}):
            with pytest.raises(EntryContractViolationError):
                validate_entry_evaluation(bad)

    def test_validator_rejects_subclass(self):
        class TamperedEntry(EntryEvaluation):
            def __post_init__(self):
                pass  # ослабленная валидация подкласса
        tampered = TamperedEntry(STRATEGY_ID, CONFIG_HASH, FIGI,
                                 EntryOutcome.ENTRY_ALLOWED, "FREE_ENTRY")
        with pytest.raises(EntryContractViolationError):
            validate_entry_evaluation(tampered)


# ===========================================================================
# Entry runner: конвертация ВСЕХ проблем в НЕ-разрешающие состояния
# ===========================================================================

class _RunnerStrategy(Strategy):
    strategy_id = STRATEGY_ID
    strategy_version = "1.0.0"

    def __init__(self, direction=SignalDirection.BUY):
        self._direction = direction

    def param_specs(self):
        return ()

    def evaluate_entry(self, signal_input, config):
        return Signal(strategy_id=config.strategy_id,
                      config_hash=config.config_hash,
                      direction=self._direction,
                      reason="runner-test", figi=signal_input.figi)


class _RaisingStrategy(_RunnerStrategy):
    def evaluate_entry(self, signal_input, config):
        raise RuntimeError("boom during entry evaluation")


class _LiarStrategy(_RunnerStrategy):
    def evaluate_entry(self, signal_input, config):
        return Signal(strategy_id="other-strategy",
                      config_hash=config.config_hash,
                      direction=SignalDirection.BUY, reason="forged")


class _GarbageStrategy(_RunnerStrategy):
    def evaluate_entry(self, signal_input, config):
        return {"direction": "BUY"}  # не Signal


def make_input(figi=FIGI, candles="ok", last_price=10.0):
    frame = pd.DataFrame({"c": [1.0, 2.0]}) if candles == "ok" else candles
    return EntrySignalInput(figi=figi, ticker="TEST", candles=frame,
                            last_price=last_price)


class TestEntryRunner:
    """ТЗ §3.1 + §6.1/§6.2: рантайм-конвертация входа в контракт."""

    def test_buy_maps_to_allowed(self):
        runner = EntryEvaluationRunner()
        result = runner.evaluate(strategy=_RunnerStrategy(
            SignalDirection.BUY), config=make_config(),
            entry_input=make_input())
        assert result.outcome is EntryOutcome.ENTRY_ALLOWED
        assert result.reason_code == "ENTRY_SIGNAL_BUY"
        assert result.diagnostics["direction"] == "BUY"
        assert result.diagnostics["signal_reason"] == "runner-test"

    def test_hold_maps_to_no_signal(self):
        runner = EntryEvaluationRunner()
        result = runner.evaluate(strategy=_RunnerStrategy(
            SignalDirection.HOLD), config=make_config(),
            entry_input=make_input())
        assert result.outcome is EntryOutcome.NO_SIGNAL
        assert result.reason_code == "NO_SIGNAL_HOLD"

    def test_sell_maps_to_forbidden(self):
        runner = EntryEvaluationRunner()
        result = runner.evaluate(strategy=_RunnerStrategy(
            SignalDirection.SELL), config=make_config(),
            entry_input=make_input())
        assert result.outcome is EntryOutcome.ENTRY_FORBIDDEN
        assert result.reason_code == "ENTRY_FORBIDDEN_SELL"

    def test_missing_candles_is_data_insufficient(self):
        runner = EntryEvaluationRunner()
        result = runner.evaluate(strategy=_RunnerStrategy(),
                                 config=make_config(),
                                 entry_input=make_input(candles=None))
        assert result.outcome is EntryOutcome.DATA_INSUFFICIENT
        assert result.reason_code == "CANDLES_MISSING"

    @pytest.mark.parametrize("bad_price", [0.0, -1.0, float("nan"),
                                           float("inf"), "10"])
    def test_invalid_price_is_data_insufficient(self, bad_price):
        runner = EntryEvaluationRunner()
        result = runner.evaluate(strategy=_RunnerStrategy(),
                                 config=make_config(),
                                 entry_input=make_input(
                                     last_price=bad_price))
        assert result.outcome is EntryOutcome.DATA_INSUFFICIENT
        assert result.reason_code == "PRICE_INVALID"

    def test_invalid_figi_is_caller_misuse(self):
        """Некорректный figi — ошибка маршрутизации вызывающего кода:
        fail-fast исключение; контракт с недействительным figi не
        создаётся."""
        runner = EntryEvaluationRunner()
        with pytest.raises(CoordinatorViolationError):
            runner.evaluate(strategy=_RunnerStrategy(), config=make_config(),
                            entry_input=make_input(figi="bad figi!"))

    def test_strategy_exception_never_allows_entry(self):
        runner = EntryEvaluationRunner()
        result = runner.evaluate(strategy=_RaisingStrategy(),
                                 config=make_config(),
                                 entry_input=make_input())
        assert result.outcome is EntryOutcome.EVALUATION_ERROR
        assert result.reason_code == "EVALUATOR_RAISED"
        assert result.diagnostics["exception_type"] == "RuntimeError"

    def test_forged_attribution_rejected(self):
        runner = EntryEvaluationRunner()
        result = runner.evaluate(strategy=_LiarStrategy(),
                                 config=make_config(),
                                 entry_input=make_input())
        assert result.outcome is EntryOutcome.INVALID_STRATEGY_RESULT
        assert result.reason_code == "ATTRIBUTION_MISMATCH"

    def test_non_signal_result_rejected(self):
        runner = EntryEvaluationRunner()
        result = runner.evaluate(strategy=_GarbageStrategy(),
                                 config=make_config(),
                                 entry_input=make_input())
        assert result.outcome is EntryOutcome.INVALID_STRATEGY_RESULT
        assert result.reason_code == "RESULT_WRONG_TYPE"

    def test_unknown_direction_rejected(self):
        class WeirdDirection(_RunnerStrategy):
            def evaluate_entry(self, signal_input, config):
                return Signal(strategy_id=config.strategy_id,
                              config_hash=config.config_hash,
                              direction="MAYBE", reason="x")

        runner = EntryEvaluationRunner()
        result = runner.evaluate(strategy=WeirdDirection(),
                                 config=make_config(),
                                 entry_input=make_input())
        assert result.outcome is EntryOutcome.INVALID_STRATEGY_RESULT
        assert result.reason_code == "DIRECTION_UNKNOWN"

    def test_caller_misuse_raises(self):
        runner = EntryEvaluationRunner()
        with pytest.raises(CoordinatorViolationError):
            runner.evaluate(strategy=_RunnerStrategy(),
                            config={"not": "config"}, entry_input=make_input())
        with pytest.raises(CoordinatorViolationError):
            runner.evaluate(strategy=_RunnerStrategy(),
                            config=make_config(), entry_input={"x": 1})
        with pytest.raises(CoordinatorViolationError):
            runner.evaluate(strategy="not-a-strategy", config=make_config(),
                            entry_input=make_input())


# ===========================================================================
# ТЗ §6.3 — все допустимые состояния Exit contract
# ===========================================================================

class TestExitContractStates:
    """ТЗ §6.3: все допустимые состояния Exit contract создаются;
    стратегический и защитный источники остаются разными."""

    def test_strategic_exit(self):
        result = ExitEvaluation.strategic_exit(STRATEGY_ID, CONFIG_HASH,
                                               FIGI, "TAKE_PROFIT",
                                               "TAKE_PROFIT_HIT")
        assert result.outcome is ExitOutcome.STRATEGIC_EXIT
        assert result.decision_source is ExitDecisionSource.STRATEGIC
        assert result.exit_type == "TAKE_PROFIT"
        assert validate_exit_evaluation(result) is result

    def test_protective_exit(self):
        result = ExitEvaluation.protective_exit(STRATEGY_ID, CONFIG_HASH,
                                                FIGI, "STOP_LOSS",
                                                "STOP_LOSS_HIT")
        assert result.outcome is ExitOutcome.PROTECTIVE_EXIT
        assert result.decision_source is ExitDecisionSource.PROTECTIVE
        assert result.exit_type == "STOP_LOSS"
        assert validate_exit_evaluation(result) is result

    def test_no_exit_strategic_source(self):
        result = ExitEvaluation.no_exit(STRATEGY_ID, CONFIG_HASH, FIGI,
                                        ExitDecisionSource.STRATEGIC,
                                        "NO_EXIT_RULES")
        assert result.outcome is ExitOutcome.NO_EXIT
        assert result.exit_type is None

    def test_no_exit_protective_source(self):
        result = ExitEvaluation.no_exit(STRATEGY_ID, CONFIG_HASH, FIGI,
                                        ExitDecisionSource.PROTECTIVE,
                                        "NO_EXIT_RULES")
        assert result.outcome is ExitOutcome.NO_EXIT
        assert result.exit_type is None

    @pytest.mark.parametrize("source", [ExitDecisionSource.PRICE_GATE,
                                        ExitDecisionSource.STRATEGIC,
                                        ExitDecisionSource.PROTECTIVE])
    def test_evaluation_blocked_all_sources(self, source):
        result = ExitEvaluation.evaluation_blocked(
            STRATEGY_ID, CONFIG_HASH, FIGI, source, "PRICE_MISSING")
        assert result.outcome is ExitOutcome.EVALUATION_BLOCKED
        assert result.decision_source is source
        assert result.exit_type is None
        assert validate_exit_evaluation(result) is result

    def test_decided_at_optional_but_validated(self):
        result = ExitEvaluation.strategic_exit(
            STRATEGY_ID, CONFIG_HASH, FIGI, "TAKE_PROFIT", "TP",
            decided_at="2026-11-28T12:00:00+00:00")
        assert result.decided_at == "2026-11-28T12:00:00+00:00"
        with pytest.raises(ExitContractViolationError):
            ExitEvaluation.strategic_exit(STRATEGY_ID, CONFIG_HASH, FIGI,
                                          "TAKE_PROFIT", "TP",
                                          decided_at="not-a-timestamp")
        with pytest.raises(ExitContractViolationError):
            ExitEvaluation.strategic_exit(STRATEGY_ID, CONFIG_HASH, FIGI,
                                          "TAKE_PROFIT", "TP",
                                          decided_at="2026-11-28T12:00:00")

    def test_exit_states_are_frozen(self):
        result = ExitEvaluation.protective_exit(STRATEGY_ID, CONFIG_HASH,
                                                FIGI, "STOP_LOSS", "SL")
        with pytest.raises(Exception):
            result.outcome = ExitOutcome.NO_EXIT
        with pytest.raises(Exception):
            result.diagnostics["injection"] = True


# ===========================================================================
# ТЗ §6.4 — отклонение некорректного Exit result
# ===========================================================================

class TestExitContractRejections:
    """ТЗ §6.4: несогласованные комбинации исходного состояния и
    источника решения отклоняются; подклассы не проходят границу."""

    def test_strategic_exit_with_protective_source_rejected(self):
        with pytest.raises(ExitContractViolationError):
            ExitEvaluation(STRATEGY_ID, CONFIG_HASH, FIGI,
                           ExitOutcome.STRATEGIC_EXIT,
                           ExitDecisionSource.PROTECTIVE, "R", "TAKE_PROFIT")

    def test_protective_exit_with_strategic_source_rejected(self):
        with pytest.raises(ExitContractViolationError):
            ExitEvaluation(STRATEGY_ID, CONFIG_HASH, FIGI,
                           ExitOutcome.PROTECTIVE_EXIT,
                           ExitDecisionSource.STRATEGIC, "R", "STOP_LOSS")

    def test_exit_without_exit_type_rejected(self):
        with pytest.raises(ExitContractViolationError):
            ExitEvaluation(STRATEGY_ID, CONFIG_HASH, FIGI,
                           ExitOutcome.STRATEGIC_EXIT,
                           ExitDecisionSource.STRATEGIC, "R", None)

    def test_no_exit_with_price_gate_source_rejected(self):
        with pytest.raises(ExitContractViolationError):
            ExitEvaluation(STRATEGY_ID, CONFIG_HASH, FIGI,
                           ExitOutcome.NO_EXIT,
                           ExitDecisionSource.PRICE_GATE, "R", None)

    def test_no_exit_with_exit_type_rejected(self):
        with pytest.raises(ExitContractViolationError):
            ExitEvaluation(STRATEGY_ID, CONFIG_HASH, FIGI,
                           ExitOutcome.NO_EXIT,
                           ExitDecisionSource.STRATEGIC, "R", "STOP_LOSS")

    def test_blocked_with_exit_type_rejected(self):
        with pytest.raises(ExitContractViolationError):
            ExitEvaluation(STRATEGY_ID, CONFIG_HASH, FIGI,
                           ExitOutcome.EVALUATION_BLOCKED,
                           ExitDecisionSource.PRICE_GATE, "PRICE_MISSING",
                           "STOP_LOSS")

    def test_validator_rejects_wrong_type_and_subclass(self):
        with pytest.raises(ExitContractViolationError):
            validate_exit_evaluation(None)
        with pytest.raises(ExitContractViolationError):
            validate_exit_evaluation({"outcome": "STRATEGIC_EXIT"})

        class TamperedExit(ExitEvaluation):
            def __post_init__(self):
                pass  # ослабленная валидация подкласса

        tampered = TamperedExit(STRATEGY_ID, CONFIG_HASH, FIGI,
                                ExitOutcome.PROTECTIVE_EXIT,
                                ExitDecisionSource.PROTECTIVE, "FORGED",
                                "STOP_LOSS")
        with pytest.raises(ExitContractViolationError):
            validate_exit_evaluation(tampered)


# ===========================================================================
# ТЗ §6.5–§6.8 — объединение выходов
# ===========================================================================

def s_exit(reason="TAKE_PROFIT_HIT", exit_type="TAKE_PROFIT"):
    return ExitEvaluation.strategic_exit(STRATEGY_ID, CONFIG_HASH, FIGI,
                                         exit_type, reason)


def p_exit(reason="STOP_LOSS_HIT", exit_type="STOP_LOSS"):
    return ExitEvaluation.protective_exit(STRATEGY_ID, CONFIG_HASH, FIGI,
                                          exit_type, reason)


def s_no(reason="NO_EXIT_RULES"):
    return ExitEvaluation.no_exit(STRATEGY_ID, CONFIG_HASH, FIGI,
                                  ExitDecisionSource.STRATEGIC, reason)


def p_no(reason="NO_EXIT_RULES"):
    return ExitEvaluation.no_exit(STRATEGY_ID, CONFIG_HASH, FIGI,
                                  ExitDecisionSource.PROTECTIVE, reason)


def s_blocked(reason="EVALUATOR_RAISED"):
    return ExitEvaluation.evaluation_blocked(STRATEGY_ID, CONFIG_HASH, FIGI,
                                             ExitDecisionSource.STRATEGIC,
                                             reason)


def p_blocked(reason="PRICE_MISSING",
              source=ExitDecisionSource.PRICE_GATE):
    return ExitEvaluation.evaluation_blocked(STRATEGY_ID, CONFIG_HASH, FIGI,
                                             source, reason)


class TestExitMerging:
    """ТЗ §6.5–§6.8: правила приоритета, детерминированность, конфликты."""

    @pytest.mark.parametrize("strategic,protective,expected", [
        (s_exit(), p_exit(), ExitMergeOutcome.PROTECTIVE_EXIT),
        (s_no(), p_exit(), ExitMergeOutcome.PROTECTIVE_EXIT),
        (s_blocked(), p_exit(), ExitMergeOutcome.PROTECTIVE_EXIT),
        (s_exit(), p_no(), ExitMergeOutcome.STRATEGIC_EXIT),
        (s_no(), p_no(), ExitMergeOutcome.NO_EXIT),
        (s_blocked(), p_no(),
         ExitMergeOutcome.INCOMPLETE_STRATEGIC_EVALUATION),
        (s_exit(), p_blocked(),
         ExitMergeOutcome.INCOMPLETE_PROTECTIVE_EVALUATION),
        (s_no(), p_blocked(),
         ExitMergeOutcome.INCOMPLETE_PROTECTIVE_EVALUATION),
        (s_blocked("EVALUATOR_RAISED"),
         p_blocked("PRICE_STALE", ExitDecisionSource.PROTECTIVE),
         ExitMergeOutcome.INCOMPLETE_PROTECTIVE_EVALUATION),
    ])
    def test_merge_truth_table(self, strategic, protective, expected):
        result = merge_exit_evaluations(strategic, protective)
        assert type(result) is sc.ExitMergeResult
        assert result.final_outcome is expected
        assert result.strategy_id == STRATEGY_ID
        assert result.config_hash == CONFIG_HASH
        assert result.figi == FIGI

    def test_protective_not_suppressed_by_strategic(self):
        """ТЗ §6.5: защитный выход не подавляется стратегическим."""
        result = merge_exit_evaluations(s_exit(), p_exit())
        assert result.final_outcome is ExitMergeOutcome.PROTECTIVE_EXIT
        assert result.decision_source is ExitDecisionSource.PROTECTIVE
        assert result.reason_code == "STOP_LOSS_HIT"
        assert result.exit_type == "STOP_LOSS"
        assert result.diagnostics["note"] == \
            "PROTECTIVE_PRIORITY_OVER_STRATEGIC_EXIT"

    def test_strategic_exit_cannot_cancel_protective(self):
        """ТЗ §6.6: стратегический выход не отменяет защитный; оба
        источника и обе причины сохраняются в итоге."""
        result = merge_exit_evaluations(
            s_exit("STRATEGIC_REASON_X", "TAKE_PROFIT"),
            p_exit("PROTECTIVE_REASON_Y", "STOP_LOSS"))
        assert result.final_outcome is ExitMergeOutcome.PROTECTIVE_EXIT
        assert result.reason_code == "PROTECTIVE_REASON_Y"
        assert result.diagnostics["strategic"]["reason_code"] == \
            "STRATEGIC_REASON_X"
        assert result.diagnostics["protective"]["reason_code"] == \
            "PROTECTIVE_REASON_Y"

    def test_missing_strategic_exit_does_not_cancel_protective(self):
        result = merge_exit_evaluations(s_no(), p_exit())
        assert result.final_outcome is ExitMergeOutcome.PROTECTIVE_EXIT

    def test_merge_is_deterministic(self):
        """ТЗ §6.7: одинаковые входы всегда дают одинаковый итог."""
        inputs = (s_exit("R1", "TAKE_PROFIT"), p_exit("R2", "STOP_LOSS"))
        first = merge_exit_evaluations(*inputs)
        for _ in range(10):
            again = merge_exit_evaluations(s_exit("R1", "TAKE_PROFIT"),
                                           p_exit("R2", "STOP_LOSS"))
            assert again == first
            assert again.diagnostics == first.diagnostics
        # Чистая функция: без времени/случайности — тоже с другим порядком
        # создания тех же значений результат совпадает.
        other_pair = (ExitEvaluation.strategic_exit(
            STRATEGY_ID, CONFIG_HASH, FIGI, "TAKE_PROFIT", "R1"),
            ExitEvaluation.protective_exit(STRATEGY_ID, CONFIG_HASH, FIGI,
                                           "STOP_LOSS", "R2"))
        assert merge_exit_evaluations(*other_pair) == first

    def test_conflicting_reasons_preserved(self):
        """ТЗ §6.8: конфликтующие причины выхода — итог несёт причину
        победившего (защитного) решения и сохраняет обе в diagnostics."""
        result = merge_exit_evaluations(
            s_exit("TAKE_PROFIT_HIT"), p_exit("TRAILING_STOP_TRIGGERED"))
        assert result.final_outcome is ExitMergeOutcome.PROTECTIVE_EXIT
        assert result.reason_code == "TRAILING_STOP_TRIGGERED"
        assert result.diagnostics["strategic"]["reason_code"] == \
            "TAKE_PROFIT_HIT"
        assert result.diagnostics["protective"]["reason_code"] == \
            "TRAILING_STOP_TRIGGERED"
        assert result.diagnostics["merge_rules_version"] == \
            sc.EXIT_MERGE_RULES_VERSION

    def test_incomplete_does_not_lose_strategic_info(self):
        """Блокированная защитная оценка не теряет информацию
        стратегического слоя (ничего не отбрасывается молча)."""
        result = merge_exit_evaluations(
            s_exit("TAKE_PROFIT_HIT"), p_blocked("PRICE_MISSING"))
        assert result.final_outcome is \
            ExitMergeOutcome.INCOMPLETE_PROTECTIVE_EVALUATION
        assert result.reason_code == "PRICE_MISSING"
        assert result.decision_source is None
        assert result.exit_type is None
        assert result.diagnostics["strategic"]["outcome"] == \
            "STRATEGIC_EXIT"
        assert result.diagnostics["strategic"]["reason_code"] == \
            "TAKE_PROFIT_HIT"

    def test_merge_rejects_attribution_mismatch(self):
        other_config = make_config(params={"n": 4})
        foreign = ExitEvaluation.protective_exit(
            "beta", other_config.config_hash, FIGI, "STOP_LOSS", "SL")
        with pytest.raises(ExitMergeViolationError):
            merge_exit_evaluations(s_exit(), foreign)
        foreign_figi = ExitEvaluation.protective_exit(
            STRATEGY_ID, CONFIG_HASH, "FIGI2", "STOP_LOSS", "SL")
        with pytest.raises(ExitMergeViolationError):
            merge_exit_evaluations(s_exit(), foreign_figi)

    def test_merge_rejects_wrong_types(self):
        with pytest.raises(ExitMergeViolationError):
            merge_exit_evaluations("strategic", p_exit())
        with pytest.raises(ExitMergeViolationError):
            merge_exit_evaluations(s_exit(), None)

    def test_merge_rejects_subclasses(self):
        class TamperedExit(ExitEvaluation):
            def __post_init__(self):
                pass

        tampered = TamperedExit(STRATEGY_ID, CONFIG_HASH, FIGI,
                                ExitOutcome.PROTECTIVE_EXIT,
                                ExitDecisionSource.PROTECTIVE, "FORGED",
                                "STOP_LOSS")
        with pytest.raises(ExitMergeViolationError):
            merge_exit_evaluations(s_exit(), tampered)


# ===========================================================================
# ТЗ §6.9–§6.11 — fail-closed проверка цены
# ===========================================================================

class TestPriceGate:
    """ТЗ §6.9–§6.11: отсутствующая/некорректная/устаревшая цена —
    отдельный типизированный результат, никаких подстановок."""

    def test_missing_price(self):
        result = check_price(None, expected_figi=FIGI, now=NOW,
                             max_age_seconds=120.0)
        assert result.outcome is PriceCheckOutcome.PRICE_MISSING
        assert result.reason_code == "PRICE_MISSING"
        assert result.price is None
        assert "подстановка" in result.diagnostics["detail"]

    def test_wrong_type_price(self):
        for bad in ("100.0", 100.0, {"price": 100.0}):
            result = check_price(bad, expected_figi=FIGI, now=NOW,
                                 max_age_seconds=120.0)
            assert result.outcome is PriceCheckOutcome.PRICE_INVALID
            assert result.reason_code == "PRICE_WRONG_TYPE"

    def test_foreign_figi_price_rejected(self):
        result = check_price(make_price(figi="OTHER"), expected_figi=FIGI,
                             now=NOW, max_age_seconds=120.0)
        assert result.outcome is PriceCheckOutcome.PRICE_INVALID
        assert result.reason_code == "PRICE_FOREIGN_FIGI"

    def test_future_price_rejected(self):
        result = check_price(make_price(offset_seconds=+5.0),
                             expected_figi=FIGI, now=NOW,
                             max_age_seconds=120.0)
        assert result.outcome is PriceCheckOutcome.PRICE_INVALID
        assert result.reason_code == "PRICE_FROM_FUTURE"

    def test_stale_price(self):
        result = check_price(make_price(offset_seconds=-300.0),
                             expected_figi=FIGI, now=NOW,
                             max_age_seconds=120.0)
        assert result.outcome is PriceCheckOutcome.PRICE_STALE
        assert result.reason_code == "PRICE_STALE"
        assert result.price is None

    def test_staleness_boundary_exactly_max_age_is_ok(self):
        result = check_price(make_price(offset_seconds=-120.0),
                             expected_figi=FIGI, now=NOW,
                             max_age_seconds=120.0)
        assert result.outcome is PriceCheckOutcome.PRICE_OK
        assert result.price is not None

    def test_staleness_disabled_only_explicitly(self):
        result = check_price(make_price(offset_seconds=-100000.0),
                             expected_figi=FIGI, now=NOW,
                             max_age_seconds=None)
        assert result.outcome is PriceCheckOutcome.PRICE_OK
        assert result.diagnostics["max_age_seconds"] is None

    def test_valid_price_passes(self):
        price = make_price()
        result = check_price(price, expected_figi=FIGI, now=NOW,
                             max_age_seconds=120.0)
        assert result.outcome is PriceCheckOutcome.PRICE_OK
        assert result.price is price
        assert result.diagnostics["age_seconds"] == pytest.approx(30.0)

    def test_invalid_max_age_rejected(self):
        with pytest.raises(PriceDataViolationError):
            check_price(make_price(), expected_figi=FIGI, now=NOW,
                        max_age_seconds=-1.0)
        with pytest.raises(PriceDataViolationError):
            check_price(make_price(), expected_figi=FIGI, now=NOW,
                        max_age_seconds=float("nan"))

    @pytest.mark.parametrize("bad_price", [0.0, -5.0, float("nan"),
                                           float("inf"), "100", True])
    def test_price_data_construction_rejects_invalid_values(self, bad_price):
        with pytest.raises(PriceDataViolationError):
            PriceData(figi=FIGI, price=bad_price,
                      timestamp=make_price().timestamp, source="feed")

    def test_price_data_rejects_naive_timestamp_and_empty_source(self):
        with pytest.raises(PriceDataViolationError):
            PriceData(figi=FIGI, price=1.0,
                      timestamp="2026-11-28T12:00:00", source="feed")
        with pytest.raises(PriceDataViolationError):
            PriceData(figi=FIGI, price=1.0, timestamp=make_price().timestamp,
                      source="   ")

    def test_zero_price_substitution_is_impossible(self):
        """ТЗ §3.4: нулевая цена не может попасть в контракт — ни как
        значение PriceData, ни как подстановка при проверке."""
        with pytest.raises(PriceDataViolationError):
            PriceData(figi=FIGI, price=0.0, timestamp=make_price().timestamp,
                      source="feed")
        result = check_price(None, expected_figi=FIGI, now=NOW,
                             max_age_seconds=120.0)
        assert result.price is None  # отсутствие цены — отсутствие цены


# ===========================================================================
# ExitEvaluationRequest
# ===========================================================================

class TestExitEvaluationRequest:
    def test_request_validated_and_frozen(self):
        request = ExitEvaluationRequest(
            strategy_id=STRATEGY_ID, config_hash=CONFIG_HASH, figi=FIGI,
            state_data={"position": 10}, price=make_price())
        assert request.state_data["position"] == 10
        with pytest.raises(Exception):
            request.figi = "OTHER"

    def test_request_rejects_invalid_price_type(self):
        with pytest.raises(ExitContractViolationError):
            ExitEvaluationRequest(strategy_id=STRATEGY_ID,
                                  config_hash=CONFIG_HASH, figi=FIGI,
                                  price={"price": 1.0})

    def test_request_rejects_non_json_state_data(self):
        with pytest.raises(ExitContractViolationError):
            ExitEvaluationRequest(strategy_id=STRATEGY_ID,
                                  config_hash=CONFIG_HASH, figi=FIGI,
                                  state_data={"obj": object()})

    def test_request_rejects_tampered_keys(self):
        with pytest.raises(ExitContractViolationError):
            ExitEvaluationRequest(strategy_id="bad strategy id!",
                                  config_hash=CONFIG_HASH, figi=FIGI)
