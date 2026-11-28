# historical_engine/report.py
# SAMSUNG V4 — NEW STRATEGY ENGINE. STAGE E.
#
# BacktestReport: статистика сделок, доходность, просадка, Profit Factor,
# Win Rate, средняя прибыль и убыток, суммарные издержки, причины входов
# и выходов (ТЗ Stage E §3.7). Канонический JSON + SHA-256 отчёта;
# повторный прогон даёт идентичные байты и контрольный хеш (ТЗ §7).

from __future__ import annotations

import math
from typing import Any, Dict, List, Mapping, Optional

from .data_feed import HistoricalDataFeed
from .ledger import ClosedTrade, PortfolioLedger
from .models import (
    ENGINE_VERSION,
    EngineConfig,
    JournalEvent,
    canonical_json,
    sha256_hex,
)
from strategy_api import StrategyConfig


def _pct(value: float, base: float) -> float:
    return value / base * 100.0 if base != 0.0 else 0.0


class BacktestReportBuilder:
    """Сборка детерминированного отчёта прогона."""

    def __init__(self, *,
                 segment_label: str,
                 start_index: int,
                 end_index: int,
                 feed: HistoricalDataFeed,
                 engine_config: EngineConfig,
                 strategy_config: StrategyConfig,
                 ledger: PortfolioLedger,
                 events: List[JournalEvent],
                 run_summary: Mapping[str, Any]) -> None:
        self._label = segment_label
        self._start = start_index
        self._end = end_index
        self._feed = feed
        self._cfg = engine_config
        self._s_cfg = strategy_config
        self._ledger = ledger
        self._events = events
        self._summary = dict(run_summary)

    # --- вычисление статистики -------------------------------------------------

    def _trade_statistics(self, trades: List[ClosedTrade]) -> Dict[str, Any]:
        net_pnls = [trade.pnl_net for trade in trades]
        wins = [p for p in net_pnls if p > 0.0]
        losses = [p for p in net_pnls if p < 0.0]
        gross_profit = math.fsum(wins)
        gross_loss = -math.fsum(losses)   # положительное число
        total_trades = len(trades)
        if total_trades == 0:
            win_rate: Optional[float] = None
        else:
            win_rate = len(wins) / total_trades
        if gross_loss > 0.0:
            profit_factor: Optional[float] = gross_profit / gross_loss
            pf_note = "PROFIT_FACTOR_GROSS_PROFIT_OVER_GROSS_LOSS"
        elif gross_profit > 0.0:
            profit_factor = None
            pf_note = "PROFIT_FACTOR_UNDEFINED_NO_LOSSING_TRADES"
        else:
            profit_factor = None
            pf_note = "PROFIT_FACTOR_UNDEFINED_NO_TRADES"
        return {
            "total_trades": total_trades,
            "winning_trades": len(wins),
            "losing_trades": len(losses),
            "win_rate": win_rate,
            "gross_profit_net": gross_profit,
            "gross_loss_net": gross_loss,
            "profit_factor": profit_factor,
            "profit_factor_note": pf_note,
            "average_win_net": math.fsum(wins) / len(wins) if wins else None,
            "average_loss_net": math.fsum(losses) / len(losses)
            if losses else None,
            "average_trade_pnl_net": math.fsum(net_pnls) / total_trades
            if total_trades else None,
            "total_pnl_net": math.fsum(net_pnls),
        }

    def _histograms(self) -> Dict[str, Any]:
        entry_reasons: Dict[str, int] = {}
        exit_reasons: Dict[str, int] = {}
        blocked_reasons: Dict[str, int] = {}
        for event in self._events:
            payload = event.payload
            if event.event_type == "ENTRY_DECISION":
                key = payload["reason_code"]
                entry_reasons[key] = entry_reasons.get(key, 0) + 1
            elif event.event_type == "ENTRY_BLOCKED_SIZING":
                key = payload.get("reason_code", "UNKNOWN")
                blocked_reasons[key] = blocked_reasons.get(key, 0) + 1
            elif event.event_type == "ENTRY_BLOCKED_INSUFFICIENT_CASH":
                key = payload.get("reason_code", "UNKNOWN")
                blocked_reasons[key] = blocked_reasons.get(key, 0) + 1
            elif event.event_type == "EXIT_EXECUTED":
                key = f"{payload.get('exit_type', 'UNKNOWN')}:" \
                      f"{payload.get('reason_code', 'UNKNOWN')}"
                exit_reasons[key] = exit_reasons.get(key, 0) + 1
            elif event.event_type == "ENTRY_NOT_TAKEN":
                key = payload.get("reason_code", "UNKNOWN")
                entry_reasons[key] = entry_reasons.get(key, 0) + 1
        return {
            "entry_decision_reasons": entry_reasons,
            "blocked_entry_reasons": blocked_reasons,
            "exit_reasons": exit_reasons,
        }

    # --- сборка ------------------------------------------------------------------

    def build(self) -> Dict[str, Any]:
        cfg = self._cfg
        s_cfg = self._s_cfg
        ledger = self._ledger
        candles = self._feed.view_upto(self._end - 1)[self._start:]
        trades = list(ledger.closed_trades)
        stats = self._trade_statistics(trades)
        histograms = self._histograms()

        final_equity = self._summary["equity_curve"][-1]["equity"] \
            if self._summary["equity_curve"] else ledger.initial_cash
        total_return_pct = _pct(final_equity - ledger.initial_cash,
                                ledger.initial_cash)
        buy_hold_return_pct = None
        if candles:
            buy_hold_return_pct = _pct(
                candles[-1].close - candles[0].close, candles[0].close)

        open_position = ledger.position
        open_position_info = None
        if open_position is not None:
            open_position_info = {
                "quantity": open_position.quantity,
                "lot_count": open_position.lot_count,
                "entry_exec_price": open_position.entry_exec_price,
                "entry_timestamp": open_position.entry_timestamp_iso,
                "stop_price": open_position.stop_price,
                "take_price": open_position.take_price,
            }

        ambiguity_incidents = math.fsum(
            len(trade.ambiguity_flags) for trade in trades)

        metadata = {
            "engine_version": ENGINE_VERSION,
            "segment_label": self._label,
            "start_index": self._start,
            "end_index": self._end,
            "candle_count": self._end - self._start,
            "first_candle_timestamp": candles[0].timestamp_iso
            if candles else "",
            "last_candle_timestamp": candles[-1].timestamp_iso
            if candles else "",
            "figi": cfg.figi,
            "ticker": cfg.ticker,
            "data_sha256": self._feed.data_sha256,
            "engine_config_sha256": cfg.config_sha256(),
            "strategy_id": s_cfg.strategy_id,
            "strategy_version": s_cfg.strategy_version,
            "strategy_config_hash": s_cfg.config_hash,
            "risk_policy_hash": self._risk_policy_hash(),
            "calendar_sha256": self._feed.calendar_sha256,
        }
        run_id = sha256_hex(canonical_json({
            "engine_version": ENGINE_VERSION,
            "data_sha256": metadata["data_sha256"],
            "engine_config_sha256": metadata["engine_config_sha256"],
            "strategy_config_hash": metadata["strategy_config_hash"],
            "segment_label": self._label,
            "start_index": self._start,
            "end_index": self._end,
        }))
        metadata["run_id"] = run_id

        report: Dict[str, Any] = {
            "report_schema": "samsung_v4_stage_e_report_v1",
            "metadata": metadata,
            "execution_model": {
                "signal_moment": "close_of_candle_i",
                "decision_moment": "close_of_candle_i_stage_c_contracts",
                "execution_moment": "open_of_candle_i_plus_1",
                "slippage_model": "adverse_fraction_of_open_bounded_by_candle",
                "slippage_accounting":
                    "ADVERSE_COST_AND_FAVORABLE_IMPROVEMENT_SPLIT_"
                    "DIRECTION_AWARE",
                "reference_price_definition":
                    "raw reference of the operation: open of execution "
                    "candle for entries and strategic exits; stop/take "
                    "level for protective exits; gapped open for "
                    "gap-through-stop (gap loss itself is market risk, "
                    "never counted as slippage)",
                "total_execution_cost_definition":
                    "TOTAL_EXECUTION_COST = TOTAL_COMMISSION + "
                    "TOTAL_ADVERSE_SLIPPAGE_COST; favorable price "
                    "improvement is NOT a cost and is reported separately",
                "stop_model": "intra_candle_conservative_sl_before_tp",
                "sl_tp_same_candle_policy": "STOP_LOSS_PRIORITIZED_FLAGGED",
                "gap_policy": cfg.gap_policy,
                "commission_rate_per_side": cfg.commission_rate,
                "slippage_rate_per_side": cfg.slippage_rate,
            },
            "risk_integration": {
                "sizing_source": "stage_d_calculate_position_size",
                "risk_per_trade_fraction": cfg.risk_per_trade_fraction,
                "max_position_notional_fraction":
                    cfg.max_position_notional_fraction,
                "stop_loss_fraction": cfg.stop_loss_fraction,
                "take_profit_fraction": cfg.take_profit_fraction,
                "lot_size": cfg.lot_size,
                "contract_multiplier": cfg.contract_multiplier,
            },
            "account": {
                "initial_cash": ledger.initial_cash,
                "final_cash": ledger.cash,
                "final_equity": final_equity,
                "total_return_pct": total_return_pct,
                "buy_hold_price_return_pct": buy_hold_return_pct,
                "max_drawdown_pct": self._summary["max_drawdown_pct"],
                "peak_equity": self._summary["peak_equity"],
                "open_position_at_end": open_position_info,
            },
            "statistics": stats,
            "costs": {
                # Обратная совместимость Stage E: имя сохранено; значение —
                # суммарное НЕБЛАГОПРИЯТНОЕ проскальзывание (>= 0).
                "total_commission": ledger.total_commission,
                "total_slippage_cost": ledger.total_slippage_cost,
                # Stage E.1 (Correction 2): раздельные показатели.
                "total_adverse_slippage_cost": ledger.total_slippage_cost,
                "total_favorable_price_improvement":
                    ledger.total_price_improvement,
                "total_execution_cost": ledger.total_execution_cost,
                "total_execution_cost_definition":
                    "TOTAL_EXECUTION_COST = TOTAL_COMMISSION + "
                    "TOTAL_ADVERSE_SLIPPAGE_COST; favorable price "
                    "improvement is NOT a cost and is reported separately",
            },
            "reasons": histograms,
            "ambiguity_incidents": ambiguity_incidents,
            "gaps": [list(gap) for gap in self._feed.gaps],
            # Stage E.1 (Correction 1): календарно-корректный контроль
            # пропусков — полная классификация инцидентов и ЯВНЫЙ статус
            # верификации полноты данных (без ложного подтверждения).
            "gap_analysis": [incident.as_dict()
                             for incident in self._feed.gap_incidents],
            "gap_verification": self._gap_verification(),
            "unresolved_decisions": {
                "exit_pending_at_segment_end":
                    bool(self._summary["unresolved_exit_pending"]),
                "entry_pending_at_segment_end":
                    bool(self._summary["unresolved_entry_pending"]),
            },
            "trades": [trade.as_dict() for trade in trades],
            "equity_curve": list(self._summary["equity_curve"]),
        }
        # Незакрытые операции в историю операций не входят: история —
        # фактические движения денег (вход/выход); открытая позиция
        # отражена в account.open_position_at_end.
        report["ledger_operations"] = [
            operation.as_dict() for operation in ledger.operations]
        report_sha256 = sha256_hex(canonical_json(report))
        report["metadata"]["report_sha256"] = report_sha256
        report["report_sha256"] = report_sha256
        return report

    def _gap_verification(self) -> Dict[str, Any]:
        """Явное сообщение о верификации полноты серии (Stage E.1).

        Календарные перерывы НЕ считаются пропущенными свечами;
        отсутствие календаря НЕ создаёт ложного подтверждения полноты:
        статус прямо указывает на ограниченную проверку.
        """
        incidents = self._feed.gap_incidents
        by_category: Dict[str, int] = {}
        for incident in incidents:
            by_category[incident.category] = \
                by_category.get(incident.category, 0) + 1
        calendar_sha = self._feed.calendar_sha256
        return {
            "status": self._feed.gap_verification_status,
            "calendar_present": calendar_sha is not None,
            "calendar_sha256": calendar_sha,
            "expected_candle_interval_seconds":
                self._cfg.expected_candle_interval_seconds,
            "gap_policy": self._cfg.gap_policy,
            "incident_counts": {
                "total": len(incidents),
                "confirmed_expected_candle_missing": by_category.get(
                    "CONFIRMED_EXPECTED_CANDLE_MISSING", 0),
                "session_break": by_category.get("SESSION_BREAK", 0),
                "non_trading_day": by_category.get("NON_TRADING_DAY", 0),
                "non_trading_time": by_category.get("NON_TRADING_TIME", 0),
                "confirmed_irregular_spacing": by_category.get(
                    "CONFIRMED_IRREGULAR_SPACING", 0),
                "unverified_no_calendar": by_category.get(
                    "UNVERIFIED_NO_CALENDAR_LIMITED_CHRONOLOGY_CHECK", 0),
                "unverified_outside_calendar_coverage": by_category.get(
                    "UNVERIFIED_OUTSIDE_CALENDAR_COVERAGE", 0),
            },
        }

    def _risk_policy_hash(self) -> str:
        for event in self._events:
            payload = event.payload
            if event.event_type == "ENTRY_EXECUTED":
                sizing = payload.get("sizing") or {}
                if sizing.get("risk_policy_hash"):
                    return str(sizing["risk_policy_hash"])
            if event.event_type == "ENTRY_BLOCKED_SIZING":
                sizing = payload.get("sizing") or {}
                if sizing.get("risk_policy_hash"):
                    return str(sizing["risk_policy_hash"])
        return ""
