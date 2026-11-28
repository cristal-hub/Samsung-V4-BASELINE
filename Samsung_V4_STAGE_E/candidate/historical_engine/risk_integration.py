# historical_engine/risk_integration.py
# SAMSUNG V4 — NEW STRATEGY ENGINE. STAGE E.
#
# RiskIntegration: расчёт размера позиции СТРОГО через СУЩЕСТВУЮЩИЙ
# контракт Stage D (candidate/strategy_risk.py). Движок НЕ дублирует и НЕ
# меняет: формулу риска, правила округления лотов, проверки входных
# данных, config_hash и стратегическую атрибуцию (ТЗ Stage E §6).
#
# Единственная роль этого модуля — подготовить SizingInput из фактических
# данных симуляции и передать его в calculate_position_size. Альтернативной
# реализации риск-формулы здесь НЕТ и быть не может.

from __future__ import annotations

from typing import Any, Dict, Optional

from strategy_risk import (
    AttributionContext,
    RiskPolicy,
    SizingInput,
    SizingResult,
    TradeSide,
    calculate_position_size,
)

from strategy_api import StrategyConfig

from .models import EngineConfig, ExecutionError


class RiskIntegration:
    """Связка симулятора с Stage D (calculate_position_size).

    Гарантии:
      * RiskPolicy строится РОВНО на паре (strategy_id, config_hash)
        переданной StrategyConfig и проверяется Stage D при каждом расчёте
        (verify_policy_hash внутри calculate_position_size);
      * сторона запроса — ТОЛЬКО TradeSide.LONG (long-only движок; SHORT
        явно не поддерживается Stage D и никогда не запрашивается);
      * available_equity  = фактический кэш портфеля на момент исполнения;
      * buying_power_limit = фактический кэш; резерв под комиссию входа
        выполняет САМА формула Stage D (per-unit buying-power стоимость
        включает entry_cost_per_unit); финальная точная проверка кэша
        выполняется исполнителем ДОТЧКУ;
      * entry_cost_per_unit / stop_exit_cost_per_unit — комиссия за единицу
        при входе/выходе по стопу (та же commission_rate, согласована с
        моделью исполнения);
      * результат Stage D (SizingResult) возвращается БЕЗ изменений:
        исход SIZED — единственный источник положительного объёма;
        блокирующие исходы (ZERO_SIZE, MISSING_REQUIRED_DATA,
        ATTRIBUTION_MISMATCH, ...) переносятся в журнал как блокировки
        входа с сохранением reason_code Stage D.
    """

    def __init__(self, *,
                 engine_config: EngineConfig,
                 strategy_config: StrategyConfig) -> None:
        if type(engine_config) is not EngineConfig:
            raise ExecutionError(
                "RiskIntegration требует точный тип EngineConfig")
        if type(strategy_config) is not StrategyConfig:
            raise ExecutionError(
                "RiskIntegration требует точный тип StrategyConfig "
                "(Stage A.2.1)")
        self._engine_config = engine_config
        self._strategy_config = strategy_config
        self._policy = RiskPolicy(
            strategy_id=strategy_config.strategy_id,
            config_hash=strategy_config.config_hash,
            risk_per_trade_fraction=engine_config.risk_per_trade_fraction,
            max_position_notional_fraction=
            engine_config.max_position_notional_fraction,
        )

    @property
    def policy(self) -> RiskPolicy:
        return self._policy

    @property
    def policy_hash(self) -> str:
        return self._policy.policy_hash

    # --- расчёт объёма (делегация Stage D) -----------------------------------

    def size_entry(self, *,
                   execution_price: float,
                   cash: float,
                   config: Optional[StrategyConfig] = None,
                   diagnostics_sink: Optional[Dict[str, Any]] = None
                   ) -> SizingResult:
        """Полный расчёт входного объёма через Stage D (чистая функция).

        execution_price — ФАКТИЧЕСКАЯ цена исполнения на следующей свече
        (уже с slippage, ограниченная диапазоном свечи); protective stop —
        строго ниже входа на stop_loss_fraction (геометрию дополнительно
        проверяет Stage D: INVALID_STOP_GEOMETRY при нарушении).

        config — переопределение конфигурации ТОЛЬКО для негативных тестов
        атрибуции; production-путь всегда использует конфигурацию,
        привязанную при создании (None).
        """
        cfg = self._engine_config
        s_cfg = self._strategy_config if config is None else config
        if type(s_cfg) is not StrategyConfig:
            raise ExecutionError(
                "size_entry: config должен быть точным типом "
                "StrategyConfig или None")
        if isinstance(execution_price, bool) or \
                not isinstance(execution_price, (int, float)):
            raise ExecutionError(
                "execution_price должен быть числом")
        entry_price = float(execution_price)
        if entry_price <= 0.0:
            raise ExecutionError(
                f"execution_price должен быть > 0; получено {entry_price!r}")
        if isinstance(cash, bool) or not isinstance(cash, (int, float)) \
                or float(cash) <= 0.0:
            raise ExecutionError(
                f"cash должен быть конечным числом > 0; получено {cash!r}")

        # Защитный стоп: строго ниже цены входа (LONG). Обязателен:
        # формула Stage D требует protective_stop_price (см. EngineConfig).
        stop_price = entry_price * (1.0 - cfg.stop_loss_fraction)
        # Комиссия за единицу: согласована с исполнителем (rate * цена).
        entry_cost_per_unit = cfg.commission_rate * entry_price
        stop_exit_cost_per_unit = cfg.commission_rate * stop_price
        # Покупательная способность = фактический кэш БЕЗ дополнительного
        # резерва: формула Stage D уже включает комиссию входа в
        # per-unit buying-power стоимость (entry_price + entry_cost_per_unit),
        # поэтому лимит Stage D сам оставляет место под комиссию.
        # Финальная точная проверка кэша — у исполнителя ДОТЧКУ.
        buying_power_limit = float(cash)

        sizing_input = SizingInput(
            attribution=AttributionContext.from_config(s_cfg),
            figi=cfg.figi,
            side=TradeSide.LONG,
            available_equity=float(cash),
            buying_power_limit=buying_power_limit,
            entry_price=entry_price,
            protective_stop_price=stop_price,
            lot_size=cfg.lot_size,
            contract_multiplier=cfg.contract_multiplier,
            entry_cost_per_unit=entry_cost_per_unit,
            stop_exit_cost_per_unit=stop_exit_cost_per_unit,
        )
        result = calculate_position_size(
            policy=self._policy, config=s_cfg, sizing_input=sizing_input)
        if diagnostics_sink is not None:
            diagnostics = dict(result.diagnostics)
            inputs_decimal = dict(diagnostics.get("inputs_decimal") or {})
            diagnostics_sink["sizing_outcome"] = result.outcome.value
            diagnostics_sink["sizing_reason_code"] = result.reason_code
            diagnostics_sink["sizing_quantity"] = result.quantity
            diagnostics_sink["sizing_lot_count"] = result.lot_count
            diagnostics_sink["risk_policy_hash"] = result.risk_policy_hash
            diagnostics_sink["sizing_rules_version"] = \
                diagnostics.get("sizing_rules_version", "")
            diagnostics_sink["entry_price_exact"] = \
                inputs_decimal.get("entry_price", "")
            diagnostics_sink["stop_price_exact"] = \
                inputs_decimal.get("stop_price", "")
            diagnostics_sink["units_by_risk"] = \
                diagnostics.get("units_by_risk")
            diagnostics_sink["units_by_notional"] = \
                diagnostics.get("units_by_notional")
            diagnostics_sink["units_by_buying_power"] = \
                diagnostics.get("units_by_buying_power")
            diagnostics_sink["limiting_constraint"] = \
                diagnostics.get("limiting_constraint", "")
        return result
