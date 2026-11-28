# tests/test_stage_a_legacy_profiles.py
# STAGE A: сохранение исторических профилей и параметров (ТЗ раздел 5).
#
#   G-5 — ИДЕНТИЧНОСТЬ ИСТОРИЧЕСКИХ ПРОФИЛЕЙ: значения SANDBOX_TEST /
#         TECH_CHECK / CONSERVATIVE в strategies/legacy_samsung_v4
#         в точности совпадают с исходным baseline config.py (коммит
#         884cefd...). Baseline-файл читается как ТЕКСТ (AST) и никогда
#         не изменяется.
#
# Offline; без сети, брокера и заявок.

import ast
import json
import os

import pytest

from strategies.legacy_samsung_v4 import profiles, schema

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PY = os.path.join(PROJECT_ROOT, "config.py")
PARAMS_JSON = os.path.join(
    PROJECT_ROOT, "strategies", "legacy_samsung_v4", "params.json")


# ---------------------------------------------------------------------------
# AST-извлечение исторических значений из baseline config.py (только чтение)
# ---------------------------------------------------------------------------

def _constant_assigns(body):
    """Присваивания вида NAME = константа в списке узлов AST."""
    result = {}
    for node in body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 \
                and isinstance(node.targets[0], ast.Name):
            value = node.value
            if isinstance(value, ast.Constant):
                result[node.targets[0].id] = value.value
            elif isinstance(value, ast.IfExp):
                # COMMISSION_PER_SIDE = 0.003 if ... else 0.0005 — пропускаем
                continue
    return result


def _extract_profile_branches(source):
    """Ветка `if PROFILE == "ИМЯ":`/elif — значения присваиваний каждой."""
    tree = ast.parse(source)
    branches = {}

    def walk_if(node):
        test = node.test
        if (isinstance(test, ast.Compare)
                and isinstance(test.left, ast.Name)
                and test.left.id == "PROFILE"
                and len(test.ops) == 1
                and isinstance(test.ops[0], ast.Eq)
                and len(test.comparators) == 1
                and isinstance(test.comparators[0], ast.Constant)):
            name = test.comparators[0].value
            branches[name] = _constant_assigns(node.body)
        # elif-цепочка живёт в orelse
        for child in node.orelse:
            if isinstance(child, ast.If):
                walk_if(child)

    for node in tree.body:
        if isinstance(node, ast.If):
            walk_if(node)
    return branches


def _extract_base_assigns(source):
    """Только модульные (не вложенные в If) присваивания baseline config.py."""
    tree = ast.parse(source)
    return _constant_assigns(tree.body)


@pytest.fixture(scope="module")
def config_py_source():
    with open(CONFIG_PY, "r", encoding="utf-8") as handle:
        return handle.read()


# ---------------------------------------------------------------------------
# G-5: идентичность исторических профилей
# ---------------------------------------------------------------------------

class TestG5HistoricalProfilesIdentity:
    def test_g5_profiles_match_baseline_exactly(self, config_py_source):
        baseline = _extract_profile_branches(config_py_source)
        for name in profiles.PROFILE_NAMES:
            assert name in baseline, name
            assert profiles.PROFILES[name] == baseline[name], (
                f"профиль {name} отличается от baseline config.py")

    def test_g5_all_three_profiles_present(self):
        assert profiles.PROFILE_NAMES == (
            "SANDBOX_TEST", "TECH_CHECK", "CONSERVATIVE")

    def test_g5_force_trade_not_carried_into_new_architecture(
            self, config_py_source):
        baseline = _extract_profile_branches(config_py_source)
        assert "FORCE_TRADE" in baseline  # в baseline он есть (история)
        assert "FORCE_TRADE" not in profiles.PROFILES
        assert "FORCE_TRADE" not in profiles.PROFILE_NAMES
        with pytest.raises(ValueError):
            profiles.build_regression_params("FORCE_TRADE")

    def test_g5_profile_types_preserved(self, config_py_source):
        baseline = _extract_profile_branches(config_py_source)
        for name in profiles.PROFILE_NAMES:
            for key, value in baseline[name].items():
                assert type(profiles.PROFILES[name][key]) is type(value), (
                    name, key)

    def test_g5_base_params_match_baseline(self, config_py_source):
        baseline_base = _extract_base_assigns(config_py_source)
        shared = profiles.shared_params()
        expected_keys = {
            "MA_FAST_PERIOD", "MA_SLOW_PERIOD", "TREND_FILTER_MA_PERIOD",
            "BB_PERIOD", "BB_STD_DEV", "RSI_PERIOD",
            "RSI_OVERBOUGHT", "RSI_OVERSOLD", "MIN_CANDLES_FOR_SIGNAL",
            "ADX_PERIOD", "VOLUME_CONFIRMATION_WINDOW",
        }
        for key in expected_keys:
            assert key in baseline_base, key
            assert shared[key] == baseline_base[key], key

    def test_g5_baseline_config_file_not_modified(self, config_py_source):
        # исходный файл baseline читается, но не изменяется тестами:
        # побайтовая проверка невозможна здесь, поэтому проверяем,
        # что FORCE_TRADE-ветка осталась нетронутой в исходнике
        assert 'PROFILE = "FORCE_TRADE"' in config_py_source
        baseline = _extract_profile_branches(config_py_source)
        assert baseline["FORCE_TRADE"] == {
            "ADX_TREND_THRESHOLD": 5,
            "ADX_HYSTERESIS_CANDLES": 1,
            "VOLUME_SPIKE_FACTOR": 0.0,
            "MA_FAST_PERIOD": 2,
            "MA_SLOW_PERIOD": 3,
            "TREND_FILTER_MA_PERIOD": 5,
            "RSI_OVERSOLD": 50,
            "RSI_OVERBOUGHT": 50,
            "MIN_CANDLES_FOR_SIGNAL": 10,
        }


# ---------------------------------------------------------------------------
# Дополнительные гарантии исторических данных
# ---------------------------------------------------------------------------

class TestHistoricalParamsIntegrity:
    def test_params_json_structure(self):
        with open(PARAMS_JSON, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        assert data["strategy_id"] == "legacy_samsung_v4"
        assert data["strategy_version"] == "tsclp_v2.0"
        assert isinstance(data["shared_params"], dict)

    def test_build_regression_params_merges_base_and_profile(self):
        merged = profiles.build_regression_params("SANDBOX_TEST")
        assert merged["MA_FAST_PERIOD"] == 5      # профильное
        assert merged["BB_PERIOD"] == 20          # базовое
        assert merged["RSI_PERIOD"] == 14         # базовое
        assert merged["VOLUME_CONFIRMATION_WINDOW"] == 20  # базовое
        # вход не мутируется (возвращается копия)
        merged["MA_FAST_PERIOD"] = 999
        assert profiles.build_regression_params(
            "SANDBOX_TEST")["MA_FAST_PERIOD"] == 5

    def test_build_regression_params_unknown_profile(self):
        with pytest.raises(ValueError):
            profiles.build_regression_params("NO_SUCH_PROFILE")

    def test_no_default_profile_selection(self):
        # ни один профиль не является «активным по умолчанию»:
        # модуль не экспортирует никакого DEFAULT/ACTIVE профиля
        module_public = [name for name in dir(profiles)
                         if name.upper().startswith(("DEFAULT", "ACTIVE"))]
        assert module_public == []

    def test_all_profiles_pass_schema_validation(self):
        for name in profiles.PROFILE_NAMES:
            params = profiles.build_regression_params(name)
            assert schema.validate_params(params) == [], name
