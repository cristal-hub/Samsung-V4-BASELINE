# historical_engine/strategy_runner.py
# SAMSUNG V4 — NEW STRATEGY ENGINE. STAGE E.
#
# StrategyRunner: получение данных ТОЛЬКО до текущей закрытой свечи,
# вызов ПРИНЯТЫХ стратегических контрактов (Stage A/C) и обработка
# EntryDecision / ExitDecision (ТЗ Stage E §3.3).
#
# КОНТРАКТЫ, ИСПОЛЬЗУЕМЫЕ КАК ЕСТЬ (без дублирования и изменений):
#   * Stage A: Strategy.evaluate_entry, EntrySignalInput, Signal;
#   * Stage C: EntryEvaluationRunner, EntryEvaluation, ExitEvaluation,
#     ExitEvaluationRequest, ExitDecisionCoordinator, merge_exit_evaluations
#     (внутри координатора), PriceData, check_price (внутри price gate);
#   * Stage B.1: StrategyStateManager + StateStore(memory) — изолированное
#     состояние прогона; режим memory задокументирован Stage B (без файлов,
#     оффлайн); часы состояния ИНЪЕЦИРОВАНЫ (метка свечи) — детерминизм.
#
# LOOK-AHEAD (ТЗ §4): стратегия получает DataFrame среза [0..i] (защитная
# копия) и last_price = close(i). Ни один вызов стратегического контракта
# не получает доступ к свечам с индексом больше i.

from __future__ import annotations

from typing import Any, Callable, Dict, Optional

from strategy_api import EntrySignalInput, Strategy, StrategyConfig
from strategy_contracts import (
    EntryEvaluation,
    EntryEvaluationRunner,
    EntryOutcome,
    ExitDecisionReport,
    ExitDecisionSource,
    ExitEvaluation,
    PriceData,
)
from strategy_state import StateStore, StrategyStateManager

from .data_feed import HistoricalDataFeed
from .models import (
    EngineConfig,
    ExecutionError,
    EXIT_TYPE_STRATEGIC_SELL,
    EXIT_TYPE_STOP_LOSS,
    EXIT_TYPE_TAKE_PROFIT,
)

# Явное решение оператора для исторических данных: проверка устаревания
# цены ОТКЛЮЧЕНА (цена свечи не может быть «устаревшей» внутри прогона —
# решения принимаются на её же закрытии). Параметр price_max_age_seconds
# контракта Stage C передаётся ЯВНО как None (скрытых умолчаний нет).
PRICE_MAX_AGE_SECONDS: Optional[float] = None


class SignalExitEvaluator:
    """Стратегический оценщик выхода для СИГНАЛЬНЫХ стратегий (Stage C).

    Отображение направления сигнала Stage A на контракт выхода Stage C
    (long-only; историческая семантика Samsung V4: SELL — сигнал выхода
    из длинной позиции):
      * ENTRY_ALLOWED  (BUY)  -> NO_EXIT  (оставаться в длинной позиции);
      * NO_SIGNAL      (HOLD) -> NO_EXIT;
      * ENTRY_FORBIDDEN(SELL) -> STRATEGIC_EXIT (STRATEGIC_SELL_SIGNAL);
      * прочие исходы         -> EVALUATION_BLOCKED (fail-closed).
    Логика стратегии НЕ копируется: вызывается тот же контракт Stage A
    (evaluate_entry), что и для входа; срез данных тот же [0..i].
    """

    def __init__(self, *, runner: "StrategyRunner") -> None:
        self._runner = runner

    def evaluate_exit(self, request: Any) -> ExitEvaluation:
        runner = self._runner
        evaluation = runner.evaluate_entry_signal()
        strategy_id = runner.strategy_config.strategy_id
        config_hash = runner.strategy_config.config_hash
        figi = runner.engine_config.figi
        if evaluation.outcome is EntryOutcome.ENTRY_ALLOWED:
            return ExitEvaluation.no_exit(
                strategy_id, config_hash, figi,
                ExitDecisionSource.STRATEGIC,
                "NO_EXIT_BUY_SIGNAL_STAY_LONG",
                decided_at=runner.current_candle_iso,
                diagnostics={"mapped_from": evaluation.reason_code})
        if evaluation.outcome is EntryOutcome.NO_SIGNAL:
            return ExitEvaluation.no_exit(
                strategy_id, config_hash, figi,
                ExitDecisionSource.STRATEGIC,
                "NO_EXIT_HOLD",
                decided_at=runner.current_candle_iso,
                diagnostics={"mapped_from": evaluation.reason_code})
        if evaluation.outcome is EntryOutcome.ENTRY_FORBIDDEN:
            return ExitEvaluation.strategic_exit(
                strategy_id, config_hash, figi,
                exit_type=EXIT_TYPE_STRATEGIC_SELL,
                reason_code="STRATEGIC_EXIT_SELL_SIGNAL",
                decided_at=runner.current_candle_iso,
                diagnostics={"mapped_from": evaluation.reason_code})
        return ExitEvaluation.evaluation_blocked(
            strategy_id, config_hash, figi,
            ExitDecisionSource.STRATEGIC,
            "STRATEGIC_SIGNAL_NOT_EVALUABLE",
            decided_at=runner.current_candle_iso,
            diagnostics={"entry_outcome": evaluation.outcome.value,
                         "entry_reason": evaluation.reason_code})


class StopLevelsProtectiveEvaluator:
    """Защитный оценщик выхода по уровням стопа/цели (Stage C).

    Слой-страховка на закрытии свечи: проверка breach уровней по ЦЕНЕ
    ЗАКРЫТИЯ. При включённой внутри-свечной эмуляции стопов (обязательна
    для входов — формула Stage D требует стоп) этот слой обычно
    предвосхищается исполнителем (стоп исполняется ВНУТРИ свечи по стопу,
    а не по закрытию); слой остаётся активным как fail-closed защита
    (например, гэп ровно до уровня, при котором исполнитель уже вышел —
    тогда позиции нет и слой возвращает NO_EXIT).
    """

    def __init__(self, *,
                 levels_provider: Callable[[], Any]) -> None:
        self._levels_provider = levels_provider

    def evaluate_exit(self, request: Any) -> ExitEvaluation:
        levels = self._levels_provider()
        strategy_id = request.strategy_id
        config_hash = request.config_hash
        figi = request.figi
        price = request.price
        decided_at = request.price.timestamp if price is not None else ""
        if levels is None:
            return ExitEvaluation.no_exit(
                strategy_id, config_hash, figi,
                ExitDecisionSource.PROTECTIVE, "NO_POSITION_NO_PROTECTIVE",
                decided_at=decided_at)
        if price is None:
            return ExitEvaluation.evaluation_blocked(
                strategy_id, config_hash, figi,
                ExitDecisionSource.PROTECTIVE, "PROTECTIVE_PRICE_MISSING",
                decided_at=decided_at)
        stop_price = levels["stop_price"]
        take_price = levels.get("take_price")
        if float(price.price) <= float(stop_price):
            return ExitEvaluation.protective_exit(
                strategy_id, config_hash, figi,
                exit_type=EXIT_TYPE_STOP_LOSS,
                reason_code="PROTECTIVE_CLOSE_BELOW_STOP",
                decided_at=decided_at,
                diagnostics={"close": price.price,
                             "stop_price": stop_price})
        if take_price is not None and float(price.price) >= float(take_price):
            return ExitEvaluation.protective_exit(
                strategy_id, config_hash, figi,
                exit_type=EXIT_TYPE_TAKE_PROFIT,
                reason_code="PROTECTIVE_CLOSE_ABOVE_TARGET",
                decided_at=decided_at,
                diagnostics={"close": price.price,
                             "take_price": take_price})
        return ExitEvaluation.no_exit(
            strategy_id, config_hash, figi,
            ExitDecisionSource.PROTECTIVE, "PROTECTIVE_LEVELS_RESPECTED",
            decided_at=decided_at,
            diagnostics={"close": price.price, "stop_price": stop_price,
                         "take_price": take_price})


class StrategyRunner:
    """Запуск стратегических контрактов на историческом срезе [0..i]."""

    def __init__(self, *,
                 strategy: Strategy,
                 strategy_config: StrategyConfig,
                 feed: HistoricalDataFeed,
                 engine_config: EngineConfig,
                 levels_provider: Callable[[], Any]) -> None:
        if not isinstance(strategy, Strategy):
            raise ExecutionError(
                "StrategyRunner требует стратегию контракта Stage A "
                "(isinstance Strategy)")
        if type(strategy_config) is not StrategyConfig:
            raise ExecutionError(
                "StrategyRunner требует точный тип StrategyConfig")
        if type(feed) is not HistoricalDataFeed:
            raise ExecutionError(
                "StrategyRunner требует точный тип HistoricalDataFeed")
        if type(engine_config) is not EngineConfig:
            raise ExecutionError(
                "StrategyRunner требует точный тип EngineConfig")
        if strategy_config.strategy_id != strategy.strategy_id:
            raise ExecutionError(
                "конфигурация принадлежит другой стратегии: "
                f"{strategy_config.strategy_id!r} != "
                f"{strategy.strategy_id!r}")
        self._strategy = strategy
        self._strategy_config = strategy_config
        self._feed = feed
        self._engine_config = engine_config
        self._levels_provider = levels_provider
        self._entry_runner = EntryEvaluationRunner()
        self._current_index: int = -1
        # Изолированное состояние прогона: Stage B.1 memory-режим (оффлайн,
        # без файлов), часы ИНЪЕЦИРОВАНЫ (метка свечи) — детерминизм.
        self._current_candle_iso: str = ""
        self._current_candle_ts: Any = None
        self._manager = StrategyStateManager(
            StateStore(path=None), clock=lambda: self._current_candle_iso)
        self._coordinator = _make_coordinator(self)

    # --- свойства для оценщиков и движка --------------------------------------

    @property
    def strategy_config(self) -> StrategyConfig:
        return self._strategy_config

    @property
    def engine_config(self) -> EngineConfig:
        return self._engine_config

    @property
    def current_candle_iso(self) -> str:
        return self._current_candle_iso

    # --- входной сигнал (Stage A + граница Stage C) ------------------------------

    def evaluate_entry_signal(self) -> EntryEvaluation:
        """Оценка входного сигнала на ЗАКРЫТИИ текущей свечи.

        Данные: срез [0..current_index] (защитная копия DataFrame),
        last_price = close текущей свечи. Будущие свечи в вызов не
        попадают физически (feed.view_upto не отдаёт их).
        """
        index = self._current_index
        candle = self._feed.candle(index)
        candles_frame = self._feed.entry_dataframe_upto(index)
        entry_input = EntrySignalInput(
            figi=self._engine_config.figi,
            ticker=self._engine_config.ticker,
            candles=candles_frame,
            last_price=float(candle.close),
            drop_incomplete=False,   # все свечи кормушки уже закрыты
        )
        return self._entry_runner.evaluate(
            strategy=self._strategy,
            config=self._strategy_config,
            entry_input=entry_input,
        )

    # --- решения на закрытии свечи ------------------------------------------------

    def begin_candle(self, index: int) -> None:
        """Фиксация текущей свечи для всех последующих решений (данные
        строго до index включительно)."""
        if index < 0 or index >= self._feed.length:
            raise ExecutionError(
                f"begin_candle: index {index} вне диапазона данных")
        self._current_index = index
        candle = self._feed.candle(index)
        self._current_candle_iso = candle.timestamp_iso
        self._current_candle_ts = candle.timestamp

    def entry_decision(self) -> Dict[str, Any]:
        """EntryDecision на закрытии текущей свечи (контракт Stage C)."""
        evaluation = self.evaluate_entry_signal()
        payload: Dict[str, Any] = {
            "outcome": evaluation.outcome.value,
            "reason_code": evaluation.reason_code,
            "strategy_id": evaluation.strategy_id,
            "config_hash": evaluation.config_hash,
            "figi": evaluation.figi,
            "decided_at": self._current_candle_iso,
            "diagnostics": dict(evaluation.diagnostics),
            "entry_allowed": evaluation.outcome is EntryOutcome.ENTRY_ALLOWED,
        }
        return payload

    def exit_decision(self) -> Dict[str, Any]:
        """ExitDecision на закрытии текущей свечи через контракт Stage C:
        price gate -> стратегический/защитный оценщики -> merge -> запись
        в изолированное состояние прогона (ExitDecisionCoordinator)."""
        candle = self._feed.candle(self._current_index)
        price = PriceData(
            figi=self._engine_config.figi,
            price=float(candle.close),
            timestamp=candle.timestamp_iso,
            source="historical_feed_close",
        )
        report = self._coordinator.evaluate_and_record(
            config=self._strategy_config,
            figi=self._engine_config.figi,
            price_required=True,
            price_max_age_seconds=PRICE_MAX_AGE_SECONDS,
            price=price,
            now=self._current_candle_ts,
        )
        return _exit_report_summary(report)


def _make_coordinator(runner: "StrategyRunner") -> Any:
    from strategy_contracts import ExitDecisionCoordinator
    return ExitDecisionCoordinator(
        manager=runner._manager,
        strategic_evaluator=SignalExitEvaluator(runner=runner),
        protective_evaluator=StopLevelsProtectiveEvaluator(
            levels_provider=runner._levels_provider),
        clock=lambda: runner.current_candle_iso,
    )


def _exit_report_summary(report: ExitDecisionReport) -> Dict[str, Any]:
    """JSON-совместимая сводка ExitDecisionReport (в журнал и отчёт)."""
    merged = report.merged
    strategic = report.strategic_result
    protective = report.protective_result
    return {
        "decided_at": report.decided_at,
        "price_check_outcome": report.price_check.outcome.value,
        "price_check_reason": report.price_check.reason_code,
        "merged_outcome": merged.final_outcome.value,
        "merged_reason_code": merged.reason_code,
        "merged_exit_type": merged.exit_type,
        "merged_decision_source": merged.decision_source.value
        if merged.decision_source is not None else None,
        "merge_rules_version":
            dict(merged.diagnostics).get("merge_rules_version", ""),
        "strategic_outcome": strategic.outcome.value
        if strategic is not None else None,
        "strategic_reason_code": strategic.reason_code
        if strategic is not None else None,
        "protective_outcome": protective.outcome.value
        if protective is not None else None,
        "protective_reason_code": protective.reason_code
        if protective is not None else None,
        "state_updated": bool(report.state_updated),
        "executable_exit": merged.final_outcome.value in (
            "PROTECTIVE_EXIT", "STRATEGIC_EXIT"),
        "diagnostics": dict(merged.diagnostics),
    }
