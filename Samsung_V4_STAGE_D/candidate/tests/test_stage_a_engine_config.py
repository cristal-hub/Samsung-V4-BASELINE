# tests/test_stage_a_engine_config.py
# STAGE A: конфигурация нового движка — engine.json / ACTIVE_STRATEGY /
# приоритет окружения / fail-closed поведение (ТЗ разделы 6, 10, 12).
#
# Нумерация N-01..N-04 — определения тестов конфигурации Этапа A:
#   N-01: ACTIVE_STRATEGY отсутствует в обоих источниках -> UNCONFIGURED,
#         торговый режим запрещён; offline-проверки допустимы.
#   N-02: неизвестное ACTIVE_STRATEGY -> CONFIG_ERROR (fail-closed).
#   N-03: некорректный engine.json (битый JSON / не объект /
#         нестроковое значение) -> CONFIG_ERROR; env не «спасает».
#   N-04: известная, но regression-only стратегия (legacy_samsung_v4) ->
#         CONFIG_ERROR; активируемых стратегий на Этапе A нет.
#
# Offline; без сети, брокера и заявок.

import json

import pytest

import engine_config
from engine_config import (
    ConfigSource,
    EngineConfigError,
    EngineStatus,
    default_engine_json_path,
    load_engine_config,
    require_trading_ready,
)
import strategies as registry


def _write_json(path, payload):
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8")
    return str(path)


# ---------------------------------------------------------------------------
# N-01: значение отсутствует в обоих источниках
# ---------------------------------------------------------------------------

class TestMissingActiveStrategy:
    def test_n01_json_null_and_no_env(self, tmp_path):
        p = _write_json(tmp_path / "engine.json",
                        {"ENGINE_SCHEMA_VERSION": 1,
                         "ACTIVE_STRATEGY": None})
        cfg = load_engine_config(engine_json_path=p, environ={})
        assert cfg.status is EngineStatus.UNCONFIGURED
        assert cfg.active_strategy is None
        assert cfg.active_strategy_source is ConfigSource.NONE
        assert cfg.trading_allowed is False
        assert cfg.errors == ()
        assert cfg.engine_json_present is True

    def test_n01_missing_file_and_no_env(self, tmp_path):
        cfg = load_engine_config(
            engine_json_path=str(tmp_path / "absent.json"), environ={})
        assert cfg.status is EngineStatus.UNCONFIGURED
        assert cfg.engine_json_present is False
        assert cfg.trading_allowed is False
        assert any("не найден" in w for w in cfg.warnings)

    def test_n01_empty_string_in_both_sources(self, tmp_path):
        p = _write_json(tmp_path / "engine.json",
                        {"ACTIVE_STRATEGY": ""})
        cfg = load_engine_config(engine_json_path=p,
                                 environ={"ACTIVE_STRATEGY": "   "})
        assert cfg.status is EngineStatus.UNCONFIGURED
        assert cfg.trading_allowed is False
        # документированное поведение: пустая env не считается заданной
        assert any("пуста" in w for w in cfg.warnings)

    def test_n01_loader_does_not_raise_for_unconfigured(self, tmp_path):
        p = _write_json(tmp_path / "engine.json", {"ACTIVE_STRATEGY": None})
        cfg = load_engine_config(engine_json_path=p, environ={})
        # offline-сценарий разрешён: загрузка конфигурации не исключение
        assert cfg.status is EngineStatus.UNCONFIGURED

    def test_require_trading_ready_blocks_unconfigured(self, tmp_path):
        p = _write_json(tmp_path / "engine.json", {"ACTIVE_STRATEGY": None})
        cfg = load_engine_config(engine_json_path=p, environ={})
        with pytest.raises(EngineConfigError):
            require_trading_ready(cfg)

    def test_shipped_engine_json_is_unconfigured(self):
        # поставляемый engine.json (рядом с runtime.env) — явный UNCONFIGURED
        cfg = load_engine_config(environ={})
        assert cfg.engine_json_path == default_engine_json_path()
        assert cfg.engine_json_present is True
        assert cfg.status is EngineStatus.UNCONFIGURED
        assert cfg.trading_allowed is False


# ---------------------------------------------------------------------------
# Приоритет: environment > engine.json
# ---------------------------------------------------------------------------

class TestSourcePriority:
    def test_env_overrides_json(self, tmp_path):
        p = _write_json(tmp_path / "engine.json",
                        {"ACTIVE_STRATEGY": "from_json_unknown"})
        cfg = load_engine_config(
            engine_json_path=p,
            environ={"ACTIVE_STRATEGY": "from_env_unknown"})
        assert cfg.status is EngineStatus.CONFIG_ERROR
        # ошибка называет именно значение ОКРУЖЕНИЯ — приоритет доказан
        assert "from_env_unknown" in cfg.errors[0]
        assert "from_json_unknown" not in cfg.errors[0]

    def test_json_used_when_env_absent(self, tmp_path):
        p = _write_json(tmp_path / "engine.json",
                        {"ACTIVE_STRATEGY": "json_only_unknown"})
        cfg = load_engine_config(engine_json_path=p, environ={})
        assert cfg.status is EngineStatus.CONFIG_ERROR
        assert "json_only_unknown" in cfg.errors[0]
        assert cfg.active_strategy_source is ConfigSource.NONE

    def test_empty_env_falls_back_to_json(self, tmp_path):
        p = _write_json(tmp_path / "engine.json",
                        {"ACTIVE_STRATEGY": "json_value_unknown"})
        cfg = load_engine_config(engine_json_path=p,
                                 environ={"ACTIVE_STRATEGY": "  "})
        assert cfg.status is EngineStatus.CONFIG_ERROR
        assert "json_value_unknown" in cfg.errors[0]

    def test_env_overrides_null_json(self, tmp_path):
        p = _write_json(tmp_path / "engine.json", {"ACTIVE_STRATEGY": None})
        cfg = load_engine_config(
            engine_json_path=p, environ={"ACTIVE_STRATEGY": "env_value"})
        assert cfg.status is EngineStatus.CONFIG_ERROR
        assert "env_value" in cfg.errors[0]


# ---------------------------------------------------------------------------
# N-02: неизвестная стратегия
# ---------------------------------------------------------------------------

class TestUnknownStrategy:
    def test_n02_unknown_env_value(self, tmp_path):
        p = _write_json(tmp_path / "engine.json", {"ACTIVE_STRATEGY": None})
        cfg = load_engine_config(
            engine_json_path=p, environ={"ACTIVE_STRATEGY": "no_such_strat"})
        assert cfg.status is EngineStatus.CONFIG_ERROR
        assert cfg.trading_allowed is False
        assert any("неизвестная стратегия" in e for e in cfg.errors)
        # ошибка перечисляет известные id и упоминает запрет автоподбора
        assert any("legacy_samsung_v4" in e for e in cfg.errors)
        assert any("автоматический выбор запрещён" in e
                   for e in cfg.errors)

    def test_n02_unknown_json_value(self, tmp_path):
        p = _write_json(tmp_path / "engine.json",
                        {"ACTIVE_STRATEGY": "no_such_strat"})
        cfg = load_engine_config(engine_json_path=p, environ={})
        assert cfg.status is EngineStatus.CONFIG_ERROR
        assert "no_such_strat" in cfg.errors[0]
        assert cfg.attribution is None

    def test_require_trading_ready_blocks_unknown(self, tmp_path):
        p = _write_json(tmp_path / "engine.json",
                        {"ACTIVE_STRATEGY": "no_such_strat"})
        cfg = load_engine_config(engine_json_path=p, environ={})
        with pytest.raises(EngineConfigError):
            require_trading_ready(cfg)


# ---------------------------------------------------------------------------
# N-03: некорректный engine.json / некорректные значения
# ---------------------------------------------------------------------------

class TestIncorrectConfig:
    def test_n03_broken_json_is_fail_closed(self, tmp_path):
        p = tmp_path / "engine.json"
        p.write_text("{ это не json ]", encoding="utf-8")
        cfg = load_engine_config(
            engine_json_path=str(p),
            environ={"ACTIVE_STRATEGY": "legacy_samsung_v4"})
        assert cfg.status is EngineStatus.CONFIG_ERROR
        assert cfg.trading_allowed is False
        assert any("не читается как JSON" in e for e in cfg.errors)

    def test_n03_json_array_is_error(self, tmp_path):
        p = tmp_path / "engine.json"
        p.write_text("[1, 2, 3]", encoding="utf-8")
        cfg = load_engine_config(engine_json_path=str(p), environ={})
        assert cfg.status is EngineStatus.CONFIG_ERROR
        assert any("JSON-объектом" in e for e in cfg.errors)

    def test_n03_non_string_json_value(self, tmp_path):
        p = _write_json(tmp_path / "engine.json", {"ACTIVE_STRATEGY": 42})
        cfg = load_engine_config(engine_json_path=str(p), environ={})
        assert cfg.status is EngineStatus.CONFIG_ERROR
        assert any("должен быть строкой или null" in e for e in cfg.errors)

    def test_n03_non_string_env_value(self, tmp_path):
        p = _write_json(tmp_path / "engine.json", {"ACTIVE_STRATEGY": None})
        cfg = load_engine_config(
            engine_json_path=str(p), environ={"ACTIVE_STRATEGY": 123})
        assert cfg.status is EngineStatus.CONFIG_ERROR
        assert any("должен быть строкой" in e for e in cfg.errors)

    def test_unknown_json_keys_warn_not_fail(self, tmp_path):
        p = _write_json(tmp_path / "engine.json",
                        {"ACTIVE_STRATEGY": None,
                         "FUTURE_KEY": "future"})
        cfg = load_engine_config(engine_json_path=str(p), environ={})
        assert cfg.status is EngineStatus.UNCONFIGURED
        assert any("FUTURE_KEY" in w for w in cfg.warnings)

    def test_comment_keys_ignored(self, tmp_path):
        p = _write_json(tmp_path / "engine.json",
                        {"_comment": "ok", "ACTIVE_STRATEGY": None})
        cfg = load_engine_config(engine_json_path=str(p), environ={})
        assert cfg.status is EngineStatus.UNCONFIGURED
        assert not any("_comment" in w for w in cfg.warnings)


# ---------------------------------------------------------------------------
# N-04: известная, но regression-only стратегия; реестр без автовыбора
# ---------------------------------------------------------------------------

class TestRegressionOnlySelection:
    def test_n04_legacy_strategy_not_activatable(self, tmp_path):
        p = _write_json(tmp_path / "engine.json",
                        {"ACTIVE_STRATEGY": "legacy_samsung_v4"})
        cfg = load_engine_config(engine_json_path=str(p), environ={})
        assert cfg.status is EngineStatus.CONFIG_ERROR
        assert cfg.trading_allowed is False
        assert any("regression-only" in e for e in cfg.errors)
        assert cfg.attribution is None

    def test_n04_registry_has_no_activatable_strategies(self):
        assert registry.activatable_strategy_ids() == ()
        assert registry.is_known("legacy_samsung_v4") is True
        assert registry.is_activatable("legacy_samsung_v4") is False

    def test_n04_any_nonempty_value_is_config_error_at_stage_a(
            self, tmp_path):
        p = _write_json(tmp_path / "engine.json", {"ACTIVE_STRATEGY": None})
        for value in ("legacy_samsung_v4", "future_strategy", "*"):
            cfg = load_engine_config(
                engine_json_path=str(p),
                environ={"ACTIVE_STRATEGY": value})
            assert cfg.status is EngineStatus.CONFIG_ERROR, value
            assert cfg.trading_allowed is False, value


# ---------------------------------------------------------------------------
# Детерминизм загрузки
# ---------------------------------------------------------------------------

class TestDeterminism:
    def test_same_inputs_same_result(self, tmp_path):
        p = _write_json(tmp_path / "engine.json",
                        {"ACTIVE_STRATEGY": "legacy_samsung_v4"})
        env = {"ACTIVE_STRATEGY": ""}
        cfg1 = load_engine_config(engine_json_path=str(p), environ=env)
        cfg2 = load_engine_config(engine_json_path=str(p), environ=env)
        assert cfg1.status == cfg2.status
        assert cfg1.errors == cfg2.errors
        assert cfg1.warnings == cfg2.warnings

    def test_no_auto_selection_attribution_stays_none(self, tmp_path):
        # ни один сценарий Этапа A не порождает контекст атрибуции:
        # конфигурация CONFIGURED невозможна без явной активируемой стратегии
        for payload in ({"ACTIVE_STRATEGY": None},
                        {"ACTIVE_STRATEGY": "legacy_samsung_v4"}):
            p = _write_json(tmp_path / "engine.json", payload)
            cfg = load_engine_config(engine_json_path=str(p),
                                     environ={"ACTIVE_STRATEGY": "x_y_z"})
            assert cfg.attribution is None
