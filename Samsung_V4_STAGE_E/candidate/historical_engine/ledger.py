# historical_engine/ledger.py
# SAMSUNG V4 — NEW STRATEGY ENGINE. STAGE E.
#
# PortfolioLedger: виртуальные позиции, денежный баланс, реализованный и
# нереализованный PnL, комиссии, история операций (ТЗ Stage E §3.6).
#
# Только виртуальный расчёт; никаких заявок и обращений к брокеру.
# Детерминированная float-арифметика с ФИКСИРОВАННЫМ порядком операций
# (однопоточный детерминированный цикл) — повторный прогон даёт
# идентичные балансы; инвариант сохранения денег проверяется всегда.

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional, Tuple

from .models import (
    EXIT_TYPE_STOP_LOSS,
    EXIT_TYPE_STRATEGIC_SELL,
    EXIT_TYPE_TAKE_PROFIT,
    LedgerError,
    LedgerOperation,
)


@dataclass(frozen=True)
class OpenPosition:
    """Открытая виртуальная LONG-позиция (неизменяемая).

    SHORT в движке отсутствует: исторический симулятор Stage E
    обрабатывает ТОЛЬКО long-only сторону — ровно ту, которую поддерживает
    Stage D (TradeSide.LONG; SHORT -> UNSUPPORTED_SIDE).
    """
    figi: str
    quantity: int
    lot_size: int
    lot_count: int
    entry_exec_price: float        # фактическая цена входа (со slippage)
    entry_raw_price: float         # «сырая» цена до slippage (аудит)
    entry_timestamp_iso: str
    stop_price: float
    take_price: Optional[float]
    entry_notional: float
    entry_commission: float
    entry_slippage_cost: float
    risk_policy_hash: str
    sizing_reason_code: str
    contract_multiplier: float
    decision_candle_index: int     # свеча закрытия сигнала
    entry_candle_index: int        # свеча исполнения


@dataclass(frozen=True)
class ClosedTrade:
    """Закрытая сделка: полный атрибутированный результат (для отчёта)."""
    figi: str
    quantity: int
    lot_size: int
    lot_count: int
    contract_multiplier: float
    entry_candle_index: int
    exit_candle_index: int
    entry_timestamp_iso: str
    exit_timestamp_iso: str
    entry_exec_price: float
    exit_exec_price: float
    exit_raw_price: float
    entry_commission: float
    exit_commission: float
    entry_slippage_cost: float
    exit_slippage_cost: float
    pnl_gross: float
    pnl_net: float
    exit_type: str
    exit_reason_code: str
    ambiguity_flags: Tuple[str, ...]
    risk_policy_hash: str
    sizing_reason_code: str
    exit_decision_diagnostics: Mapping[str, Any]

    def as_dict(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = dict(
            (k, v) for k, v in vars(self).items())
        payload["ambiguity_flags"] = list(self.ambiguity_flags)
        payload["exit_decision_diagnostics"] = \
            dict(self.exit_decision_diagnostics)
        return payload


class PortfolioLedger:
    """Виртуальный денежный портфель long-only (fail-closed инварианты).

    Инварианты (проверяются при каждой операции):
      * кэш не может стать отрицательным (плечо отсутствует: вход
        разрешён только при полном покрытии notional + комиссии);
      * cash == initial_cash + сумма реализованных net-PnL закрытых сделок
        (сохранение денег);
      * одновременно не более одной позиции по инструменту;
      * история операций — только добавление, неизменяемые записи.
    """

    def __init__(self, *, initial_cash: float, figi: str) -> None:
        if isinstance(initial_cash, bool) or \
                not isinstance(initial_cash, (int, float)) or \
                not math.isfinite(float(initial_cash)) or \
                float(initial_cash) <= 0.0:
            raise LedgerError(
                f"initial_cash должен быть конечным числом > 0; получено "
                f"{initial_cash!r}")
        if not isinstance(figi, str) or not figi:
            raise LedgerError("figi портфеля должен быть непустой строкой")
        self._initial_cash = float(initial_cash)
        self._cash = float(initial_cash)
        self._figi = figi
        self._position: Optional[OpenPosition] = None
        self._operations: List[LedgerOperation] = []
        self._closed_trades: List[ClosedTrade] = []
        self._op_counter = 0

    # --- состояние ----------------------------------------------------------

    @property
    def cash(self) -> float:
        return self._cash

    @property
    def initial_cash(self) -> float:
        return self._initial_cash

    @property
    def position(self) -> Optional[OpenPosition]:
        return self._position

    @property
    def operations(self) -> Tuple[LedgerOperation, ...]:
        return tuple(self._operations)

    @property
    def closed_trades(self) -> Tuple[ClosedTrade, ...]:
        return tuple(self._closed_trades)

    @property
    def total_commission(self) -> float:
        return math.fsum(op.commission for op in self._operations)

    @property
    def total_slippage_cost(self) -> float:
        return math.fsum(op.slippage_cost for op in self._operations)

    def verify_cash_conservation(self) -> None:
        """Инвариант сохранения денег (fail-closed).

        При открытой позиции деньги находятся В ПОЗИЦИИ:
          cash == initial + realized(закрытых) - стоимость_открытой_позиции;
        при закрытой — стоимость открытой позиции равна нулю и инвариант
        вырождается в cash == initial + realized. Порядок float-операций
        в правой и левой частях различается, поэтому сравнение — с
        относительным допуском 1e-9 (ошибки формул дают расхождения
        НАМНОГО больше; 1e-9 отлавливает любые содержательные дефекты).
        """
        realized = math.fsum(
            trade.pnl_net for trade in self._closed_trades)
        open_cost = 0.0
        if self._position is not None:
            open_cost = self._position.entry_notional \
                + self._position.entry_commission
        expected = self._initial_cash + realized - open_cost
        if not math.isclose(self._cash, expected,
                            rel_tol=1e-9, abs_tol=1e-9):
            raise LedgerError(
                "инвариант сохранения денег нарушен: cash="
                f"{self._cash!r}, expected initial+realized-open="
                f"{expected!r}")

    def equity_at_price(self, mark_price: float) -> float:
        """Стоимость портфеля по цене отметки: кэш + рыночная стоимость
        позиции (LONG; комиссия входа уже списана с кэша)."""
        if isinstance(mark_price, bool) or \
                not isinstance(mark_price, (int, float)) or \
                not math.isfinite(float(mark_price)) or \
                float(mark_price) <= 0.0:
            raise LedgerError(
                f"mark_price должен быть конечным числом > 0; получено "
                f"{mark_price!r}")
        if self._position is None:
            return self._cash
        multiplier = self._position.contract_multiplier
        return self._cash + self._position.quantity * multiplier * \
            float(mark_price)

    def unrealized_pnl_net(self, mark_price: float) -> Optional[float]:
        """Нереализованный PnL открытой позиции: рыночная стоимость по
        отметке минус полная стоимость входа (notional + комиссия входа).
        Оценка комиссии будущего выхода сознательно НЕ включается (точная
        цена выхода неизвестна); None — позиции нет."""
        if self._position is None:
            return None
        pos = self._position
        market_value = pos.quantity * pos.contract_multiplier * \
            float(mark_price)
        return market_value - (pos.entry_notional + pos.entry_commission)

    # --- операции ------------------------------------------------------------

    def open_position(self, *,
                      position: OpenPosition,
                      timestamp_iso: str) -> LedgerOperation:
        """Открытие LONG-позиции ПОЛНОЙ суммой объёма от Stage D.

        Fail-closed: при недостатке кэша (notional + комиссия > кэш)
        позиция НЕ открывается и поднимается LedgerError — вызывающий
        симулятор обязан предварительно проверять покупательную
        способность; двойного расходования денег не существует.
        """
        if type(position) is not OpenPosition:
            raise LedgerError(
                "open_position требует точный тип OpenPosition")
        if self._position is not None:
            raise LedgerError(
                "открытие второй позиции запрещено: позиция уже открыта "
                f"(figi={self._position.figi}, qty="
                f"{self._position.quantity})")
        if position.figi != self._figi:
            raise LedgerError(
                f"позиция чужого инструмента {position.figi!r} не может "
                f"быть открыта в портфеле {self._figi!r}")
        needed = position.entry_notional + position.entry_commission
        if needed > self._cash:
            raise LedgerError(
                "недостаточно кэша для входа: нужно "
                f"{needed!r}, доступно {self._cash!r} (плечо запрещено)")
        self._cash = self._cash - needed
        self._position = position
        self._op_counter += 1
        operation = LedgerOperation(
            op_index=self._op_counter,
            kind="ENTRY_EXECUTED",
            timestamp_iso=timestamp_iso,
            price=position.entry_exec_price,
            quantity=position.quantity,
            notional=position.entry_notional,
            commission=position.entry_commission,
            slippage_cost=position.entry_slippage_cost,
            cash_after=self._cash,
            realized_pnl_net=None,
            details={
                "risk_policy_hash": position.risk_policy_hash,
                "sizing_reason_code": position.sizing_reason_code,
                "lot_count": position.lot_count,
                "decision_candle_index": position.decision_candle_index,
                "entry_candle_index": position.entry_candle_index,
            },
        )
        self._operations.append(operation)
        self.verify_cash_conservation()
        return operation

    def close_position(self, *,
                       exit_exec_price: float,
                       exit_raw_price: float,
                       exit_commission: float,
                       exit_slippage_cost: float,
                       exit_type: str,
                       exit_reason_code: str,
                       exit_timestamp_iso: str,
                       exit_candle_index: int,
                       ambiguity_flags: Tuple[str, ...] = (),
                       exit_decision_diagnostics: Optional[
                           Mapping[str, Any]] = None) -> ClosedTrade:
        """Полное закрытие LONG-позиции (частичных закрытий нет: объём
        позиций задаётся Stage D целиком; ТЗ Stage D/§6 не меняются)."""
        if self._position is None:
            raise LedgerError("закрытие при отсутствии позиции запрещено")
        if isinstance(exit_exec_price, bool) or \
                not isinstance(exit_exec_price, (int, float)) or \
                not math.isfinite(float(exit_exec_price)) or \
                float(exit_exec_price) <= 0.0:
            raise LedgerError(
                f"exit_exec_price должен быть конечным числом > 0; "
                f"получено {exit_exec_price!r}")
        if exit_type not in (EXIT_TYPE_STOP_LOSS, EXIT_TYPE_TAKE_PROFIT,
                             EXIT_TYPE_STRATEGIC_SELL):
            raise LedgerError(
                f"неизвестный тип выхода: {exit_type!r}")
        pos = self._position
        multiplier = pos.contract_multiplier
        exit_notional = float(exit_exec_price) * pos.quantity * multiplier
        proceeds = exit_notional - exit_commission
        self._cash = self._cash + proceeds
        pnl_gross = (float(exit_exec_price) - pos.entry_exec_price) * \
            pos.quantity * multiplier
        pnl_net = proceeds - (pos.entry_notional + pos.entry_commission)
        trade = ClosedTrade(
            figi=pos.figi,
            quantity=pos.quantity,
            lot_size=pos.lot_size,
            lot_count=pos.lot_count,
            contract_multiplier=multiplier,
            entry_candle_index=pos.entry_candle_index,
            exit_candle_index=exit_candle_index,
            entry_timestamp_iso=pos.entry_timestamp_iso,
            exit_timestamp_iso=exit_timestamp_iso,
            entry_exec_price=pos.entry_exec_price,
            exit_exec_price=float(exit_exec_price),
            exit_raw_price=float(exit_raw_price),
            entry_commission=pos.entry_commission,
            exit_commission=exit_commission,
            entry_slippage_cost=pos.entry_slippage_cost,
            exit_slippage_cost=exit_slippage_cost,
            pnl_gross=pnl_gross,
            pnl_net=pnl_net,
            exit_type=exit_type,
            exit_reason_code=exit_reason_code,
            ambiguity_flags=tuple(ambiguity_flags),
            risk_policy_hash=pos.risk_policy_hash,
            sizing_reason_code=pos.sizing_reason_code,
            exit_decision_diagnostics=dict(exit_decision_diagnostics or {}),
        )
        self._closed_trades.append(trade)
        self._position = None
        self._op_counter += 1
        operation = LedgerOperation(
            op_index=self._op_counter,
            kind="EXIT_EXECUTED",
            timestamp_iso=exit_timestamp_iso,
            price=float(exit_exec_price),
            quantity=pos.quantity,
            notional=exit_notional,
            commission=exit_commission,
            slippage_cost=exit_slippage_cost,
            cash_after=self._cash,
            realized_pnl_net=pnl_net,
            details={
                "exit_type": exit_type,
                "exit_reason_code": exit_reason_code,
                "ambiguity_flags": list(ambiguity_flags),
            },
        )
        self._operations.append(operation)
        self.verify_cash_conservation()
        return trade
