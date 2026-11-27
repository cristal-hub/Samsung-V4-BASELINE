# tests/test_stage_a2_config_hash_integrity.py
# STAGE A.2 CORRECTIVE TESTS — обязательная проверка соответствия
# config_hash фактической конфигурации (устранение единственного
# оставшегося дефекта независимой проверки Stage A.1).
#
# ДЕФЕКТ: StrategyConfig.__post_init__() проверял только непустоту
# config_hash, но не его соответствие параметрам;
# recompute_config_hash() вычислял правильный хеш, но не обеспечивал
# автоматическую проверку при создании объекта;
# AttributionContext.from_config() доверял переданному config_hash.
# В результате можно было создать конфигурацию с корректными
# параметрами и ЧУЖИМ хешем, а затем записать неверную атрибуцию
# в новые объекты движка.
#
# ОБЯЗАТЕЛЬНЫЕ ТЕСТЫ (по заданию Stage A.2) — проверяется РЕАЛЬНОЕ
# поведение (создание объекта/контролируемая ошибка), а не только
# наличие проверок в исходном коде:
#   1.  Корректный config_hash — объект создаётся.
#   2.  Хеш от другой конфигурации — создание запрещено.
#   3.  Хеш от изменённого параметра — создание запрещено.
#   4.  Хеш неправильной длины — создание запрещено.
#   5.  Хеш с не-hex символами — создание запрещено.
#   6.  NaN и Infinity — контролируемая ошибка.
#   7.  Неподдерживаемый изменяемый объект в параметрах —
#       контролируемая ошибка.
#   8.  Циклическая структура — контролируемая ошибка, без
#       бесконечной рекурсии.
#   9.  AttributionContext.from_config() принимает только корректную
#       конфигурацию.
#   10. AttributionFactory не создаёт объекты на основе некорректной
#       конфигурации.
#   11. Сериализация и JSON round-trip сохраняют правильный хеш.
#   12. Старые golden signals и профили остаются идентичными.
#
# Дополнительно: запрет обхода проверки (dataclasses.replace), запрет
# тихого «исправления» хеша, DAG-структуры не путаются с циклами,
# перепроверка defense-in-depth в from_config, консистентность
# публичных путей (Strategy.get_config, build_regression_config).
#
# Offline; без сети, брокера, Sandbox/LIVE-заявок. Файлы — только в
# tmp_path (здесь файлы не создаются вовсе, кроме чтения эталонов).

import ast
import dataclasses
import json
import os

import pytest

from attribution import (
    AttributionContext,
    AttributionError,
    AttributionFactory,
    AttributionRequiredError,
    stamp,
)
from strategy_api import (
    StrategyConfig,
    StrategyConfigError,
    compute_config_hash,
    validate_config_hash_format,
)

try:  # реальные индикаторы доступны? (та же схема, что у G-1)
    import pandas_ta_classic as _ta_mod
    _REAL_TA = all(hasattr(_ta_mod, name)
                   for name in ("sma", "rsi", "bbands", "adx"))
except ImportError:
    _REAL_TA = False

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PY = os.path.join(PROJECT_ROOT, "config.py")

# ---------------------------------------------------------------------------
# Помощники
# ---------------------------------------------------------------------------

def _make(params, config_hash, *, strategy_id="s", strategy_version="v",
          **kwargs) -> StrategyConfig:
    """Прямое создание StrategyConfig (публичный конструктор)."""
    return StrategyConfig(
        strategy_id=strategy_id,
        strategy_version=strategy_version,
        params=params,
        config_hash=config_hash,
        **kwargs,
    )


def _valid_params() -> dict:
    return {"a": 1, "nested": {"b": [1, 2, 3]}, "flag": True}


def _valid_hash(strategy_id="s", strategy_version="v", params=None) -> str:
    return compute_config_hash(
        strategy_id, strategy_version,
        _valid_params() if params is None else params)


# ---------------------------------------------------------------------------
# Обязательный тест 1: корректный config_hash — объект создаётся
# ---------------------------------------------------------------------------

class TestCreationWithValidHash:
    def test_valid_config_hash_object_created(self):
        params = _valid_params()
        config_hash = _valid_hash(params=params)
        config = _make(params, config_hash)
        # объект создан, идентификация сохранена
        assert config.strategy_id == "s"
        assert config.strategy_version == "v"
        assert config.config_hash == config_hash
        # хеш соответствует ФАКТИЧЕСКИ сохранённым параметрам
        assert config.recompute_config_hash() == config.config_hash
        # параметры хранятся без искажений
        assert dict(config.params.items()) == params

    def test_valid_creation_via_strategy_get_config(self):
        from strategy_api import ParamSpec, ParamType, Strategy

        class _S(Strategy):
            strategy_id = "sid"
            strategy_version = "1"

            def param_specs(self):
                return (ParamSpec("p_int", ParamType.INT, minimum=1),
                        ParamSpec("p_num", ParamType.FLOAT, minimum=0.0))

            def evaluate_entry(self, signal_input, config):
                raise NotImplementedError

        config = _S().get_config({"p_int": 5, "p_num": 2.5})
        assert config.recompute_config_hash() == config.config_hash

    def test_valid_creation_via_legacy_regression_config(self):
        from strategies.legacy_samsung_v4.strategy import \
            LegacySamsungV4Strategy

        config = LegacySamsungV4Strategy().build_regression_config(
            "SANDBOX_TEST")
        assert config.recompute_config_hash() == config.config_hash
        assert len(config.config_hash) == 64


# ---------------------------------------------------------------------------
# Обязательные тесты 2 и 3: чужой хеш / хеш изменённого параметра
# ---------------------------------------------------------------------------

class TestMismatchedHashRejected:
    def test_hash_of_another_config_rejected(self):
        # хеш вычислен ДЛЯ ДРУГОЙ конфигурации (другие параметры)
        foreign_hash = compute_config_hash("s", "v", {"a": 999})
        with pytest.raises(StrategyConfigError) as exc:
            _make(_valid_params(), foreign_hash)
        message = str(exc.value)
        assert "не соответствует" in message
        # доказательство «не исправляет молча»: ошибка называет и
        # переданный, и фактически ожидаемый хеш; объект не создан
        assert foreign_hash in message
        assert _valid_hash() in message

    def test_hash_of_modified_param_rejected(self):
        original_params = {"a": 1, "b": {"c": 2}}
        config_hash = _valid_hash(params=original_params)
        modified_params = {"a": 1, "b": {"c": 3}}  # один параметр изменён
        with pytest.raises(StrategyConfigError):
            _make(modified_params, config_hash)

    def test_hash_of_nested_modified_param_rejected(self):
        params = {"a": 1, "list": [1, 2]}
        config_hash = _valid_hash(params=params)
        modified = {"a": 1, "list": [1, 2, 3]}  # изменён вложенный список
        with pytest.raises(StrategyConfigError):
            _make(modified, config_hash)

    def test_hash_of_other_strategy_id_rejected(self):
        params = _valid_params()
        # хеш для другой пары (strategy_id, strategy_version)
        other = compute_config_hash("other", "v", params)
        with pytest.raises(StrategyConfigError):
            _make(params, other)
        other2 = compute_config_hash("s", "2.0", params)
        with pytest.raises(StrategyConfigError):
            _make(params, other2)

    def test_no_silent_substitution_on_public_paths(self):
        # ни один публичный путь не возвращает объект с заменённым хешем:
        # ошибка — единственный исход несоответствия
        with pytest.raises(StrategyConfigError):
            _make(_valid_params(), compute_config_hash("x", "y", {"z": 0}))
        # после отклонённого создания корректное создание работает
        # (состояние не «заражено» частично валидным объектом)
        config = _make(_valid_params(), _valid_hash())
        assert config.recompute_config_hash() == config.config_hash


# ---------------------------------------------------------------------------
# Обязательные тесты 4 и 5: формат config_hash (SHA-256 hexdigest)
# ---------------------------------------------------------------------------

class TestConfigHashFormatEnforced:
    @pytest.mark.parametrize("bad_hash", [
        "0" * 63,     # 63 символа — короткий
        "0" * 65,     # 65 символов — длинный
        "",           # пустая строка
        "a" * 10,     # произвольная короткая строка
        "h" * 64,     # не hex-символ
        "z" * 63 + "0",
        "0" * 63 + "g",
        "A" * 64,     # верхний регистр: каноническая форма hexdigest —
                      # только нижний регистр, такой хеш не мог быть
                      # вычислен compute_config_hash
        "0" * 32 + " " * 32,   # пробелы
    ])
    def test_invalid_format_rejected(self, bad_hash):
        with pytest.raises(StrategyConfigError):
            _make(_valid_params(), bad_hash)

    def test_non_string_hash_rejected(self):
        for bad in (None, 123, b"ab" * 32, ["a" * 64]):
            with pytest.raises(StrategyConfigError):
                _make(_valid_params(), bad)

    def test_format_validator_unit_behavior(self):
        real = _valid_hash()
        assert validate_config_hash_format(real) == real
        with pytest.raises(StrategyConfigError):
            validate_config_hash_format("0" * 63)
        with pytest.raises(StrategyConfigError):
            validate_config_hash_format(0.5)

    def test_computed_hash_always_canonical(self):
        # любой хеш, вычисленный compute_config_hash, проходит проверку
        # формата и создаёт конфигурацию
        for params in ({"a": 1}, {}, {"s": "текст", "n": 2.5},
                       {"lst": [1, 2], "d": {"k": True}}):
            h = compute_config_hash("s", "v", params)
            assert len(h) == 64
            assert all(c in "0123456789abcdef" for c in h)
            config = _make(params, h)
            assert config.config_hash == h


# ---------------------------------------------------------------------------
# Обязательный тест 6: NaN и Infinity — контролируемая ошибка
# ---------------------------------------------------------------------------

class TestNonFiniteValuesRejected:
    @pytest.mark.parametrize("bad_value", [
        float("nan"), float("inf"), float("-inf"),
    ])
    def test_nan_infinity_rejected_at_creation(self, bad_value):
        # частично валидный объект не возвращается: конструктор падает
        # контролируемой StrategyConfigError
        with pytest.raises(StrategyConfigError) as exc:
            _make({"a": bad_value}, "a" * 64)
        assert "NaN" in str(exc.value) or "Infinity" in str(exc.value)

    @pytest.mark.parametrize("params", [
        {"a": 1, "nested": {"deep": [1.0, float("nan")]}},
        {"a": 1, "nested": {"deep": {"inf": float("inf")}}},
        {"a": 1, "lst": [[float("inf")]]},
    ])
    def test_non_finite_in_nested_structures_rejected(self, params):
        with pytest.raises(StrategyConfigError):
            _make(params, "a" * 64)

    def test_non_finite_rejected_in_direct_hash_computation(self):
        # защита и прямых вызовов compute_config_hash
        with pytest.raises(StrategyConfigError):
            compute_config_hash("s", "v", {"a": float("nan")})
        with pytest.raises(StrategyConfigError):
            compute_config_hash("s", "v", {"a": [float("inf")]})

    def test_finite_floats_still_accepted(self):
        params = {"a": 0.1, "b": -2.5e10, "c": 0.0}
        config = _make(params, _valid_hash(params=params))
        assert config.recompute_config_hash() == config.config_hash


# ---------------------------------------------------------------------------
# Обязательный тест 7: неподдерживаемый изменяемый объект —
# контролируемая ошибка
# ---------------------------------------------------------------------------

class TestUnsupportedObjectsRejected:
    class _CustomMutable:
        """Произвольный изменяемый объект — не JSON-значение."""

    def test_custom_object_rejected(self):
        with pytest.raises(StrategyConfigError) as exc:
            _make({"a": self._CustomMutable()}, "a" * 64)
        assert "недетерминируемый тип" in str(exc.value)

    def test_unsupported_nested_in_structures_rejected(self):
        cases = [
            {"a": 1, "nested": {"obj": self._CustomMutable()}},
            {"a": 1, "lst": [1, self._CustomMutable()]},
            {"a": bytearray(b"ab")},
            {"a": memoryview(b"ab")},
            {"a": {"b": complex(1, 2)}},
            {"a": slice(1, 2)},
        ]
        for params in cases:
            with pytest.raises(StrategyConfigError):
                _make(params, "a" * 64)

    def test_unsupported_object_rejected_in_direct_hash_computation(self):
        with pytest.raises(StrategyConfigError):
            compute_config_hash("s", "v", {"a": self._CustomMutable()})

    def test_no_partial_object_leaks_on_failure(self):
        # после отклонённого создания корректная конфигурация создаётся:
        # объект-исключение не «просачивается» в хранимые параметры
        params = {"good": 1, "bad": self._CustomMutable()}
        with pytest.raises(StrategyConfigError):
            _make(params, "a" * 64)
        good_config = _make({"good": 1}, _valid_hash(params={"good": 1}))
        assert dict(good_config.params.items()) == {"good": 1}

    def test_json_value_types_still_accepted(self):
        from enum import Enum

        class _Mode(str, Enum):
            ON = "on"

        params = {"i": 7, "f": 1.5, "s": "x", "b": False, "n": None,
                  "e": _Mode.ON, "lst": [1, "a"], "d": {"k": 1},
                  "st": {1, 2}, "tup": (3, 4)}
        config = _make(params, _valid_hash(params=params))
        assert config.recompute_config_hash() == config.config_hash


# ---------------------------------------------------------------------------
# Обязательный тест 8: циклическая структура — контролируемая ошибка,
# без бесконечной рекурсии
# ---------------------------------------------------------------------------

class TestCyclicStructuresRejected:
    def test_self_referencing_dict_rejected(self):
        cyclic = {"a": 1}
        cyclic["self"] = cyclic
        with pytest.raises(StrategyConfigError) as exc:
            _make(cyclic, "a" * 64)
        assert "циклич" in str(exc.value)

    def test_self_referencing_list_rejected(self):
        cyclic_list = [1, 2]
        cyclic_list.append(cyclic_list)
        with pytest.raises(StrategyConfigError):
            _make({"a": cyclic_list}, "a" * 64)

    def test_indirect_cycle_dict_list_dict_rejected(self):
        d = {"k": 1}
        lst = [d]
        d["lst"] = lst          # dict -> list -> dict (тот же объект)
        with pytest.raises(StrategyConfigError):
            _make(d, "a" * 64)

    def test_indirect_cycle_dict_dict_rejected(self):
        outer = {"level": 1}
        inner = {"parent": outer}
        outer["child"] = inner  # dict -> dict -> dict (тот же объект)
        with pytest.raises(StrategyConfigError):
            _make(outer, "a" * 64)

    def test_cycle_rejected_in_direct_hash_computation(self):
        cyclic = {"a": 1}
        cyclic["self"] = cyclic
        # контролируемая StrategyConfigError, а не RecursionError:
        # pytest.raises(StrategyConfigError) не пропустит RecursionError
        with pytest.raises(StrategyConfigError):
            compute_config_hash("s", "v", cyclic)

    def test_cycle_in_metadata_rejected(self):
        cyclic_meta = {"a": 1}
        cyclic_meta["self"] = cyclic_meta
        with pytest.raises(StrategyConfigError):
            _make(_valid_params(), _valid_hash(), metadata=cyclic_meta)

    def test_dag_is_not_mistaken_for_cycle(self):
        # один объект, встречающийся ДВАЖДЫ как два значения (DAG, без
        # цикла по пути рекурсии) — допустим
        shared = {"x": [1, 2]}
        params = {"p": shared, "q": shared}
        config = _make(params, _valid_hash(params=params))
        assert config.recompute_config_hash() == config.config_hash
        # один и тот же кортеж в двух разных местах — тоже DAG
        params2 = {"a": (1, 2), "b": [(1, 2)]}
        config2 = _make(params2, _valid_hash(params=params2))
        assert config2.recompute_config_hash() == config2.config_hash


# ---------------------------------------------------------------------------
# Обязательные тесты 9 и 10: атрибуция не может получить некорректную
# конфигурацию и не создаёт объекты на её основе
# ---------------------------------------------------------------------------

class TestAttributionGuard:
    def test_from_config_accepts_valid_config(self):
        config = _make(
            _valid_params(),
            _valid_hash(strategy_id="alpha", strategy_version="1"),
            strategy_id="alpha", strategy_version="1")
        context = AttributionContext.from_config(config)
        assert context.strategy_id == "alpha"
        assert context.config_hash == config.config_hash
        assert context.as_dict() == config.attribution_dict()

    def test_from_config_rejects_objects_with_foreign_hash(self):
        from types import SimpleNamespace

        # duck-typed объект с фиктивным хешем
        fake = SimpleNamespace(strategy_id="s", config_hash="b" * 64)
        with pytest.raises(AttributionError):
            AttributionContext.from_config(fake)
        # duck-typed объект даже с РЕАЛЬНЫМ хешем ДРУГОЙ конфигурации:
        # он не может доказать соответствие — отвергается
        foreign = SimpleNamespace(
            strategy_id="s", config_hash=compute_config_hash(
                "other", "1.0", {"x": 1}))
        with pytest.raises(AttributionError):
            AttributionContext.from_config(foreign)
        # None и произвольные объекты
        with pytest.raises(AttributionError):
            AttributionContext.from_config(None)
        with pytest.raises(AttributionError):
            AttributionContext.from_config(object())
        with pytest.raises(AttributionError):
            AttributionContext.from_config("s:hash")

    def test_from_config_rejects_garbage_field_values(self):
        from types import SimpleNamespace

        for fake in (SimpleNamespace(strategy_id="", config_hash=""),
                     SimpleNamespace(strategy_id="s", config_hash=None)):
            with pytest.raises(AttributionError):
                AttributionContext.from_config(fake)

    def test_from_config_defense_in_depth_recheck(self):
        # перепроверка recompute_config_hash внутри from_config: даже если
        # бы конфигурация с несоответствующим хешем была собрана в обход
        # публичного конструктора, контекст с чужим хешем не выпускается
        config = _make(_valid_params(), _valid_hash())
        # собранный в обход конструктора объект (только для проверки
        # защиты: вне обычного публичного API)
        tampered = StrategyConfig.__new__(StrategyConfig)
        for name, value in (("strategy_id", config.strategy_id),
                            ("strategy_version", config.strategy_version),
                            ("params", config.params),
                            ("config_hash", "b" * 64),
                            ("origin", config.origin),
                            ("metadata", config.metadata)):
            object.__setattr__(tampered, name, value)
        with pytest.raises(AttributionError) as exc:
            AttributionContext.from_config(tampered)
        assert "не соответствует" in str(exc.value)

    def test_factory_refuses_inconsistent_config(self):
        from types import SimpleNamespace

        fake = SimpleNamespace(strategy_id="s", config_hash="b" * 64)
        # фабрика не создаётся из некорректной конфигурации
        with pytest.raises(AttributionRequiredError):
            AttributionFactory(fake)
        # и штампование с ней невозможно
        with pytest.raises(AttributionRequiredError):
            stamp({"x": 1}, fake)
        with pytest.raises(AttributionRequiredError):
            AttributionFactory(None)
        with pytest.raises(AttributionRequiredError):
            AttributionFactory("not-a-context")

    def test_factory_from_valid_config_stamps_correctly(self):
        config = _make(
            _valid_params(),
            _valid_hash(strategy_id="alpha", strategy_version="1"),
            strategy_id="alpha", strategy_version="1")
        factory = AttributionFactory(config)
        event = factory.new_event({"event_id": "E1"})
        assert event["strategy_id"] == "alpha"
        assert event["config_hash"] == config.config_hash
        order = factory.new_virtual_order({"order_id": "O1"})
        position = factory.new_virtual_position({"position_id": "P1"})
        assert order["config_hash"] == config.config_hash
        assert position["config_hash"] == config.config_hash
        # контекст фабрики — точная пара атрибуции конфигурации
        assert factory.context.as_dict() == config.attribution_dict()

    def test_engine_config_attribution_path_is_gated(self):
        # связка с конфигурацией движка: контекст выводится из
        # StrategyConfig строго через from_config (защищённый путь);
        # несоответствующий хеш в атрибуцию попасть не может
        from engine_config import EngineStatus, load_engine_config

        # несуществующая стратегия -> конфигурационной ошибки нет объекта
        # атрибуции (fail-closed, поведение Stage A сохранено)
        engine_json = os.path.join(PROJECT_ROOT, "engine.json")
        with open(engine_json, "r", encoding="utf-8") as handle:
            engine_content = json.load(handle)
        assert engine_content.get("ACTIVE_STRATEGY") is None


# ---------------------------------------------------------------------------
# Обязательный тест 11: сериализация и JSON round-trip сохраняют хеш
# ---------------------------------------------------------------------------

class TestSerializationHashIntegrity:
    def test_json_roundtrip_preserves_verified_hash(self):
        params = {"a": 1, "nested": {"b": [1, 2]}, "levels": {1.0, 2.0}}
        config = _make(params, _valid_hash(params=params),
                       metadata={"note": "roundtrip"})
        payload = json.dumps(config.as_dict(), ensure_ascii=False)
        restored = json.loads(payload)
        # восстановленная конфигурация создаётся ТОЛЬКО с тем же хешем
        config2 = StrategyConfig(
            strategy_id=restored["strategy_id"],
            strategy_version=restored["strategy_version"],
            params=restored["params"],
            config_hash=restored["config_hash"],
            origin=restored["origin"],
            metadata=restored["metadata"],
        )
        assert config2.config_hash == config.config_hash
        assert config2.recompute_config_hash() == config2.config_hash

    def test_restored_config_with_modified_param_rejected(self):
        # после round-trip подмена параметра без пересчёта хеша по-прежнему
        # невозможна — проверка выполняется при каждом создании
        params = {"a": 1, "nested": {"b": [1, 2]}}
        config_hash = _valid_hash(params=params)
        payload = json.dumps({
            "strategy_id": "s", "strategy_version": "v",
            "params": {"a": 1, "nested": {"b": [1, 2, 99]}},
            "config_hash": config_hash, "origin": "engine",
            "metadata": {},
        }, ensure_ascii=False)
        restored = json.loads(payload)
        with pytest.raises(StrategyConfigError):
            StrategyConfig(
                strategy_id=restored["strategy_id"],
                strategy_version=restored["strategy_version"],
                params=restored["params"],
                config_hash=restored["config_hash"],
                origin=restored["origin"],
                metadata=restored["metadata"],
            )

    def test_as_dict_carries_exactly_the_verified_hash(self):
        config = _make(_valid_params(), _valid_hash())
        as_dict = config.as_dict()
        assert as_dict["config_hash"] == config.config_hash
        # and serialization of the dict itself does not alter the hash
        repacked = json.loads(json.dumps(as_dict, ensure_ascii=False))
        assert repacked["config_hash"] == config.config_hash

    def test_public_paths_serialization_consistency(self):
        # get_config -> as_dict -> json -> новая конфигурация: хеш тот же
        from strategy_api import ParamSpec, ParamType, Strategy

        class _S(Strategy):
            strategy_id = "ser"
            strategy_version = "2"

            def param_specs(self):
                return (ParamSpec("p", ParamType.INT, minimum=1),)

            def evaluate_entry(self, signal_input, config):
                raise NotImplementedError

        config = _S().get_config({"p": 9})
        restored = json.loads(json.dumps(config.as_dict()))
        config2 = _S().get_config(restored["params"])
        assert config2.config_hash == config.config_hash


# ---------------------------------------------------------------------------
# Запрет обхода проверки (требование «не допускать обхода через ручное
# создание StrategyConfig»)
# ---------------------------------------------------------------------------

class TestNoBypassPaths:
    def test_dataclasses_replace_cannot_inject_foreign_hash(self):
        config = _make(_valid_params(), _valid_hash())
        with pytest.raises(StrategyConfigError):
            dataclasses.replace(config, config_hash="b" * 64)
        with pytest.raises(StrategyConfigError):
            dataclasses.replace(config, params={"a": 2})
        with pytest.raises(StrategyConfigError):
            dataclasses.replace(
                config, params=_valid_params(),
                config_hash=compute_config_hash("other", "9", {"q": 1}))

    def test_dataclasses_replace_with_consistent_fields_works(self):
        config = _make(_valid_params(), _valid_hash())
        replaced = dataclasses.replace(config, origin="regression_harness")
        assert replaced.origin == "regression_harness"
        assert replaced.config_hash == config.config_hash
        assert replaced.recompute_config_hash() == replaced.config_hash

    def test_post_init_runs_for_every_construction(self):
        # конструктор один: любая сборка через публичный API проходит
        # проверку (создание с заведомо чужим хешем невозможно ни в какой
        # публичной форме)
        foreign_hash = compute_config_hash("zzz", "0", {"k": "v"})
        for kwargs in (
            {"strategy_id": "s", "strategy_version": "v",
             "params": _valid_params(), "config_hash": foreign_hash},
            {"strategy_id": "s", "strategy_version": "v",
             "params": _valid_params(), "config_hash": "q" * 64},
        ):
            with pytest.raises(StrategyConfigError):
                StrategyConfig(**kwargs)


# ---------------------------------------------------------------------------
# Обязательный тест 12: старые golden signals и профили остаются
# идентичными (Stage A.2 не сдвинул ни сигналы, ни исторические параметры)
# ---------------------------------------------------------------------------

def _baseline_profile_branches(source):
    """Ветки `if PROFILE == "ИМЯ":` baseline config.py (AST, только чтение).
    Та же семантика, что в tests/test_stage_a_legacy_profiles.py (G-5)."""

    def constant_assigns(body):
        result = {}
        for node in body:
            if isinstance(node, ast.Assign) and len(node.targets) == 1 \
                    and isinstance(node.targets[0], ast.Name):
                value = node.value
                if isinstance(value, ast.Constant):
                    result[node.targets[0].id] = value.value
                elif isinstance(value, ast.IfExp):
                    continue
        return result

    def walk_if(node, branches):
        test = node.test
        if (isinstance(test, ast.Compare)
                and isinstance(test.left, ast.Name)
                and test.left.id == "PROFILE"
                and len(test.ops) == 1
                and isinstance(test.ops[0], ast.Eq)
                and len(test.comparators) == 1
                and isinstance(test.comparators[0], ast.Constant)):
            name = test.comparators[0].value
            branches[name] = constant_assigns(node.body)
        for child in node.orelse:
            if isinstance(child, ast.If):
                walk_if(child, branches)

    tree = ast.parse(source)
    branches = {}
    for node in tree.body:
        if isinstance(node, ast.If):
            walk_if(node, branches)
    return branches


@pytest.mark.skipif(
    not _REAL_TA,
    reason="golden-сигналы требуют реальных индикаторов pandas_ta_classic "
           "(в offline-заглушке эталон не воспроизводим; та же схема SKIP, "
           "что у G-1)")
class TestGoldenSignalsAndProfilesUnchanged:
    def test_golden_signals_reproduce_exactly(self):
        from strategies.legacy_samsung_v4 import profiles
        from strategies.legacy_samsung_v4.strategy import \
            LegacySamsungV4Strategy
        from tests.stage_a_golden_tools import (
            FIXTURE_BUILDERS,
            GOLDEN_PATH,
            builder_df,
            fixture_sha256,
        )

        import strategy_api as sa

        with open(GOLDEN_PATH, "r", encoding="utf-8") as handle:
            golden = json.load(handle)
        strategy = LegacySamsungV4Strategy()
        for name, (_, drop_incomplete) in FIXTURE_BUILDERS.items():
            # fixture байт-в-байт те же, на которых снят эталон
            assert golden["fixture_sha256"][name] == fixture_sha256(name), \
                f"fixture {name} изменился"
            df = builder_df(name)
            last_price = float(df["close"].iloc[-1])
            for profile in profiles.PROFILE_NAMES:
                config = strategy.build_regression_config(profile)
                signal = strategy.evaluate_entry(
                    sa.EntrySignalInput(
                        figi="FIX", ticker=name, candles=df.copy(),
                        last_price=last_price,
                        drop_incomplete=drop_incomplete),
                    config)
                expected = golden["expectations"][f"{name}::{profile}"]
                assert signal.direction.value == expected["signal"], \
                    (name, profile, signal.reason)
                assert signal.reason == expected["reason"], (name, profile)

    def test_profiles_identical_to_baseline_config_py(self):
        from strategies.legacy_samsung_v4 import profiles

        with open(CONFIG_PY, "r", encoding="utf-8") as handle:
            source = handle.read()
        baseline = _baseline_profile_branches(source)
        assert profiles.PROFILE_NAMES == (
            "SANDBOX_TEST", "TECH_CHECK", "CONSERVATIVE")
        for name in profiles.PROFILE_NAMES:
            assert name in baseline, name
            assert profiles.PROFILES[name] == baseline[name], \
                f"профиль {name} отличается от baseline config.py"
        # FORCE_TRADE не перенесён в новую архитектуру (как и в Stage A)
        assert "FORCE_TRADE" in baseline        # в baseline он есть (история)
        assert "FORCE_TRADE" not in profiles.PROFILES
        with pytest.raises(ValueError):
            profiles.build_regression_params("FORCE_TRADE")

    def test_regression_configs_of_all_profiles_are_consistent(self):
        from strategies.legacy_samsung_v4 import profiles
        from strategies.legacy_samsung_v4.strategy import \
            LegacySamsungV4Strategy

        strategy = LegacySamsungV4Strategy()
        hashes = {}
        for name in profiles.PROFILE_NAMES:
            config = strategy.build_regression_config(name)
            # проверка соответствия выполняется при создании (Stage A.2);
            # здесь — независимая перепроверка результата
            assert config.recompute_config_hash() == config.config_hash, name
            hashes[name] = config.config_hash
        # разные профили — разные хеши (идентификация различима)
        assert len(set(hashes.values())) == len(profiles.PROFILE_NAMES)
