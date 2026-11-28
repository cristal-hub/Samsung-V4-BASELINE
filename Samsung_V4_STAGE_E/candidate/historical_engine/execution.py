# historical_engine/execution.py
# SAMSUNG V4 — NEW STRATEGY ENGINE. STAGE E.
#
# HistoricalExecutionSimulator: ВИРТУАЛЬНОЕ исполнение сделок на
# исторических свечах (ТЗ Stage E §3.4, §5). Никаких заявок, никакой
# брокерской инфраструктуры, никакой сети.
#
# ЗАДОКУМЕНТИРОВАННАЯ МОДЕЛЬ ИСПОЛНЕНИЯ (ТЗ §5):
#   * сигнал формируется на ЗАКРЫТИИ свечи i (момент формирования);
#   * решение принимается на закрытии свечи i (контракты Stage C);
#   * исполнение происходит на СЛЕДУЮЩЕЙ доступной свече i+1 ПО ОТКРЫТИЮ
#     (момент виртуального исполнения). Исполнение по Close сигнальной
#     свечи ЗАПРЕЩЕНО (задним числом недоступная цена);
#   * цена исполнения: open(i+1) с неблагоприятным slippage, ограниченная
#     диапазоном свечи [low; high] (buy не выше high, sell не ниже low);
#   * гэп: если open(i+1) уже за уровнем стопа — выход по open (хуже
#     стопа), никогда по стопу задним числом;
#   * SL/TP внутри одной свечи: если low/high позволяют предположить
#     достижение обоих уровней, но последовательность движения цены
#     неизвестна — КОНСЕРВАТИВНАЯ модель: СТОП ЛОСС первым; факт
#     неоднозначности фиксируется флагом AMBIGUITY_SL_TP_SAME_CANDLE.
#     Более выгодный сценарий автоматически НЕ выбирается (ТЗ §5).

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from .ledger import ClosedTrade, OpenPosition, PortfolioLedger
from .models import (
    AMBIGUITY_SL_TP_SAME_CANDLE,
    Candle,
    EngineConfig,
    ExecutionError,
    EXIT_TYPE_STOP_LOSS,
    EXIT_TYPE_STRATEGIC_SELL,
    EXIT_TYPE_TAKE_PROFIT,
    REASON_ENTRY_BLOCKED_INSUFFICIENT_CASH,
    REASON_ENTRY_BLOCKED_SIZING,
)
from .risk_integration import RiskIntegration
from strategy_risk import SizingOutcome


class HistoricalExecutionSimulator:
    """Виртуальный исполнитель на исторических свечах (long-only)."""

    def __init__(self, *,
                 engine_config: EngineConfig,
                 ledger: PortfolioLedger,
                 risk_integration: RiskIntegration) -> None:
        if type(engine_config) is not EngineConfig:
            raise ExecutionError(
                "HistoricalExecutionSimulator требует точный тип "
                "EngineConfig")
        if type(ledger) is not PortfolioLedger:
            raise ExecutionError(
                "HistoricalExecutionSimulator требует точный тип "
                "PortfolioLedger")
        if type(risk_integration) is not RiskIntegration:
            raise ExecutionError(
                "HistoricalExecutionSimulator требует точный тип "
                "RiskIntegration")
        self._cfg = engine_config
        self._ledger = ledger
        self._risk = risk_integration

    # --- цена исполнения ------------------------------------------------------

    def execution_buy_price(self, raw_price: float,
                            candle: Candle) -> float:
        """Цена покупки: open с неблагоприятным slippage, НЕ выше high
        свечи (внутри диапазона свечи; детерминированная float-операция)."""
        price = raw_price * (1.0 + self._cfg.slippage_rate)
        return min(price, candle.high)

    def execution_sell_price(self, raw_price: float,
                             candle: Candle) -> float:
        """Цена продажи: open с неблагоприятным slippage, НЕ ниже low
        свечи (внутри диапазона свечи)."""
        price = raw_price * (1.0 - self._cfg.slippage_rate)
        return max(price, candle.low)

    # --- вход -------------------------------------------------------------------

    def execute_pending_entry(self, *, decision_candle_index: int,
                              entry_candle_index: int,
                              execution_candle: Candle) -> Dict[str, Any]:
        """Исполнение отложенного входа на открытии execution_candle.

        Возвращает JSON-совместимое событие:
          ENTRY_EXECUTED / ENTRY_BLOCKED_* с атрибуцией Stage D.
        Порядок: цена исполнения -> размер через Stage D -> точная проверка
        кэша -> открытие позиции в ledger (fail-closed).
        """
        cfg = self._cfg
        raw_open = execution_candle.open
        exec_price = self.execution_buy_price(raw_open, execution_candle)
        cash = self._ledger.cash
        sizing_diagnostics: Dict[str, Any] = {}
        sizing = self._risk.size_entry(
            execution_price=exec_price, cash=cash,
            diagnostics_sink=sizing_diagnostics)

        if sizing.outcome is not SizingOutcome.SIZED:
            # Любой не-SIZED исход Stage D блокирует сделку: положительный
            # объём в блокирующем результате невозможен (Stage D §7).
            blocked_event = {
                "kind": "ENTRY_BLOCKED_SIZING",
                "reason_code": sizing.reason_code,
                "sizing_outcome": sizing.outcome.value,
                "execution_price": exec_price,
                "raw_open": raw_open,
                "cash_before": cash,
                "sizing": sizing_diagnostics,
            }
            blocked_event[REASON_ENTRY_BLOCKED_SIZING] = True
            return blocked_event

        quantity = sizing.quantity          # кратно lot_size (Stage D)
        multiplier = cfg.contract_multiplier
        entry_notional = exec_price * quantity * multiplier
        entry_commission = cfg.commission_rate * entry_notional
        entry_slippage_cost = quantity * multiplier * (exec_price - raw_open)
        needed = entry_notional + entry_commission
        if needed > cash:
            # Fail-closed: плеча нет; вход не исполняется (ТЗ §5
            # «недостаточный капитал / покупательная способность»).
            return {
                "kind": "ENTRY_BLOCKED_INSUFFICIENT_CASH",
                "reason_code": REASON_ENTRY_BLOCKED_INSUFFICIENT_CASH,
                "sizing_outcome": sizing.outcome.value,
                "sizing_reason_code": sizing.reason_code,
                "required": needed,
                "cash_before": cash,
                "execution_price": exec_price,
                "quantity": quantity,
            }

        stop_price = exec_price * (1.0 - cfg.stop_loss_fraction)
        take_price = None if cfg.take_profit_fraction is None \
            else exec_price * (1.0 + cfg.take_profit_fraction)
        position = OpenPosition(
            figi=cfg.figi,
            quantity=quantity,
            lot_size=cfg.lot_size,
            lot_count=sizing.lot_count,
            entry_exec_price=exec_price,
            entry_raw_price=raw_open,
            entry_timestamp_iso=execution_candle.timestamp_iso,
            stop_price=stop_price,
            take_price=take_price,
            entry_notional=entry_notional,
            entry_commission=entry_commission,
            entry_slippage_cost=entry_slippage_cost,
            risk_policy_hash=sizing.risk_policy_hash,
            sizing_reason_code=sizing.reason_code,
            contract_multiplier=multiplier,
            decision_candle_index=decision_candle_index,
            entry_candle_index=entry_candle_index,
        )
        self._ledger.open_position(position=position,
                                   timestamp_iso=execution_candle.timestamp_iso)
        return {
            "kind": "ENTRY_EXECUTED",
            "reason_code": sizing.reason_code,
            "execution_price": exec_price,
            "raw_open": raw_open,
            "quantity": quantity,
            "lot_count": sizing.lot_count,
            "lot_size": cfg.lot_size,
            "entry_notional": entry_notional,
            "entry_commission": entry_commission,
            "entry_slippage_cost": entry_slippage_cost,
            "stop_price": stop_price,
            "take_price": take_price,
            "cash_after": self._ledger.cash,
            "sizing": sizing_diagnostics,
        }

    # --- выход ------------------------------------------------------------------

    def execute_pending_exit(self, *, exit_type: str,
                             exit_reason_code: str,
                             exit_diagnostics: Dict[str, Any],
                             exit_candle_index: int,
                             execution_candle: Candle) -> Dict[str, Any]:
        """Исполнение отложенного выхода на открытии execution_candle."""
        raw_open = execution_candle.open
        exec_price = self.execution_sell_price(raw_open, execution_candle)
        cfg = self._cfg
        pos = self._ledger.position
        if pos is None:
            raise ExecutionError(
                "execute_pending_exit при отсутствии позиции (fail-closed)")
        exit_notional = exec_price * pos.quantity * pos.contract_multiplier
        exit_commission = cfg.commission_rate * exit_notional
        exit_slippage_cost = pos.quantity * pos.contract_multiplier * \
            (raw_open - exec_price)
        trade = self._ledger.close_position(
            exit_exec_price=exec_price,
            exit_raw_price=raw_open,
            exit_commission=exit_commission,
            exit_slippage_cost=exit_slippage_cost,
            exit_type=exit_type,
            exit_reason_code=exit_reason_code,
            exit_timestamp_iso=execution_candle.timestamp_iso,
            exit_candle_index=exit_candle_index,
            exit_decision_diagnostics=exit_diagnostics,
        )
        return {
            "kind": "EXIT_EXECUTED",
            "exit_type": exit_type,
            "reason_code": exit_reason_code,
            "execution_price": exec_price,
            "raw_open": raw_open,
            "quantity": pos.quantity,
            "exit_notional": exit_notional,
            "exit_commission": exit_commission,
            "exit_slippage_cost": exit_slippage_cost,
            "pnl_net": trade.pnl_net,
            "cash_after": self._ledger.cash,
            "diagnostics": exit_diagnostics,
            "_ledger_trade": trade,
        }

    # --- внутри-свечная защита (эмуляция стопов) --------------------------------

    def protect_intra_candle(self, *, candle: Candle,
                             candle_index: int) \
            -> Optional[Tuple[Dict[str, Any], ClosedTrade]]:
        """Проверка SL/TP открытой позиции по ЗАКРЫТОЙ свече.

        Консервативная модель (ТЗ §5):
          * гэп вниз за стоп: open < stop -> выход по open со slippage
            (хуже стопа; задним числом по стопу НЕ исполняется);
          * SL: low <= stop -> выход по stop со slippage (не ниже low);
          * TP: high >= take -> выход по take со slippage (не ниже low);
          * SL и TP в одной свече -> СТОП ЛОСС (консервативно) + флаг
            неоднозначности; выгодный сценарий не выбирается.
        Порядок проверок фиксированный: гэп-стоп -> SL -> TP.
        """
        pos = self._ledger.position
        if pos is None:
            return None
        cfg = self._cfg
        ambiguity: Tuple[str, ...] = ()

        sl_hit = candle.low <= pos.stop_price
        tp_hit = (pos.take_price is not None
                  and candle.high >= pos.take_price)
        if sl_hit and tp_hit:
            ambiguity = (AMBIGUITY_SL_TP_SAME_CANDLE,)
            # Консервативная модель: исполнится СТОП ЛОСС.
            tp_hit = False

        if sl_hit:
            # Гэп вниз за стоп: открытая ранее позиция встречает открытие
            # свечи уже ниже стопа — исполнение по открытию (хуже стопа).
            if candle.open < pos.stop_price:
                raw_exit = candle.open
            else:
                raw_exit = pos.stop_price
            exec_price = self.execution_sell_price(raw_exit, candle)
            exit_type = EXIT_TYPE_STOP_LOSS
            reason = "SL_TOUCHED"
            if candle.open < pos.stop_price:
                reason = "SL_GAP_THROUGH_STOP"
        elif tp_hit:
            raw_exit = pos.take_price
            exec_price = self.execution_sell_price(raw_exit, candle)
            exit_type = EXIT_TYPE_TAKE_PROFIT
            reason = "TP_TOUCHED"
        else:
            return None

        exit_notional = exec_price * pos.quantity * pos.contract_multiplier
        exit_commission = cfg.commission_rate * exit_notional
        exit_slippage_cost = pos.quantity * pos.contract_multiplier * \
            (raw_exit - exec_price)
        trade = self._ledger.close_position(
            exit_exec_price=exec_price,
            exit_raw_price=raw_exit,
            exit_commission=exit_commission,
            exit_slippage_cost=exit_slippage_cost,
            exit_type=exit_type,
            exit_reason_code=reason,
            exit_timestamp_iso=candle.timestamp_iso,
            exit_candle_index=candle_index,
            ambiguity_flags=ambiguity,
            exit_decision_diagnostics={
                "model": "intra_candle_conservative",
                "candle_low": candle.low,
                "candle_high": candle.high,
                "candle_open": candle.open,
                "stop_price": pos.stop_price,
                "take_price": pos.take_price,
            },
        )
        event = {
            "kind": "EXIT_EXECUTED",
            "exit_type": exit_type,
            "reason_code": reason,
            "execution_price": exec_price,
            "raw_exit": raw_exit,
            "quantity": pos.quantity,
            "pnl_net": trade.pnl_net,
            "cash_after": self._ledger.cash,
            "ambiguity_flags": list(ambiguity),
            "diagnostics": {
                "model": "intra_candle_conservative",
                "candle_low": candle.low,
                "candle_high": candle.high,
                "candle_open": candle.open,
            },
            "_ledger_trade": trade,
        }
        return event, trade
