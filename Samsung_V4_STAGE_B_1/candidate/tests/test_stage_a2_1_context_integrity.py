# tests/test_stage_a2_1_context_integrity.py
# STAGE A.2.1 CORRECTIVE TESTS — закрытие трёх оставшихся ограничений,
# обнаруженных независимой проверкой Stage A.2.
#
# ДЕФЕКТ №1 — прямое создание AttributionContext:
#   публичный конструктор AttributionContext(strategy_id, config_hash)
#   выпускал произвольный контекст без проверки соответствия config_hash
#   реальной StrategyConfig; _resolve_context принимал его как есть, и
#   AttributionFactory мог штамповать им новые объекты — обход проверки
#   Stage A.2. Решение: контекст создаётся ТОЛЬКО на основании проверенной
#   StrategyConfig (охраняемый конструктор с внутренним приватным билетом);
#   любой путь обычного публичного создания с произвольной парой строк —
#   AttributionError; отсутствие подтверждённой конфигурации — fail-closed.
#
# ДЕФЕКТ №2 — наследование StrategyConfig:
#   AttributionContext.from_config() использовал isinstance(config,
#   StrategyConfig) и перепроверку через переопределяемый
#   config.recompute_config_hash(): подкласс мог переопределить
#   recompute_config_hash (и даже __post_init__) и ослабить проверку.
#   РЕШЕНИЕ (документировано в attribution.py): принимается ТОЛЬКО точный
#   тип StrategyConfig (type(config) is StrategyConfig) — наследование не
#   поддерживается; соответствие хеша перепроверяется ИСХОДНЫМ алгоритмом
#   strategy_api.compute_config_hash по фактическим strategy_id/
#   strategy_version/params/config_hash (несовпадение любого поля —
#   AttributionError); переопределяемые методы объекта НЕ используются как
#   источник проверки.
#
# ДЕФЕКТ №3 — изменяемый Enum.value:
#   Enum рассматривался как скаляр, но его .value мог содержать изменяемый
#   объект: фактическое содержимое параметра менялось ПОСЛЕ вычисления
#   config_hash. Решение (strategy_api.py): рекурсивная _validate_enum_value
#   — допустимы только безопасные неизменяемые скаляры (None/bool/int/
#   float/str); изменяемые значения (dict/list/set/bytearray/...) и прочие
#   нескалярные отклоняются StrategyConfigError при каждом создании
#   конфигурации, при ПРЯМОМ compute_config_hash и в deep_freeze.
#
# ОБЯЗАТЕЛЬНЫЕ ТЕСТЫ (по заданию Stage A.2.1) — проверяется РЕАЛЬНОЕ
# поведение (объект создаётся / контролируемая ошибка), а не только
# наличие проверок в исходном коде:
#    1. Прямое создание AttributionContext с произвольными строками
#       запрещено.
#    2. Валидная StrategyConfig позволяет получить корректный
#       AttributionContext.
#    3. AttributionFactory принимает только проверенный контекст.
#    4. stamp не принимает произвольный неподтверждённый контекст.
#    5. CSV/JSONL не могут получить неподтверждённую атрибуцию.
#    6. Подкласс StrategyConfig с переопределённым recompute_config_hash
#       не обходит защиту.
#    7. Подкласс с изменёнными параметрами не может получить чужой хеш.
#    8. Обычный Enum со строковым value работает.
#    9. Обычный Enum с числовым value работает.
#   10. Enum со значением list отклоняется.
#   11. Enum со значением dict отклоняется.
#   12. Enum со вложенным изменяемым значением отклоняется.
#   13. Прямой compute_config_hash отклоняет небезопасные Enum.
#   14. Все корректные существующие конфигурации сохраняют прежние хеши
#       (эталонные значения вычислены КОДОМ STAGE A.2 ДО изменений —
#       см. STAGE_A_2_REFERENCE_HASHES ниже).
#   15. AttributionContext и AttributionFactory остаются неизменяемыми.
#   16. Параллельная работа нескольких стратегий сохраняет правильную
#       атрибуцию.
# Плюс: сериализация, JSON round-trip и обратная совместимость.
#
# Offline; без сети, брокера, Sandbox/LIVE-заявок. Файлы — только в
# tmp_path.

import copy
import dataclasses
import hashlib
import json
import os
import pickle
import threading
from enum import Enum
from types import MappingProxyType

import pytest

from attribution import (
    ATTRIBUTION_FIELDS,
    AttributionContext,
    AttributionError,
    AttributionFactory,
    AttributionRequiredError,
    append_attributed_csv_row,
    append_attributed_jsonl_row,
    read_csv_attribution_report,
    read_jsonl_attribution_report,
    record_has_attribution,
    stamp,
)
from strategy_api import (
    ParamSpec,
    ParamType,
    Strategy,
    StrategyConfig,
    StrategyConfigError,
    compute_config_hash,
    deep_freeze,
    validate_config_hash_format,
)


# ---------------------------------------------------------------------------
# Помощники: две явные стратегии и проверенные конфигурации
# ---------------------------------------------------------------------------

class _StrategyAlpha(Strategy):
    strategy_id = "alpha_engine"
    strategy_version = "1.0"

    def param_specs(self):
        return (ParamSpec("p_int", ParamType.INT, minimum=1),)

    def evaluate_entry(self, signal_input, config):
        raise NotImplementedError


class _StrategyBeta(Strategy):
    strategy_id = "beta_engine"
    strategy_version = "2.0"

    def param_specs(self):
        return (ParamSpec("p_int", ParamType.INT, minimum=1),)

    def evaluate_entry(self, signal_input, config):
        raise NotImplementedError


def _config_for(cls, p_int: int) -> StrategyConfig:
    """Проверенная StrategyConfig через публичный путь get_config."""
    return cls().get_config({"p_int": p_int})


def _plain_config(strategy_id: str = "s", strategy_version: str = "v",
                  params: dict = None) -> StrategyConfig:
    """Проверенная StrategyConfig прямым публичным конструктором."""
    params = params if params is not None else {"p": 1}
    return StrategyConfig(
        strategy_id=strategy_id,
        strategy_version=strategy_version,
        params=params,
        config_hash=compute_config_hash(strategy_id, strategy_version, params),
    )


def _verified_context(config: StrategyConfig = None) -> AttributionContext:
    return AttributionContext.from_config(
        config if config is not None else _config_for(_StrategyAlpha, 1))


# ---------------------------------------------------------------------------
# Тест 1: прямое создание AttributionContext с произвольными строками
# запрещено (дефект №1)
# ---------------------------------------------------------------------------

class TestDirectCreationForbidden:
    def test_arbitrary_pair_rejected(self):
        # самая соблазнительная форма: произвольные strategy_id/config_hash
        with pytest.raises(AttributionError):
            AttributionContext(strategy_id="any", config_hash="a" * 64)
        with pytest.raises(AttributionError):
            AttributionContext("any", "a" * 64)  # позиционно тоже

    def test_fake_hash_of_another_config_rejected(self):
        # даже РЕАЛЬНЫЙ хеш чужой конфигурации не создаёт контекст:
        # пара строк сама по себе не может подтвердить соответствие
        foreign = compute_config_hash("zzz", "9", {"q": 1})
        with pytest.raises(AttributionError):
            AttributionContext(strategy_id="s", config_hash=foreign)

    def test_degenerate_values_rejected(self):
        for args in (("", "a" * 64), ("s", ""), (None, None), (None,),
                     (), (123, "a" * 64), ("s", 123), ("s", "zz")):
            with pytest.raises(AttributionError):
                AttributionContext(*args)

    def test_error_message_points_to_from_config(self):
        with pytest.raises(AttributionError) as exc:
            AttributionContext("s", "a" * 64)
        message = str(exc.value)
        assert "from_config" in message
        assert "запрещено" in message

    def test_instance_assembled_around_constructor_is_rejected(self):
        # defense-in-depth: экземпляр, собранный В ОБХОД конструктора
        # (object.__new__, интроспекция), не имеет маркера проверенного
        # создания и отклоняется на границе использования (интроспекция
        # сама по себе не является целью абсолютной защиты по условию,
        # но граница API её дополнительно отсекает).
        fabricated = object.__new__(AttributionContext)
        object.__setattr__(fabricated, "strategy_id", "evil")
        object.__setattr__(fabricated, "config_hash", "b" * 64)
        with pytest.raises(AttributionError):
            stamp({"x": 1}, fabricated)
        with pytest.raises(AttributionError):
            AttributionFactory(fabricated)


# ---------------------------------------------------------------------------
# Тест 2: валидная StrategyConfig даёт корректный AttributionContext
# ---------------------------------------------------------------------------

class TestValidConfigProducesContext:
    def test_from_config_returns_correct_pair(self):
        config = _config_for(_StrategyAlpha, 1)
        ctx = AttributionContext.from_config(config)
        assert ctx.strategy_id == "alpha_engine"
        assert ctx.config_hash == config.config_hash
        assert ctx.as_dict() == {
            "strategy_id": "alpha_engine",
            "config_hash": config.config_hash,
        }

    def test_hash_pair_is_stable_and_deterministic(self):
        config = _config_for(_StrategyBeta, 2)
        ctx1 = AttributionContext.from_config(config)
        ctx2 = AttributionContext.from_config(config)
        assert ctx1 == ctx2 and hash(ctx1) == hash(ctx2)

    def test_different_configs_different_contexts(self):
        ctx_a = AttributionContext.from_config(_config_for(_StrategyAlpha, 1))
        ctx_b = AttributionContext.from_config(_config_for(_StrategyBeta, 2))
        assert ctx_a != ctx_b
        assert ctx_a.config_hash != ctx_b.config_hash

    def test_direct_config_also_works(self):
        # конфигурация, собранная прямым публичным конструктором с
        # ВЫЧИСЛЕННЫМ хешем, тоже проходит (Stage A.2 гарантирует
        # соответствие при создании)
        config = _plain_config("direct", "1", {"p": 1})
        ctx = AttributionContext.from_config(config)
        assert ctx.config_hash == config.config_hash

    def test_missing_configuration_fails_closed(self):
        # отсутствие подтверждённой конфигурации — fail-closed ошибка
        with pytest.raises(AttributionError):
            AttributionContext.from_config(None)
        with pytest.raises(AttributionError):
            AttributionContext.from_config(object())
        with pytest.raises(AttributionError):
            AttributionContext.from_config({"strategy_id": "s",
                                            "config_hash": "a" * 64})
        with pytest.raises(AttributionError):
            AttributionContext.from_config("s:a" * 8)
        with pytest.raises(AttributionRequiredError):
            stamp({}, None)


# ---------------------------------------------------------------------------
# Тест 3: AttributionFactory принимает только проверенный контекст
# ---------------------------------------------------------------------------

class TestFactoryAcceptsOnlyVerifiedContext:
    def test_factory_accepts_verified_context(self):
        ctx = _verified_context()
        factory = AttributionFactory(ctx)
        stamped = factory.new_event({"event": "TEST"})
        assert stamped["strategy_id"] == ctx.strategy_id
        assert stamped["config_hash"] == ctx.config_hash

    def test_factory_accepts_verified_strategy_config(self):
        config = _config_for(_StrategyAlpha, 1)
        factory = AttributionFactory(config)
        assert factory.context == AttributionContext.from_config(config)

    def test_factory_rejects_arbitrary_pair(self):
        # произвольную пару строк вообще невозможно оформить в контекст
        foreign = compute_config_hash("zzz", "9", {"q": 1})
        with pytest.raises(AttributionError):
            AttributionFactory(AttributionContext("x", foreign))  # noqa

    def test_factory_rejects_duck_typed_object(self):
        class _Fake:
            strategy_id = "s"
            config_hash = "a" * 64

        with pytest.raises(AttributionError):
            AttributionFactory(_Fake())

    def test_factory_rejects_unmarked_instance(self):
        fabricated = object.__new__(AttributionContext)
        object.__setattr__(fabricated, "strategy_id", "evil")
        object.__setattr__(fabricated, "config_hash", "b" * 64)
        with pytest.raises(AttributionError):
            AttributionFactory(fabricated)

    def test_factory_rejects_none(self):
        with pytest.raises(AttributionRequiredError):
            AttributionFactory(None)


# ---------------------------------------------------------------------------
# Тест 4: stamp не принимает произвольный неподтверждённый контекст
# ---------------------------------------------------------------------------

class TestStampRejectsUnverifiedContext:
    def test_stamp_accepts_verified_context_and_config(self):
        ctx = _verified_context()
        config = _config_for(_StrategyBeta, 2)
        r1 = stamp({"x": 1}, ctx)
        r2 = stamp({"x": 1}, config)
        assert r1["config_hash"] == ctx.config_hash
        assert r2["config_hash"] == config.config_hash

    def test_stamp_rejects_duck_typed_object(self):
        class _Fake:
            strategy_id = "s"
            config_hash = "a" * 64

        with pytest.raises(AttributionError):
            stamp({"x": 1}, _Fake())

    def test_stamp_rejects_unmarked_instance(self):
        fabricated = object.__new__(AttributionContext)
        object.__setattr__(fabricated, "strategy_id", "evil")
        object.__setattr__(fabricated, "config_hash", "b" * 64)
        with pytest.raises(AttributionError):
            stamp({"x": 1}, fabricated)
        # запись осталась без атрибуции (объект не создан)
        assert record_has_attribution({"x": 1}) is False

    def test_stamp_rejects_arbitrary_strings(self):
        # строку нельзя использовать как контекст; и нельзя из неё собрать
        # контекст в обход проверки (тест 1)
        with pytest.raises(AttributionError):
            stamp({"x": 1}, "s:" + "a" * 64)
        with pytest.raises(AttributionRequiredError):
            stamp({"x": 1}, None)

    def test_stamp_conflict_rules_unchanged(self):
        ctx = _verified_context()
        with pytest.raises(AttributionError):
            stamp({"strategy_id": "other", "config_hash": "c" * 64}, ctx)
        stamped = stamp(
            {"strategy_id": ctx.strategy_id,
             "config_hash": ctx.config_hash, "x": 1}, ctx)
        assert stamped == {"strategy_id": ctx.strategy_id,
                           "config_hash": ctx.config_hash, "x": 1}


# ---------------------------------------------------------------------------
# Тест 5: CSV/JSONL не могут получить неподтверждённую атрибуцию
# ---------------------------------------------------------------------------

class TestLogsRejectUnverifiedAttribution:
    BASE_FIELDS = ["event_id", "timestamp_utc", "figi", "kind"]

    def test_csv_row_with_verified_context(self, tmp_path):
        path = str(tmp_path / "events.csv")
        ctx = _verified_context()
        row = append_attributed_csv_row(
            path, {"event_id": "E1"}, self.BASE_FIELDS, context=ctx)
        assert row["config_hash"] == ctx.config_hash
        assert os.path.isfile(path)

    def test_csv_row_rejects_unverified(self, tmp_path):
        path = str(tmp_path / "events.csv")
        fabricated = object.__new__(AttributionContext)
        object.__setattr__(fabricated, "strategy_id", "evil")
        object.__setattr__(fabricated, "config_hash", "b" * 64)
        with pytest.raises(AttributionError):
            append_attributed_csv_row(
                path, {"event_id": "E1"}, self.BASE_FIELDS,
                context=fabricated)
        assert not os.path.isfile(path)

    def test_csv_row_rejects_duck_typed_and_none(self, tmp_path):
        class _Fake:
            strategy_id = "s"
            config_hash = "a" * 64

        path = str(tmp_path / "events.csv")
        with pytest.raises(AttributionError):
            append_attributed_csv_row(
                path, {"event_id": "E1"}, self.BASE_FIELDS, context=_Fake())
        with pytest.raises(AttributionError):
            append_attributed_csv_row(
                path, {"event_id": "E1"}, self.BASE_FIELDS, context=None)
        assert not os.path.isfile(path)

    def test_jsonl_row_with_verified_context(self, tmp_path):
        path = str(tmp_path / "events.jsonl")
        ctx = _verified_context()
        stamped = append_attributed_jsonl_row(
            path, {"event": "TEST"}, context=ctx)
        assert stamped["config_hash"] == ctx.config_hash
        restored = read_jsonl_attribution_report(path)
        assert restored[0]["has_attribution"] is True
        assert restored[0]["config_hash"] == ctx.config_hash

    def test_jsonl_row_rejects_unverified(self, tmp_path):
        path = str(tmp_path / "events.jsonl")
        fabricated = object.__new__(AttributionContext)
        object.__setattr__(fabricated, "strategy_id", "evil")
        object.__setattr__(fabricated, "config_hash", "b" * 64)
        with pytest.raises(AttributionError):
            append_attributed_jsonl_row(path, {"event": "TEST"},
                                        context=fabricated)
        assert not os.path.isfile(path)

    def test_factory_log_paths_use_verified_context(self, tmp_path):
        ctx = _verified_context()
        factory = AttributionFactory(ctx)
        csv_path = str(tmp_path / "f.csv")
        jsonl_path = str(tmp_path / "f.jsonl")
        factory.append_csv_row(csv_path, {"event_id": "E1"},
                               self.BASE_FIELDS)
        factory.append_jsonl_row(jsonl_path, {"event": "TEST"})
        rows = read_csv_attribution_report(csv_path)
        assert rows[0]["config_hash"] == ctx.config_hash
        events = read_jsonl_attribution_report(jsonl_path)
        assert events[0]["config_hash"] == ctx.config_hash


# ---------------------------------------------------------------------------
# Тест 6: подкласс StrategyConfig с переопределённым recompute_config_hash
# не обходит защиту (дефект №2)
# ---------------------------------------------------------------------------

class TestSubclassWithOverriddenRecompute:
    def _sneaky_class(self):
        class _Sneaky(StrategyConfig):
            # «пропускающая» перепроверка: всегда возвращает собственный
            # config_hash (так подкласс пытался ослабить защиту Stage A.2)
            def recompute_config_hash(self):
                return self.config_hash

        return _Sneaky

    def test_sneaky_instance_cannot_get_context(self):
        _Sneaky = self._sneaky_class()
        params = {"p": 1}
        sneaky = _Sneaky(
            strategy_id="s", strategy_version="v", params=params,
            config_hash=compute_config_hash("s", "v", params))
        # создание подкласса прошло (наследование __post_init__ сохранило
        # проверку Stage A.2), но контекст выпустить НЕЛЬЗЯ: принимается
        # ТОЛЬКО точный тип StrategyConfig
        with pytest.raises(AttributionError):
            AttributionContext.from_config(sneaky)

    def test_sneaky_cannot_stamp_or_create_factory(self):
        _Sneaky = self._sneaky_class()
        params = {"p": 2}
        sneaky = _Sneaky(
            strategy_id="s", strategy_version="v", params=params,
            config_hash=compute_config_hash("s", "v", params))
        with pytest.raises(AttributionError):
            stamp({"x": 1}, sneaky)
        with pytest.raises(AttributionError):
            AttributionFactory(sneaky)

    def test_error_message_documents_exact_type_decision(self):
        _Sneaky = self._sneaky_class()
        params = {"p": 3}
        sneaky = _Sneaky(
            strategy_id="s", strategy_version="v", params=params,
            config_hash=compute_config_hash("s", "v", params))
        with pytest.raises(AttributionError) as exc:
            AttributionContext.from_config(sneaky)
        message = str(exc.value)
        assert "точный тип" in message
        assert "наследование" in message

    def test_exact_type_is_required_even_for_correct_content(self):
        # отклоняется сам ФАКТ подкласса, а не только содержимое:
        # консистентный подкласс тоже не получает контекст
        _Sneaky = self._sneaky_class()
        params = {"p": 4}
        sneaky = _Sneaky(
            strategy_id="s", strategy_version="v", params=params,
            config_hash=compute_config_hash("s", "v", params))
        # содержание полностью корректно — но тип другой
        assert compute_config_hash(
            sneaky.strategy_id, sneaky.strategy_version,
            sneaky.params) == sneaky.config_hash
        with pytest.raises(AttributionError):
            AttributionContext.from_config(sneaky)


# ---------------------------------------------------------------------------
# Тест 7: подкласс с изменёнными параметрами не может получить чужой хеш
# ---------------------------------------------------------------------------

class TestSubclassWithSwappedParams:
    def _evil_class(self):
        class _Evil(StrategyConfig):
            # ослабление ОБЕИХ проверок подклассом: создание без валидации
            # и фальшивая перепроверка (именно такую цепочку закрыла
            # граница точного типа Stage A.2.1)
            def __post_init__(self):
                pass  # проверка Stage A.2 пропущена

            def recompute_config_hash(self):
                return self.config_hash  # фальшивая перепроверка

        return _Evil

    def test_subclass_cannot_obtain_foreign_hash_context(self):
        _Evil = self._evil_class()
        foreign_hash = compute_config_hash("other", "9", {"q": 1})
        evil = _Evil(strategy_id="s", strategy_version="v",
                     params={"p": 1}, config_hash=foreign_hash)
        # подлинный алгоритм по фактическим полям даёт ДРУГОЙ хеш:
        # несоответствие объективно существует и обнаруживается
        assert compute_config_hash(
            evil.strategy_id, evil.strategy_version,
            evil.params) != foreign_hash
        # контекст с чужим хешем НЕ выпускается ни одним путём
        with pytest.raises(AttributionError):
            AttributionContext.from_config(evil)
        with pytest.raises(AttributionError):
            stamp({"x": 1}, evil)
        with pytest.raises(AttributionError):
            AttributionFactory(evil)

    def test_original_algorithm_used_not_overridden_method(self):
        # даже для точного типа, собранного в обход конструктора,
        # проверка выполняется ИСХОДНЫМ алгоритмом compute_config_hash,
        # а не переопределяемым методом объекта
        foreign_hash = compute_config_hash("other", "9", {"q": 1})
        bare = object.__new__(StrategyConfig)
        object.__setattr__(bare, "strategy_id", "s")
        object.__setattr__(bare, "strategy_version", "v")
        object.__setattr__(bare, "params", {"p": 1})
        object.__setattr__(bare, "config_hash", foreign_hash)
        object.__setattr__(bare, "origin", "engine")
        object.__setattr__(bare, "metadata", {})
        assert compute_config_hash("s", "v", {"p": 1}) != foreign_hash
        with pytest.raises(AttributionError):
            AttributionContext.from_config(bare)

    def test_mismatch_of_any_field_is_detected(self):
        # несовпадение ЛЮБОГО из strategy_id/strategy_version/params/
        # config_hash обнаруживается исходным алгоритмом
        real_hash = compute_config_hash("s", "v", {"p": 1})
        bare = object.__new__(StrategyConfig)
        object.__setattr__(bare, "strategy_id", "OTHER")  # чужой strategy_id
        object.__setattr__(bare, "strategy_version", "v")
        object.__setattr__(bare, "params", {"p": 1})
        object.__setattr__(bare, "config_hash", real_hash)
        object.__setattr__(bare, "origin", "engine")
        object.__setattr__(bare, "metadata", {})
        with pytest.raises(AttributionError):
            AttributionContext.from_config(bare)


# ---------------------------------------------------------------------------
# Тесты 8–12: Enum-значения параметров (дефект №3)
# ---------------------------------------------------------------------------

class Mode(str, Enum):
    """str-миксин Enum (как в существующих параметрах)."""
    ON = "on"
    OFF = "off"


class PlainStringEnum(Enum):
    """Обычный Enum со строковым значением."""
    A = "a"


class PlainIntEnum(Enum):
    """Обычный Enum с числовым значением."""
    N = 7


class _EnumWithList(Enum):
    L = [1, 2]


class _EnumWithDict(Enum):
    D = {"k": 1}


class _EnumWithSet(Enum):
    S = {1, 2}


class _EnumWithBytearray(Enum):
    B = bytearray(b"ab")


class _InnerEnum(Enum):
    I = {"deep": 1}


class _OuterEnum(Enum):
    O = _InnerEnum.I


class TestSafeEnumsStillWork:
    def test_str_mixin_enum_works(self):
        # тест 8: Enum со строковым value работает
        params = {"e": Mode.ON, "i": 7}
        config = _plain_config("s", "v", params)
        assert config.recompute_config_hash() == config.config_hash
        ctx = AttributionContext.from_config(config)
        assert ctx.config_hash == config.config_hash
        # хеш детерминирован
        again = _plain_config("s", "v", {"e": Mode.OFF, "i": 7})
        assert again.config_hash != config.config_hash

    def test_plain_string_enum_works(self):
        params = {"e": PlainStringEnum.A, "i": 7}
        config = _plain_config("s", "v", params)
        assert config.recompute_config_hash() == config.config_hash
        # JSON round-trip: Enum нормализуется к своему значению
        restored = json.loads(json.dumps(config.as_dict()))
        config2 = StrategyConfig(
            strategy_id="s", strategy_version="v",
            params=restored["params"],
            config_hash=restored["config_hash"])
        assert config2.config_hash == config.config_hash

    def test_plain_int_enum_works(self):
        # тест 9: Enum с числовым value работает
        params = {"e": PlainIntEnum.N, "i": 7}
        config = _plain_config("s", "v", params)
        assert config.recompute_config_hash() == config.config_hash
        ctx = AttributionContext.from_config(config)
        assert ctx.config_hash == config.config_hash
        stamped = stamp({"x": 1}, ctx)
        assert stamped["config_hash"] == config.config_hash

    def test_safe_enum_config_creation_not_broken(self):
        # полный путь: Strategy -> get_config -> context -> factory
        class _EnumStrategy(Strategy):
            strategy_id = "enum_engine"
            strategy_version = "1.0"

            def param_specs(self):
                return (ParamSpec("mode", ParamType.STRING),)

            def evaluate_entry(self, signal_input, config):
                raise NotImplementedError

        config = _EnumStrategy().get_config({"mode": "on"})
        ctx = AttributionContext.from_config(config)
        factory = AttributionFactory(ctx)
        assert factory.new_event({"e": 1})["strategy_id"] == "enum_engine"


class TestMutableEnumValuesRejected:
    def test_list_valued_enum_rejected(self):
        # тест 10: Enum со значением list отклоняется при создании
        with pytest.raises(StrategyConfigError):
            _plain_config("s", "v", {"e": _EnumWithList.L})
        # изменяемое значение МОЖЕТ быть изменено после вычисления хеша:
        # именно так раньше обходилась неизменяемость конфигурации
        # (member.value указывает на тот же список)
        _EnumWithList.L.value.append(3)
        assert _EnumWithList.L.value == [1, 2, 3]

    def test_dict_valued_enum_rejected(self):
        # тест 11: Enum со значением dict отклоняется при создании
        with pytest.raises(StrategyConfigError):
            _plain_config("s", "v", {"e": _EnumWithDict.D})
        with pytest.raises(StrategyConfigError):
            _plain_config("s", "v", {"e": _EnumWithBytearray.B})

    def test_set_valued_enum_rejected(self):
        with pytest.raises(StrategyConfigError):
            _plain_config("s", "v", {"e": _EnumWithSet.S})

    def test_nested_mutable_enum_value_rejected(self):
        # тест 12: вложенное изменяемое значение (Enum -> Enum -> dict)
        with pytest.raises(StrategyConfigError):
            _plain_config("s", "v", {"e": _OuterEnum.O})

    def test_mutable_enum_rejected_in_frozen_structure(self):
        # defense-in-depth deep_freeze: замороженная структура не должна
        # содержать Enum с изменяемым значением
        with pytest.raises(StrategyConfigError):
            deep_freeze({"e": _EnumWithDict.D})
        with pytest.raises(StrategyConfigError):
            deep_freeze([_EnumWithList.L])
        # безопасный Enum проходит
        assert deep_freeze(Mode.ON) is Mode.ON

    def test_error_message_explains_fail_closed(self):
        with pytest.raises(StrategyConfigError) as exc:
            _plain_config("s", "v", {"e": _EnumWithList.L})
        message = str(exc.value)
        assert "Enum.value" in message
        assert "неизменяемым скаляром" in message

    def test_unsafe_enum_object_is_not_stored_anywhere(self):
        # частично валидного объекта не существует: создание отклонено
        with pytest.raises(StrategyConfigError):
            _plain_config("s", "v", {"e": _EnumWithDict.D})


# ---------------------------------------------------------------------------
# Тест 13: прямой compute_config_hash отклоняет небезопасные Enum
# ---------------------------------------------------------------------------

class TestDirectComputeHashRejectsUnsafeEnums:
    def test_direct_compute_rejects_list_valued_enum(self):
        with pytest.raises(StrategyConfigError):
            compute_config_hash("s", "v", {"e": _EnumWithList.L})

    def test_direct_compute_rejects_dict_valued_enum(self):
        with pytest.raises(StrategyConfigError):
            compute_config_hash("s", "v", {"e": _EnumWithDict.D})

    def test_direct_compute_rejects_nested_mutable_enum(self):
        with pytest.raises(StrategyConfigError):
            compute_config_hash("s", "v", {"e": _OuterEnum.O})

    def test_direct_compute_rejects_unsafe_enum_deep_inside(self):
        with pytest.raises(StrategyConfigError):
            compute_config_hash("s", "v", {"outer": [{"e": _EnumWithSet.S}]})

    def test_direct_compute_accepts_safe_enums(self):
        h1 = compute_config_hash("s", "v", {"e": Mode.ON})
        h2 = compute_config_hash("s", "v", {"e": PlainStringEnum.A})
        h3 = compute_config_hash("s", "v", {"e": PlainIntEnum.N})
        assert len(h1) == 64 and len(h2) == 64 and len(h3) == 64

    def test_canonical_payload_rejects_unsafe_enum(self):
        from strategy_api import canonical_config_payload
        with pytest.raises(StrategyConfigError):
            canonical_config_payload("s", "v", {"e": _EnumWithDict.D})

    def test_format_validation_still_applies(self):
        # формат хеша при этом по-прежнему проверяется
        assert validate_config_hash_format("a" * 64) == "a" * 64
        with pytest.raises(StrategyConfigError):
            validate_config_hash_format("A" * 64)  # верхний регистр
        with pytest.raises(StrategyConfigError):
            validate_config_hash_format("a" * 63)  # короткий


# ---------------------------------------------------------------------------
# Тест 14: все корректные существующие конфигурации сохраняют прежние хеши
# ---------------------------------------------------------------------------

# ЭТАЛОННЫЕ ЗНАЧЕНИЯ ВЫЧИСЛЕНЫ КОДОМ STAGE A.2 ДО ИЗМЕНЕНИЙ A.2.1
# (из поставленного пакета Samsung_V4_STAGE_A_2.zip, strategy_api.py,
# compute_config_hash). Stage A.2.1 не имеет права их сдвинуть:
# рекурсивная проверка Enum добавляет ТОЛЬКО отклонение опасных значений,
# не меняя нормализацию безопасных (обычный Enum -> .value, str-миксин —
# как str, множества -> отсортированный список).
STAGE_A_2_REFERENCE_HASHES = {
    ("plain", "s", "v"): (
        {"a": 1, "nested": {"b": [1, 2, 3]}, "flag": True},
        "d1b0ab5406446fd4e4e3904f59e6c3bac785a6d8ebfa123e12a163a66c66e876"),
    ("a2_json_types", "s", "v"): (
        {"i": 7, "f": 1.5, "s": "x", "b": False, "n": None,
         "lst": [1, "a"], "d": {"k": 1}, "st": {1, 2}, "tup": (3, 4)},
        "b4a5dae0b78eeb97f095a330ec24d1ecefe2f03b9b7a562803daa6053f76f2ee"),
    ("str_mixin_enum", "s", "v"): (
        {"e": Mode.ON, "i": 7},
        "623f103028223c2f7a19bc00676ad4e99992508762e8f6a0b4b1b4cf8af71b4c"),
    ("plain_str_enum", "s", "v"): (
        {"e": PlainStringEnum.A, "i": 7},
        "83400db068ed65e9a72c08486905542770bfb3b7086abdcd70bc32bfbac70125"),
    ("int_enum", "s", "v"): (
        {"e": PlainIntEnum.N, "i": 7},
        "dd054f67b444851a6cc0ff80a90d4590fdb358474976225312e6b6791ad7cf8a"),
    ("mixed_enum_struct", "legacy_samsung_v4", "4.0"): (
        {"e": PlainStringEnum.A, "lst": [{"k": PlainStringEnum.A}],
         "t": (Mode.ON,)},
        "d463414d51f4ea7f32695d13329840f86d38ad838c8505494db0b5073c488f62"),
    ("alpha", "alpha_engine", "1.0"): (
        {"p_int": 1},
        "1a7f4580fcbb65d5daa1b32743545d36d1bbbcf6d8b9336fa68d510f70868ee1"),
    ("beta", "beta_engine", "2.0"): (
        {"p_int": 2},
        "c0d159f60667161167871ed20ea41b0bc38d8803c72e2cf7a4101f100ba39283"),
}


class TestExistingHashesPreserved:
    @pytest.mark.parametrize(
        "name,sid,sver",
        [(name, sid, sver)
         for (name, sid, sver) in STAGE_A_2_REFERENCE_HASHES])
    def test_hashes_identical_to_stage_a2(self, name, sid, sver):
        params, expected = STAGE_A_2_REFERENCE_HASHES[(name, sid, sver)]
        assert compute_config_hash(sid, sver, params) == expected

    def test_reference_configs_still_created_and_attributed(self):
        # конфигурации с прежними хешами создаются и получают контексты
        for (name, sid, sver), (params, expected) in \
                STAGE_A_2_REFERENCE_HASHES.items():
            config = StrategyConfig(
                strategy_id=sid, strategy_version=sver, params=params,
                config_hash=expected)
            assert config.config_hash == expected
            ctx = AttributionContext.from_config(config)
            assert ctx.config_hash == expected
            assert ctx.strategy_id == sid

    def test_legacy_golden_fixture_unchanged(self):
        # golden-фикстура legacy-сигналов не тронута Stage A.2.1 (байт-
        # идентична поставленной в Stage A.2: SHA256 файла из пакета
        # Samsung_V4_STAGE_A_2.zip); перегенерация ради PASS запрещена
        fixture_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "fixtures", "legacy_golden_signals.json")
        with open(fixture_path, "rb") as handle:
            data = handle.read()
        assert hashlib.sha256(data).hexdigest() == \
            "bce8c9528fd91d6d597ed145d5a8a0822b6bae61ec3005ef2a5012a87641fab5"


# ---------------------------------------------------------------------------
# Тест 15: AttributionContext и AttributionFactory остаются неизменяемыми
# ---------------------------------------------------------------------------

class TestContextAndFactoryImmutability:
    def test_context_attribute_assignment_rejected(self):
        ctx = _verified_context()
        with pytest.raises(Exception):
            ctx.strategy_id = "evil"
        with pytest.raises(Exception):
            ctx.config_hash = "b" * 64
        with pytest.raises(Exception):
            del ctx.strategy_id

    def test_dataclasses_replace_rejected(self):
        ctx = _verified_context()
        with pytest.raises(Exception):
            dataclasses.replace(ctx, strategy_id="evil")
        with pytest.raises(Exception):
            dataclasses.replace(ctx, config_hash="b" * 64)
        # контекст не изменился
        assert ctx.strategy_id == "alpha_engine"

    def test_factory_is_immutable(self):
        ctx = _verified_context()
        factory = AttributionFactory(ctx)
        with pytest.raises(TypeError):
            factory._context = AttributionContext.from_config(
                _config_for(_StrategyBeta, 2))
        # контекст фабрики не заменён
        assert factory.context == ctx

    def test_deepcopy_preserves_verified_context(self):
        ctx = _verified_context()
        clone = copy.deepcopy(ctx)
        assert clone == ctx
        stamped = stamp({"x": 1}, clone)
        assert stamped["config_hash"] == ctx.config_hash

    def test_pickle_preserves_verified_context(self):
        ctx = _verified_context()
        restored = pickle.loads(pickle.dumps(ctx))
        assert restored == ctx
        stamped = stamp({"x": 1}, restored)
        assert stamped["config_hash"] == ctx.config_hash

    def test_context_equality_and_hash_semantics(self):
        config = _config_for(_StrategyAlpha, 1)
        ctx1 = AttributionContext.from_config(config)
        ctx2 = AttributionContext.from_config(config)
        other = AttributionContext.from_config(_config_for(_StrategyBeta, 2))
        assert ctx1 == ctx2 and hash(ctx1) == hash(ctx2)
        assert ctx1 != other
        assert len({ctx1, ctx2, other}) == 2


# ---------------------------------------------------------------------------
# Тест 16: параллельная работа нескольких стратегий сохраняет правильную
# атрибуцию
# ---------------------------------------------------------------------------

class TestParallelAttribution:
    def test_two_strategies_parallel_stamping(self):
        ctx_a = AttributionContext.from_config(_config_for(_StrategyAlpha, 1))
        ctx_b = AttributionContext.from_config(_config_for(_StrategyBeta, 2))
        factory_a = AttributionFactory(ctx_a)
        factory_b = AttributionFactory(ctx_b)
        results = {"alpha": [], "beta": []}
        errors: list = []

        def work(name, factory):
            try:
                for i in range(60):
                    results[name].append(
                        factory.new_event({"i": i, "thread": name}))
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)

        threads = [threading.Thread(target=work, args=("alpha", factory_a)),
                   threading.Thread(target=work, args=("beta", factory_b))]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert not errors
        assert len(results["alpha"]) == 60
        assert len(results["beta"]) == 60
        assert all(r["strategy_id"] == "alpha_engine"
                   and r["config_hash"] == ctx_a.config_hash
                   for r in results["alpha"])
        assert all(r["strategy_id"] == "beta_engine"
                   and r["config_hash"] == ctx_b.config_hash
                   for r in results["beta"])
        # фабрики не перепутались
        assert factory_a.context == ctx_a
        assert factory_b.context == ctx_b

    def test_parallel_jsonl_writers_isolated(self, tmp_path):
        ctx_a = AttributionContext.from_config(_config_for(_StrategyAlpha, 1))
        ctx_b = AttributionContext.from_config(_config_for(_StrategyBeta, 2))
        factory_a = AttributionFactory(ctx_a)
        factory_b = AttributionFactory(ctx_b)
        path_a = str(tmp_path / "alpha.jsonl")
        path_b = str(tmp_path / "beta.jsonl")
        errors: list = []

        def work(factory, path):
            try:
                for i in range(25):
                    factory.append_jsonl_row(path, {"i": i})
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)

        threads = [threading.Thread(target=work, args=(factory_a, path_a)),
                   threading.Thread(target=work, args=(factory_b, path_b))]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert not errors
        rows_a = read_jsonl_attribution_report(path_a)
        rows_b = read_jsonl_attribution_report(path_b)
        assert len(rows_a) == 25 and len(rows_b) == 25
        assert all(r["config_hash"] == ctx_a.config_hash for r in rows_a)
        assert all(r["config_hash"] == ctx_b.config_hash for r in rows_b)
        # перекрёстное загрязнение отсутствует
        assert not any(r["config_hash"] == ctx_b.config_hash
                       for r in rows_a)
        assert not any(r["config_hash"] == ctx_a.config_hash
                       for r in rows_b)


# ---------------------------------------------------------------------------
# Сериализация, JSON round-trip и обратная совместимость
# ---------------------------------------------------------------------------

class TestSerializationRoundTripAndCompatibility:
    def test_config_with_enum_round_trip(self):
        params = {"e": PlainStringEnum.A, "n": PlainIntEnum.N,
                  "mode": Mode.ON, "lst": [1, 2]}
        config = _plain_config("s", "v", params)
        as_dict = config.as_dict()
        # JSON-совместимость: Enum приведён к своим значениям
        text = json.dumps(as_dict, ensure_ascii=False)
        restored = json.loads(text)
        config2 = StrategyConfig(
            strategy_id=restored["strategy_id"],
            strategy_version=restored["strategy_version"],
            params=restored["params"],
            config_hash=restored["config_hash"],
            origin=restored["origin"],
            metadata=restored["metadata"])
        assert config2.config_hash == config.config_hash
        ctx1 = AttributionContext.from_config(config)
        ctx2 = AttributionContext.from_config(config2)
        assert ctx1 == ctx2

    def test_stamped_record_json_round_trip(self):
        config = _plain_config("s", "v", {"e": PlainStringEnum.A})
        ctx = AttributionContext.from_config(config)
        payload = stamp({"event": "SIGNAL", "figi": "F"}, ctx)
        text = json.dumps(payload, ensure_ascii=False)
        restored = json.loads(text)
        assert restored["strategy_id"] == ctx.strategy_id
        assert restored["config_hash"] == ctx.config_hash

    def test_jsonl_round_trip_with_enum_config(self, tmp_path):
        config = _plain_config("s", "v", {"e": PlainIntEnum.N})
        ctx = AttributionContext.from_config(config)
        path = str(tmp_path / "events.jsonl")
        append_attributed_jsonl_row(path, {"event": "TEST"}, context=ctx)
        restored = json.loads(open(path, encoding="utf-8").read())
        assert restored["config_hash"] == ctx.config_hash
        assert restored["strategy_id"] == ctx.strategy_id

    def test_engine_config_path_still_works(self, tmp_path):
        # обратная совместимость: путь engine_config -> from_config
        from engine_config import (
            EngineStatus,
            load_engine_config,
        )
        engine_json = tmp_path / "engine.json"
        engine_json.write_text(
            json.dumps({"ACTIVE_STRATEGY": None}), encoding="utf-8")
        cfg = load_engine_config(engine_json_path=str(engine_json),
                                 environ={})
        assert cfg.status is EngineStatus.UNCONFIGURED
        assert cfg.attribution is None

    def test_no_global_context_state_returned(self):
        # обратная совместимость Stage A.1: глобального состояния нет
        import attribution as at
        for name in ("set_current_context", "get_current_context",
                     "clear_current_context", "_current_context"):
            assert not hasattr(at, name)

    def test_stage_a2_api_unchanged(self):
        # публичный API Stage A.2 доступен как прежде
        import attribution as at
        import strategy_api as sa
        for name in ("AttributionContext", "AttributionFactory",
                     "AttributionError", "AttributionRequiredError",
                     "stamp", "append_attributed_csv_row",
                     "append_attributed_jsonl_row"):
            assert hasattr(at, name)
        for name in ("StrategyConfig", "StrategyConfigError",
                     "compute_config_hash", "validate_config_hash_format",
                     "recompute_config_hash"):
            assert hasattr(sa.StrategyConfig, name) or hasattr(sa, name)
