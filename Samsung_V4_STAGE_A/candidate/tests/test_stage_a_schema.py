# tests/test_stage_a_schema.py
# STAGE A: структура и валидация исторических параметров (ТЗ раздел 10).
#
#   T-16 — корректная обработка РАВНЫХ RSI-порогов: допустимы (исходная
#          семантика строгих сравнений "<" и ">"); инвертированные — ошибка.
#   T-17 — разделение валидности конфигурации и готовности данных:
#          MIN_CANDLES_FOR_SIGNAL НЕ обязан быть >= TREND_FILTER_MA_PERIOD,
#          недостаток свечей — не ошибка конфигурации.
#
# Offline; без сети, брокера и заявок.

import pytest

import strategy_api
from strategy_api import StrategyConfigError
from strategies.legacy_samsung_v4 import profiles, schema


def _valid_base():
    """Валидный полный набор (эффективные параметры CONSERVATIVE)."""
    return profiles.build_regression_params("CONSERVATIVE")


# ---------------------------------------------------------------------------
# T-16: RSI-пороги
# ---------------------------------------------------------------------------

class TestT16RsiThresholds:
    def test_equal_thresholds_are_valid(self):
        params = dict(_valid_base())
        params["RSI_OVERSOLD"] = 50
        params["RSI_OVERBOUGHT"] = 50
        assert schema.validate_params(params) == []

    def test_equal_thresholds_match_historical_50_50_case(self):
        # равенство порогов — исторически реальный случай (50/50);
        # строгие сравнения "<" и ">" остаются корректными
        params = dict(_valid_base())
        params["RSI_OVERSOLD"] = 50.0
        params["RSI_OVERBOUGHT"] = 50
        assert schema.validate_params(params) == []

    def test_inverted_thresholds_rejected(self):
        params = dict(_valid_base())
        params["RSI_OVERSOLD"] = 70
        params["RSI_OVERBOUGHT"] = 30
        errors = schema.validate_params(params)
        assert any("инвертированные пороги" in e for e in errors)

    def test_thresholds_out_of_domain_rejected(self):
        params = dict(_valid_base())
        params["RSI_OVERSOLD"] = 101
        errors = schema.validate_params(params)
        assert any("RSI_OVERSOLD" in e for e in errors)

        params2 = dict(_valid_base())
        params2["RSI_OVERBOUGHT"] = -1
        errors2 = schema.validate_params(params2)
        assert any("RSI_OVERBOUGHT" in e for e in errors2)

    def test_nan_threshold_rejected(self):
        params = dict(_valid_base())
        params["RSI_OVERSOLD"] = float("nan")
        errors = schema.validate_params(params)
        assert errors


# ---------------------------------------------------------------------------
# T-17: валидность конфигурации != готовность данных
# ---------------------------------------------------------------------------

class TestT17DataReadinessSeparation:
    def test_min_candles_not_tied_to_trend_ma(self):
        # НЕВВЕДЕНИЕ ошибочного требования
        # MIN_CANDLES_FOR_SIGNAL >= TREND_FILTER_MA_PERIOD:
        # такая конфигурация валидна
        params = dict(_valid_base())
        params["MIN_CANDLES_FOR_SIGNAL"] = 10
        params["TREND_FILTER_MA_PERIOD"] = 100
        assert schema.validate_params(params) == []

    def test_no_error_message_mentions_dependency(self):
        errors = schema.validate_params(_valid_base())
        # строгая проверка: валидация полного набора пуста
        assert errors == []

    def test_short_history_is_hold_not_config_error(self):
        """Недостаток свечей — вопрос готовности ДАННЫХ.

        Проверяется на уровне baseline-логики: короткая история даёт
        HOLD 'Недостаточно данных', а не исключение конфигурации.
        Реальные индикаторы нужны только для этого сценария.
        """
        pytest.importorskip("pandas")
        try:
            import pandas_ta_classic as ta_mod
            if not all(hasattr(ta_mod, name)
                       for name in ("sma", "rsi", "bbands", "adx")):
                pytest.skip("pandas_ta_classic недоступен (offline-заглушка)")
        except ImportError:
            pytest.skip("pandas_ta_classic недоступен (offline-заглушка)")

        from tests.stage_a_golden_tools import fixture_d_short_history
        import strategy_api as sa
        from strategies.legacy_samsung_v4.strategy import (
            LegacySamsungV4Strategy)

        df = fixture_d_short_history()
        strategy = LegacySamsungV4Strategy()
        config = strategy.build_regression_config("TECH_CHECK")
        signal = strategy.evaluate_entry(
            sa.EntrySignalInput(figi="F", ticker="D", candles=df.copy(),
                                last_price=float(df["close"].iloc[-1])),
            config)
        assert signal.direction.value == "HOLD"
        assert "Недостаточно данных" in signal.reason
        # конфигурация при этом валидна
        assert schema.validate_params(
            profiles.build_regression_params("TECH_CHECK")) == []


# ---------------------------------------------------------------------------
# Общая структурная валидация (fail-closed)
# ---------------------------------------------------------------------------

class TestStructuralValidation:
    def test_historical_profiles_are_valid(self):
        for name in profiles.PROFILE_NAMES:
            params = profiles.build_regression_params(name)
            assert schema.validate_params(params) == [], name

    def test_unknown_key_rejected(self):
        params = dict(_valid_base())
        params["NEW_FILTER_PERIOD"] = 5
        errors = schema.validate_params(params)
        assert any("неизвестный параметр" in e for e in errors)

    def test_missing_required_rejected(self):
        params = dict(_valid_base())
        del params["ADX_PERIOD"]
        errors = schema.validate_params(params)
        assert any("ADX_PERIOD" in e for e in errors)

    def test_string_type_rejected(self):
        # никакой тихой автоконверсии типов ("правильность типов")
        params = dict(_valid_base())
        params["MA_FAST_PERIOD"] = "9"
        errors = schema.validate_params(params)
        assert any("MA_FAST_PERIOD" in e for e in errors)

    def test_bool_type_rejected_for_int(self):
        params = dict(_valid_base())
        params["MIN_CANDLES_FOR_SIGNAL"] = True
        errors = schema.validate_params(params)
        assert any("MIN_CANDLES_FOR_SIGNAL" in e for e in errors)

    def test_infinity_rejected(self):
        params = dict(_valid_base())
        params["VOLUME_SPIKE_FACTOR"] = float("inf")
        errors = schema.validate_params(params)
        assert errors

    def test_zero_volume_spike_factor_is_valid(self):
        # 0.0 — историческое значение (SANDBOX_TEST): проверка отключена
        # исходной семантикой, НЕ является ошибкой структуры
        params = dict(_valid_base())
        params["VOLUME_SPIKE_FACTOR"] = 0.0
        assert schema.validate_params(params) == []

    def test_non_positive_periods_rejected(self):
        params = dict(_valid_base())
        params["MA_FAST_PERIOD"] = 0
        errors = schema.validate_params(params)
        assert any("MA_FAST_PERIOD" in e for e in errors)

    def test_supported_param_names_complete(self):
        expected = {
            "MA_FAST_PERIOD", "MA_SLOW_PERIOD", "TREND_FILTER_MA_PERIOD",
            "BB_PERIOD", "BB_STD_DEV", "RSI_PERIOD",
            "RSI_OVERSOLD", "RSI_OVERBOUGHT", "MIN_CANDLES_FOR_SIGNAL",
            "ADX_PERIOD", "ADX_TREND_THRESHOLD", "ADX_HYSTERESIS_CANDLES",
            "VOLUME_SPIKE_FACTOR", "VOLUME_CONFIRMATION_WINDOW",
        }
        assert set(schema.SUPPORTED_PARAM_NAMES) == expected

    def test_normalize_produces_canonical_types(self):
        normalized = schema.normalize_params(_valid_base())
        for name in ("MA_FAST_PERIOD", "MIN_CANDLES_FOR_SIGNAL",
                     "ADX_HYSTERESIS_CANDLES", "VOLUME_CONFIRMATION_WINDOW",
                     "BB_PERIOD", "RSI_PERIOD", "ADX_PERIOD",
                     "MA_SLOW_PERIOD", "TREND_FILTER_MA_PERIOD"):
            assert isinstance(normalized[name], int), name
        for name in ("BB_STD_DEV", "RSI_OVERSOLD", "RSI_OVERBOUGHT",
                     "ADX_TREND_THRESHOLD", "VOLUME_SPIKE_FACTOR"):
            assert isinstance(normalized[name], float), name
        # нормализация стабильна: повторный вызов даёт то же
        assert schema.normalize_params(_valid_base()) == normalized
