# tests/test_stage_b_state_isolation.py — SAMSUNG V4 — STAGE B (+ B.1).
#
# Изолированное состояние стратегии по ключу (strategy_id, FIGI).
# Обязательные сценарии ТЗ Stage B §4 (1–16) + граничные случаи и
# гонки конкурентного доступа. Все тесты offline, без сети и брокера;
# никаких реальных заявок; старые файлы Samsung не затрагиваются.
#
# Соответствие сценариев ТЗ §4 — заголовки блоков тестов помечены
# «ТЗ §4.N».
#
# Stage B.1: имя файла записи строится только инъективным длинно-
# префиксным кодированием (ss.encode_state_filename, помощник fname
# ниже); семантика всех проверок сохранена. Дополнительные тесты
# Stage B.1 (коллизии имён, проверка ключа после чтения, атомарный
# read-modify-write нескольких менеджеров) — в отдельном файле
# tests/test_stage_b1_state_key_and_concurrency.py.

import json
import os
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

import strategy_state as ss
from attribution import AttributionContext
from strategy_api import (
    ActivationMode,
    StrategyConfig,
    compute_config_hash,
)


# ---------------------------------------------------------------------------
# Фикстуры и помощники
# ---------------------------------------------------------------------------

HASH_A = "a" * 64
HASH_B = "b" * 64
HASH_C = "c" * 64
STAMP_T1 = "2026-01-01T10:00:00.000000Z"
STAMP_T2 = "2026-01-02T11:00:00.000000Z"


def make_config(strategy_id="s_a", params=None, version="v1"):
    """Валидная StrategyConfig с корректным config_hash (Stage A контракт)."""
    params = params or {"length": 14}
    return StrategyConfig(
        strategy_id=strategy_id,
        strategy_version=version,
        params=params,
        config_hash=compute_config_hash(strategy_id, version, params),
    )


@pytest.fixture
def store_path(tmp_path):
    """Явный путь persistent-хранилища (вне дерева проекта)."""
    return str(tmp_path / "state_store")


@pytest.fixture
def store(store_path):
    return ss.StateStore(path=store_path)


@pytest.fixture
def manager(store):
    return ss.StrategyStateManager(store)


def sha256_of(path):
    import hashlib
    with open(path, "rb") as handle:
        return hashlib.sha256(handle.read()).hexdigest()


def fname(sid, figi):
    """Имя файла записи ПО АЛГОРИТМУ Stage B.1 (инъективное,
    длинно-префиксное кодирование; ТЗ Stage B.1 §3, дефект №1).

    Все проверки файлов в этом файле строят имя ТОЛЬКО этим
    алгоритмом — прежний неинъективный шаблон f"{sid}__{figi}.json"
    заменён заданием Stage B.1.
    """
    return ss.encode_state_filename(sid, figi)


# ---------------------------------------------------------------------------
# ТЗ §4.1 — две стратегии на одном FIGI имеют независимое состояние
# ---------------------------------------------------------------------------


class TestTwoStrategiesSameFigi:
    def test_states_are_independent_objects_and_records(self, manager):
        st_a = manager.get_state("s_a", "FIGI_X", config_hash=HASH_A)
        st_b = manager.get_state("s_b", "FIGI_X", config_hash=HASH_B)
        assert st_a is not st_b
        assert st_a.strategy_id == "s_a" and st_b.strategy_id == "s_b"
        assert st_a.figi == st_b.figi == "FIGI_X"
        assert st_a.config_hash == HASH_A
        assert st_b.config_hash == HASH_B
        assert st_a.data == {} and st_b.data == {}

    def test_update_of_one_does_not_leak_into_other(self, manager):
        manager.get_state("s_a", "FIGI_X", config_hash=HASH_A)
        manager.get_state("s_b", "FIGI_X", config_hash=HASH_B)
        manager.update_state("s_a", "FIGI_X", config_hash=HASH_A,
                             data={"position": "LONG", "streak": 3})
        st_b = manager.get_state("s_b", "FIGI_X", config_hash=HASH_B)
        st_a = manager.get_state("s_a", "FIGI_X", config_hash=HASH_A)
        assert dict(st_b.data) == {}
        assert dict(st_a.data) == {"position": "LONG", "streak": 3}

    def test_persistent_records_are_separate_files(self, store_path):
        store = ss.StateStore(path=store_path)
        mgr = ss.StrategyStateManager(store)
        mgr.get_state("s_a", "FIGI_X", config_hash=HASH_A)
        mgr.get_state("s_b", "FIGI_X", config_hash=HASH_B)
        files = sorted(os.listdir(store_path))
        assert files == [fname("s_a", "FIGI_X"), fname("s_b", "FIGI_X")]


# ---------------------------------------------------------------------------
# ТЗ §4.2 — одна стратегия на двух FIGI имеет независимое состояние
# ---------------------------------------------------------------------------


class TestOneStrategyTwoFigi:
    def test_states_are_independent(self, manager):
        st_x = manager.get_state("s_a", "FIGI_X", config_hash=HASH_A)
        st_y = manager.get_state("s_a", "FIGI_Y", config_hash=HASH_A)
        assert st_x is not st_y
        assert st_x.figi == "FIGI_X" and st_y.figi == "FIGI_Y"
        assert st_x.config_hash == st_y.config_hash == HASH_A

    def test_update_of_one_figi_does_not_leak_into_other(self, manager):
        manager.get_state("s_a", "FIGI_X", config_hash=HASH_A)
        manager.get_state("s_a", "FIGI_Y", config_hash=HASH_A)
        manager.update_state("s_a", "FIGI_X", config_hash=HASH_A,
                             data={"streak": 2})
        assert dict(manager.get_state(
            "s_a", "FIGI_Y", config_hash=HASH_A).data) == {}
        assert dict(manager.get_state(
            "s_a", "FIGI_X", config_hash=HASH_A).data) == {"streak": 2}

    def test_reset_of_one_figi_keeps_other(self, manager):
        store = manager._store
        st_y_before = store.create_state("s_a", "FIGI_Y", HASH_A,
                                         data={"v": "Y"}, now=STAMP_T1)
        manager.get_state("s_a", "FIGI_X", config_hash=HASH_A)
        assert manager.reset_state("s_a", "FIGI_X") is True
        # FIGI_Y не затронут: запись та же, данные на месте.
        st_y_after = store.get_state("s_a", "FIGI_Y", config_hash=HASH_A)
        assert st_y_after == st_y_before
        assert st_y_after.data["v"] == "Y"
        # FIGI_X пересоздаётся как новое независимое состояние.
        st_x = manager.get_state("s_a", "FIGI_X", config_hash=HASH_A)
        assert dict(st_x.data) == {}


# ---------------------------------------------------------------------------
# ТЗ §4.3 — изменение состояния одной пары не изменяет остальные
# ---------------------------------------------------------------------------


class TestChangeOnePairOnly:
    def test_payloads_of_other_pairs_byte_identical(self, manager, store_path):
        pairs = [("s_a", "FIGI_X"), ("s_a", "FIGI_Y"), ("s_b", "FIGI_X")]
        for sid, figi in pairs:
            manager.get_state(sid, figi, config_hash=HASH_A)
        manager.update_state("s_a", "FIGI_X", config_hash=HASH_A,
                             data={"n": 1})

        def payload_of(sid, figi):
            with open(os.path.join(
                    store_path, fname(sid, figi)),
                    "r", encoding="utf-8") as handle:
                return handle.read()

        assert payload_of("s_a", "FIGI_Y") == payload_of("s_a", "FIGI_Y")
        y_before = payload_of("s_a", "FIGI_Y")
        x_before = payload_of("s_b", "FIGI_X")
        manager.update_state("s_a", "FIGI_Y", config_hash=HASH_A,
                             data={"n": 99})
        assert payload_of("s_a", "FIGI_Y") != y_before  # целевая изменилась
        assert payload_of("s_b", "FIGI_X") == x_before  # чужая НЕ изменилась
        st_x = manager.get_state("s_a", "FIGI_X", config_hash=HASH_A)
        assert dict(st_x.data) == {"n": 1}              # и эта тоже

    def test_created_at_of_untouched_pairs_preserved(self, manager):
        # Явные метки времени для проверки сохранности created_at:
        store = manager._store
        store.create_state("s_a", "FIGI_X", HASH_A, now=STAMP_T1)
        store.create_state("s_b", "FIGI_X", HASH_B, now=STAMP_T1)
        manager.update_state("s_a", "FIGI_X", config_hash=HASH_A,
                             data={"n": 1}, now=STAMP_T2)
        st1_after = store.get_state("s_a", "FIGI_X", config_hash=HASH_A)
        st2_after = store.get_state("s_b", "FIGI_X", config_hash=HASH_B)
        # Целевая пара: обновление (created_at сохранён), не пересоздание.
        assert st1_after.created_at == STAMP_T1
        assert st1_after.updated_at == STAMP_T2
        # Чужая пара не тронута вовсе.
        assert st2_after.created_at == STAMP_T1
        assert st2_after.updated_at == STAMP_T1


# ---------------------------------------------------------------------------
# ТЗ §4.4 — создание новой пары не затрагивает существующие пары
# ---------------------------------------------------------------------------


class TestNewPairDoesNotTouchExisting:
    def test_creation_is_additive(self, manager, store_path):
        manager.get_state("s_a", "FIGI_X", config_hash=HASH_A)
        x_bytes_before = open(
            os.path.join(store_path, fname("s_a", "FIGI_X")), "rb").read()
        manager.get_state("s_b", "FIGI_NEW", config_hash=HASH_B)
        x_bytes_after = open(
            os.path.join(store_path, fname("s_a", "FIGI_X")), "rb").read()
        assert x_bytes_before == x_bytes_after
        assert os.path.isfile(
            os.path.join(store_path, fname("s_b", "FIGI_NEW")))
        assert dict(manager.get_state(
            "s_a", "FIGI_X", config_hash=HASH_A).data) == {}

    def test_list_states_contains_all_and_is_deterministic(self, manager):
        for sid, figi in [("s_b", "FIGI_Y"), ("s_a", "FIGI_X"),
                          ("s_b", "FIGI_X")]:
            manager.get_state(sid, figi, config_hash=HASH_A)
        keys1 = [st.key() for st in manager.list_states()]
        keys2 = [st.key() for st in manager.list_states()]
        assert keys1 == keys2
        assert keys1 == sorted([("s_b", "FIGI_Y"), ("s_a", "FIGI_X"),
                                ("s_b", "FIGI_X")])
        assert keys1 == [("s_a", "FIGI_X"), ("s_b", "FIGI_X"),
                         ("s_b", "FIGI_Y")]


# ---------------------------------------------------------------------------
# ТЗ §4.5 — сохранение и восстановление после перезапуска
# ---------------------------------------------------------------------------


class TestRestartPersistence:
    def test_state_restored_by_new_store_instance(self, store_path):
        mgr1 = ss.StrategyStateManager(ss.StateStore(path=store_path))
        mgr1.get_state("s_a", "FIGI_X", config_hash=HASH_A)
        created = mgr1.update_state(
            "s_a", "FIGI_X", config_hash=HASH_A, data={
                "position": "LONG", "entry": 100.5, "streak": 2,
                "seen": ["t1", "t2"], "nested": {"a": [1, 2, {"b": True}]},
            })
        # «Перезапуск»: новый экземпляр хранилища на том же явном пути.
        mgr2 = ss.StrategyStateManager(ss.StateStore(path=store_path))
        restored = mgr2.get_state("s_a", "FIGI_X", config_hash=HASH_A)
        assert restored == created
        assert restored.created_at == created.created_at
        assert restored.updated_at == created.updated_at
        assert restored.config_hash == HASH_A
        assert dict(restored.data) == {
            "position": "LONG", "entry": 100.5, "streak": 2,
            "seen": ["t1", "t2"], "nested": {"a": [1, 2, {"b": True}]},
        }

    def test_unicode_and_empty_data_survive_restart(self, store_path):
        mgr1 = ss.StrategyStateManager(ss.StateStore(path=store_path))
        mgr1.update_state("s_a", "FIGI_X", config_hash=HASH_A,
                          data={"комментарий": "стратегия «Альфа»",
                                "пусто": {}})
        mgr2 = ss.StrategyStateManager(ss.StateStore(path=store_path))
        restored = mgr2.get_state("s_a", "FIGI_X", config_hash=HASH_A)
        assert restored.data["комментарий"] == "стратегия «Альфа»"
        assert restored.data["пусто"] == {}
        # Пустое состояние тоже персистентно: пустой data != отсутствие записи.
        mgr2.get_state("s_b", "FIGI_Y", config_hash=HASH_B)
        mgr2b = ss.StrategyStateManager(ss.StateStore(path=store_path))
        assert dict(mgr2b.get_state("s_b", "FIGI_Y",
                                    config_hash=HASH_B).data) == {}

    def test_memory_mode_does_not_persist(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        mgr = ss.StrategyStateManager(ss.StateStore())
        assert mgr._store.mode == "memory"
        mgr.update_state("s_a", "FIGI_X", config_hash=HASH_A, data={"n": 1})
        assert mgr.get_state("s_a", "FIGI_X",
                             config_hash=HASH_A).data["n"] == 1
        # Новый экземпляр memory-хранилища ничего не «восстанавливает»:
        mgr2 = ss.StrategyStateManager(ss.StateStore())
        st = mgr2.get_state("s_a", "FIGI_X", config_hash=HASH_A)
        assert dict(st.data) == {}
        assert list(os.listdir(tmp_path)) == []  # ни одного файла на диске


# ---------------------------------------------------------------------------
# ТЗ §4.6 — детерминированная сериализация
# ---------------------------------------------------------------------------


class TestDeterministicSerialization:
    def test_same_content_same_bytes(self, store_path):
        d1 = ss.StrategyState.create("s_a", "FIGI_X", HASH_A,
                                     data={"b": 2, "a": [1, {"c": "x"}]},
                                     now=STAMP_T1)
        d2 = ss.StrategyState.create("s_a", "FIGI_X", HASH_A,
                                     data={"a": [1, {"c": "x"}], "b": 2},
                                     now=STAMP_T1)
        assert d1.to_json() == d2.to_json()
        assert d1.to_json() == d1.to_json()  # повторный вызов идентичен

    def test_store_file_bytes_equal_state_json(self, store, store_path):
        st = store.create_state("s_a", "FIGI_X", HASH_A,
                                data={"z": 1, "a": {"m": [3, 1, 2]}},
                                now=STAMP_T1)
        with open(os.path.join(store_path, fname("s_a", "FIGI_X")),
                  "rb") as h:
            file_bytes = h.read()
        assert file_bytes == st.to_json().encode("utf-8")
        # Каноничность: ключи отсортированы, без случайных пробелов.
        text = file_bytes.decode("utf-8")
        assert text == json.dumps(json.loads(text), sort_keys=True,
                                  separators=(",", ":"),
                                  ensure_ascii=False)

    def test_two_stores_write_identical_bytes(self, tmp_path):
        p1 = str(tmp_path / "one")
        p2 = str(tmp_path / "two")
        for p in (p1, p2):
            s = ss.StateStore(path=p)
            s.create_state("s_a", "FIGI_X", HASH_A,
                           data={"streak": 2, "tags": ["x", "y"]},
                           now=STAMP_T1)
        b1 = open(os.path.join(p1, fname("s_a", "FIGI_X")), "rb").read()
        b2 = open(os.path.join(p2, fname("s_a", "FIGI_X")), "rb").read()
        assert b1 == b2

    def test_json_round_trip_preserves_state(self):
        st = ss.StrategyState.create(
            "s_a", "FIGI_X", HASH_A,
            data={"unicode": "стратегия «Альфа»", "nums": [1, 2.5, -3],
                  "flags": {"on": True, "off": False}, "none": None},
            now=STAMP_T1)
        restored = ss.StrategyState.from_payload(
            json.loads(st.to_json()))
        assert restored == st
        assert restored.to_json() == st.to_json()

    def test_set_normalized_to_sorted_list_deterministically(self):
        s1 = ss.StrategyState.create("s_a", "FIGI_X", HASH_A,
                                     data={"tags": {"z", "a", "m"}},
                                     now=STAMP_T1)
        s2 = ss.StrategyState.create("s_a", "FIGI_X", HASH_A,
                                     data={"tags": {"m", "z", "a"}},
                                     now=STAMP_T1)
        assert s1.to_json() == s2.to_json()
        assert list(s1.data["tags"]) == ["a", "m", "z"]


# ---------------------------------------------------------------------------
# ТЗ §4.7 — повреждённая запись обнаруживается
# ---------------------------------------------------------------------------


class TestCorruptionDetection:
    def _write_raw(self, store_path, sid, figi, text):
        with open(os.path.join(
                store_path, fname(sid, figi)),
                "w", encoding="utf-8") as handle:
            handle.write(text)

    def test_garbage_file_detected_not_replaced(self, store, store_path):
        store.create_state("s_a", "FIGI_X", HASH_A, now=STAMP_T1)
        self._write_raw(store_path, "s_a", "FIGI_X", "{broken json,,,")
        with pytest.raises(ss.StateCorruptionError):
            store.get_state("s_a", "FIGI_X", config_hash=HASH_A)
        with pytest.raises(ss.StateCorruptionError):
            store.list_states()
        # Запись НЕ подменена пустым состоянием: файл остался повреждённым.
        with open(os.path.join(store_path, fname("s_a", "FIGI_X")),
                  "r", encoding="utf-8") as handle:
            assert handle.read() == "{broken json,,,"

    def test_missing_fields_detected(self, store, store_path):
        payload = ss.StrategyState.create(
            "s_a", "FIGI_X", HASH_A, data={"n": 1},
            now=STAMP_T1).to_payload()
        broken = {k: v for k, v in payload.items() if k != "config_hash"}
        self._write_raw(store_path, "s_a", "FIGI_X", json.dumps(broken))
        with pytest.raises(ss.StateCorruptionError):
            store.get_state("s_a", "FIGI_X", config_hash=HASH_A)

    def test_wrong_field_types_detected(self, store, store_path):
        payload = ss.StrategyState.create(
            "s_a", "FIGI_X", HASH_A, now=STAMP_T1).to_payload()
        payload["data"] = [1, 2, 3]  # data должен быть объектом
        self._write_raw(store_path, "s_a", "FIGI_X", json.dumps(payload))
        with pytest.raises(ss.StateCorruptionError):
            store.get_state("s_a", "FIGI_X", config_hash=HASH_A)

    def test_bad_hash_format_in_record_detected(self, store, store_path):
        payload = ss.StrategyState.create(
            "s_a", "FIGI_X", HASH_A, now=STAMP_T1).to_payload()
        payload["config_hash"] = "не-хеш"
        self._write_raw(store_path, "s_a", "FIGI_X", json.dumps(payload))
        with pytest.raises(ss.StateValidationError):
            store.get_state("s_a", "FIGI_X")

    def test_manager_does_not_mask_corruption(self, manager, store_path):
        manager.get_state("s_a", "FIGI_X", config_hash=HASH_A)
        with open(os.path.join(store_path, fname("s_a", "FIGI_X")),
                  "w", encoding="utf-8") as handle:
            handle.write("[]")
        with pytest.raises(ss.StateCorruptionError):
            manager.get_state("s_a", "FIGI_X", config_hash=HASH_A)
        with pytest.raises(ss.StateCorruptionError):
            manager.update_state("s_a", "FIGI_X", config_hash=HASH_A,
                                 data={"n": 1})

    def test_filename_content_mismatch_detected(self, store, store_path):
        st = store.create_state("s_a", "FIGI_X", HASH_A, now=STAMP_T1)
        payload = st.to_payload()
        payload["figi"] = "FIGI_XX"  # содержимое другого ключа
        with open(os.path.join(store_path, fname("s_a", "FIGI_OTHER")),
                  "w", encoding="utf-8") as handle:
            json.dump(payload, handle)
        with pytest.raises(ss.StateCorruptionError):
            store.list_states()


# ---------------------------------------------------------------------------
# ТЗ §4.8 — неизвестная версия схемы отклоняется
# ---------------------------------------------------------------------------


class TestUnknownSchemaVersion:
    def _payload_with_version(self, version):
        payload = ss.StrategyState.create(
            "s_a", "FIGI_X", HASH_A, data={"n": 1},
            now=STAMP_T1).to_payload()
        payload["schema_version"] = version
        return payload

    def test_future_version_rejected(self, store, store_path):
        with open(os.path.join(store_path, fname("s_a", "FIGI_X")),
                  "w", encoding="utf-8") as handle:
            json.dump(self._payload_with_version(999), handle)
        with pytest.raises(ss.StateSchemaError):
            store.get_state("s_a", "FIGI_X")
        with pytest.raises(ss.StateSchemaError):
            store.list_states()
        with pytest.raises(ss.StateSchemaError):
            ss.StrategyState.from_payload(self._payload_with_version(2))

    def test_string_version_is_corruption(self, store, store_path):
        with open(os.path.join(store_path, fname("s_a", "FIGI_X")),
                  "w", encoding="utf-8") as handle:
            json.dump(self._payload_with_version("1"), handle)
        with pytest.raises(ss.StateCorruptionError):
            store.get_state("s_a", "FIGI_X")

    def test_missing_version_is_corruption(self, store, store_path):
        payload = self._payload_with_version(1)
        del payload["schema_version"]
        with open(os.path.join(store_path, fname("s_a", "FIGI_X")),
                  "w", encoding="utf-8") as handle:
            json.dump(payload, handle)
        with pytest.raises(ss.StateCorruptionError):
            store.get_state("s_a", "FIGI_X")

    def test_direct_constructor_rejects_wrong_version(self):
        with pytest.raises(ss.StateSchemaError):
            ss.StrategyState(
                strategy_id="s_a", figi="FIGI_X", config_hash=HASH_A,
                schema_version=2, created_at=STAMP_T1, updated_at=STAMP_T1)


# ---------------------------------------------------------------------------
# ТЗ §4.9 — несовпадающий config_hash отклоняется
# ---------------------------------------------------------------------------


class TestConfigHashMismatch:
    def test_get_state_with_expected_hash_mismatch(self, manager):
        manager.get_state("s_a", "FIGI_X", config_hash=HASH_A)
        with pytest.raises(ss.StateConfigMismatchError):
            manager.get_state("s_a", "FIGI_X", config_hash=HASH_B)

    def test_get_state_with_config_object_mismatch(self, manager):
        cfg_old = make_config(params={"length": 14})
        cfg_new = make_config(params={"length": 21})
        manager.get_state("s_a", "FIGI_X", config=cfg_old)
        with pytest.raises(ss.StateConfigMismatchError):
            manager.get_state("s_a", "FIGI_X", config=cfg_new)

    def test_save_state_does_not_migrate_old_data_to_new_config(
            self, store):
        st_old = store.create_state("s_a", "FIGI_X", HASH_A, now=STAMP_T1)
        evolved = st_old.with_data({"n": 1}, now=STAMP_T2)
        with pytest.raises(ss.StateConfigMismatchError):
            # Попытка записать данные старой конфигурации под новым хешем.
            store.save_state("s_a", "FIGI_X", ss.StrategyState(
                strategy_id="s_a", figi="FIGI_X", config_hash=HASH_B,
                schema_version=ss.STATE_SCHEMA_VERSION,
                data=evolved.data, created_at=STAMP_T1,
                updated_at=STAMP_T2))
        # Запись не изменена и не «перенесена».
        current = store.get_state("s_a", "FIGI_X")
        assert current.config_hash == HASH_A
        assert dict(current.data) == {}

    def test_mismatch_file_untouched(self, manager, store_path):
        manager.get_state("s_a", "FIGI_X", config_hash=HASH_A)
        before = open(os.path.join(store_path, fname("s_a", "FIGI_X")),
                      "rb").read()
        with pytest.raises(ss.StateConfigMismatchError):
            manager.get_state("s_a", "FIGI_X", config_hash=HASH_B)
        after = open(os.path.join(store_path, fname("s_a", "FIGI_X")),
                     "rb").read()
        assert before == after

    def test_explicit_reset_is_the_controlled_solution(self, manager):
        manager.get_state("s_a", "FIGI_X", config_hash=HASH_A)
        with pytest.raises(ss.StateConfigMismatchError):
            manager.get_state("s_a", "FIGI_X", config_hash=HASH_B)
        assert manager.reset_state("s_a", "FIGI_X") is True
        st = manager.get_state("s_a", "FIGI_X", config_hash=HASH_B)
        assert st.config_hash == HASH_B
        assert st.data == {}          # НОВОЕ пустое состояние после ЯВНОГО
                                      # решения, а не перенос старого


# ---------------------------------------------------------------------------
# ТЗ §4.10 — отсутствие записи обрабатывается корректно
# ---------------------------------------------------------------------------


class TestMissingRecord:
    def test_store_returns_none_for_missing(self, store):
        assert store.get_state("s_a", "FIGI_X") is None

    def test_manager_creates_fresh_independent_state(self, manager):
        st = manager.get_state("s_a", "FIGI_X", config_hash=HASH_A)
        assert st.strategy_id == "s_a" and st.figi == "FIGI_X"
        assert st.config_hash == HASH_A
        assert st.data == {}
        assert st.created_at != "" and st.updated_at != ""
        # Повторное получение возвращает ТУ ЖЕ запись, а не новую.
        again = manager.get_state("s_a", "FIGI_X", config_hash=HASH_A)
        assert again == st

    def test_missing_then_created_then_missing_after_reset(self, manager):
        manager.get_state("s_a", "FIGI_X", config_hash=HASH_A)
        assert manager.reset_state("s_a", "FIGI_X") is True
        assert manager._store.get_state("s_a", "FIGI_X") is None

    def test_create_on_existing_fails_closed(self, store):
        store.create_state("s_a", "FIGI_X", HASH_A, data={"n": 1})
        with pytest.raises(ss.StateAlreadyExistsError):
            store.create_state("s_a", "FIGI_X", HASH_A, data={"n": 2})
        assert dict(store.get_state("s_a", "FIGI_X").data) == {"n": 1}

    def test_save_state_on_missing_fails_closed(self, store):
        st = ss.StrategyState.create("s_a", "FIGI_X", HASH_A, now=STAMP_T1)
        with pytest.raises(ss.StateNotFoundError):
            store.save_state("s_a", "FIGI_X", st)


# ---------------------------------------------------------------------------
# ТЗ §4.11 — явный reset затрагивает только выбранную пару
# ---------------------------------------------------------------------------


class TestExplicitResetScope:
    def test_reset_only_selected_pair(self, manager, store_path):
        for sid, figi in [("s_a", "FIGI_X"), ("s_a", "FIGI_Y"),
                          ("s_b", "FIGI_X")]:
            manager.update_state(sid, figi, config_hash=HASH_A,
                                 data={"v": figi})
        assert manager.reset_state("s_a", "FIGI_X") is True
        files = sorted(os.listdir(store_path))
        assert fname("s_a", "FIGI_X") not in files
        assert fname("s_a", "FIGI_Y") in files
        assert fname("s_b", "FIGI_X") in files
        assert manager.get_state("s_a", "FIGI_Y",
                                 config_hash=HASH_A).data["v"] == "FIGI_Y"
        assert manager.get_state("s_b", "FIGI_X",
                                 config_hash=HASH_A).data["v"] == "FIGI_X"
        # Повторный reset отсутствующей записи: False, без исключений.
        assert manager.reset_state("s_a", "FIGI_X") is False

    def test_reset_does_not_resurrect_old_data_with_same_config(
            self, manager):
        manager.update_state("s_a", "FIGI_X", config_hash=HASH_A,
                             data={"n": 42})
        manager.reset_state("s_a", "FIGI_X")
        st = manager.get_state("s_a", "FIGI_X", config_hash=HASH_A)
        assert dict(st.data) == {}  # прежние данные не «воскресли»


# ---------------------------------------------------------------------------
# ТЗ §4.12 — параллельные операции не приводят к перекрёстному загрязнению
# ---------------------------------------------------------------------------


class TestConcurrency:
    def test_parallel_updates_of_distinct_pairs_are_isolated(self, manager):
        pairs = [(f"s_{i}", f"FIGI_{i}") for i in range(8)]
        for sid, figi in pairs:
            manager.get_state(sid, figi, config_hash=HASH_A)

        def worker(index):
            sid, figi = pairs[index]
            for step in range(25):
                manager.update_state(
                    sid, figi, config_hash=HASH_A,
                    data={"owner": index, "step": step})
                st = manager.get_state(sid, figi, config_hash=HASH_A)
                # Чужие данные в моей паре — перекрёстное загрязнение.
                assert st.data["owner"] == index
                assert st.data["step"] in range(step + 1)

        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(worker, range(8)))

        for index, (sid, figi) in enumerate(pairs):
            st = manager.get_state(sid, figi, config_hash=HASH_A)
            assert st.data["owner"] == index
            assert st.data["step"] == 24

    def test_parallel_get_or_create_same_key_single_record(self, store):
        def worker(_):
            st = store.get_state("s_a", "FIGI_X", config_hash=HASH_A)
            if st is not None:
                return st
            try:
                # Хранилище атомарно по ОДНОЙ операции: составной
                # get-or-create обрабатывает гонку ЯВНО (договорённость
                # интерфейса); StrategyStateManager делает это внутренне.
                return store.create_state("s_a", "FIGI_X", HASH_A)
            except ss.StateAlreadyExistsError:
                return store.get_state("s_a", "FIGI_X",
                                       config_hash=HASH_A)

        with ThreadPoolExecutor(max_workers=12) as pool:
            results = list(pool.map(worker, range(12)))
        # Все потоки получили одно и то же состояние; ошибок гонки наружу
        # не вышло; запись создана ровно одна.
        assert all(st.config_hash == HASH_A for st in results)
        states = store.list_states()
        assert len(states) == 1
        assert states[0].key() == ("s_a", "FIGI_X")

    def test_manager_get_or_create_race_is_handled_internally(self, manager):
        # Менеджер сам обрабатывает гонку get/create: 16 потоков,
        # ни одного исключения наружу, одна запись.
        def worker(_):
            return manager.get_state("s_race", "FIGI_R",
                                     config_hash=HASH_A)

        with ThreadPoolExecutor(max_workers=16) as pool:
            results = list(pool.map(worker, range(16)))
        assert len(results) == 16
        assert all(st.key() == ("s_race", "FIGI_R") for st in results)
        assert len(manager.list_states()) == 1

    def test_parallel_updates_same_key_no_lost_update(self, manager):
        manager.get_state("s_a", "FIGI_X", config_hash=HASH_A)

        def increment(_):
            def updater(current):
                n = current.data.get("n", 0)
                return {"n": n + 1}
            manager.update_state("s_a", "FIGI_X", config_hash=HASH_A,
                                 updater=updater)

        with ThreadPoolExecutor(max_workers=10) as pool:
            list(pool.map(increment, range(40)))
        st = manager.get_state("s_a", "FIGI_X", config_hash=HASH_A)
        assert st.data["n"] == 40  # ни одно обновление не потеряно

    def test_parallel_mixed_operations_no_cross_contamination(self, manager):
        pairs = [(f"s_{i}", f"FIGI_{i}") for i in range(6)]
        for sid, figi in pairs:
            manager.get_state(sid, figi, config_hash=HASH_A)

        def mixed(task):
            kind, index = task
            sid, figi = pairs[index]
            if kind == "update":
                manager.update_state(sid, figi, config_hash=HASH_A,
                                     data={"owner": index})
            elif kind == "reset":
                manager.reset_state(sid, figi)
                manager.get_state(sid, figi, config_hash=HASH_A)
            elif kind == "read":
                st = manager.get_state(sid, figi, config_hash=HASH_A)
                owner = st.data.get("owner", index)
                assert owner == index

        tasks = [(kind, i % 6)
                 for i in range(60)
                 for kind in ("update", "reset", "read")]
        with ThreadPoolExecutor(max_workers=12) as pool:
            list(pool.map(mixed, tasks))

        for index, (sid, figi) in enumerate(pairs):
            st = manager.get_state(sid, figi, config_hash=HASH_A)
            assert st.data.get("owner", index) == index


# ---------------------------------------------------------------------------
# ТЗ §4.13 — изменение возвращённого объекта не меняет хранилище
# ---------------------------------------------------------------------------


class TestReturnedObjectIsolation:
    def test_state_is_frozen(self, manager):
        st = manager.get_state("s_a", "FIGI_X", config_hash=HASH_A)
        with pytest.raises(Exception):
            st.strategy_id = "s_hacked"
        with pytest.raises(Exception):
            st.config_hash = HASH_B

    def test_data_mapping_is_immutable(self, manager):
        manager.update_state("s_a", "FIGI_X", config_hash=HASH_A,
                             data={"n": 1, "lst": [1, 2]})
        st = manager.get_state("s_a", "FIGI_X", config_hash=HASH_A)
        with pytest.raises(TypeError):
            st.data["n"] = 999
        with pytest.raises(TypeError):
            st.data["new_key"] = "x"
        with pytest.raises((TypeError, AttributeError)):
            st.data["lst"].append(3)  # ImmutableList: tuple без append

    def test_mutating_source_after_create_does_not_change_store(self, store):
        source = {"n": 1, "nested": {"deep": [1, 2]}}
        store.create_state("s_a", "FIGI_X", HASH_A, data=source)
        source["n"] = 999
        source["nested"]["deep"].append(3)
        st = store.get_state("s_a", "FIGI_X")
        assert st.data["n"] == 1
        assert list(st.data["nested"]["deep"]) == [1, 2]

    def test_updater_cannot_mutate_current_state_in_place(self, manager):
        manager.update_state("s_a", "FIGI_X", config_hash=HASH_A,
                             data={"n": 1})

        def bad_updater(current):
            try:
                current.data["n"] = 999      # изменение состояния на месте
            except TypeError:
                pass                          # неизменяемость сработала
            return {"n": current.data.get("n", 0) + 1}

        new_state = manager.update_state("s_a", "FIGI_X",
                                         config_hash=HASH_A,
                                         updater=bad_updater)
        assert new_state.data["n"] == 2
        stored = manager.get_state("s_a", "FIGI_X", config_hash=HASH_A)
        assert stored.data["n"] == 2

    def test_to_payload_copies_do_not_affect_store(self, manager):
        manager.update_state("s_a", "FIGI_X", config_hash=HASH_A,
                             data={"n": 1, "lst": [1, 2]})
        st = manager.get_state("s_a", "FIGI_X", config_hash=HASH_A)
        payload = st.to_payload()
        payload["data"]["n"] = 999
        payload["data"]["lst"].append(3)
        st_after = manager.get_state("s_a", "FIGI_X", config_hash=HASH_A)
        assert st_after.data["n"] == 1
        assert list(st_after.data["lst"]) == [1, 2]


# ---------------------------------------------------------------------------
# ТЗ §4.14 — записи Stage A и golden fixtures остаются совместимыми
# ---------------------------------------------------------------------------


class TestStageACompatibility:
    PROTECTED = [
        "engine.json",
        "strategy_api.py",
        "attribution.py",
        "engine_config.py",
        "strategies/legacy_samsung_v4/strategy.py",
        "strategies/legacy_samsung_v4/params.json",
        "strategies/legacy_samsung_v4/profiles.py",
        "strategies/legacy_samsung_v4/schema.py",
    ]

    def test_stage_b_writes_only_into_explicit_store_path(
            self, tmp_path, monkeypatch):
        cwd_dir = str(tmp_path / "cwd")
        store_dir = str(tmp_path / "explicit_store")
        os.makedirs(cwd_dir, exist_ok=True)
        monkeypatch.chdir(cwd_dir)
        store = ss.StateStore(path=store_dir)
        mgr = ss.StrategyStateManager(store)
        mgr.update_state("s_a", "FIGI_X", config_hash=HASH_A,
                         data={"n": 1})
        mgr.list_states()
        # В рабочей директории НЕ появилось ничего (ни state.json Samsung,
        # ни «своего» файла по умолчанию); запись только по явному пути.
        assert os.listdir(cwd_dir) == []
        assert sorted(os.listdir(store_dir)) == [fname("s_a", "FIGI_X")]

    def test_stage_a_files_untouched_by_stage_b_operations(
            self, store_path):
        base = os.path.dirname(os.path.abspath(__file__))
        root = os.path.dirname(base)  # candidate/
        before = {rel: sha256_of(os.path.join(root, rel))
                  for rel in self.PROTECTED}
        store = ss.StateStore(path=store_path)
        mgr = ss.StrategyStateManager(store)
        mgr.update_state("s_a", "FIGI_X", config_hash=HASH_A, data={"n": 1})
        mgr.reset_state("s_a", "FIGI_X")
        mgr.list_states()
        after = {rel: sha256_of(os.path.join(root, rel))
                 for rel in self.PROTECTED}
        assert before == after

    def test_stage_a_attribution_contract_still_works(self, manager):
        # config_hash Stage A не меняется: конфигурация строится тем же
        # алгоритмом, контекст — тем же from_config (Stage A.2.1).
        cfg = make_config(params={"length": 14})
        ctx = AttributionContext.from_config(cfg)
        assert ctx.strategy_id == cfg.strategy_id
        assert ctx.config_hash == cfg.config_hash
        st = manager.get_state_for_context(ctx, "FIGI_X")
        assert st.strategy_id == cfg.strategy_id
        assert st.config_hash == cfg.config_hash

    def test_legacy_strategy_remains_regression_only(self):
        from strategies.legacy_samsung_v4.strategy import (
            LegacySamsungV4Strategy,
        )
        assert LegacySamsungV4Strategy.activation_mode \
            == ActivationMode.REGRESSION_ONLY


# ---------------------------------------------------------------------------
# ТЗ §4.15 — невалидные strategy_id или FIGI отклоняются
# ---------------------------------------------------------------------------


class TestInvalidKeys:
    BAD_KEYS = [
        None, 123, "", "   ", "../escape", "a/b", "a\\b", "a\nb",
        "..", ".", ".hidden", "a\x00b", "a b", "ключ-с-юникодом",
        "a" * 129,
    ]

    @pytest.mark.parametrize("bad", BAD_KEYS)
    def test_bad_strategy_id_rejected(self, store, bad):
        with pytest.raises(ss.StateValidationError):
            store.get_state(bad, "FIGI_X")
        with pytest.raises(ss.StateValidationError):
            store.create_state(bad, "FIGI_X", HASH_A)
        with pytest.raises(ss.StateValidationError):
            store.reset_state(bad, "FIGI_X")

    @pytest.mark.parametrize("bad", BAD_KEYS)
    def test_bad_figi_rejected(self, store, bad):
        with pytest.raises(ss.StateValidationError):
            store.get_state("s_a", bad)
        with pytest.raises(ss.StateValidationError):
            store.create_state("s_a", bad, HASH_A)
        with pytest.raises(ss.StateValidationError):
            store.reset_state("s_a", bad)

    def test_manager_validates_keys_before_any_io(self, manager):
        with pytest.raises(ss.StateValidationError):
            manager.get_state("../evil", "FIGI_X", config_hash=HASH_A)
        with pytest.raises(ss.StateValidationError):
            manager.update_state("s_a", "a/b", config_hash=HASH_A,
                                 data={"n": 1})

    def test_no_file_created_for_invalid_keys(self, store_path):
        store = ss.StateStore(path=store_path)
        for bad in ["../escape", "a/b", ".hidden"]:
            with pytest.raises(ss.StateValidationError):
                store.get_state(bad, "FIGI_X")
        assert os.listdir(store_path) == []

    def test_figi_length_limit(self, store):
        with pytest.raises(ss.StateValidationError):
            store.get_state("s_a", "F" * 65)


# ---------------------------------------------------------------------------
# ТЗ §4.16 — отсутствие обязательной конфигурации persistent-хранилища
# не приводит к скрытому переходу на другой путь
# ---------------------------------------------------------------------------


class TestNoHiddenPathFallback:
    def test_missing_config_key_fails_closed(self):
        with pytest.raises(ss.StateStoreConfigError):
            ss.resolve_state_store_path({})

    def test_none_value_fails_closed(self):
        with pytest.raises(ss.StateStoreConfigError):
            ss.resolve_state_store_path({ss.STATE_STORE_CONFIG_KEY: None})

    def test_non_string_value_fails_closed(self):
        for bad in (123, True, ["path"], {"p": 1}):
            with pytest.raises(ss.StateStoreConfigError):
                ss.resolve_state_store_path({ss.STATE_STORE_CONFIG_KEY: bad})

    def test_empty_string_fails_closed(self):
        for bad in ("", "   "):
            with pytest.raises(ss.StateStoreConfigError):
                ss.resolve_state_store_path({ss.STATE_STORE_CONFIG_KEY: bad})

    def test_explicit_config_key_resolves_exactly(self):
        assert ss.resolve_state_store_path(
            {"STATE_STORE_PATH": "/explicit/path"}) == "/explicit/path"

    def test_memory_mode_is_explicit_not_a_hidden_path(self, tmp_path,
                                                       monkeypatch):
        monkeypatch.chdir(tmp_path)
        store = ss.StateStore()
        assert store.mode == "memory"
        assert store.path is None
        store.create_state("s_a", "FIGI_X", HASH_A)
        assert os.listdir(tmp_path) == []  # на диске ничего нет

    def test_persistent_mode_requires_explicit_path(self):
        # Единственный способ включить persistent-режим — ЯВНЫЙ path;
        # путь по умолчанию в модуле не существует.
        store = ss.StateStore()
        assert store.mode == "memory"  # без path — только память
        assert store.path is None
        with pytest.raises(ss.StateStoreConfigError):
            ss.StateStore(path="")
        # Проверка «нет скрытого пути по умолчанию»: у модуля нет
        # константы пути, хранилище без path ничего не пишет на диск.
        assert not any(name.startswith("DEFAULT_") or "PATH" in name
                       for name in dir(ss)
                       if name.isupper() and name != "STATE_STORE_CONFIG_KEY")

    def test_store_does_not_touch_old_samsung_files(self, tmp_path,
                                                    monkeypatch):
        # Имитация рабочего каталога Samsung: старые файлы присутствуют,
        # StateStore не пишет в них и не читает их.
        monkeypatch.chdir(tmp_path)
        for name in ("state.json", "state.json.tmp",
                     "research_events.jsonl", "orders_registry.json"):
            with open(name, "w", encoding="utf-8") as handle:
                handle.write("{}")
        before = {name: sha256_of(name)
                  for name in ("state.json", "research_events.jsonl",
                               "orders_registry.json")}
        store = ss.StateStore()  # memory-режим: явный, без пути
        mgr = ss.StrategyStateManager(store)
        mgr.update_state("s_a", "FIGI_X", config_hash=HASH_A, data={"n": 1})
        persistent = ss.StateStore(path=str(tmp_path / "explicit_store"))
        persistent.create_state("s_a", "FIGI_X", HASH_A)
        after = {name: sha256_of(name)
                 for name in ("state.json", "research_events.jsonl",
                              "orders_registry.json")}
        assert before == after
        assert sorted(os.listdir(tmp_path)) == [
            "explicit_store", "orders_registry.json", "research_events.jsonl",
            "state.json", "state.json.tmp"]
        assert sorted(os.listdir(
            str(tmp_path / "explicit_store"))) == [fname("s_a", "FIGI_X")]

    def test_manager_requires_exact_state_store_type(self):
        with pytest.raises(ss.StateStoreConfigError):
            ss.StrategyStateManager(object())
        with pytest.raises(ss.StateStoreConfigError):
            ss.StrategyStateManager(None)


# ---------------------------------------------------------------------------
# Граничные случаи: менеджер, конфигурация, данные
# ---------------------------------------------------------------------------


class TestManagerConfigBinding:
    def test_no_config_at_all_fails_closed(self, manager):
        with pytest.raises(ss.StateValidationError):
            manager.get_state("s_a", "FIGI_X")
        with pytest.raises(ss.StateValidationError):
            manager.update_state("s_a", "FIGI_X", data={"n": 1})

    def test_exact_strategy_config_accepted(self, manager):
        cfg = make_config()
        st = manager.get_state("s_a", "FIGI_X", config=cfg)
        assert st.config_hash == cfg.config_hash

    def test_subclass_of_strategy_config_rejected(self, manager):
        cfg = make_config()

        class SubConfig(StrategyConfig):
            pass

        sub = SubConfig(
            strategy_id=cfg.strategy_id,
            strategy_version=cfg.strategy_version,
            params=dict(cfg.params),
            config_hash=cfg.config_hash,
        )
        with pytest.raises(ss.StateValidationError):
            manager.get_state("s_a", "FIGI_X", config=sub)

    def test_duck_typed_config_rejected(self, manager):
        fake = type("Fake", (), {})()
        fake.strategy_id = "s_a"
        fake.config_hash = HASH_A
        with pytest.raises(ss.StateValidationError):
            manager.get_state("s_a", "FIGI_X", config=fake)

    def test_config_of_other_strategy_rejected(self, manager):
        cfg = make_config(strategy_id="s_other")
        with pytest.raises(ss.StateValidationError):
            manager.get_state("s_a", "FIGI_X", config=cfg)

    def test_config_and_config_hash_contradiction_rejected(self, manager):
        cfg = make_config(params={"length": 14})
        with pytest.raises(ss.StateValidationError):
            manager.get_state("s_a", "FIGI_X",
                              config=cfg, config_hash=HASH_B)

    def test_hash_only_path_also_works(self, manager):
        st = manager.get_state("s_a", "FIGI_X", config_hash=HASH_A)
        assert st.config_hash == HASH_A

    def test_unverified_attribution_context_rejected(self, manager):
        cfg = make_config()
        with pytest.raises(Exception):
            AttributionContext(cfg.strategy_id, cfg.config_hash)
        # Проверенный контекст работает:
        ctx = AttributionContext.from_config(cfg)
        st = manager.get_state_for_context(ctx, "FIGI_X")
        assert st.config_hash == cfg.config_hash
        # Самодельный объект без маркера — отклоняется (Stage A.2.1).
        with pytest.raises(Exception):
            manager.get_state_for_context(object(), "FIGI_X")

    def test_update_state_requires_exactly_one_data_source(self, manager):
        with pytest.raises(ss.StateValidationError):
            manager.update_state("s_a", "FIGI_X", config_hash=HASH_A)
        with pytest.raises(ss.StateValidationError):
            manager.update_state("s_a", "FIGI_X", config_hash=HASH_A,
                                 data={"n": 1},
                                 updater=lambda cur: {"n": 2})

    def test_updater_failure_leaves_store_unchanged(self, manager):
        manager.update_state("s_a", "FIGI_X", config_hash=HASH_A,
                             data={"n": 1})

        def failing_updater(current):
            assert current.data["n"] == 1
            raise RuntimeError("updater failed")

        with pytest.raises(RuntimeError):
            manager.update_state("s_a", "FIGI_X", config_hash=HASH_A,
                                 updater=failing_updater)
        st = manager.get_state("s_a", "FIGI_X", config_hash=HASH_A)
        assert st.data["n"] == 1  # запись не изменена

    def test_updater_returning_non_mapping_rejected(self, manager):
        manager.get_state("s_a", "FIGI_X", config_hash=HASH_A)
        with pytest.raises(ss.StateValidationError):
            manager.update_state("s_a", "FIGI_X", config_hash=HASH_A,
                                 updater=lambda cur: [1, 2])

    def test_save_state_rejects_foreign_state_object(self, store):
        st_a = store.create_state("s_a", "FIGI_X", HASH_A, now=STAMP_T1)
        store.create_state("s_b", "FIGI_X", HASH_B, now=STAMP_T1)
        # Запись пары A под ключом пары B — отклоняется.
        with pytest.raises(ss.StateValidationError):
            store.save_state("s_b", "FIGI_X", st_a)
        # Не-StrategyState — отклоняется.
        with pytest.raises(ss.StateValidationError):
            store.save_state("s_a", "FIGI_X", {"data": {}})
        # Подкласс StrategyState — отклоняется (точный тип).

        class SubState(ss.StrategyState):
            pass

        sub = SubState(
            strategy_id="s_a", figi="FIGI_X", config_hash=HASH_A,
            schema_version=1, data={}, created_at=STAMP_T1,
            updated_at=STAMP_T1)
        with pytest.raises(ss.StateValidationError):
            store.save_state("s_a", "FIGI_X", sub)

    def test_data_validation_rejects_nan_and_objects(self, store):
        with pytest.raises(ss.StateValidationError):
            store.create_state("s_a", "FIGI_X", HASH_A,
                               data={"x": float("nan")})
        with pytest.raises(ss.StateValidationError):
            store.create_state("s_a", "FIGI_X", HASH_A,
                               data={"x": float("inf")})
        with pytest.raises(ss.StateValidationError):
            store.create_state("s_a", "FIGI_X", HASH_A,
                               data={"x": object()})
        with pytest.raises(ss.StateValidationError):
            store.create_state("s_a", "FIGI_X", HASH_A,
                               data={1: "не строковый ключ"})

    def test_atomic_persistence_no_tmp_leftovers(self, manager, store_path):
        for i in range(5):
            manager.update_state("s_a", "FIGI_X", config_hash=HASH_A,
                                 data={"n": i})
        files = os.listdir(store_path)
        assert files == [fname("s_a", "FIGI_X")]

    def test_store_creates_missing_directory(self, tmp_path):
        nested = str(tmp_path / "deep" / "nested" / "store")
        store = ss.StateStore(path=nested)
        assert os.path.isdir(nested)
        store.create_state("s_a", "FIGI_X", HASH_A)
        assert store.get_state("s_a", "FIGI_X") is not None

    def test_invalid_timestamps_rejected(self):
        with pytest.raises(ss.StateValidationError):
            ss.StrategyState.create("s_a", "FIGI_X", HASH_A,
                                    now="не-время")
        with pytest.raises(ss.StateValidationError):
            ss.StrategyState.create("s_a", "FIGI_X", HASH_A,
                                    now="2026-01-01T10:00:00")  # без зоны
        payload = ss.StrategyState.create(
            "s_a", "FIGI_X", HASH_A, now=STAMP_T1).to_payload()
        payload["created_at"] = "мусор"
        with pytest.raises(ss.StateValidationError):
            ss.StrategyState.from_payload(payload)

    def test_state_data_top_level_must_be_mapping(self, store):
        with pytest.raises(ss.StateValidationError):
            store.create_state("s_a", "FIGI_X", HASH_A, data=[1, 2, 3])

    def test_with_data_creates_new_object_original_untouched(self, store):
        st = store.create_state("s_a", "FIGI_X", HASH_A,
                                data={"n": 1}, now=STAMP_T1)
        evolved = st.with_data({"n": 2}, now=STAMP_T2)
        assert st.data["n"] == 1
        assert evolved.data["n"] == 2
        assert evolved.created_at == st.created_at == STAMP_T1
        assert evolved.updated_at == STAMP_T2
        assert st.updated_at == STAMP_T1
        assert evolved is not st

    def test_persisted_file_matches_canonical_json_exactly(
            self, store, store_path):
        st = store.create_state("s_a", "FIGI_X", HASH_A,
                                data={"b": 1, "a": 2}, now=STAMP_T1)
        with open(os.path.join(store_path, fname("s_a", "FIGI_X")),
                  "r", encoding="utf-8") as handle:
            raw = handle.read()
        assert raw == st.to_json()
        assert raw.startswith('{"config_hash"')  # sort_keys: a<...<z
        parsed = json.loads(raw)
        assert parsed["data"] == {"a": 2, "b": 1}
