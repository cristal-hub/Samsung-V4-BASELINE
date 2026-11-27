# tests/test_stage_a1_config_immutability.py
# STAGE A.1 CORRECTIVE TESTS — ЗАМЕЧАНИЕ №1 НЕЗАВИСИМОГО АУДИТА:
# «StrategyConfig действительно immutable, включая вложенные структуры».
#
# Обязательные проверки (по заданию Stage A.1):
#   1. попытка изменить верхнеуровневый params;
#   2. попытка изменить вложенный словарь;
#   3. попытка изменить вложенный список;
#   4. попытка изменить metadata;
#   5. изменение исходного словаря после создания StrategyConfig;
#   6. попытка изменить config_hash;
#   7. одинаковая конфигурация после сериализации даёт одинаковый hash;
#   8. изменение значимого параметра создаёт новый hash;
#   9. round-trip сериализация не меняет семантику параметров.
#
# Плюс: защита внутреннего хранилища, hash-совместимость, deepcopy,
# консистентность config_hash с фактически сохранёнными параметрами,
# совместимость с существующими потребителями (Strategy.get_config,
# engine_config, legacy adapter).
#
# Тесты проверяют РЕАЛЬНОЕ поведение, а не только наличие frozen=True.
# Offline; без сети, брокера и заявок.

import copy
import json

import pytest
from dataclasses import FrozenInstanceError

import strategy_api
from strategy_api import (
    ImmutableMapping,
    ImmutableList,
    ParamSpec,
    ParamType,
    Strategy,
    StrategyConfig,
    StrategyConfigError,
    compute_config_hash,
)


# ---------------------------------------------------------------------------
# Фикстуры
# ---------------------------------------------------------------------------

_SPECS = (
    ParamSpec("int_p", ParamType.INT, minimum=1),
    ParamSpec("num_p", ParamType.FLOAT, minimum=0.0),
)


class _DummyStrategy(Strategy):
    strategy_id = "immutability_dummy"
    strategy_version = "1.0"

    def param_specs(self):
        return _SPECS

    def evaluate_entry(self, signal_input, config):
        return strategy_api.Signal(
            strategy_id=self.strategy_id,
            config_hash=config.config_hash,
            direction=strategy_api.SignalDirection.HOLD,
            reason="dummy",
        )


def _make_config(params=None, metadata=None) -> StrategyConfig:
    strategy = _DummyStrategy()
    base = {"int_p": 5, "num_p": 2.5}
    if params is not None:
        base = params
    config = strategy.get_config(base)
    if metadata is not None:
        # пересборка с metadata через прямой конструктор (валидные поля)
        return StrategyConfig(
            strategy_id=config.strategy_id,
            strategy_version=config.strategy_version,
            params=config.params,
            config_hash=config.config_hash,
            origin=config.origin,
            metadata=metadata,
        )
    return config


def _direct_config(params, metadata=None) -> StrategyConfig:
    """Конфигурация с произвольными (в т.ч. несхемными) ключами.

    Мини-стратегия валидирует ТОЛЬКО int_p/num_p, поэтому ключи вне схемы
    (например, 'extra') вводятся прямым конструктором — как и делает
    Strategy.get_config после нормализации параметров.
    """
    params = dict(params)
    return StrategyConfig(
        strategy_id=_DummyStrategy.strategy_id,
        strategy_version=_DummyStrategy.strategy_version,
        params=params,
        config_hash=compute_config_hash(
            _DummyStrategy.strategy_id,
            _DummyStrategy.strategy_version, params),
        origin="engine",
        metadata=dict(metadata or {}),
    )


def _nested_config() -> StrategyConfig:
    """Конфигурация с вложенными словарями, списками и множествами."""
    return StrategyConfig(
        strategy_id="nested_demo",
        strategy_version="1.0",
        params={
            "rsi": {"thresholds": {"upper": 70, "lower": 30}},
            "ma_window": [5, 13, [21, 34]],
            "levels": {1.0, 2.0},
        },
        config_hash="e" * 64,
    )


# ---------------------------------------------------------------------------
# Требование 1: попытка изменить верхнеуровневый params
# ---------------------------------------------------------------------------

class TestTopLevelImmutability:
    def test_params_field_assignment_blocked(self):
        config = _make_config()
        with pytest.raises(FrozenInstanceError):
            config.params = {"int_p": 99, "num_p": 1.0}

    def test_params_item_assignment_blocked(self):
        config = _make_config()
        with pytest.raises(TypeError):
            config.params["int_p"] = 99

    def test_params_item_deletion_blocked(self):
        config = _make_config()
        with pytest.raises(TypeError):
            del config.params["int_p"]

    def test_params_is_immutable_mapping(self):
        config = _make_config()
        assert isinstance(config.params, ImmutableMapping)
        # у типа не существует операций записи вообще (Mapping ABC:
        # только чтение; setdefault/pop/update/__setitem__ отсутствуют)
        assert not hasattr(config.params, "setdefault")
        assert not hasattr(config.params, "pop")
        assert not hasattr(config.params, "update")
        assert not hasattr(type(config.params), "__setitem__")
        assert not hasattr(type(config.params), "__delitem__")
        # setattr на объекте отображения запрещён
        with pytest.raises(TypeError):
            config.params.__setattr__("_data", {})

    def test_identity_fields_assignment_blocked(self):
        config = _make_config()
        with pytest.raises(FrozenInstanceError):
            config.strategy_id = "other"
        with pytest.raises(FrozenInstanceError):
            config.strategy_version = "9.9"
        with pytest.raises(FrozenInstanceError):
            config.origin = "regression_harness"


# ---------------------------------------------------------------------------
# Требование 2: попытка изменить вложенный словарь
# ---------------------------------------------------------------------------

class TestNestedDictImmutability:
    def test_nested_dict_item_assignment_blocked(self):
        config = _nested_config()
        with pytest.raises(TypeError):
            config.params["rsi"]["thresholds"]["upper"] = 99

    def test_deeply_nested_dict_item_assignment_blocked(self):
        config = _nested_config()
        with pytest.raises(TypeError):
            config.params["rsi"]["thresholds"]["new_key"] = 1

    def test_nested_dict_deletion_blocked(self):
        config = _nested_config()
        with pytest.raises(TypeError):
            del config.params["rsi"]["thresholds"]["upper"]

    def test_nested_dict_value_is_immutable_mapping(self):
        config = _nested_config()
        assert isinstance(config.params["rsi"], ImmutableMapping)
        assert isinstance(config.params["rsi"]["thresholds"], ImmutableMapping)

    def test_backing_store_write_blocked(self):
        # даже запись через приватное хранилище отклоняется (MappingProxyType)
        config = _nested_config()
        with pytest.raises(TypeError):
            config.params._data["injected"] = True
        assert "injected" not in config.params


# ---------------------------------------------------------------------------
# Требование 3: попытка изменить вложенный список
# ---------------------------------------------------------------------------

class TestNestedListImmutability:
    def test_nested_list_item_assignment_blocked(self):
        config = _nested_config()
        with pytest.raises(TypeError):
            config.params["ma_window"][0] = 99

    def test_nested_list_append_blocked(self):
        config = _nested_config()
        with pytest.raises(AttributeError):
            config.params["ma_window"].append(55)

    def test_inner_list_mutation_blocked(self):
        config = _nested_config()
        inner = config.params["ma_window"][2]
        with pytest.raises(TypeError):
            inner[0] = 99
        with pytest.raises(AttributeError):
            inner.append(55)

    def test_nested_list_is_immutable_list(self):
        config = _nested_config()
        assert isinstance(config.params["ma_window"], ImmutableList)

    def test_nested_set_is_frozenset(self):
        config = _nested_config()
        assert isinstance(config.params["levels"], frozenset)
        with pytest.raises(AttributeError):
            config.params["levels"].add(3.0)


# ---------------------------------------------------------------------------
# Требование 4: попытка изменить metadata
# ---------------------------------------------------------------------------

class TestMetadataImmutability:
    def test_metadata_field_assignment_blocked(self):
        config = _make_config(metadata={"profile": "SANDBOX_TEST"})
        with pytest.raises(FrozenInstanceError):
            config.metadata = {"profile": "OTHER"}

    def test_metadata_item_assignment_blocked(self):
        config = _make_config(metadata={"profile": "SANDBOX_TEST"})
        with pytest.raises(TypeError):
            config.metadata["profile"] = "OTHER"

    def test_metadata_nested_dict_blocked(self):
        config = _make_config(
            metadata={"source": {"file": "params.json", "rows": [1, 2]}})
        with pytest.raises(TypeError):
            config.metadata["source"]["file"] = "hacked.json"
        with pytest.raises(AttributeError):
            config.metadata["source"]["rows"].append(3)

    def test_metadata_non_mapping_rejected(self):
        with pytest.raises(StrategyConfigError):
            StrategyConfig(
                strategy_id="s", strategy_version="v",
                params={"a": 1}, config_hash="c" * 64, metadata="not-a-map")


# ---------------------------------------------------------------------------
# Требование 5: изменение исходного словаря после создания StrategyConfig
# ---------------------------------------------------------------------------

class TestSourceIsolation:
    def test_source_dict_mutation_after_creation_isolated(self):
        source = {"int_p": 5, "num_p": 2.5,
                  "extra": {"nested": [1, 2, {"deep": "v"}]}}
        config = _direct_config(source)
        before_hash = config.config_hash
        source["int_p"] = 999
        source["extra"]["nested"][2]["deep"] = "hacked"
        source["extra"]["nested"].append(4)
        assert config.params["int_p"] == 5
        assert config.params["extra"]["nested"][2]["deep"] == "v"
        assert len(config.params["extra"]["nested"]) == 3
        assert config.config_hash == before_hash

    def test_source_metadata_mutation_after_creation_isolated(self):
        source_meta = {"profile": "SANDBOX_TEST",
                       "tags": ["a", "b"]}
        config = _make_config(metadata=source_meta)
        source_meta["profile"] = "HACKED"
        source_meta["tags"].append("c")
        assert config.metadata["profile"] == "SANDBOX_TEST"
        assert list(config.metadata["tags"]) == ["a", "b"]

    def test_recomputed_hash_reflects_stored_params_not_source(self):
        source = {"int_p": 5, "num_p": 2.5}
        config = _direct_config(source)
        source["int_p"] = 7  # источник изменён ПОСЛЕ создания
        # config_hash по-прежнему соответствует ФАКТИЧЕСКИ сохранённым
        # параметрам, а не изменённому источнику
        assert config.recompute_config_hash() == config.config_hash


# ---------------------------------------------------------------------------
# Требование 6: попытка изменить config_hash
# ---------------------------------------------------------------------------

class TestConfigHashImmutability:
    def test_config_hash_assignment_blocked(self):
        config = _make_config()
        with pytest.raises(FrozenInstanceError):
            config.config_hash = "f" * 64

    def test_config_hash_not_mutable_via_params(self):
        config = _make_config()
        with pytest.raises(TypeError):
            config.params["int_p"] = 99
        assert config.config_hash == compute_config_hash(
            "immutability_dummy", "1.0", {"int_p": 5, "num_p": 2.5})

    def test_stored_params_match_config_hash(self):
        # config_hash соответствует ФАКТИЧЕСКИ сохранённым параметрам
        config = _make_config()
        assert config.recompute_config_hash() == config.config_hash

    def test_hashable_config_object(self):
        config = _make_config()
        # frozen dataclass: hash(config) требует хешируемость всех полей
        assert hash(config) == hash(_make_config())


# ---------------------------------------------------------------------------
# Требование 7: одинаковая конфигурация после сериализации -> одинаковый hash
# ---------------------------------------------------------------------------

class TestSerializationHashStability:
    def test_same_config_after_json_roundtrip_same_hash(self):
        strategy = _DummyStrategy()
        params = {"int_p": 7, "num_p": 3.5}
        config = strategy.get_config(params)
        payload = json.dumps(config.as_dict(), ensure_ascii=False)
        restored = json.loads(payload)
        config2 = strategy.get_config(restored["params"])
        assert config2.config_hash == config.config_hash
        assert config2 == config

    def test_hash_independent_of_json_key_order(self):
        config = _make_config()
        payload_a = json.dumps(config.as_dict(), sort_keys=True)
        payload_b = json.dumps(
            dict(reversed(list(config.as_dict().items()))), sort_keys=True)
        assert payload_a == payload_b
        assert json.loads(payload_a)["params"] == json.loads(payload_b)["params"]

    def test_nested_structures_survive_serialization(self):
        config = _nested_config()
        payload = json.dumps(config.as_dict(), ensure_ascii=False)
        restored = json.loads(payload)
        assert restored["params"]["rsi"]["thresholds"]["upper"] == 70
        assert restored["params"]["ma_window"][2] == [21, 34]
        # множество -> отсортированный список (документированная нормализация,
        # совпадающая с нормализацией config_hash)
        assert restored["params"]["levels"] == [1.0, 2.0]


# ---------------------------------------------------------------------------
# Требование 8: изменение значимого параметра -> новый hash
# ---------------------------------------------------------------------------

class TestHashSensitivity:
    def test_meaningful_param_change_creates_new_hash(self):
        strategy = _DummyStrategy()
        h1 = strategy.get_config({"int_p": 5, "num_p": 2.5}).config_hash
        h2 = strategy.get_config({"int_p": 6, "num_p": 2.5}).config_hash
        h3 = strategy.get_config({"int_p": 5, "num_p": 2.6}).config_hash
        assert len({h1, h2, h3}) == 3

    def test_nested_param_change_creates_new_hash(self):
        params_a = {"int_p": 5, "num_p": 2.5}
        params_b = {"int_p": 5, "num_p": 2.5, "extra": {"k": [1, 2]}}
        params_c = {"int_p": 5, "num_p": 2.5, "extra": {"k": [1, 3]}}
        h_a = compute_config_hash("s", "v", params_a)
        h_b = compute_config_hash("s", "v", params_b)
        h_c = compute_config_hash("s", "v", params_c)
        assert h_a != h_b
        assert h_b != h_c

    def test_metadata_change_does_not_silently_keep_hash_claim(self):
        # metadata НЕ входит в config_hash (задокументировано); при этом
        # конфигурация с той же парой атрибуции остаётся различимой по
        # содержимому metadata
        c1 = _make_config(metadata={"profile": "SANDBOX_TEST"})
        c2 = _make_config(metadata={"profile": "TECH_CHECK"})
        assert c1.config_hash == c2.config_hash
        assert c1.metadata["profile"] != c2.metadata["profile"]


# ---------------------------------------------------------------------------
# Требование 9: round-trip сериализация не меняет семантику параметров
# ---------------------------------------------------------------------------

class TestRoundTripSemantics:
    def test_round_trip_preserves_param_semantics(self):
        config = _nested_config()
        restored = json.loads(json.dumps(config.as_dict(), ensure_ascii=False))
        params = restored["params"]
        # семантическое равенство значений; множество представлено
        # отсортированным списком (документированная JSON-нормализация)
        assert params == {
            "rsi": {"thresholds": {"upper": 70, "lower": 30}},
            "ma_window": [5, 13, [21, 34]],
            "levels": [1.0, 2.0],
        }

    def test_json_roundtrip_preserves_config_hash_even_for_sets(self):
        # множество и его JSON-представление дают ОДИН и тот же config_hash:
        # _normalize_for_json отображает set -> отсортированный список в
        # обоих случаях
        params = {"levels": {1.0, 2.0}, "nested": {"a": [1, 2]}}
        config = StrategyConfig(
            strategy_id="s", strategy_version="v",
            params=params,
            config_hash=compute_config_hash("s", "v", params),
        )
        restored = json.loads(json.dumps(config.as_dict(), ensure_ascii=False))
        config2 = StrategyConfig(
            strategy_id=restored["strategy_id"],
            strategy_version=restored["strategy_version"],
            params=restored["params"],
            config_hash=restored["config_hash"],
            origin=restored["origin"],
            metadata=restored["metadata"],
        )
        # hash, вычисленный по сохранённым параметрам (список после JSON),
        # совпадает с исходным hash (множество до JSON)
        assert config2.recompute_config_hash() == config.config_hash
        assert config2.config_hash == config.config_hash
        # и обе конфигурации внутренне консистентны
        assert config.recompute_config_hash() == config.config_hash
        assert config2.recompute_config_hash() == config2.config_hash

    def test_round_trip_reconstructed_config_is_equal_and_frozen(self):
        # конфигурация без множеств восстанавливается ПОЛНОСТЬЮ равной
        config = _direct_config({"int_p": 5, "num_p": 2.5,
                                 "nested": {"a": [1, 2]}})
        restored = json.loads(json.dumps(config.as_dict(), ensure_ascii=False))
        config2 = StrategyConfig(
            strategy_id=restored["strategy_id"],
            strategy_version=restored["strategy_version"],
            params=restored["params"],
            config_hash=restored["config_hash"],
            origin=restored["origin"],
            metadata=restored["metadata"],
        )
        assert config2 == config
        assert isinstance(config2.params, ImmutableMapping)
        with pytest.raises(TypeError):
            config2.params["nested"]["a"][0] = 9

    def test_as_dict_is_deep_mutable_copy(self):
        config = _nested_config()
        snapshot = config.as_dict()
        snapshot["params"]["rsi"]["thresholds"]["upper"] = 99
        snapshot["params"]["ma_window"].append(99)
        # конфигурация не изменилась
        assert config.params["rsi"]["thresholds"]["upper"] == 70
        assert list(config.params["ma_window"]) == [5, 13, [21, 34]]

    def test_unfreeze_and_deep_freeze_are_inverse_for_json_values(self):
        params = {"a": {"b": [1, 2, {"c": {3}}]}, "d": 1.5}
        frozen = strategy_api.deep_freeze(params)
        assert strategy_api.unfreeze(frozen) == params
        # idempotence
        assert strategy_api.deep_freeze(frozen) is frozen


# ---------------------------------------------------------------------------
# Служебные гарантии ImmutableMapping/ImmutableList
# ---------------------------------------------------------------------------

class TestImmutableStructures:
    def test_immutable_mapping_eq_dict_and_hash_consistent(self):
        m = ImmutableMapping({"a": 1, "b": [1, 2]})
        assert m == {"a": 1, "b": [1, 2]}
        assert {"a": 1, "b": [1, 2]} == m
        assert hash(ImmutableMapping({"a": 1})) == \
            hash(ImmutableMapping({"a": 1}))

    def test_immutable_mapping_non_string_keys_rejected(self):
        with pytest.raises(StrategyConfigError):
            ImmutableMapping({1: "x"})

    def test_immutable_list_eq_list_and_hash_consistent_with_tuple(self):
        lst = ImmutableList([1, 2, 3])
        assert lst == [1, 2, 3]
        assert lst == (1, 2, 3)
        assert hash(lst) == hash((1, 2, 3))

    def test_immutable_list_slice_returns_immutable_list(self):
        lst = ImmutableList([1, 2, 3, 4])
        assert isinstance(lst[1:3], ImmutableList)
        assert lst[1:3] == [2, 3]

    def test_deepcopy_and_reduce_keep_freeze(self):
        config = _nested_config()
        clone = copy.deepcopy(config)
        assert clone == config
        with pytest.raises(TypeError):
            clone.params["rsi"]["thresholds"]["lower"] = 0
        with pytest.raises(AttributeError):
            clone.params["ma_window"].append(0)

    def test_copy_of_frozen_structures_shares_content(self):
        # неизменяемый объект может безопасно разделять содержимое
        m = ImmutableMapping({"a": [1, 2]})
        assert copy.copy(m) == m
        assert copy.deepcopy(m) == m


# ---------------------------------------------------------------------------
# Совместимость с существующими потребителями конфигурации
# ---------------------------------------------------------------------------

class TestConsumersCompatibility:
    def test_strategy_get_config_still_works(self):
        strategy = _DummyStrategy()
        config = strategy.get_config({"int_p": 3, "num_p": 1.0})
        assert config.params == {"int_p": 3, "num_p": 1.0}
        assert config.recompute_config_hash() == config.config_hash

    def test_signal_metadata_frozen(self):
        strategy = _DummyStrategy()
        config = strategy.get_config({"int_p": 3, "num_p": 1.0})
        signal = strategy.evaluate_entry(
            strategy_api.EntrySignalInput(
                figi="F", ticker="T", candles=None, last_price=1.0,
                extra={"note": "x"}),
            config)
        assert isinstance(signal.metadata, ImmutableMapping)
        with pytest.raises(TypeError):
            signal.metadata["k"] = "v"

    def test_entry_signal_input_extra_frozen(self):
        entry = strategy_api.EntrySignalInput(
            figi="F", ticker="T", candles=None, last_price=1.0,
            extra={"note": [1, 2]})
        assert isinstance(entry.extra, ImmutableMapping)
        with pytest.raises(TypeError):
            entry.extra["note2"] = "v"
        with pytest.raises(AttributeError):
            entry.extra["note"].append(3)

    def test_engine_config_load_path_unaffected(self, tmp_path):
        from engine_config import EngineStatus, load_engine_config
        p = tmp_path / "engine.json"
        p.write_text(json.dumps({"ACTIVE_STRATEGY": None}),
                     encoding="utf-8")
        cfg = load_engine_config(engine_json_path=str(p), environ={})
        assert cfg.status is EngineStatus.UNCONFIGURED

    def test_legacy_adapter_params_still_usable(self):
        # ImmutableMapping предоставляет items()/get()/[] для моста
        # к baseline (_override_legacy_config использует params.items())
        from strategies.legacy_samsung_v4.profiles import \
            build_regression_params
        from strategies.legacy_samsung_v4.strategy import \
            LegacySamsungV4Strategy
        adapter = LegacySamsungV4Strategy()
        config = adapter.build_regression_config("SANDBOX_TEST")
        assert dict(config.params.items()) == \
            dict(build_regression_params("SANDBOX_TEST"))
        assert config.metadata.get("profile") == "SANDBOX_TEST"
        assert config.recompute_config_hash() == config.config_hash
