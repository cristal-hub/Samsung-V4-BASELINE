# historical_engine/event_engine.py
# SAMSUNG V4 — NEW STRATEGY ENGINE. STAGE E.
#
# EventEngine: детерминированная обработка событий с ФИКСИРОВАННЫМ
# порядком обработки внутри каждой свечи (ТЗ Stage E §3.2, §7):
#
#   ФАЗА 1 — ИСПОЛНЕНИЕ НА ОТКРЫТИИ (отложенные решения прошлой свечи):
#       1a. отложенный ВЫХОД (если есть)  -> исполнение по open;
#       1b. отложенный ВХОД  (если есть)  -> размер через Stage D -> open.
#       Порядок 1a -> 1b фиксирован; обе операции одновременно невозможны
#       по построению (решение на закрытии либо вход, либо выход).
#   ФАЗА 2 — ЗАЩИТА ПОЗИЦИИ ВНУТРИ СВЕЧИ (эмуляция стопов):
#       гэп-стоп -> SL -> TP; SL+TP в одной свече -> СТОП ЛОСС
#       (консервативно) + флаг неоднозначности.
#   ФАЗА 3 — РЕШЕНИЯ НА ЗАКРЫТИИ:
#       3a. позиция открыта -> ExitDecision (Stage C координатор);
#       3b. позиции нет     -> EntryDecision (Stage C граница входа);
#       отложенные решения исполняются на ОТКРЫТИИ следующей свечи.
#
# Детерминизм: никакой зависимости от системного времени (все метки — из
# данных свечей), никакого случайного, фиксированный порядок фаз,
# одинаковый результат при повторном запуске (ТЗ §7). Решение, принятое
# на закрытии последней свечи сегмента, остаётся НЕИСПОЛНЕННЫМ и
# фиксируется в отчёте (unresolved) — задним числом не исполняется.

from __future__ import annotations

from typing import Any, Dict, List, Optional

from strategy_api import Strategy, StrategyConfig

from .data_feed import HistoricalDataFeed
from .execution import HistoricalExecutionSimulator
from .ledger import PortfolioLedger
from .models import (
    JournalEvent,
    REASON_ENTRY_FORBIDDEN_BY_STRATEGY,
    REASON_ENTRY_NO_SIGNAL,
    REASON_EXIT_UNRESOLVED_AT_SEGMENT_END,
)
from .strategy_runner import StrategyRunner


class EventEngine:
    """Детерминированный цикл событий исторического прогона."""

    def __init__(self, *,
                 strategy: Strategy,
                 strategy_config: StrategyConfig,
                 feed: HistoricalDataFeed,
                 engine_config: Any,
                 ledger: PortfolioLedger,
                 simulator: HistoricalExecutionSimulator,
                 runner: StrategyRunner) -> None:
        self._strategy = strategy
        self._strategy_config = strategy_config
        self._feed = feed
        self._cfg = engine_config
        self._ledger = ledger
        self._simulator = simulator
        self._runner = runner
        self._events: List[JournalEvent] = []
        self._event_counter = 0

    # --- журнал ---------------------------------------------------------------

    def _record(self, *, event_type: str, candle_index: int,
                timestamp_iso: str,
                payload: Dict[str, Any]) -> None:
        self._event_counter += 1
        self._events.append(JournalEvent(
            event_index=self._event_counter,
            event_type=event_type,
            candle_index=candle_index,
            timestamp_iso=timestamp_iso,
            payload=payload,
        ))

    @property
    def events(self) -> List[JournalEvent]:
        return list(self._events)

    # --- служебные --------------------------------------------------------------

    def _position_levels(self) -> Optional[Dict[str, Any]]:
        """Уровни стопа/цели открытой позиции (для защитного оценщика)."""
        position = self._ledger.position
        if position is None:
            return None
        return {
            "stop_price": position.stop_price,
            "take_price": position.take_price,
        }

    # --- фазы ---------------------------------------------------------------------

    def _phase_1_execute_pending(self, candle_index: int) -> None:
        candle = self._feed.candle(candle_index)
        pending = self._pending
        self._pending = None
        if pending is None:
            return
        decision = pending.get("decision", {})
        if pending["kind"] == "EXIT":
            event = self._simulator.execute_pending_exit(
                exit_type=decision["exit_type"],
                exit_reason_code=decision["exit_reason_code"],
                exit_diagnostics=decision.get("diagnostics", {}),
                exit_candle_index=candle_index,
                execution_candle=candle,
            )
            trade = event.pop("_ledger_trade", None)
            self._record(
                event_type="EXIT_EXECUTED",
                candle_index=candle_index,
                timestamp_iso=candle.timestamp_iso,
                payload=event)
            if trade is not None:
                self._trades_by_index[trade.exit_candle_index] = trade
            return
        if pending["kind"] == "ENTRY":
            event = self._simulator.execute_pending_entry(
                decision_candle_index=pending["decision_index"],
                entry_candle_index=candle_index,
                execution_candle=candle,
            )
            self._record(
                event_type=event["kind"],
                candle_index=candle_index,
                timestamp_iso=candle.timestamp_iso,
                payload=event)
            return
        raise RuntimeError(f"неизвестный вид отложенного решения: "
                           f"{pending['kind']!r}")

    def _phase_2_protect(self, candle_index: int) -> None:
        candle = self._feed.candle(candle_index)
        result = self._simulator.protect_intra_candle(
            candle=candle, candle_index=candle_index)
        if result is None:
            return
        event, trade = result
        event = dict(event)
        event.pop("_ledger_trade", None)
        self._record(
            event_type="EXIT_EXECUTED",
            candle_index=candle_index,
            timestamp_iso=candle.timestamp_iso,
            payload=event)
        self._trades_by_index[trade.exit_candle_index] = trade

    def _phase_3_decide(self, candle_index: int) -> None:
        self._runner.begin_candle(candle_index)
        if self._ledger.position is not None:
            exit_decision = self._runner.exit_decision()
            self._record(
                event_type="EXIT_DECISION",
                candle_index=candle_index,
                timestamp_iso=self._runner.current_candle_iso,
                payload=exit_decision)
            if exit_decision["executable_exit"]:
                self._pending = {
                    "kind": "EXIT",
                    "decision_index": candle_index,
                    "decision": {
                        "exit_type": exit_decision["merged_exit_type"],
                        "exit_reason_code":
                            exit_decision["merged_reason_code"],
                        "diagnostics": {
                            "decision_source":
                                exit_decision["merged_decision_source"],
                            "decision_model": "next_open_stage_c_merge",
                            "strategic_outcome":
                                exit_decision["strategic_outcome"],
                            "protective_outcome":
                                exit_decision["protective_outcome"],
                            "price_check_outcome":
                                exit_decision["price_check_outcome"],
                        },
                    },
                }
            return
        entry_decision = self._runner.entry_decision()
        self._record(
            event_type="ENTRY_DECISION",
            candle_index=candle_index,
            timestamp_iso=self._runner.current_candle_iso,
            payload=entry_decision)
        if entry_decision["entry_allowed"]:
            self._pending = {
                "kind": "ENTRY",
                "decision_index": candle_index,
                "decision": entry_decision,
            }
        else:
            reason = REASON_ENTRY_NO_SIGNAL \
                if entry_decision["outcome"] == "NO_SIGNAL" \
                else REASON_ENTRY_FORBIDDEN_BY_STRATEGY
            self._record(
                event_type="ENTRY_NOT_TAKEN",
                candle_index=candle_index,
                timestamp_iso=self._runner.current_candle_iso,
                payload={"reason_code": reason,
                         "entry_outcome": entry_decision["outcome"],
                         "entry_reason_code":
                             entry_decision["reason_code"]})

    # --- основной цикл ------------------------------------------------------------

    def run(self, *, start_index: int, end_index: int) -> Dict[str, Any]:
        """Прогон по свечам [start_index, end_index) с фиксированными
        фазами на каждой свече. Возвращает сводку прогона."""
        if start_index < 0 or end_index > self._feed.length \
                or end_index <= start_index:
            raise RuntimeError(
                f"некорректный диапазон прогона [{start_index}, "
                f"{end_index}) при длине данных {self._feed.length}")
        self._pending: Optional[Dict[str, Any]] = None
        self._trades_by_index: Dict[int, Any] = {}
        equity_curve: List[Dict[str, Any]] = []
        peak_equity = self._ledger.initial_cash
        max_drawdown_pct = 0.0

        for candle_index in range(start_index, end_index):
            candle = self._feed.candle(candle_index)
            # ФАЗА 1: исполнение отложенных решений на открытии.
            self._phase_1_execute_pending(candle_index)
            # ФАЗА 2: внутри-свечная защита позиции (стоп-эмуляция).
            self._phase_2_protect(candle_index)
            # ФАЗА 3: решения на закрытии (контракты Stage A/C).
            self._phase_3_decide(candle_index)
            # Отметка портфеля по закрытию (кривая капитала).
            equity = self._ledger.equity_at_price(candle.close)
            if equity > peak_equity:
                peak_equity = equity
            drawdown_pct = 0.0 if peak_equity <= 0 else \
                (peak_equity - equity) / peak_equity * 100.0
            if drawdown_pct > max_drawdown_pct:
                max_drawdown_pct = drawdown_pct
            equity_curve.append({
                "candle_index": candle_index,
                "timestamp": candle.timestamp_iso,
                "close": candle.close,
                "equity": equity,
                "drawdown_pct": drawdown_pct,
                "position_open": self._ledger.position is not None,
            })

        unresolved_exit = False
        if self._pending is not None and self._pending["kind"] == "EXIT":
            unresolved_exit = True
            self._record(
                event_type="DECISION_UNRESOLVED",
                candle_index=end_index - 1,
                timestamp_iso=self._feed.candle(
                    end_index - 1).timestamp_iso,
                payload={"reason_code": REASON_EXIT_UNRESOLVED_AT_SEGMENT_END,
                         "decision_kind": "EXIT"})
        unresolved_entry = False
        if self._pending is not None and self._pending["kind"] == "ENTRY":
            unresolved_entry = True
            self._record(
                event_type="DECISION_UNRESOLVED",
                candle_index=end_index - 1,
                timestamp_iso=self._feed.candle(
                    end_index - 1).timestamp_iso,
                payload={"reason_code": "ENGINE_ENTRY_UNRESOLVED_AT_END",
                         "decision_kind": "ENTRY"})

        return {
            "equity_curve": equity_curve,
            "max_drawdown_pct": max_drawdown_pct,
            "peak_equity": peak_equity,
            "unresolved_exit_pending": unresolved_exit,
            "unresolved_entry_pending": unresolved_entry,
        }
