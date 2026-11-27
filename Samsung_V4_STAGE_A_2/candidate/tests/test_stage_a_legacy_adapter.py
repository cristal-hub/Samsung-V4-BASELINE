# tests/test_stage_a_legacy_adapter.py
# STAGE A: изолированный regression-адаптер старой стратегии (ТЗ разделы 3, 7).
#
#   G-1 — GOLDEN SIGNALS: сигналы ОРИГИНАЛЬНОЙ baseline-логики
#         (candidate/strategy.py, StrategyManager) воспроизводятся
#         regression-адаптером на детерминированных fixture и сверяются
#         с записанным эталоном tests/fixtures/legacy_golden_signals.json.
#
# Изоляция: адаптер вызывает исходный код baseline без его изменения;
# после каждого вызова состояние модуля config восстанавливается.
# Offline; без сети, брокера и заявок.
#
# Примечание по окружению: fixture используют РЕАЛЬНЫЕ индикаторы
# pandas_ta_classic (заявленная зависимость requirements.txt). В чистом
# CI-окружении с SDK-заглушкой (пустой модуль pandas_ta_classic) G-1
# честно помечается SKIP — эталон на такие условия не рассчитан.

import json
import os

import pytest

import config as legacy_config
import strategy_api as sa
from strategies.legacy_samsung_v4 import profiles
from strategies.legacy_samsung_v4.strategy import (
    LegacyRegressionError,
    LegacySamsungV4Strategy,
    _override_legacy_config,
)
from tests.stage_a_golden_tools import (
    FIXTURE_BUILDERS,
    GOLDEN_PATH,
    builder_df,
    fixture_sha256,
)

try:  # реальные индикаторы доступны?
    import pandas_ta_classic as _ta_mod
    _REAL_TA = all(hasattr(_ta_mod, name)
                   for name in ("sma", "rsi", "bbands", "adx"))
except ImportError:
    _REAL_TA = False

pytestmark = pytest.mark.skipif(
    not _REAL_TA,
    reason="G-1 требует реальных индикаторов pandas_ta_classic "
           "(в offline-заглушке эталон не воспроизводим)")


def _signal_for(strategy, config, df, drop_incomplete):
    return strategy.evaluate_entry(
        sa.EntrySignalInput(
            figi="TEST",
            ticker="GOLDEN",
            candles=df.copy(),
            last_price=float(df["close"].iloc[-1]),
            drop_incomplete=drop_incomplete,
        ),
        config,
    )


# ---------------------------------------------------------------------------
# G-1: golden signals
# ---------------------------------------------------------------------------

class TestG1GoldenSignals:
    @pytest.fixture(scope="class")
    def golden(self):
        with open(GOLDEN_PATH, "r", encoding="utf-8") as handle:
            return json.load(handle)

    def test_golden_file_contains_all_fixture_x_profile(self, golden):
        expected_keys = {
            f"{name}::{profile}"
            for name in FIXTURE_BUILDERS
            for profile in profiles.PROFILE_NAMES
        }
        assert set(golden["expectations"]) == expected_keys

    def test_fixture_integrity_sha256(self, golden):
        # fixture в тестовом модуле байт-в-байт совпадают с теми,
        # на которых снят эталон
        for name in FIXTURE_BUILDERS:
            assert golden["fixture_sha256"][name] == fixture_sha256(name), \
                f"fixture {name} изменился — эталон G-1 требует пересборки"

    @pytest.mark.parametrize("name", sorted(FIXTURE_BUILDERS))
    @pytest.mark.parametrize("profile", profiles.PROFILE_NAMES)
    def test_g1_signal_matches_golden(self, golden, name, profile):
        strategy = LegacySamsungV4Strategy()
        config = strategy.build_regression_config(profile)
        builder, drop_incomplete = FIXTURE_BUILDERS[name]
        df = builder()
        signal = _signal_for(strategy, config, df, drop_incomplete)
        expected = golden["expectations"][f"{name}::{profile}"]
        assert signal.direction.value == expected["signal"], (
            name, profile, signal.reason)
        assert signal.reason == expected["reason"], (name, profile)

    def test_g1_real_buy_and_sell_are_fired(self, golden):
        # эталон покрывает не только HOLD: реальная логика даёт и BUY, и SELL
        fired = {value["signal"] for value in golden["expectations"].values()}
        assert "BUY" in fired
        assert "SELL" in fired


# ---------------------------------------------------------------------------
# Идентичность моста: адаптер == прямой вызов baseline-логики
# ---------------------------------------------------------------------------

class TestBridgeIdentity:
    @pytest.mark.parametrize("profile", profiles.PROFILE_NAMES)
    def test_adapter_equals_direct_legacy_call(self, profile):
        from tests.stage_a_golden_tools import fixture_a_long_rise_reversal

        df = fixture_a_long_rise_reversal()
        last_price = float(df["close"].iloc[-1])
        params = profiles.build_regression_params(profile)

        strategy = LegacySamsungV4Strategy()
        config = strategy.build_regression_config(profile)
        via_adapter = strategy._legacy_get_signal(
            config.params, df.copy(), last_price)

        with _override_legacy_config(params):
            import strategy as legacy_strategy_module
            manager = legacy_strategy_module.StrategyManager()
            direct = manager.get_signal(df.copy(), last_price)

        assert via_adapter == direct


# ---------------------------------------------------------------------------
# Изоляция baseline-состояния и fail-closed ограничения адаптера
# ---------------------------------------------------------------------------

class TestAdapterIsolation:
    def test_baseline_config_untouched_after_calls(self):
        snapshot_before = {
            name: getattr(legacy_config, name)
            for name in ("PROFILE", "MA_FAST_PERIOD", "MA_SLOW_PERIOD",
                         "RSI_OVERSOLD", "RSI_OVERBOUGHT",
                         "MIN_CANDLES_FOR_SIGNAL", "ADX_TREND_THRESHOLD",
                         "VOLUME_SPIKE_FACTOR")
        }
        strategy = LegacySamsungV4Strategy()
        for profile in profiles.PROFILE_NAMES:
            config = strategy.build_regression_config(profile)
            builder, drop = FIXTURE_BUILDERS["A_long_rise_reversal"]
            _signal_for(strategy, config, builder(), drop)
        snapshot_after = {
            name: getattr(legacy_config, name)
            for name in snapshot_before
        }
        assert snapshot_before == snapshot_after
        # историческое значение baseline не тронуто
        assert snapshot_after["PROFILE"] == "FORCE_TRADE"

    def test_override_restores_even_on_error(self):
        original = legacy_config.MA_FAST_PERIOD
        with pytest.raises(RuntimeError):
            with _override_legacy_config({"MA_FAST_PERIOD": 5}):
                raise RuntimeError("boom")
        assert legacy_config.MA_FAST_PERIOD == original

    def test_regression_config_origin(self):
        strategy = LegacySamsungV4Strategy()
        config = strategy.build_regression_config("TECH_CHECK")
        assert config.origin == "regression_harness"
        assert config.strategy_id == "legacy_samsung_v4"
        assert config.metadata["profile"] == "TECH_CHECK"

    def test_evaluate_entry_rejects_engine_origin(self):
        strategy = LegacySamsungV4Strategy()
        params = profiles.build_regression_params("TECH_CHECK")
        # Stage A.2: фикстура вычисляет РЕАЛЬНЫЙ config_hash через
        # compute_config_hash (искусственные хеши больше не проходят
        # обязательную проверку соответствия при создании StrategyConfig);
        # суть теста не меняется: конфигурация с origin="engine"
        # отклоняется адаптером (LegacyRegressionError).
        normalized = strategy.normalize_params(params)
        config = sa.StrategyConfig(
            strategy_id="legacy_samsung_v4",
            strategy_version=strategy.strategy_version,
            params=normalized,
            config_hash=sa.compute_config_hash(
                "legacy_samsung_v4", strategy.strategy_version, normalized),
            origin="engine",
        )
        from tests.stage_a_golden_tools import fixture_a_long_rise_reversal
        df = fixture_a_long_rise_reversal()
        with pytest.raises(LegacyRegressionError):
            _signal_for(strategy, config, df, False)

    def test_get_config_rejects_engine_origin(self):
        strategy = LegacySamsungV4Strategy()
        params = profiles.build_regression_params("TECH_CHECK")
        with pytest.raises(LegacyRegressionError):
            strategy.get_config(params)

    def test_default_params_refuse_silent_profile(self):
        strategy = LegacySamsungV4Strategy()
        with pytest.raises(Exception) as exc:
            strategy.default_params()
        assert "no silent defaults" in str(exc.value).lower() or \
            "автоподстановка запрещена" in str(exc.value)

    def test_unknown_profile_rejected(self):
        strategy = LegacySamsungV4Strategy()
        with pytest.raises(ValueError):
            strategy.build_regression_config("FORCE_TRADE")

    def test_config_hash_stable_across_instances(self):
        h1 = LegacySamsungV4Strategy().build_regression_config(
            "CONSERVATIVE").config_hash
        h2 = LegacySamsungV4Strategy().build_regression_config(
            "CONSERVATIVE").config_hash
        assert h1 == h2
        # разные профили — разные hash
        h3 = LegacySamsungV4Strategy().build_regression_config(
            "SANDBOX_TEST").config_hash
        assert h1 != h3


# ---------------------------------------------------------------------------
# Регистрация в реестре (regression-only)
# ---------------------------------------------------------------------------

class TestRegistryPlacement:
    def test_legacy_registered_regression_only(self):
        import strategies as registry
        assert registry.is_known("legacy_samsung_v4")
        assert not registry.is_activatable("legacy_samsung_v4")
        registration = registry.get_registration("legacy_samsung_v4")
        assert registration.regression_only is True
        assert registration.activatable is False
        assert registration.registered_at_stage == "A"

    def test_no_other_strategies_registered(self):
        import strategies as registry
        assert registry.known_strategy_ids() == ("legacy_samsung_v4",)
