# tests/test_stage_d_strategy_risk.py — SAMSUNG V4 — STAGE D.
#
# Стратегическое риск-масштабирование позиций (strategy_risk.py).
# Покрытие обязательных сценариев ТЗ Stage D §10 (17 категорий) и
# fail-closed требований §8:
#   §10.1  детерминированный расчёт валидного LONG-входа;
#   §10.2  две политики для одного инструмента -> разные объёмы;
#   §10.3  несоответствие policy/config атрибуции отклоняется;
#   §10.4  корректное округление ВНИЗ до целого лота;
#   §10.5  риск одного лота превышает бюджет;
#   §10.6  ограничение объёма max notional;
#   §10.7  ограничение объёма покупательной способностью;
#   §10.8  входные/выходные затраты корректно уменьшают объём;
#   §10.9  стоп не на стороне убытка блокирует расчёт;
#   §10.10 отсутствующие входы блокируют расчёт;
#   §10.11 NaN/Infinity/bool отклоняются;
#   §10.12 неподдерживаемая сторона отклоняется;
#   §10.13 атрибуция и хеши результата корректны;
#   §10.14 хеш политики стабилен;
#   §10.15 результат неизменяем;
#   §10.16 блокирующий результат никогда не содержит положительный
#          объём (параметризованно по всем блокирующим исходам);
#   §10.17 повторный расчёт детерминированно идентичен (в т.ч. при
#          чужом ambient-контексте Decimal);
#   плюс fail-closed §8: нулевые/отрицательные equity/цены, NaN/
#   Infinity, bool-как-число, нулевой/отрицательный лот, некорректный
#   multiplier/затраты, отсутствие cash/buying-power, стоп не на той
#   стороне, mismatched strategy_id/config_hash/FIGI, целостность
#   policy_hash, объём ниже одного лота, бюджет ниже риска одного
#   лота, notional-кап ниже одного лота, недостаточная покупательная
#   способность, границы округления, экстремальные значения и
#   переполнение;
#   плюс НЕГАТИВНЫЕ тесты (ТЗ §10): заведомо сломанные реализации
#   (позитивный объём в блокирующем исходе, превышение бюджета/
#   notional/buying power, некратность лоту, подмена атрибуции/хешей,
#   подклассы-обход) перехватываются публичным validate_sizing_result
#   и точными проверками типов — тесты ловят некорректные реализации.
#
# Все тесты offline, без сети и брокера; никаких заявок; старые файлы
# Samsung не затрагиваются. Legacy Samsung V4 остаётся REGRESSION_ONLY.

import dataclasses
import decimal
import json
from datetime import datetime, timedelta, timezone

import pytest

from attribution import AttributionContext
from strategy_api import StrategyConfig, compute_config_hash
from strategy_contracts import PriceData
from strategy_risk import (
    REASON_BUYING_POWER_BELOW_ONE_LOT,
    REASON_CONFIG_HASH_MISMATCH,
    REASON_FIGI_MISMATCH,
    REASON_INPUT_ATTRIBUTION_MISMATCH,
    REASON_INPUT_WRONG_TYPE,
    REASON_MISSING_REQUIRED_FIELDS,
    REASON_NOTIONAL_CAP_BELOW_ONE_LOT,
    REASON_POLICY_HASH_MISMATCH,
    REASON_QUANTITY_BELOW_ONE_LOT,
    REASON_RISK_BUDGET_BELOW_ONE_LOT,
    REASON_SIDE_UNSUPPORTED_SHORT,
    REASON_SIZED_LONG,
    REASON_STOP_NOT_BELOW_ENTRY,
    REASON_STRATEGY_ID_MISMATCH,
    SIZING_INPUT_DATA_FIELDS,
    RiskPolicy,
    RiskPolicyViolationError,
    SizingContractViolationError,
    SizingInput,
    SizingInputViolationError,
    SizingOutcome,
    SizingResult,
    SizingResultViolationError,
    StrategyRiskError,
    SUPPORTED_TRADE_SIDES,
    TradeSide,
    calculate_position_size,
    compute_risk_policy_hash,
    validate_sizing_result,
)


NOW = datetime(2026, 11, 28, 12, 0, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Фабрики (каждый тест создаёт собственные объекты — общего состояния нет)
# ---------------------------------------------------------------------------


def make_config(strategy_id="alpha", params=None):
    params = {"n": 3} if params is None else params
    return StrategyConfig(
        strategy_id=strategy_id,
        strategy_version="1.0.0",
        params=params,
        config_hash=compute_config_hash(strategy_id, "1.0.0", params),
    )


def make_policy(config=None, *, strategy_id=None, risk=0.01, cap=0.2):
    config = config or make_config()
    return RiskPolicy(
        strategy_id=strategy_id or config.strategy_id,
        config_hash=config.config_hash,
        risk_per_trade_fraction=risk,
        max_position_notional_fraction=cap,
    )


def make_input(config=None, **overrides):
    config = config or make_config()
    base = dict(
        attribution=AttributionContext.from_config(config),
        figi="FIGI1",
        side=TradeSide.LONG,
        available_equity=100000.0,
        buying_power_limit=50000.0,
        entry_price=100.0,
        protective_stop_price=95.0,
        lot_size=10,
        contract_multiplier=1.0,
        entry_cost_per_unit=0.05,
        stop_exit_cost_per_unit=0.05,
    )
    base.update(overrides)
    return SizingInput(**base)


def make_price(figi="FIGI1", price=100.0):
    ts = NOW + timedelta(seconds=-30)
    return PriceData(
        figi=figi, price=price,
        timestamp=ts.isoformat(timespec="microseconds")
        .replace("+00:00", "Z"),
        source="test-feed")


def make_sized_result():
    """Валидный SIZED-результат для негативных мутаций валидатора."""
    config = make_config()
    policy = make_policy(config)
    result = calculate_position_size(
        policy=policy, config=config, sizing_input=make_input(config))
    assert result.outcome is SizingOutcome.SIZED
    return config, policy, result


def assert_blocked(result, outcome=None, reason=None):
    """Блокирующий результат: нулевой объём и ноль лотов (ТЗ §10.16)."""
    assert type(result) is SizingResult
    assert result.outcome is not SizingOutcome.SIZED
    if outcome is not None:
        assert result.outcome is outcome
    if reason is not None:
        assert result.reason_code == reason
    assert result.quantity == 0
    assert result.lot_count == 0


# ---------------------------------------------------------------------------
# §10.1 Детерминированный расчёт валидного LONG-входа
# ---------------------------------------------------------------------------


class TestStageD1ValidLongSizing:
    def test_valid_long_deterministic_formula(self):
        config = make_config()
        policy = make_policy(config)  # 1% риска, 20% notional
        result = calculate_position_size(
            policy=policy, config=config, sizing_input=make_input(config))
        # budget = 100000*0.01 = 1000; price_risk = 5; total = 5.1;
        # units_by_risk = floor(1000/5.1) = 196; notional: 20000/100 = 200;
        # bp: 50000/100.05 = 499; min = 196 -> 19 лотов -> 190 единиц.
        assert result.outcome is SizingOutcome.SIZED
        assert result.reason_code == REASON_SIZED_LONG
        assert result.quantity == 190
        assert result.lot_count == 19
        assert result.lot_size == 10
        assert result.risk_budget == pytest.approx(1000.0)
        assert result.risk_per_unit == pytest.approx(5.1)
        assert result.total_position_risk == pytest.approx(969.0)
        assert result.position_notional == pytest.approx(19000.0)
        assert result.notional_cap == pytest.approx(20000.0)
        assert result.buying_power_cap == pytest.approx(50000.0)
        assert result.diagnostics["limiting_constraint"]["binding"] == "RISK"

    def test_exact_limits_hold_in_decimal(self):
        config = make_config()
        policy = make_policy(config, risk=0.013, cap=0.17)
        inp = make_input(config, entry_price=33.33,
                         protective_stop_price=31.11,
                         contract_multiplier=2.0,
                         entry_cost_per_unit=0.01,
                         stop_exit_cost_per_unit=0.02)
        result = calculate_position_size(policy=policy, config=config,
                                         sizing_input=inp)
        assert result.outcome is SizingOutcome.SIZED
        # Точные десятичные проверки лимитов (ТЗ §6).
        q = decimal.Decimal(result.quantity)
        with decimal.localcontext() as ctx:
            ctx.prec = 60
            budget = decimal.Decimal("100000") * decimal.Decimal("0.013")
            assert q * decimal.Decimal(str(result.risk_per_unit)) <= budget
            notional = q * decimal.Decimal("33.33") * decimal.Decimal("2.0")
            assert notional <= decimal.Decimal("100000") * \
                decimal.Decimal("0.17")
            bp = notional + q * decimal.Decimal("0.01")
            assert bp <= decimal.Decimal("50000")
        validate_sizing_result(result, expected_policy=policy,
                               expected_config=config, expected_input=inp)

    def test_result_carries_full_attribution_and_diagnostics(self):
        config = make_config()
        policy = make_policy(config)
        result = calculate_position_size(
            policy=policy, config=config, sizing_input=make_input(config))
        assert result.strategy_id == "alpha"
        assert result.config_hash == config.config_hash
        assert result.risk_policy_hash == policy.policy_hash
        assert result.figi == "FIGI1"
        diag = result.diagnostics
        assert diag["sizing_rules_version"] == "sizing_rules_v1"
        assert diag["rounding_method"] == "DECIMAL_EXACT_FLOOR_TO_LOT"
        # Точные десятичные представления: сравнение через Decimal
        # (десятичная арифметика сохраняет масштаб: 100000.0 * 0.01 =
        # 1000.000 — значащие нули масштаба честно отражены).
        assert decimal.Decimal(diag["inputs_decimal"]["equity"]) == \
            decimal.Decimal("100000.0")
        assert decimal.Decimal(
            diag["computed_decimal"]["risk_budget"]) == \
            decimal.Decimal("1000.0")
        assert diag["verification"] == {"risk_ok": True,
                                        "notional_ok": True,
                                        "buying_power_ok": True}


# ---------------------------------------------------------------------------
# §10.2 Две политики для одного инструмента -> разные объёмы
# ---------------------------------------------------------------------------


class TestStageD2TwoPolicies:
    def test_same_instrument_different_policies_different_quantities(self):
        config = make_config()
        conservative = make_policy(config, risk=0.01, cap=0.2)
        aggressive = make_policy(config, risk=0.02, cap=0.4)
        inp = make_input(config)
        r1 = calculate_position_size(policy=conservative, config=config,
                                     sizing_input=inp)
        r2 = calculate_position_size(policy=aggressive, config=config,
                                     sizing_input=inp)
        assert r1.outcome is SizingOutcome.SIZED
        assert r2.outcome is SizingOutcome.SIZED
        assert r1.quantity != r2.quantity
        # 1%: budget 1000 -> 196 ед. -> 19 лотов -> 190;
        # 2%: budget 2000 -> 392 ед. (notional-кап 40000/100 = 400 не
        # связывает) -> 39 лотов -> 390.
        assert r1.quantity == 190
        assert r2.quantity == 390
        assert r1.risk_policy_hash != r2.risk_policy_hash

    def test_notional_fraction_changes_quantity(self):
        config = make_config()
        wide = make_policy(config, risk=0.01, cap=0.2)
        narrow = make_policy(config, risk=0.01, cap=0.15)
        inp = make_input(config)
        r_wide = calculate_position_size(policy=wide, config=config,
                                         sizing_input=inp)
        r_narrow = calculate_position_size(policy=narrow, config=config,
                                           sizing_input=inp)
        assert r_wide.quantity == 190
        # cap 0.15 -> 15000/100 = 150 единиц -> 15 лотов -> 150.
        assert r_narrow.quantity == 150
        assert r_narrow.diagnostics["limiting_constraint"]["binding"] == \
            "NOTIONAL"


# ---------------------------------------------------------------------------
# §10.3 Несоответствие policy/config атрибуции отклоняется
# ---------------------------------------------------------------------------


class TestStageD3AttributionMismatch:
    def test_policy_of_other_strategy_rejected(self):
        config = make_config()
        foreign_policy = make_policy(make_config(strategy_id="beta"))
        result = calculate_position_size(
            policy=foreign_policy, config=config,
            sizing_input=make_input(config))
        assert_blocked(result, SizingOutcome.ATTRIBUTION_MISMATCH,
                       REASON_STRATEGY_ID_MISMATCH)
        assert result.diagnostics["policy_strategy_id"] == "beta"
        assert result.diagnostics["config_strategy_id"] == "alpha"

    def test_policy_of_other_config_hash_rejected(self):
        config = make_config()
        other_config = make_config(params={"n": 4})
        stale_policy = make_policy(other_config)  # тот же strategy_id
        assert stale_policy.strategy_id == config.strategy_id
        result = calculate_position_size(
            policy=stale_policy, config=config,
            sizing_input=make_input(config))
        assert_blocked(result, SizingOutcome.ATTRIBUTION_MISMATCH,
                       REASON_CONFIG_HASH_MISMATCH)
        assert result.diagnostics["policy_config_hash"] == \
            other_config.config_hash
        assert result.diagnostics["config_config_hash"] == config.config_hash

    def test_input_attribution_of_other_config_rejected(self):
        config = make_config()
        policy = make_policy(config)
        other_config = make_config(params={"n": 5})
        result = calculate_position_size(
            policy=policy, config=config,
            sizing_input=make_input(
                config, attribution=AttributionContext.from_config(
                    other_config)))
        assert_blocked(result, SizingOutcome.ATTRIBUTION_MISMATCH,
                       REASON_INPUT_ATTRIBUTION_MISMATCH)


# ---------------------------------------------------------------------------
# §10.4 Корректное округление ВНИЗ до целого лота
# ---------------------------------------------------------------------------


class TestStageD4DownwardLotRounding:
    def test_floor_to_lot_never_rounds_up(self):
        config = make_config()
        policy = make_policy(config)
        # 196 единиц по риску -> 19.6 лотов -> 19 лотов (НЕ 20).
        result = calculate_position_size(
            policy=policy, config=config, sizing_input=make_input(config))
        assert result.quantity == 190
        assert result.lot_count == 19
        assert result.quantity % result.lot_size == 0

    def test_exact_multiple_boundary(self):
        config = make_config()
        policy = make_policy(config)
        # total_risk = 5.0 -> budget 1000 -> ровно 200 единиц = 20 лотов.
        inp = make_input(config, entry_cost_per_unit=0.0,
                         stop_exit_cost_per_unit=0.0)
        result = calculate_position_size(policy=policy, config=config,
                                         sizing_input=inp)
        assert result.quantity == 200
        assert result.lot_count == 20

    def test_just_below_multiple_boundary(self):
        config = make_config()
        policy = make_policy(config)
        # budget 999 -> 199.8 -> 199 единиц -> 19 лотов (не 20).
        inp = make_input(config, available_equity=99900.0,
                         entry_cost_per_unit=0.0,
                         stop_exit_cost_per_unit=0.0)
        result = calculate_position_size(policy=policy, config=config,
                                         sizing_input=inp)
        assert result.quantity == 190
        assert result.lot_count == 19

    def test_lot_size_7_floor(self):
        config = make_config()
        policy = make_policy(config)
        # total_risk = 5.1 -> 196 единиц -> 196 // 7 = 28 лотов -> 196.
        inp = make_input(config, lot_size=7)
        result = calculate_position_size(policy=policy, config=config,
                                         sizing_input=inp)
        assert result.lot_size == 7
        assert result.quantity == 196
        assert result.lot_count == 28


# ---------------------------------------------------------------------------
# §10.5 Риск одного лота превышает бюджет
# ---------------------------------------------------------------------------


class TestStageD5OneLotRiskExceedsBudget:
    def test_risk_budget_below_one_lot(self):
        config = make_config()
        policy = make_policy(config)
        # budget 40 -> 40/5.1 = 7 единиц < 10 (лот) -> ZERO_SIZE.
        result = calculate_position_size(
            policy=policy, config=config,
            sizing_input=make_input(config, available_equity=40.0))
        assert_blocked(result, SizingOutcome.ZERO_SIZE,
                       REASON_RISK_BUDGET_BELOW_ONE_LOT)
        assert result.risk_budget == pytest.approx(0.4)

    def test_risk_exactly_one_lot_minus_epsilon(self):
        config = make_config()
        policy = make_policy(config)
        # budget 50 -> 9 единиц (50/5.1 = 9.8) < 10 -> ZERO_SIZE.
        result = calculate_position_size(
            policy=policy, config=config,
            sizing_input=make_input(config, available_equity=50.0))
        assert_blocked(result, SizingOutcome.ZERO_SIZE,
                       REASON_RISK_BUDGET_BELOW_ONE_LOT)

    def test_risk_exactly_one_lot_passes(self):
        config = make_config()
        policy = make_policy(config)
        # budget 51 (equity 5100) -> 10 единиц (51/5.1 = 10) -> ровно
        # 1 лот -> SIZED; bp 5000 покрывает 10 * 100.05 = 1000.5.
        result = calculate_position_size(
            policy=policy, config=config,
            sizing_input=make_input(config, available_equity=5100.0,
                                    buying_power_limit=5000.0))
        assert result.outcome is SizingOutcome.SIZED
        assert result.quantity == 10
        assert result.lot_count == 1


# ---------------------------------------------------------------------------
# §10.6 Ограничение объёма max notional
# ---------------------------------------------------------------------------


class TestStageD6NotionalCap:
    def test_notional_cap_limits_quantity(self):
        config = make_config()
        policy = make_policy(config, risk=0.01, cap=0.15)
        result = calculate_position_size(
            policy=policy, config=config, sizing_input=make_input(config))
        assert result.quantity == 150
        assert result.position_notional <= result.notional_cap
        assert result.diagnostics["limiting_constraint"]["binding"] == \
            "NOTIONAL"

    def test_notional_cap_below_one_lot(self):
        config = make_config()
        policy = make_policy(config, risk=0.01, cap=0.004)
        # cap 400 -> 4 единицы < 10 -> ZERO_SIZE по notional.
        result = calculate_position_size(
            policy=policy, config=config, sizing_input=make_input(config))
        assert_blocked(result, SizingOutcome.ZERO_SIZE,
                       REASON_NOTIONAL_CAP_BELOW_ONE_LOT)

    def test_multiplier_enters_notional_cap(self):
        config = make_config()
        policy = make_policy(config, risk=0.01, cap=0.08)
        # per-unit notional = 100*2 = 200 -> cap 8000 -> 40 единиц
        # -> 4 лота -> 40; риск: 1000/10.1 = 99 ед. — NOTIONAL связывает.
        inp = make_input(config, contract_multiplier=2.0)
        result = calculate_position_size(policy=policy, config=config,
                                         sizing_input=inp)
        assert result.quantity == 40
        assert result.diagnostics["units_by_notional"] == 40
        assert result.diagnostics["limiting_constraint"]["binding"] == \
            "NOTIONAL"


# ---------------------------------------------------------------------------
# §10.7 Ограничение объёма покупательной способностью
# ---------------------------------------------------------------------------


class TestStageD7BuyingPowerCap:
    def test_buying_power_limits_quantity(self):
        config = make_config()
        policy = make_policy(config)
        # bp 12000; per-unit bp = 100.05 -> 119 единиц -> 11 лотов -> 110.
        result = calculate_position_size(
            policy=policy, config=config,
            sizing_input=make_input(config, buying_power_limit=12000.0))
        assert result.quantity == 110
        assert result.diagnostics["limiting_constraint"]["binding"] == \
            "BUYING_POWER"
        # Точная проверка: расход bp не превышает лимит.
        q = decimal.Decimal(result.quantity)
        assert q * (decimal.Decimal("100") + decimal.Decimal("0.05")) \
            <= decimal.Decimal("12000")

    def test_insufficient_buying_power_below_one_lot(self):
        config = make_config()
        policy = make_policy(config)
        # bp 500 -> 4 единицы < 10 -> ZERO_SIZE.
        result = calculate_position_size(
            policy=policy, config=config,
            sizing_input=make_input(config, buying_power_limit=500.0))
        assert_blocked(result, SizingOutcome.ZERO_SIZE,
                       REASON_BUYING_POWER_BELOW_ONE_LOT)

    def test_zero_buying_power_is_explicit_zero_size(self):
        config = make_config()
        policy = make_policy(config)
        result = calculate_position_size(
            policy=policy, config=config,
            sizing_input=make_input(config, buying_power_limit=0.0))
        # Явный ноль средств — валидные данные: объём 0 (не ошибка ввода).
        assert_blocked(result, SizingOutcome.ZERO_SIZE,
                       REASON_BUYING_POWER_BELOW_ONE_LOT)
        assert result.buying_power_cap == 0.0


# ---------------------------------------------------------------------------
# §10.8 Затраты корректно уменьшают объём
# ---------------------------------------------------------------------------


class TestStageD8CostsReduceQuantity:
    def test_entry_and_exit_costs_reduce_quantity(self):
        config = make_config()
        policy = make_policy(config)
        base = calculate_position_size(
            policy=policy, config=config, sizing_input=make_input(config))
        with_costs = calculate_position_size(
            policy=policy, config=config,
            sizing_input=make_input(config, entry_cost_per_unit=0.5,
                                    stop_exit_cost_per_unit=0.5))
        assert base.quantity == 190
        # total_risk 5.1 -> 6.0: 1000/6 = 166 -> 16 лотов -> 160.
        assert with_costs.quantity == 160
        assert with_costs.quantity < base.quantity
        assert with_costs.risk_per_unit == pytest.approx(6.0)

    def test_quantity_monotonically_non_increasing_in_costs(self):
        config = make_config()
        policy = make_policy(config)
        quantities = []
        for cost in (0.0, 0.1, 1.0, 5.0):
            result = calculate_position_size(
                policy=policy, config=config,
                sizing_input=make_input(config, entry_cost_per_unit=cost,
                                        stop_exit_cost_per_unit=cost))
            assert result.outcome is SizingOutcome.SIZED
            quantities.append(result.quantity)
        assert quantities == sorted(quantities, reverse=True)
        assert quantities[0] >= quantities[-1]

    def test_explicit_zero_cost_is_data_not_missing(self):
        config = make_config()
        policy = make_policy(config)
        result = calculate_position_size(
            policy=policy, config=config,
            sizing_input=make_input(config, entry_cost_per_unit=0.0,
                                    stop_exit_cost_per_unit=0.0))
        # Явно переданный ноль затрат — данные, а не «неизвестно».
        assert result.outcome is SizingOutcome.SIZED
        assert result.risk_per_unit == pytest.approx(5.0)

    def test_missing_costs_block_sizing(self):
        config = make_config()
        policy = make_policy(config)
        result = calculate_position_size(
            policy=policy, config=config,
            sizing_input=make_input(config, entry_cost_per_unit=None,
                                    stop_exit_cost_per_unit=None))
        assert_blocked(result, SizingOutcome.MISSING_REQUIRED_DATA,
                       REASON_MISSING_REQUIRED_FIELDS)
        assert "entry_cost_per_unit" in result.diagnostics["missing_fields"]
        assert "stop_exit_cost_per_unit" in \
            result.diagnostics["missing_fields"]


# ---------------------------------------------------------------------------
# §10.9 Стоп не на стороне убытка блокирует расчёт
# ---------------------------------------------------------------------------


class TestStageD9StopGeometry:
    def test_stop_above_entry_blocks(self):
        config = make_config()
        policy = make_policy(config)
        result = calculate_position_size(
            policy=policy, config=config,
            sizing_input=make_input(config, protective_stop_price=105.0))
        assert_blocked(result, SizingOutcome.INVALID_STOP_GEOMETRY,
                       REASON_STOP_NOT_BELOW_ENTRY)
        assert result.diagnostics["stop_relation"] == "ABOVE_ENTRY"

    def test_stop_equal_to_entry_blocks(self):
        config = make_config()
        policy = make_policy(config)
        result = calculate_position_size(
            policy=policy, config=config,
            sizing_input=make_input(config, protective_stop_price=100.0))
        assert_blocked(result, SizingOutcome.INVALID_STOP_GEOMETRY,
                       REASON_STOP_NOT_BELOW_ENTRY)
        assert result.diagnostics["stop_relation"] == "EQUAL_TO_ENTRY"

    def test_stop_must_be_strictly_below(self):
        config = make_config()
        policy = make_policy(config)
        ok = calculate_position_size(
            policy=policy, config=config,
            sizing_input=make_input(config, protective_stop_price=94.999))
        assert ok.outcome is SizingOutcome.SIZED
        # price_risk = 5.001; total_risk = 5.001 + 0.05 + 0.05 = 5.101.
        assert ok.risk_per_unit == pytest.approx(5.101)


# ---------------------------------------------------------------------------
# §10.10 Отсутствующие входы блокируют расчёт (по одному полю)
# ---------------------------------------------------------------------------


class TestStageD10MissingInputs:
    @pytest.mark.parametrize("field", SIZING_INPUT_DATA_FIELDS)
    def test_each_missing_field_blocks(self, field):
        config = make_config()
        policy = make_policy(config)
        overrides = {field: None}
        result = calculate_position_size(
            policy=policy, config=config,
            sizing_input=make_input(config, **overrides))
        assert_blocked(result, SizingOutcome.MISSING_REQUIRED_DATA,
                       REASON_MISSING_REQUIRED_FIELDS)
        assert result.diagnostics["missing_fields"] == [field]

    def test_all_fields_missing_lists_all(self):
        config = make_config()
        policy = make_policy(config)
        result = calculate_position_size(
            policy=policy, config=config,
            sizing_input=make_input(
                config, **{name: None for name in SIZING_INPUT_DATA_FIELDS}))
        assert result.diagnostics["missing_fields"] == \
            list(SIZING_INPUT_DATA_FIELDS)

    def test_missing_data_is_not_invented(self):
        config = make_config()
        policy = make_policy(config)
        result = calculate_position_size(
            policy=policy, config=config,
            sizing_input=make_input(config, available_equity=None))
        # Значения НЕ придумываются: денежные поля пусты, объём 0.
        assert result.risk_budget is None
        assert result.position_notional is None
        assert result.quantity == 0


# ---------------------------------------------------------------------------
# §10.11 NaN/Infinity/bool отклоняются
# ---------------------------------------------------------------------------


class TestStageD11NonFiniteAndBoolean:
    @pytest.mark.parametrize("field", [
        "available_equity", "buying_power_limit", "entry_price",
        "protective_stop_price", "contract_multiplier",
        "entry_cost_per_unit", "stop_exit_cost_per_unit",
    ])
    @pytest.mark.parametrize("bad", [float("nan"), float("inf"),
                                     float("-inf")])
    def test_non_finite_rejected_at_construction(self, field, bad):
        with pytest.raises(SizingInputViolationError):
            make_input(**{field: bad})

    @pytest.mark.parametrize("field", [
        "available_equity", "buying_power_limit", "entry_price",
        "protective_stop_price", "contract_multiplier",
        "entry_cost_per_unit", "stop_exit_cost_per_unit",
    ])
    @pytest.mark.parametrize("bad", [True, False])
    def test_boolean_not_accepted_as_number(self, field, bad):
        with pytest.raises(SizingInputViolationError):
            make_input(**{field: bad})

    def test_boolean_lot_size_rejected(self):
        with pytest.raises(SizingInputViolationError):
            make_input(lot_size=True)
        with pytest.raises(SizingInputViolationError):
            make_input(lot_size=False)

    def test_boolean_fraction_rejected(self):
        config = make_config()
        with pytest.raises(RiskPolicyViolationError):
            make_policy(config, risk=True)
        with pytest.raises(RiskPolicyViolationError):
            make_policy(config, cap=False)

    def test_sizer_never_sees_non_finite_input(self):
        # Объект с NaN создать невозможно; расчёт на «мусорном» входе
        # невозможен в принципе — некорректное значение не упаковывается
        # в типизированный объект (fail-closed на границе типа).
        config = make_config()
        policy = make_policy(config)
        result = calculate_position_size(
            policy=policy, config=config,
            sizing_input={"available_equity": float("nan")})
        assert_blocked(result, SizingOutcome.INVALID_INPUT,
                       REASON_INPUT_WRONG_TYPE)


# ---------------------------------------------------------------------------
# §10.12 Неподдерживаемая сторона отклоняется
# ---------------------------------------------------------------------------


class TestStageD12UnsupportedSide:
    def test_short_is_explicitly_unsupported(self):
        config = make_config()
        policy = make_policy(config)
        result = calculate_position_size(
            policy=policy, config=config,
            sizing_input=make_input(config, side=TradeSide.SHORT))
        assert_blocked(result, SizingOutcome.UNSUPPORTED_SIDE,
                       REASON_SIDE_UNSUPPORTED_SHORT)
        assert result.diagnostics["requested_side"] == "SHORT"
        assert result.diagnostics["supported_sides"] == ["LONG"]

    def test_supported_sides_contains_only_long(self):
        assert SUPPORTED_TRADE_SIDES == (TradeSide.LONG,)

    def test_signal_direction_not_silently_interpreted(self):
        # SignalDirection (BUY/SELL/HOLD) — НЕ TradeSide: передача
        # отклоняется (молчаливой интерпретации нет, ТЗ §5).
        from strategy_api import SignalDirection
        config = make_config()
        with pytest.raises(SizingInputViolationError):
            make_input(config, side=SignalDirection.BUY)
        with pytest.raises(SizingInputViolationError):
            make_input(config, side=SignalDirection.SELL)
        with pytest.raises(SizingInputViolationError):
            make_input(config, side=SignalDirection.HOLD)

    def test_string_side_rejected(self):
        with pytest.raises(SizingInputViolationError):
            make_input(side="LONG")
        with pytest.raises(SizingInputViolationError):
            make_input(side="SHORT")


# ---------------------------------------------------------------------------
# §10.13 Атрибуция и хеши результата корректны
# ---------------------------------------------------------------------------


class TestStageD13ResultAttributionAndHashes:
    def test_result_attribution_matches_policy_and_config(self):
        config = make_config()
        policy = make_policy(config)
        result = calculate_position_size(
            policy=policy, config=config, sizing_input=make_input(config))
        assert result.strategy_id == policy.strategy_id
        assert result.strategy_id == config.strategy_id
        assert result.config_hash == policy.config_hash
        assert result.config_hash == config.config_hash
        assert result.risk_policy_hash == policy.policy_hash
        validate_sizing_result(result, expected_policy=policy,
                               expected_config=config)

    def test_policy_hash_recomputes_from_actual_parameters(self):
        config = make_config()
        policy = make_policy(config, risk=0.025, cap=0.3)
        expected = compute_risk_policy_hash(
            "alpha", config.config_hash, 0.025, 0.3)
        assert policy.policy_hash == expected
        assert policy.verify_policy_hash() == expected

    def test_policy_hash_detects_tampering(self):
        config = make_config()
        policy = make_policy(config)
        # Изменение поля В ОБХОД API -> целостность нарушена (ТЗ §8).
        object.__setattr__(policy, "risk_per_trade_fraction", 0.9)
        with pytest.raises(RiskPolicyViolationError):
            policy.verify_policy_hash()
        result = calculate_position_size(
            policy=policy, config=config, sizing_input=make_input(config))
        assert_blocked(result, SizingOutcome.POLICY_INVALID,
                       REASON_POLICY_HASH_MISMATCH)
        assert result.quantity == 0

    def test_blocked_result_attribution_still_verified(self):
        config = make_config()
        policy = make_policy(config)
        result = calculate_position_size(
            policy=policy, config=config,
            sizing_input=make_input(config, side=TradeSide.SHORT))
        assert result.strategy_id == config.strategy_id
        assert result.config_hash == config.config_hash
        assert result.risk_policy_hash == policy.policy_hash
        validate_sizing_result(result)


# ---------------------------------------------------------------------------
# §10.14 Хеш политики стабилен
# ---------------------------------------------------------------------------


class TestStageD14PolicyHashStability:
    def test_same_parameters_same_hash(self):
        config = make_config()
        p1 = make_policy(config, risk=0.01, cap=0.2)
        p2 = make_policy(config, risk=0.01, cap=0.2)
        assert p1.policy_hash == p2.policy_hash

    def test_any_parameter_change_changes_hash(self):
        config = make_config()
        base = make_policy(config, risk=0.01, cap=0.2).policy_hash
        assert make_policy(config, risk=0.02, cap=0.2).policy_hash != base
        assert make_policy(config, risk=0.01, cap=0.3).policy_hash != base

    def test_other_config_hash_changes_policy_hash(self):
        c1 = make_config(params={"n": 3})
        c2 = make_config(params={"n": 4})
        assert make_policy(c1).policy_hash != make_policy(c2).policy_hash

    def test_hash_is_sha256_hex_digest_without_time_or_environment(self):
        config = make_config()
        h = make_policy(config).policy_hash
        assert len(h) == 64
        assert all(char in "0123456789abcdef" for char in h)
        # Детерминизм независимо от порядка создания и «времени»:
        # повторное создание даёт тот же хеш (нет salt/времени/ENV).
        assert make_policy(config).policy_hash == h
        # Канонический payload содержит только фактические параметры.
        payload = {
            "schema": "risk_policy_v1",
            "strategy_id": "alpha",
            "config_hash": config.config_hash,
            "risk_per_trade_fraction": repr(0.01),
            "max_position_notional_fraction": repr(0.2),
        }
        import hashlib
        canonical = json.dumps(payload, sort_keys=True,
                               separators=(",", ":"), ensure_ascii=True,
                               allow_nan=False)
        assert hashlib.sha256(canonical.encode("utf-8")).hexdigest() == h

    def test_policy_dict_is_json_compatible(self):
        config = make_config()
        policy = make_policy(config)
        as_dict = policy.as_dict()
        assert json.loads(json.dumps(as_dict))["policy_hash"] == \
            policy.policy_hash


# ---------------------------------------------------------------------------
# §10.15 Результат (и вход, и политика) неизменяемы
# ---------------------------------------------------------------------------


class TestStageD15Immutability:
    def test_result_is_frozen(self):
        _, _, result = make_sized_result()
        with pytest.raises(Exception):
            result.quantity = 999
        with pytest.raises(Exception):
            result.outcome = SizingOutcome.ZERO_SIZE

    def test_result_diagnostics_deep_frozen(self):
        _, _, result = make_sized_result()
        with pytest.raises(TypeError):
            result.diagnostics["new_key"] = 1
        with pytest.raises(TypeError):
            result.diagnostics["inputs_decimal"]["equity"] = "1"

    def test_input_is_frozen(self):
        inp = make_input()
        with pytest.raises(Exception):
            inp.available_equity = 1.0

    def test_policy_is_frozen(self):
        config = make_config()
        policy = make_policy(config)
        with pytest.raises(Exception):
            policy.risk_per_trade_fraction = 0.5
        with pytest.raises(Exception):
            policy.strategy_id = "beta"
        # object.__setattr__ ОБХОДИТ frozen (так работает __post_init__):
        # именно поэтому политика несёт зафиксированный при создании
        # хеш, и обход обнаруживается verify_policy_hash (см. §10.13).
        object.__setattr__(policy, "risk_per_trade_fraction", 0.9)
        with pytest.raises(RiskPolicyViolationError):
            policy.verify_policy_hash()

    def test_dataclasses_replace_creates_new_object_original_intact(self):
        _, _, result = make_sized_result()
        before = result.quantity
        copy_result = dataclasses.replace(result)
        assert copy_result is not result
        assert copy_result == result
        assert result.quantity == before

    def test_input_source_dict_mutation_does_not_affect_object(self):
        source = {"figi": "FIGI1"}
        inp = make_input(figi=source["figi"])
        source["figi"] = "FIGI2"
        assert inp.figi == "FIGI1"


# ---------------------------------------------------------------------------
# §10.16 Блокирующий результат никогда не содержит положительный объём
# ---------------------------------------------------------------------------


BLOCKING_CASES = [
    ("input_wrong_type", {}, None),  # sizing_input задают особо
    ("missing_equity", {"available_equity": None},
     SizingOutcome.MISSING_REQUIRED_DATA),
    ("missing_figi", {"figi": None}, SizingOutcome.MISSING_REQUIRED_DATA),
    ("short_side", {"side": TradeSide.SHORT},
     SizingOutcome.UNSUPPORTED_SIDE),
    ("foreign_figi_quote", {"entry_price": make_price("FIGI9", 100.0)},
     SizingOutcome.ATTRIBUTION_MISMATCH),
    ("stop_above", {"protective_stop_price": 105.0},
     SizingOutcome.INVALID_STOP_GEOMETRY),
    ("zero_equity_invalid", {"available_equity": 0.0}, None),
]


class TestStageD16BlockedNeverPositive:
    def test_all_typed_blocked_outcomes_have_zero_quantity(self):
        config = make_config()
        policy = make_policy(config)
        cases = [
            make_input(config, available_equity=None),
            make_input(config, side=TradeSide.SHORT),
            make_input(config, protective_stop_price=105.0),
            make_input(config, protective_stop_price=100.0),
            make_input(config, available_equity=40.0),
            make_input(config, buying_power_limit=500.0),
        ]
        for inp in cases:
            result = calculate_position_size(policy=policy, config=config,
                                             sizing_input=inp)
            assert_blocked(result)
            validate_sizing_result(result)

    def test_zero_size_has_zero_notional_and_zero_risk(self):
        config = make_config()
        policy = make_policy(config)
        result = calculate_position_size(
            policy=policy, config=config,
            sizing_input=make_input(config, available_equity=40.0))
        assert result.total_position_risk == 0.0
        assert result.position_notional == 0.0
        assert result.quantity == 0

    def test_wrong_input_type_blocked_result_zero(self):
        config = make_config()
        policy = make_policy(config)
        result = calculate_position_size(policy=policy, config=config,
                                         sizing_input={"x": 1})
        assert_blocked(result, SizingOutcome.INVALID_INPUT,
                       REASON_INPUT_WRONG_TYPE)
        assert result.figi == ""

    def test_policy_invalid_blocked_result_zero(self):
        config = make_config()
        policy = make_policy(config)
        object.__setattr__(policy, "max_position_notional_fraction", 0.9)
        result = calculate_position_size(policy=policy, config=config,
                                         sizing_input=make_input(config))
        assert_blocked(result, SizingOutcome.POLICY_INVALID,
                       REASON_POLICY_HASH_MISMATCH)

    def test_blocked_results_never_carry_caps_violating_zero(self):
        config = make_config()
        policy = make_policy(config)
        for inp in (make_input(config, side=TradeSide.SHORT),
                    make_input(config, protective_stop_price=120.0)):
            result = calculate_position_size(policy=policy, config=config,
                                             sizing_input=inp)
            # Не-расчётные блокирующие исходы денег не содержат.
            assert result.risk_budget is None
            assert result.position_notional is None


# ---------------------------------------------------------------------------
# §10.17 Детерминированность повторного расчёта
# ---------------------------------------------------------------------------


class TestStageD17Determinism:
    def test_repeated_calculation_identical(self):
        config = make_config()
        policy = make_policy(config)
        inp = make_input(config)
        results = [calculate_position_size(policy=policy, config=config,
                                           sizing_input=inp)
                   for _ in range(5)]
        assert all(r == results[0] for r in results[1:])
        assert all(r.quantity == results[0].quantity for r in results)

    def test_ambient_decimal_context_does_not_leak_into_calculation(self):
        config = make_config()
        policy = make_policy(config)
        inp = make_input(config)
        reference = calculate_position_size(policy=policy, config=config,
                                            sizing_input=inp)
        saved_prec = decimal.getcontext().prec
        saved_rounding = decimal.getcontext().rounding
        try:
            decimal.getcontext().prec = 2
            decimal.getcontext().rounding = decimal.ROUND_UP
            distorted = calculate_position_size(policy=policy,
                                                config=config,
                                                sizing_input=inp)
        finally:
            decimal.getcontext().prec = saved_prec
            decimal.getcontext().rounding = saved_rounding
        assert distorted == reference

    def test_int_and_float_equivalent_inputs_same_result(self):
        config = make_config()
        policy = make_policy(config)
        as_float = calculate_position_size(
            policy=policy, config=config, sizing_input=make_input(config))
        as_int = calculate_position_size(
            policy=policy, config=config,
            sizing_input=make_input(config, available_equity=100000,
                                    buying_power_limit=50000,
                                    entry_price=100, protective_stop_price=95,
                                    contract_multiplier=1))
        assert as_float == as_int

    def test_new_objects_each_call_no_shared_state(self):
        config = make_config()
        policy = make_policy(config)
        r1 = calculate_position_size(policy=policy, config=config,
                                     sizing_input=make_input(config))
        r2 = calculate_position_size(policy=policy, config=config,
                                     sizing_input=make_input(config))
        assert r1 is not r2
        assert r1 == r2


# ---------------------------------------------------------------------------
# §8 Fail-closed: нулевые/отрицательные значения и прочие границы
# ---------------------------------------------------------------------------


class TestStageD8FailClosedZeroAndNegative:
    @pytest.mark.parametrize("bad_equity", [0.0, -1.0, -100000.0])
    def test_zero_or_negative_equity_rejected(self, bad_equity):
        with pytest.raises(SizingInputViolationError):
            make_input(available_equity=bad_equity)

    @pytest.mark.parametrize("bad_price", [0.0, -1.0, -100.0])
    def test_zero_or_negative_entry_price_rejected(self, bad_price):
        with pytest.raises(SizingInputViolationError):
            make_input(entry_price=bad_price)

    @pytest.mark.parametrize("bad_stop", [0.0, -1.0, -95.0])
    def test_zero_or_negative_stop_price_rejected(self, bad_stop):
        with pytest.raises(SizingInputViolationError):
            make_input(protective_stop_price=bad_stop)

    @pytest.mark.parametrize("bad_lot", [0, -1, -10])
    def test_zero_or_negative_lot_size_rejected(self, bad_lot):
        with pytest.raises(SizingInputViolationError):
            make_input(lot_size=bad_lot)

    @pytest.mark.parametrize("bad_mult", [0.0, -1.0])
    def test_invalid_multiplier_rejected(self, bad_mult):
        with pytest.raises(SizingInputViolationError):
            make_input(contract_multiplier=bad_mult)

    @pytest.mark.parametrize("bad_cost", [-0.001, -5.0])
    def test_negative_costs_rejected(self, bad_cost):
        with pytest.raises(SizingInputViolationError):
            make_input(entry_cost_per_unit=bad_cost)
        with pytest.raises(SizingInputViolationError):
            make_input(stop_exit_cost_per_unit=bad_cost)

    def test_negative_buying_power_rejected(self):
        with pytest.raises(SizingInputViolationError):
            make_input(buying_power_limit=-1.0)

    def test_missing_buying_power_blocks(self):
        config = make_config()
        policy = make_policy(config)
        result = calculate_position_size(
            policy=policy, config=config,
            sizing_input=make_input(config, buying_power_limit=None))
        assert_blocked(result, SizingOutcome.MISSING_REQUIRED_DATA,
                       REASON_MISSING_REQUIRED_FIELDS)

    def test_fraction_domain_is_open_zero_closed_one(self):
        config = make_config()
        for bad in (0.0, -0.01, 1.0001, 2.0):
            with pytest.raises(RiskPolicyViolationError):
                make_policy(config, risk=bad)
            with pytest.raises(RiskPolicyViolationError):
                make_policy(config, cap=bad)
        # Граница 1.0 допустима (100% капитала — явное решение).
        assert make_policy(config, risk=1.0).risk_per_trade_fraction == 1.0

    def test_missing_policy_field_blocks_creation(self):
        config = make_config()
        with pytest.raises(TypeError):
            RiskPolicy(strategy_id="alpha", config_hash=config.config_hash,
                       risk_per_trade_fraction=0.01)
        with pytest.raises(TypeError):
            RiskPolicy(strategy_id="alpha")


class TestStageD8FailClosedFigiAndTypes:
    def test_wrong_figi_in_price_quote_blocks(self):
        config = make_config()
        policy = make_policy(config)
        result = calculate_position_size(
            policy=policy, config=config,
            sizing_input=make_input(config,
                                    entry_price=make_price("FIGI2", 100.0)))
        assert_blocked(result, SizingOutcome.ATTRIBUTION_MISMATCH,
                       REASON_FIGI_MISMATCH)
        assert result.diagnostics["quote_figi"] == "FIGI2"
        assert result.diagnostics["input_figi"] == "FIGI1"

    def test_wrong_figi_in_stop_quote_blocks(self):
        config = make_config()
        policy = make_policy(config)
        result = calculate_position_size(
            policy=policy, config=config,
            sizing_input=make_input(
                config, protective_stop_price=make_price("FIGI2", 95.0)))
        assert_blocked(result, SizingOutcome.ATTRIBUTION_MISMATCH,
                       REASON_FIGI_MISMATCH)

    def test_matching_figi_quotes_pass(self):
        config = make_config()
        policy = make_policy(config)
        result = calculate_position_size(
            policy=policy, config=config,
            sizing_input=make_input(config, entry_price=make_price(
                "FIGI1", 100.0),
                protective_stop_price=make_price("FIGI1", 95.0)))
        assert result.outcome is SizingOutcome.SIZED
        assert result.quantity == 190

    def test_collaborator_wrong_types_are_contract_violations(self):
        config = make_config()
        policy = make_policy(config)
        with pytest.raises(SizingContractViolationError):
            calculate_position_size(policy=None, config=config,
                                    sizing_input=make_input(config))
        with pytest.raises(SizingContractViolationError):
            calculate_position_size(policy=policy, config=None,
                                    sizing_input=make_input(config))
        with pytest.raises(SizingContractViolationError):
            calculate_position_size(policy={"risk": 0.01}, config=config,
                                    sizing_input=make_input(config))
        with pytest.raises(SizingContractViolationError):
            calculate_position_size(policy=policy, config="config",
                                    sizing_input=make_input(config))

    def test_tampered_config_hash_rejected_by_stage_a2_1_check(self):
        config = make_config()
        policy = make_policy(config)
        broken = make_config(params={"n": 3})
        object.__setattr__(broken, "config_hash", "f" * 64)
        with pytest.raises(SizingContractViolationError):
            calculate_position_size(policy=policy, config=broken,
                                    sizing_input=make_input(config))


class TestStageD8FailClosedSubclassBypass:
    def test_policy_subclass_rejected(self):
        config = make_config()
        policy = make_policy(config)

        class WeakPolicy(RiskPolicy):
            pass

        weak = WeakPolicy(strategy_id="alpha",
                          config_hash=config.config_hash,
                          risk_per_trade_fraction=0.01,
                          max_position_notional_fraction=0.2)
        with pytest.raises(SizingContractViolationError):
            calculate_position_size(policy=weak, config=config,
                                    sizing_input=make_input(config))

    def test_config_subclass_rejected(self):
        config = make_config()
        policy = make_policy(config)

        class WeakConfig(StrategyConfig):
            pass

        weak = WeakConfig(strategy_id="alpha", strategy_version="1.0.0",
                          params={"n": 3},
                          config_hash=compute_config_hash(
                              "alpha", "1.0.0", {"n": 3}))
        with pytest.raises(SizingContractViolationError):
            calculate_position_size(policy=policy, config=weak,
                                    sizing_input=make_input(config))

    def test_input_subclass_rejected_as_wrong_type(self):
        config = make_config()
        policy = make_policy(config)

        class WeakInput(SizingInput):
            pass

        weak = WeakInput(**vars(make_input(config)))
        result = calculate_position_size(policy=policy, config=config,
                                         sizing_input=weak)
        assert_blocked(result, SizingOutcome.INVALID_INPUT,
                       REASON_INPUT_WRONG_TYPE)


class TestStageD8ExtremeValuesAndOverflow:
    def test_extreme_equity_and_tiny_prices_exact_int_math(self):
        config = make_config()
        policy = make_policy(config)
        inp = make_input(config, available_equity=1e308,
                         buying_power_limit=1e308,
                         entry_price=1e-300, protective_stop_price=1e-301)
        result = calculate_position_size(policy=policy, config=config,
                                         sizing_input=inp)
        # Экстремальные значения не ломают точную целочисленную математику.
        assert result.outcome is SizingOutcome.SIZED
        assert result.quantity > 0
        validate_sizing_result(result, expected_policy=policy,
                               expected_config=config, expected_input=inp)

    def test_overflowing_risk_per_unit_blocked_not_positive(self):
        config = make_config()
        policy = make_policy(config)
        # price_risk_per_unit = (1.7e308 - 1) * 1e308 — вне float;
        # точная арифметика даёт объём 0: риск единицы непредставим.
        result = calculate_position_size(
            policy=policy, config=config,
            sizing_input=make_input(config, entry_price=1.7e308,
                                    protective_stop_price=1.0,
                                    contract_multiplier=1e308))
        assert_blocked(result, SizingOutcome.ZERO_SIZE,
                       REASON_RISK_BUDGET_BELOW_ONE_LOT)
        assert result.risk_per_unit is None
        exact = result.diagnostics["computed_decimal"]["total_risk_per_unit"]
        assert decimal.Decimal(exact) > decimal.Decimal("1e308")

    def test_subnormal_prices_handled(self):
        config = make_config()
        policy = make_policy(config)
        result = calculate_position_size(
            policy=policy, config=config,
            sizing_input=make_input(config, entry_price=2.5e-323,
                                    protective_stop_price=5e-324,
                                    buying_power_limit=1e308))
        assert result.outcome is SizingOutcome.SIZED
        assert result.quantity > 0

    def test_huge_integer_input_rejected_cleanly(self):
        # int произвольной точности вне диапазона float — контролируемая
        # ошибка валидации (не OverflowError наружу).
        with pytest.raises(SizingInputViolationError):
            make_input(available_equity=10 ** 400)

    def test_rounding_boundary_between_zero_and_one_lot(self):
        config = make_config()
        policy = make_policy(config)
        # Ровно на границе: budget 51 (equity 5100) -> 10 единиц -> 1 лот.
        at_boundary = calculate_position_size(
            policy=policy, config=config,
            sizing_input=make_input(config, available_equity=5100.0,
                                    buying_power_limit=5000.0))
        assert at_boundary.quantity == 10
        # На копейку меньше: budget 50.99 -> 9 единиц -> 0 лотов.
        below = calculate_position_size(
            policy=policy, config=config,
            sizing_input=make_input(config, available_equity=5099.0,
                                    buying_power_limit=5000.0))
        assert_blocked(below, SizingOutcome.ZERO_SIZE,
                       REASON_RISK_BUDGET_BELOW_ONE_LOT)


# ---------------------------------------------------------------------------
# НЕГАТИВНЫЕ ТЕСТЫ (ТЗ §10): тесты перехватывают некорректные реализации
# ---------------------------------------------------------------------------


class TestStageDNegativeMutationTests:
    """НЕГАТИВНЫЕ ТЕСТЫ (ТЗ §10): заведомо некорректные результаты и
    реализации перехватываются. Два уровня защиты:
      1) КОНСТРУКЦИЯ: некорректная мутация через dataclasses.replace
         отклоняется __post_init__ (несогласованный объект невозможно
         создать вообще);
      2) ВАЛИДАТОР: результат, собранный В ОБХОД конструкции
         (object.__new__ — модель вывода сломанной реализации),
         перехватывается публичным validate_sizing_result."""

    @staticmethod
    def _bypass_result(**changes):
        """Модель вывода СЛОМАННОЙ реализации: точный тип SizingResult,
        собранный в обход __post_init__ (проверки не выполнялись)."""
        _, _, result = make_sized_result()
        fake = object.__new__(SizingResult)
        fake.__dict__.update(result.__dict__)
        for name, value in changes.items():
            object.__setattr__(fake, name, value)
        return fake

    # --- уровень 1: конструктор отклоняет некорректные мутации ---------

    def test_positive_quantity_in_blocked_outcome_not_constructible(self):
        _, _, result = make_sized_result()
        with pytest.raises(SizingResultViolationError):
            dataclasses.replace(result,
                                outcome=SizingOutcome.INVALID_STOP_GEOMETRY,
                                reason_code=REASON_STOP_NOT_BELOW_ENTRY,
                                quantity=190, lot_count=19)

    def test_quantity_not_multiple_of_lot_not_constructible(self):
        _, _, result = make_sized_result()
        with pytest.raises(SizingResultViolationError):
            dataclasses.replace(result, quantity=195, lot_count=19)

    def test_diagnostics_stripped_result_not_constructible(self):
        _, _, result = make_sized_result()
        with pytest.raises(SizingResultViolationError):
            dataclasses.replace(result, diagnostics={})

    def test_fractional_result_money_not_constructible(self):
        _, _, result = make_sized_result()
        with pytest.raises(SizingResultViolationError):
            dataclasses.replace(result, risk_budget=float("nan"))
        with pytest.raises(SizingResultViolationError):
            dataclasses.replace(result, position_notional=float("inf"))

    # --- уровень 2: валидатор ловит обход конструкции -------------------

    def test_validator_catches_positive_quantity_in_blocked(self):
        broken = self._bypass_result(
            outcome=SizingOutcome.INVALID_STOP_GEOMETRY,
            reason_code=REASON_STOP_NOT_BELOW_ENTRY,
            quantity=190, lot_count=19)
        with pytest.raises(SizingResultViolationError):
            validate_sizing_result(broken)

    def test_validator_catches_quantity_exceeding_risk_budget(self):
        config, policy, result = make_sized_result()
        # Удвоенный объём: 190*2 = 380 единиц -> 380*5.1 = 1938 > 1000.
        broken = self._bypass_result(quantity=380, lot_count=38)
        with pytest.raises(SizingResultViolationError):
            validate_sizing_result(broken, expected_policy=policy,
                                   expected_config=config)

    def test_validator_catches_quantity_exceeding_notional_cap(self):
        config, policy, result = make_sized_result()
        # 210 единиц: notional 21000 > кап 20000 (риск 210*5.1 = 1071
        # тоже превышает бюджет 1000 — перехват гарантирован).
        broken = self._bypass_result(quantity=210, lot_count=21)
        with pytest.raises(SizingResultViolationError):
            validate_sizing_result(broken, expected_policy=policy,
                                   expected_config=config)

    def test_validator_catches_quantity_exceeding_buying_power(self):
        config = make_config()
        policy = make_policy(config, risk=0.01, cap=0.2)
        inp = make_input(config, buying_power_limit=12000.0)
        result = calculate_position_size(policy=policy, config=config,
                                         sizing_input=inp)
        assert result.quantity == 110
        # 120 единиц: 120*100.05 = 12006 > 12000.
        diag = dict(result.diagnostics.to_mutable())
        fake = object.__new__(SizingResult)
        fake.__dict__.update(result.__dict__)
        object.__setattr__(fake, "quantity", 120)
        object.__setattr__(fake, "lot_count", 12)
        with pytest.raises(SizingResultViolationError):
            validate_sizing_result(fake, expected_policy=policy,
                                   expected_config=config)

    def test_validator_catches_quantity_not_multiple_of_lot(self):
        _, _, result = make_sized_result()
        broken = self._bypass_result(quantity=195, lot_count=19)
        with pytest.raises(SizingResultViolationError):
            validate_sizing_result(broken)

    def test_validator_catches_wrong_policy_hash(self):
        config, policy, result = make_sized_result()
        broken = self._bypass_result(risk_policy_hash="a" * 64)
        with pytest.raises(SizingResultViolationError):
            validate_sizing_result(broken, expected_policy=policy)

    def test_validator_catches_wrong_attribution(self):
        config, policy, result = make_sized_result()
        broken = self._bypass_result(strategy_id="beta")
        with pytest.raises(SizingResultViolationError):
            validate_sizing_result(broken, expected_policy=policy,
                                   expected_config=config)

    def test_validator_catches_wrong_figi(self):
        config, policy, result = make_sized_result()
        broken = self._bypass_result(figi="FIGI9")
        with pytest.raises(SizingResultViolationError):
            validate_sizing_result(broken,
                                   expected_input=make_input(config))

    def test_validator_catches_fabricated_money(self):
        _, _, result = make_sized_result()
        # total_position_risk НЕ равен quantity * risk_per_unit.
        broken = self._bypass_result(total_position_risk=1.0)
        with pytest.raises(SizingResultViolationError):
            validate_sizing_result(broken)

    def test_validator_catches_fabricated_budget(self):
        _, _, result = make_sized_result()
        broken = self._bypass_result(risk_budget=10.0)
        with pytest.raises(SizingResultViolationError):
            validate_sizing_result(broken)

    def test_validator_catches_stripped_diagnostics(self):
        _, _, result = make_sized_result()
        broken = self._bypass_result(diagnostics={})
        with pytest.raises(SizingResultViolationError):
            validate_sizing_result(broken)

    def test_validator_catches_tampered_diagnostics(self):
        _, _, result = make_sized_result()
        diag = dict(result.diagnostics.to_mutable())
        computed = dict(diag["computed_decimal"])
        computed["total_risk_per_unit"] = "0.000001"  # «дешёвый риск»
        diag["computed_decimal"] = computed
        broken = self._bypass_result(diagnostics=diag)
        with pytest.raises(SizingResultViolationError):
            validate_sizing_result(broken)

    def test_validator_catches_inflated_notional_money(self):
        config, policy, result = make_sized_result()
        # position_notional выше капа при исходном объёме.
        broken = self._bypass_result(position_notional=25000.0)
        with pytest.raises(SizingResultViolationError):
            validate_sizing_result(broken, expected_policy=policy,
                                   expected_config=config)

    def test_broken_sizer_implementation_is_caught(self):
        """Сломанная реализация (игнорирует геометрию стопа, выдаёт
        «успех» с положительным объёмом) перехватывается ДВАЖДЫ:
        контрактным расчётом (блок геометрии) и валидатором (подделка)."""
        config = make_config()
        policy = make_policy(config)

        def broken_sizer(sizing_input):
            # Сломанная реализация: возвращает «успех» с положительным
            # объёмом при некорректном стопе (отрицательный price risk).
            return SizingResult.sized(
                strategy_id=config.strategy_id,
                config_hash=config.config_hash,
                risk_policy_hash=policy.policy_hash,
                figi=sizing_input.figi, reason_code=REASON_SIZED_LONG,
                quantity=100, lot_count=10, lot_size=10,
                risk_budget=1000.0, risk_per_unit=0.01,
                total_position_risk=1.0, position_notional=10000.0,
                notional_cap=20000.0, buying_power_cap=50000.0,
                diagnostics={
                    "sizing_rules_version": "sizing_rules_v1",
                    "inputs_decimal": {
                        "equity": "100000.0",
                        "buying_power_limit": "50000.0",
                        "entry_price": "100.0",
                        "stop_price": "105.0",
                        "contract_multiplier": "1.0",
                        "entry_cost_per_unit": "0.05",
                        "stop_exit_cost_per_unit": "0.05",
                        "risk_per_trade_fraction": "0.01",
                        "max_position_notional_fraction": "0.2"},
                    "computed_decimal": {
                        "risk_budget": "1000.0",
                        "max_notional_cap": "20000.0",
                        "price_risk_per_unit": "-5.0",
                        "total_risk_per_unit": "0.01",
                        "per_unit_notional_cost": "100.0",
                        "per_unit_buying_power_cost": "100.05"},
                    "units_by_risk": 99999,
                    "units_by_notional": 200,
                    "units_by_buying_power": 499,
                    "limiting_constraint": {"binding": "RISK"},
                    "rounding_method": "DECIMAL_EXACT_FLOOR_TO_LOT",
                    "verification": {"risk_ok": True, "notional_ok": True,
                                     "buying_power_ok": True},
                })

        bad_input = make_input(config, protective_stop_price=105.0)
        assert broken_sizer(bad_input).quantity == 100  # сломана: даёт 100
        # Контракт перехватывает: реальный расчёт блокирует геометрию...
        real = calculate_position_size(policy=policy, config=config,
                                       sizing_input=bad_input)
        assert_blocked(real, SizingOutcome.INVALID_STOP_GEOMETRY,
                       REASON_STOP_NOT_BELOW_ENTRY)
        # ...а валидатор отвергает подделку (price_risk не согласован:
        # abs(100 - 105) * 1.0 = 5, а в диагностике -5).
        with pytest.raises(SizingResultViolationError):
            validate_sizing_result(broken_sizer(bad_input),
                                   expected_policy=policy,
                                   expected_config=config)

    def test_validator_rejects_foreign_types(self):
        with pytest.raises(SizingResultViolationError):
            validate_sizing_result({"quantity": 10})
        with pytest.raises(SizingResultViolationError):
            validate_sizing_result(None)
        config, policy, result = make_sized_result()
        with pytest.raises(SizingResultViolationError):
            validate_sizing_result(result, expected_policy={"x": 1})


# ---------------------------------------------------------------------------
# Иерархия ошибок и граничные поверхности
# ---------------------------------------------------------------------------


class TestStageDErrorHierarchy:
    def test_error_hierarchy(self):
        assert issubclass(RiskPolicyViolationError, StrategyRiskError)
        assert issubclass(SizingInputViolationError, StrategyRiskError)
        assert issubclass(SizingResultViolationError, StrategyRiskError)
        assert issubclass(SizingContractViolationError, StrategyRiskError)
        assert issubclass(StrategyRiskError, Exception)

    def test_reason_codes_are_machine_readable(self):
        config = make_config()
        policy = make_policy(config)
        results = [
            calculate_position_size(policy=policy, config=config,
                                    sizing_input=make_input(config)),
            calculate_position_size(policy=policy, config=config,
                                    sizing_input=make_input(
                                        config, side=TradeSide.SHORT)),
            calculate_position_size(policy=policy, config=config,
                                    sizing_input=make_input(
                                        config, available_equity=None)),
            calculate_position_size(policy=policy, config=config,
                                    sizing_input=make_input(
                                        config, protective_stop_price=110.0)),
            calculate_position_size(policy=policy, config=config,
                                    sizing_input={"x": 1}),
        ]
        for result in results:
            assert result.reason_code
            assert result.reason_code.replace("_", "").isalnum()
            assert result.reason_code == result.reason_code.upper()

    def test_no_exception_converted_to_positive_quantity(self):
        # Любой путь ошибки — блокирующий исход или исключение;
        # положительный объём возможен ТОЛЬКО при SIZED.
        config = make_config()
        policy = make_policy(config)
        pathological_inputs = [
            {"equity": float("nan")},
            object(),
            None,
            "string",
        ]
        for sizing_input in pathological_inputs:
            result = calculate_position_size(policy=policy, config=config,
                                             sizing_input=sizing_input)
            assert result.quantity == 0
