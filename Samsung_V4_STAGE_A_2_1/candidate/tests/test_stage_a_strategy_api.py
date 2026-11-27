# tests/test_stage_a_strategy_api.py
# STAGE A: единый контракт стратегии — unit-тесты (ТЗ раздел 8).
# Offline; без сети, брокера и заявок.

import json

import pytest

import strategy_api
from strategy_api import (
    ActivationMode,
    EntrySignalInput,
    ParamSpec,
    ParamType,
    Signal,
    SignalDirection,
    Strategy,
    StrategyConfig,
    StrategyConfigError,
    StrategyContractError,
    canonical_config_payload,
    compute_config_hash,
    normalize_params_by_specs,
    validate_params_against_specs,
)


# ---------------------------------------------------------------------------
# config_hash: детерминированность и чувствительность
# ---------------------------------------------------------------------------

class TestConfigHash:
    def test_deterministic_same_input_same_hash(self):
        params = {"a": 1, "b": 2.5, "c": "x"}
        h1 = compute_config_hash("strat", "1.0.0", params)
        h2 = compute_config_hash("strat", "1.0.0", params)
        assert h1 == h2
        assert len(h1) == 64

    def test_key_order_does_not_affect_hash(self):
        h1 = compute_config_hash("s", "v", {"ma": 9, "rsi": 30, "adx": 25})
        h2 = compute_config_hash("s", "v", {"adx": 25, "ma": 9, "rsi": 30})
        h3 = compute_config_hash(
            "s", "v", dict(reversed(list({"ma": 9, "rsi": 30,
                                          "adx": 25}.items()))))
        assert h1 == h2 == h3

    def test_param_change_changes_hash(self):
        base = compute_config_hash("s", "v", {"min_candles": 60})
        changed = compute_config_hash("s", "v", {"min_candles": 61})
        assert base != changed

    def test_value_type_change_changes_hash(self):
        # 60 и 60.0 — разные канонические значения для несхемных параметров:
        # нормализация типов выполняется спецификациями стратегии.
        base = compute_config_hash("s", "v", {"x": 60})
        changed = compute_config_hash("s", "v", {"x": 60.0})
        assert base != changed

    def test_strategy_id_and_version_change_hash(self):
        params = {"p": 1}
        assert compute_config_hash("s1", "v", params) != \
            compute_config_hash("s2", "v", params)
        assert compute_config_hash("s", "v1", params) != \
            compute_config_hash("s", "v2", params)

    def test_nested_key_order_does_not_affect_hash(self):
        p1 = {"outer": {"b": 1, "a": 2}, "list": [1, 2]}
        p2 = {"list": [1, 2], "outer": {"a": 2, "b": 1}}
        assert compute_config_hash("s", "v", p1) == \
            compute_config_hash("s", "v", p2)

    def test_nan_and_infinity_rejected(self):
        with pytest.raises(StrategyConfigError):
            compute_config_hash("s", "v", {"x": float("nan")})
        with pytest.raises(StrategyConfigError):
            compute_config_hash("s", "v", {"x": float("inf")})

    def test_non_json_types_rejected(self):
        with pytest.raises(StrategyConfigError):
            compute_config_hash("s", "v", {"x": object()})

    def test_canonical_payload_is_sorted_json_without_secrets(self):
        payload = canonical_config_payload("sid", "ver", {"b": 2, "a": 1})
        parsed = json.loads(payload)
        # отсортированные ключи верхнего уровня
        assert list(parsed) == sorted(parsed)
        assert parsed["strategy_id"] == "sid"
        assert parsed["strategy_version"] == "ver"
        assert parsed["params"] == {"a": 1, "b": 2}
        assert parsed["hash_algorithm"] == "sha256"
        # формат стабилен и не содержит разделителей-пробелов
        assert ", " not in payload and '": ' not in payload


# ---------------------------------------------------------------------------
# Общая валидация по спецификациям (fail-closed, без скрытых fallback)
# ---------------------------------------------------------------------------

_SPECS = (
    ParamSpec("int_p", ParamType.INT, minimum=1),
    ParamSpec("num_p", ParamType.FLOAT, minimum=0.0, maximum=100.0),
)


class TestSpecValidation:
    def test_unknown_param_rejected(self):
        errors = validate_params_against_specs(_SPECS, {"unknown": 1})
        assert any("неизвестный параметр" in e for e in errors)

    def test_missing_required_rejected(self):
        errors = validate_params_against_specs(_SPECS, {"int_p": 1})
        assert any("num_p" in e for e in errors)

    def test_bool_is_not_int(self):
        errors = validate_params_against_specs(_SPECS, {"int_p": True,
                                                        "num_p": 1.0})
        assert any("int_p" in e for e in errors)

    def test_nan_rejected_in_number(self):
        errors = validate_params_against_specs(_SPECS, {"int_p": 1,
                                                        "num_p": float("nan")})
        assert any("NaN" in e for e in errors)

    def test_range_checks(self):
        below = validate_params_against_specs(_SPECS, {"int_p": 0,
                                                       "num_p": 1.0})
        assert any("int_p" in e for e in below)
        above = validate_params_against_specs(_SPECS, {"int_p": 1,
                                                       "num_p": 100.5})
        assert any("num_p" in e for e in above)
        ok = validate_params_against_specs(_SPECS, {"int_p": 1, "num_p": 100})
        assert ok == []

    def test_normalize_types(self):
        normalized = normalize_params_by_specs(
            _SPECS, {"int_p": 5, "num_p": 30})
        assert normalized == {"int_p": 5, "num_p": 30.0}
        assert isinstance(normalized["int_p"], int)
        assert isinstance(normalized["num_p"], float)
        # int-значение number-параметра нормализуется к float
        normalized2 = normalize_params_by_specs(
            _SPECS, {"int_p": 5, "num_p": 30})
        assert isinstance(normalized2["num_p"], float)


# ---------------------------------------------------------------------------
# Абстрактный контракт
# ---------------------------------------------------------------------------

class _DummyStrategy(Strategy):
    strategy_id = "dummy"
    strategy_version = "0.1"

    def param_specs(self):
        return _SPECS

    def evaluate_entry(self, signal_input, config):
        return Signal(
            strategy_id=self.strategy_id,
            config_hash=config.config_hash,
            direction=SignalDirection.HOLD,
            reason="dummy",
        )


class TestStrategyContract:
    def test_default_activation_mode_is_regression_only(self):
        # fail-closed по умолчанию: не объявивший TRADING_ALLOWED
        # не может торговать
        assert _DummyStrategy.activation_mode is \
            ActivationMode.REGRESSION_ONLY

    def test_default_params_refuse_silent_defaults(self):
        with pytest.raises(StrategyContractError):
            _DummyStrategy().default_params()

    def test_get_config_validates_before_hash(self):
        strategy = _DummyStrategy()
        with pytest.raises(StrategyConfigError):
            strategy.get_config({"int_p": 0, "num_p": 1.0})
        config = strategy.get_config({"int_p": 1, "num_p": 1.0})
        assert isinstance(config, StrategyConfig)
        assert config.config_hash == compute_config_hash(
            "dummy", "0.1", {"int_p": 1, "num_p": 1.0})

    def test_get_config_error_lists_all_problems(self):
        strategy = _DummyStrategy()
        with pytest.raises(StrategyConfigError) as exc:
            strategy.get_config({"int_p": 0, "num_p": float("nan"),
                                 "junk": 1})
        message = str(exc.value)
        assert "int_p" in message and "num_p" in message and "junk" in message

    def test_signal_carries_attribution(self):
        strategy = _DummyStrategy()
        config = strategy.get_config({"int_p": 2, "num_p": 2.5})
        signal = strategy.evaluate_entry(
            EntrySignalInput(figi="F", ticker="T", candles=None,
                             last_price=1.0),
            config)
        assert signal.strategy_id == "dummy"
        assert signal.config_hash == config.config_hash
        assert signal.direction is SignalDirection.HOLD
        # контракт атрибуции сигнала
        assert hasattr(signal, "strategy_id") and hasattr(signal, "config_hash")


# ---------------------------------------------------------------------------
# Нормализация params к JSON-форме
# ---------------------------------------------------------------------------

class TestNormalizeForJson:
    def test_mapping_tuple_set_enum(self):
        class _E(str, strategy_api.Enum):
            A = "a"

        normalized = strategy_api._normalize_for_json(
            {"e": _E.A, "t": (1, 2), "s": {3, 1}})
        assert normalized["e"] == "a"
        assert normalized["t"] == [1, 2]
        assert normalized["s"] == [1, 3]

    def test_non_string_mapping_keys_rejected(self):
        with pytest.raises(StrategyConfigError):
            strategy_api._normalize_for_json({1: "x"})
