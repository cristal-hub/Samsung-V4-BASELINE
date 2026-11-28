# tests/test_stage_b1_state_key_and_concurrency.py — SAMSUNG V4 — STAGE B.1.
#
# Корректирующие тесты Stage B.1 (ТЗ Stage B.1 §6) поверх Stage B:
#   * ДЕФЕКТ №1 — инъективное кодирование имени файла пары
#     (strategy_id, FIGI): пары, дававшие ранее ОДНО имя
#     (f"{strategy_id}__{figi}.json"), теперь независимы;
#   * ДЕФЕКТ №2 — обязательная проверка ключей записи ПОСЛЕ чтения
#     (persistent и memory): подмена содержимого чужим ключом
#     обнаруживается, файл не изменяется, состояние не возвращается;
#   * ДЕФЕКТ №3 — атомарный read-modify-write в StateStore: два
#     менеджера с одним хранилищем, параллельные updater-операции без
#     потери обновлений, детерминированный итог повторов, ошибка
#     updater не меняет сохранённое состояние.
#
# Плюс: независимость разных пар при параллельной работе, границы
# допустимых строк без коллизий, отсутствие скрытой миграции старого
# формата имён. Все тесты offline; без сети, брокера и заявок; старые
# файлы Samsung не затрагиваются; торговая логика не используется.

import json
import os
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

import strategy_state as ss

HASH_A = "a" * 64
HASH_B = "b" * 64
STAMP_T1 = "2026-01-01T10:00:00.000000Z"
STAMP_T2 = "2026-01-02T11:00:00.000000Z"

# Пары, которые СТАРЫМ шаблоном f"{s1}__{s2}.json" давали ОДНО имя файла:
# "alpha__beta" + "FIGI1" -> "alpha__beta__FIGI1.json"
# "alpha"       + "beta__FIGI1" -> "alpha__beta__FIGI1.json"
COLLIDING_PAIR_1 = ("alpha__beta", "FIGI1")
COLLIDING_PAIR_2 = ("alpha", "beta__FIGI1")


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


def read_bytes(store_path, sid, figi):
    with open(os.path.join(store_path, ss.encode_state_filename(sid, figi)),
              "rb") as handle:
        return handle.read()


def listdir_names(store_path):
    return sorted(os.listdir(store_path))


# ---------------------------------------------------------------------------
# ДЕФЕКТ №1 — инъективность имени файла
# ---------------------------------------------------------------------------


class TestFilenameInjectivity:
    def test_encode_differs_for_previously_colliding_pairs(self):
        n1 = ss.encode_state_filename(*COLLIDING_PAIR_1)
        n2 = ss.encode_state_filename(*COLLIDING_PAIR_2)
        # Старый шаблон давал ОДНО имя; новое кодирование — два разных.
        assert n1 != n2
        assert ss.decode_state_filename(n1) == COLLIDING_PAIR_1
        assert ss.decode_state_filename(n2) == COLLIDING_PAIR_2

    def test_encode_decode_round_trip_allows_separators_inside_values(self):
        # Разделитель '--', цифры и длина-подобные строки внутри значений
        # не ломают позиционный разбор (значения — гранично-допустимые:
        # первый символ буква/цифра, набор [A-Za-z0-9._-]).
        tricky = [
            ("5--x", "0"),
            ("0", "12--34"),
            ("a--", "b--"),
            ("ab--", "b--a"),
            ("123", "456"),
            ("s1", "s2--3--4--5"),
            ("7x", "7--7--"),
            ("1--1", "1--1"),
        ]
        for s1, s2 in tricky:
            name = ss.encode_state_filename(s1, s2)
            assert ss.decode_state_filename(name) == (s1, s2)

    def test_previous_colliding_pairs_are_independent_files(
            self, manager, store_path):
        """ТЗ Stage B.1 §6.1: две пары, ранее дававшие одно имя файла,
        теперь создаются независимо."""
        st1 = manager.get_state(*COLLIDING_PAIR_1, config_hash=HASH_A)
        st2 = manager.get_state(*COLLIDING_PAIR_2, config_hash=HASH_B)
        # Две разные записи, два разных файла, старого имени не существует.
        assert st1.key() == COLLIDING_PAIR_1
        assert st2.key() == COLLIDING_PAIR_2
        names = listdir_names(store_path)
        assert len(names) == 2
        assert names == sorted([
            ss.encode_state_filename(*COLLIDING_PAIR_1),
            ss.encode_state_filename(*COLLIDING_PAIR_2)])
        # Имя старого формата отсутствует: скрытой миграции/совмещения нет.
        assert "alpha__beta__FIGI1.json" not in names

    def test_write_first_pair_does_not_change_second(
            self, manager, store_path):
        """ТЗ Stage B.1 §6.2: запись первой пары не меняет запись второй."""
        manager.get_state(*COLLIDING_PAIR_1, config_hash=HASH_A)
        manager.get_state(*COLLIDING_PAIR_2, config_hash=HASH_B)
        second_before = read_bytes(store_path, *COLLIDING_PAIR_2)
        for step in range(3):
            manager.update_state(*COLLIDING_PAIR_1, config_hash=HASH_A,
                                 data={"step": step})
        assert read_bytes(store_path, *COLLIDING_PAIR_2) == second_before

    def test_read_second_pair_returns_second_state(
            self, manager, store_path):
        """ТЗ Stage B.1 §6.3: чтение второй пары не возвращает состояние
        первой."""
        manager.update_state(*COLLIDING_PAIR_1, config_hash=HASH_A,
                             data={"owner": "first", "n": 10})
        manager.update_state(*COLLIDING_PAIR_2, config_hash=HASH_B,
                             data={"owner": "second", "n": 20})
        st1 = manager.get_state(*COLLIDING_PAIR_1, config_hash=HASH_A)
        st2 = manager.get_state(*COLLIDING_PAIR_2, config_hash=HASH_B)
        assert dict(st1.data) == {"owner": "first", "n": 10}
        assert dict(st2.data) == {"owner": "second", "n": 20}
        assert st2.config_hash == HASH_B
        assert st2.key() == COLLIDING_PAIR_2

    def test_list_states_returns_both_pairs(self, manager):
        """ТЗ Stage B.1 §6.4: list_states() возвращает обе пары."""
        manager.update_state(*COLLIDING_PAIR_1, config_hash=HASH_A,
                             data={"n": 1})
        manager.update_state(*COLLIDING_PAIR_2, config_hash=HASH_B,
                             data={"n": 2})
        keys = [st.key() for st in manager.list_states()]
        assert keys == sorted([COLLIDING_PAIR_1, COLLIDING_PAIR_2])
        assert len(keys) == 2

    def test_boundary_valid_strings_no_collisions(self, store):
        """ТЗ Stage B.1 §6.8: коллизий нет на граничных допустимых строках.

        Границы: максимальная длина (128/64), одиночный символ, только
        цифры, точки/дефисы/подчёркивания, строки, похожие на префикс
        длины ('5--x'), и «вложенные» коллизионные комбинации.
        """
        sid_max = "s" + "a" * 127           # 128 символов
        figi_max = "F" + "9" * 63           # 64 символа
        pairs = [
            ("s", "f"),
            ("s", "f.json"[:7]),            # точка внутри допустимого
            ("0", "0"),
            ("9" * 128, "8" * 64),
            (sid_max, figi_max),
            ("5--x", "12--34"),
            ("alpha__beta", "FIGI1"),
            ("alpha", "beta__FIGI1"),
            ("a--b", "c--d"),
            ("x", "y__z__w"),
            ("y__z", "w"),
            ("n1", "n2"),
            ("n1__n2", "n3"),
            ("n1", "n2__n3"),
        ]
        names = [ss.encode_state_filename(s, f) for s, f in pairs]
        # Инъективность на наборе: все имена различны.
        assert len(set(names)) == len(names)
        # Обратимость на наборе.
        for (s, f), name in zip(pairs, names):
            assert ss.decode_state_filename(name) == (s, f)
        # Файловый уровень: все пары живут в одном хранилище независимо.
        for i, (s, f) in enumerate(pairs):
            store.update_state(s, f, config_hash=HASH_A,
                               data={"index": i})
        states = store.list_states()
        assert [st.key() for st in states] == sorted(pairs)
        for i, (s, f) in enumerate(pairs):
            st = store.get_state(s, f)
            assert dict(st.data) == {"index": i}

    def test_filename_length_limit_is_filesystem_safe(self, store_path):
        sid_max = "s" + "a" * 127
        figi_max = "F" + "9" * 63
        name = ss.encode_state_filename(sid_max, figi_max)
        assert len(name) <= 255  # предел имени файла на распространённых ФС
        store = ss.StateStore(path=store_path)
        store.create_state(sid_max, figi_max, HASH_A)
        assert listdir_names(store_path) == [name]
        assert store.get_state(sid_max, figi_max) is not None

    def test_old_format_filename_is_not_silently_used_or_migrated(
            self, store, store_path):
        """Скрытой миграции старого формата НЕТ: старое имя не читается
        как запись нового формата и не переписывается.

        _load ищет ТОЛЬКО новое имя -> старый файл не виден как запись
        (get_state -> None, отсутствие записи — нормальная ситуация);
        list_states обнаруживает неформатное имя как повреждение
        (fail-closed, без молчаливого пропуска и без автоматической
        миграции/удаления).
        """
        st = ss.StrategyState.create(
            "alpha__beta", "FIGI1", HASH_A, data={"old": True},
            now=STAMP_T1)
        legacy_name = "alpha__beta__FIGI1.json"  # старый неинъективный шаблон
        with open(os.path.join(store_path, legacy_name), "w",
                  encoding="utf-8") as handle:
            handle.write(st.to_json())
        legacy_bytes = read_legacy = open(
            os.path.join(store_path, legacy_name), "rb").read()
        # Новое имя для этой пары другое: старая запись не видна (нет
        # скрытой миграции), состояние не переписывается.
        assert store.get_state("alpha__beta", "FIGI1") is None
        with open(os.path.join(store_path, legacy_name), "rb") as handle:
            assert handle.read() == read_legacy
        # Неформатное имя обнаруживается при перечислении (fail-closed).
        with pytest.raises(ss.StateCorruptionError):
            store.list_states()
        assert legacy_bytes  # файл не удалён и не изменён

    def test_decode_rejects_garbage_names(self):
        bad_names = [
            "",
            "notes.json",
            "s_a__FIGI_X.json",          # старый формат
            ".tmp-state-x.json",
            "12--abc.json",              # нет второй компоненты
            "12--abc--5.json",           # нет второго префикса длины
            "12--abc--x--def.json",      # второй префикс не число
            "x--abc--2--de.json",        # первый префикс не число
            "3--ab--2--cd.json",         # длина strategy_id не совпадает
            "4--abc--2--cd.json",        # длина strategy_id не совпадает
            "3--abc--2--cde.json",       # длина figi не совпадает
            "3--abc--2--cd.json.bak",    # неверный суффикс
        ]
        for name in bad_names:
            with pytest.raises(ss.StateCorruptionError):
                ss.decode_state_filename(name)

    def test_list_states_detects_old_and_foreign_names(self, store_path):
        """Файлы, не декодируемые алгоритмом Stage B.1 (старый формат,
        чужие имена), обнаруживаются при list_states — не пропускаются
        молча и не маскируются."""
        store = ss.StateStore(path=store_path)
        store.create_state("s_a", "FIGI_X", HASH_A)
        with open(os.path.join(store_path, "s_a__FIGI_X.json"), "w",
                  encoding="utf-8") as handle:
            handle.write("{}")  # старое имя + произвольное содержимое
        with pytest.raises(ss.StateCorruptionError):
            store.list_states()


# ---------------------------------------------------------------------------
# ДЕФЕКТ №2 — проверка ключа после чтения
# ---------------------------------------------------------------------------


class TestPostReadKeyVerification:
    def _make_tampered_payload(self, sid, figi, foreign_sid=None,
                               foreign_figi=None):
        payload = ss.StrategyState.create(
            sid, figi, HASH_A, data={"n": 1}, now=STAMP_T1).to_payload()
        if foreign_sid is not None:
            payload["strategy_id"] = foreign_sid
        if foreign_figi is not None:
            payload["figi"] = foreign_figi
        return payload

    def test_foreign_strategy_id_detected(self, store, store_path):
        """ТЗ Stage B.1 §6.5: подмена содержимого файла чужим strategy_id
        обнаруживается."""
        name = ss.encode_state_filename("s_a", "FIGI_X")
        with open(os.path.join(store_path, name), "w",
                  encoding="utf-8") as handle:
            json.dump(self._make_tampered_payload(
                "s_a", "FIGI_X", foreign_sid="s_evil"), handle)
        with pytest.raises(ss.StateCorruptionError):
            store.get_state("s_a", "FIGI_X")
        with pytest.raises(ss.StateCorruptionError):
            store.get_state("s_a", "FIGI_X", config_hash=HASH_A)
        # Состояние не возвращается и в менеджере; запись не создаётся.
        manager = ss.StrategyStateManager(store)
        with pytest.raises(ss.StateCorruptionError):
            manager.get_state("s_a", "FIGI_X", config_hash=HASH_A)
        with pytest.raises(ss.StateCorruptionError):
            manager.update_state("s_a", "FIGI_X", config_hash=HASH_A,
                                 data={"n": 2})

    def test_foreign_figi_detected(self, store, store_path):
        """ТЗ Stage B.1 §6.6: подмена содержимого файла чужим FIGI
        обнаруживается."""
        name = ss.encode_state_filename("s_a", "FIGI_X")
        with open(os.path.join(store_path, name), "w",
                  encoding="utf-8") as handle:
            json.dump(self._make_tampered_payload(
                "s_a", "FIGI_X", foreign_figi="FIGI_EVIL"), handle)
        with pytest.raises(ss.StateCorruptionError):
            store.get_state("s_a", "FIGI_X")

    def test_verification_error_does_not_modify_file(self, store,
                                                     store_path):
        """ТЗ Stage B.1 §6.7: ошибка проверки не изменяет исходный файл."""
        name = ss.encode_state_filename("s_a", "FIGI_X")
        tampered = json.dumps(self._make_tampered_payload(
            "s_a", "FIGI_X", foreign_sid="s_evil"))
        with open(os.path.join(store_path, name), "w",
                  encoding="utf-8") as handle:
            handle.write(tampered)
        before = read_bytes(store_path, "s_a", "FIGI_X")
        with pytest.raises(ss.StateCorruptionError):
            store.get_state("s_a", "FIGI_X")
        with pytest.raises(ss.StateCorruptionError):
            store.update_state("s_a", "FIGI_X", config_hash=HASH_A,
                               data={"n": 9})
        with pytest.raises(ss.StateCorruptionError):
            store.list_states()
        after = read_bytes(store_path, "s_a", "FIGI_X")
        assert before == after == tampered.encode("utf-8")
        # Файл не исправлен, не заменён пустой записью, не удалён.
        assert listdir_names(store_path) == [name]

    def test_save_state_does_not_silently_overwrite_foreign_content(
            self, store, store_path):
        """save_state не переписывает повреждённую/подменённую запись:
        чтение существующей записи даёт StateCorruptionError."""
        name = ss.encode_state_filename("s_a", "FIGI_X")
        with open(os.path.join(store_path, name), "w",
                  encoding="utf-8") as handle:
            json.dump(self._make_tampered_payload(
                "s_a", "FIGI_X", foreign_figi="FIGI_EVIL"), handle)
        fresh = ss.StrategyState.create(
            "s_a", "FIGI_X", HASH_A, data={"n": 5}, now=STAMP_T1)
        with pytest.raises(ss.StateCorruptionError):
            store.save_state("s_a", "FIGI_X", fresh)

    def test_key_check_in_memory_mode_unified_contract(self):
        """Единый контракт: проверка ключа после чтения выполняется и в
        memory-режиме (рассинхронизация содержимого и ключа хранения
        обнаруживается)."""
        store = ss.StateStore()
        st = ss.StrategyState.create(
            "s_evil", "FIGI_X", HASH_A, data={"n": 1}, now=STAMP_T1)
        # Белый ящик: имитация рассинхронизации внутренней записи.
        store._records[("s_a", "FIGI_X")] = st
        with pytest.raises(ss.StateCorruptionError):
            store.get_state("s_a", "FIGI_X")
        with pytest.raises(ss.StateCorruptionError):
            store.list_states()
        with pytest.raises(ss.StateCorruptionError):
            store.update_state("s_a", "FIGI_X", config_hash=HASH_A,
                               data={"n": 2})

    def test_create_state_detects_foreign_content(self, store, store_path):
        """create_state не маскирует подмену чужим ключом как
        StateAlreadyExistsError: сначала обнаруживается повреждение."""
        name = ss.encode_state_filename("s_a", "FIGI_X")
        with open(os.path.join(store_path, name), "w",
                  encoding="utf-8") as handle:
            json.dump(self._make_tampered_payload(
                "s_a", "FIGI_X", foreign_sid="s_evil"), handle)
        with pytest.raises(ss.StateCorruptionError):
            store.create_state("s_a", "FIGI_X", HASH_A)


# ---------------------------------------------------------------------------
# ДЕФЕКТ №3 — атомарный read-modify-write между менеджерами
# ---------------------------------------------------------------------------


def increment_updater(current):
    return {"n": current.data.get("n", 0) + 1}


class TestCrossManagerAtomicRMW:
    def test_two_managers_one_store_parallel_updaters_no_lost_update(
            self, store):
        """ТЗ Stage B.1 §6.9: два менеджера с одним StateStore выполняют
        параллельные updater-операции без потери обновлений.

        Атомарность обеспечивает RLock ХРАНИЛИЩА (StateStore.update_state),
        а не локальные RLock менеджеров: 2 менеджера x 4 потока x 25
        инкрементов = ровно 200.
        """
        mgr1 = ss.StrategyStateManager(store)
        mgr2 = ss.StrategyStateManager(store)

        def worker(task):
            mgr, _ = task
            for _ in range(25):
                mgr.update_state("s_a", "FIGI_X", config_hash=HASH_A,
                                 updater=increment_updater)

        tasks = [(mgr1, i) for i in range(4)] + [(mgr2, i) for i in range(4)]
        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(worker, tasks))

        final = store.get_state("s_a", "FIGI_X")
        assert final.data["n"] == 200  # ни одно обновление не потеряно

    def test_repeated_concurrent_run_is_deterministic(self, store_path):
        """ТЗ Stage B.1 §6.10: повторный конкурентный тест даёт
        детерминированный итог — одинаковое число инкрементов и
        побайтово одинаковую запись (метки времени фиксированы)."""
        results = []
        for _ in range(2):
            path = f"{store_path}_run{len(results)}"
            store = ss.StateStore(path=path)
            # Фиксированный «часы» менеджеров: метки времени записей
            # детерминированы, сравниваются байты, а не только данные.
            mgr1 = ss.StrategyStateManager(store, clock=lambda: STAMP_T1)
            mgr2 = ss.StrategyStateManager(store, clock=lambda: STAMP_T1)

            def worker(task):
                mgr, i = task
                for step in range(20):
                    mgr.update_state("s_a", "FIGI_X", config_hash=HASH_A,
                                     updater=increment_updater,
                                     now=STAMP_T1)

            tasks = [(mgr1, i) for i in range(3)] + \
                    [(mgr2, i) for i in range(3)]
            with ThreadPoolExecutor(max_workers=6) as pool:
                list(pool.map(worker, tasks))
            final = store.get_state("s_a", "FIGI_X")
            assert final.data["n"] == 6 * 20
            results.append(read_bytes(path, "s_a", "FIGI_X"))
        # Детерминированный итог: обе гонки дали байт-в-байт одну запись.
        assert results[0] == results[1]

    def test_updater_error_in_store_update_leaves_state_unchanged(
            self, store, store_path):
        """ТЗ Stage B.1 §6.11: ошибка updater не меняет сохранённое
        состояние (store.update_state)."""
        store.update_state("s_a", "FIGI_X", config_hash=HASH_A,
                           data={"n": 1}, now=STAMP_T1)
        before = read_bytes(store_path, "s_a", "FIGI_X")

        def failing_updater(current):
            assert current.data["n"] == 1
            raise RuntimeError("updater failed")

        with pytest.raises(RuntimeError):
            store.update_state("s_a", "FIGI_X", config_hash=HASH_A,
                               updater=failing_updater)
        after = read_bytes(store_path, "s_a", "FIGI_X")
        assert before == after
        assert dict(store.get_state("s_a", "FIGI_X").data) == {"n": 1}

        # Не-отображение в результате updater — StateValidationError,
        # запись тоже не меняется.
        with pytest.raises(ss.StateValidationError):
            store.update_state("s_a", "FIGI_X", config_hash=HASH_A,
                               updater=lambda cur: [1, 2])
        assert read_bytes(store_path, "s_a", "FIGI_X") == before

    def test_updater_error_via_manager_leaves_state_unchanged(
            self, manager, store_path):
        """Ошибка updater через менеджер не меняет состояние (путь
        manager -> store.update_state)."""
        manager.update_state("s_a", "FIGI_X", config_hash=HASH_A,
                             data={"n": 1}, now=STAMP_T1)
        before = read_bytes(store_path, "s_a", "FIGI_X")
        with pytest.raises(RuntimeError):
            manager.update_state("s_a", "FIGI_X", config_hash=HASH_A,
                                 updater=lambda cur: (_ for _ in ()).throw(
                                     RuntimeError("boom")))
        assert read_bytes(store_path, "s_a", "FIGI_X") == before

    def test_store_update_state_config_mismatch_rejected_before_updater(
            self, store, store_path):
        """Несовпадение config_hash в store.update_state отклоняется ДО
        вызова updater; запись не изменяется."""
        store.update_state("s_a", "FIGI_X", config_hash=HASH_A,
                           data={"n": 1}, now=STAMP_T1)
        before = read_bytes(store_path, "s_a", "FIGI_X")
        called = []

        def updater(current):
            called.append(current)
            return {"n": 999}

        with pytest.raises(ss.StateConfigMismatchError):
            store.update_state("s_a", "FIGI_X", config_hash=HASH_B,
                               updater=updater)
        assert called == []  # updater не вызывался
        assert read_bytes(store_path, "s_a", "FIGI_X") == before
        assert dict(store.get_state("s_a", "FIGI_X").data) == {"n": 1}

    def test_store_update_state_creates_missing_pair_atomically(
            self, store):
        """store.update_state на отсутствующей записи создаёт её в той же
        атомарной операции; created_at/updated_at — из created_now/now."""
        st = store.update_state(
            "s_a", "FIGI_X", config_hash=HASH_A,
            data={"n": 1}, now=STAMP_T2, created_now=STAMP_T1)
        assert st.created_at == STAMP_T1
        assert st.updated_at == STAMP_T2
        assert dict(st.data) == {"n": 1}
        # Повторное создание не происходит: существующая запись обновлена.
        st2 = store.update_state(
            "s_a", "FIGI_X", config_hash=HASH_A,
            data={"n": 2}, now=STAMP_T2, created_now=STAMP_T1)
        assert st2.created_at == STAMP_T1
        assert len(store.list_states()) == 1

    def test_get_or_create_atomic_across_managers(self, store):
        """get_or_create атомарен относительно нескольких менеджеров:
        12 потоков двух менеджеров на отсутствующей паре -> одна запись,
        все потоки получили одно состояние."""
        mgr1 = ss.StrategyStateManager(store)
        mgr2 = ss.StrategyStateManager(store)

        def worker(task):
            mgr, _ = task
            return mgr.get_state("s_a", "FIGI_X", config_hash=HASH_A)

        tasks = [(mgr1, i) for i in range(6)] + [(mgr2, i) for i in range(6)]
        with ThreadPoolExecutor(max_workers=12) as pool:
            results = list(pool.map(worker, tasks))
        assert len(results) == 12
        assert all(st.key() == ("s_a", "FIGI_X") for st in results)
        assert all(st.config_hash == HASH_A for st in results)
        assert len(store.list_states()) == 1

    def test_store_update_state_requires_exactly_one_data_source(self, store):
        with pytest.raises(ss.StateValidationError):
            store.update_state("s_a", "FIGI_X", config_hash=HASH_A)
        with pytest.raises(ss.StateValidationError):
            store.update_state("s_a", "FIGI_X", config_hash=HASH_A,
                               data={"n": 1},
                               updater=lambda cur: {"n": 2})

    def test_manager_and_store_updates_share_one_atomic_path(
            self, manager, store):
        """Менеджер и прямые операции хранилища сериализуются одним
        замком: смешанные инкременты дают точный итог."""
        manager.update_state("s_a", "FIGI_X", config_hash=HASH_A,
                             data={"n": 0})

        def worker(task):
            kind, _ = task
            if kind == "mgr":
                manager.update_state("s_a", "FIGI_X", config_hash=HASH_A,
                                     updater=increment_updater)
            else:
                store.update_state("s_a", "FIGI_X", config_hash=HASH_A,
                                   updater=increment_updater)

        tasks = ([("mgr", i) for i in range(30)] +
                 [("store", i) for i in range(30)])
        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(worker, tasks))
        assert store.get_state("s_a", "FIGI_X").data["n"] == 60

    def test_parallel_distinct_pairs_two_managers_isolated(self, store):
        """ТЗ Stage B.1 §6 (доп.): независимость разных пар при
        параллельной работе — два менеджера работают по ВСЕМ парам
        вперемешку (включая ранее коллизионные), каждая пара содержит
        только свои данные."""
        pairs = [COLLIDING_PAIR_1, COLLIDING_PAIR_2,
                 ("s_1", "FIGI_1"), ("s_2", "FIGI_2"),
                 ("s_1", "FIGI_3"), ("s_2__x", "FIGI_4"),
                 ("s_2", "x__FIGI_5"), ("s_3", "F.1-2_3")]
        mgr1 = ss.StrategyStateManager(store)
        mgr2 = ss.StrategyStateManager(store)

        def worker(task):
            mgr, i = task
            sid, figi = pairs[i % len(pairs)]
            for step in range(10):
                mgr.update_state(sid, figi, config_hash=HASH_A,
                                 data={"owner": i % len(pairs),
                                       "step": step})
                st = mgr.get_state(sid, figi, config_hash=HASH_A)
                assert st.data["owner"] == i % len(pairs)

        tasks = [(mgr1, i) for i in range(16)] + [(mgr2, i) for i in range(16)]
        with ThreadPoolExecutor(max_workers=10) as pool:
            list(pool.map(worker, tasks))

        assert len(store.list_states()) == len(pairs)
        for i, (sid, figi) in enumerate(pairs):
            st = store.get_state(sid, figi)
            assert st.data["owner"] == i
            assert st.data["step"] == 9

    def test_shared_path_lock_serializes_two_store_instances(
            self, store_path):
        """Два экземпляра StateStore на одном пути одного процесса
        разделяют один RLock (усиление Stage B.1): параллельные
        инкременты через РАЗНЫЕ экземпляры не теряются."""
        store1 = ss.StateStore(path=store_path)
        store2 = ss.StateStore(path=store_path)
        assert store1._lock is store2._lock  # один разделяемый замок

        def worker(i):
            target = store1 if i % 2 == 0 else store2
            for _ in range(15):
                target.update_state("s_a", "FIGI_X", config_hash=HASH_A,
                                    updater=increment_updater)

        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(worker, range(8)))
        assert store1.get_state("s_a", "FIGI_X").data["n"] == 8 * 15

    def test_concurrent_updates_of_previously_colliding_pairs(
            self, store):
        """Параллельная работа именно на ранее коллизионных парах:
        обновления не пересекаются (дефект №1 закрыт и под нагрузкой)."""
        mgr1 = ss.StrategyStateManager(store)
        mgr2 = ss.StrategyStateManager(store)

        def worker(task):
            mgr, i = task
            sid, figi = COLLIDING_PAIR_1 if i % 2 == 0 else COLLIDING_PAIR_2
            for step in range(15):
                mgr.update_state(sid, figi, config_hash=HASH_A,
                                 updater=increment_updater)
                st = mgr.get_state(sid, figi, config_hash=HASH_A)
                assert st.data["n"] >= step

        tasks = ([(mgr1, i) for i in range(4)] +
                 [(mgr2, i) for i in range(4)])
        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(worker, tasks))
        # Итог детерминирован: 4 потока x 15 инкрементов на каждую пару.
        assert store.get_state(*COLLIDING_PAIR_1).data["n"] == 60
        assert store.get_state(*COLLIDING_PAIR_2).data["n"] == 60

    def test_manager_updater_reentrancy_same_store_allowed(self, store):
        """Повторный вход в ТО ЖЕ хранилище из updater разрешён (RLock
        реентерабелен): взаимных блокировок нет."""
        store.update_state("s_a", "FIGI_X", config_hash=HASH_A,
                           data={"n": 1})

        def reentrant_updater(current):
            # Чтение и обновление ДРУГОЙ пары того же хранилища из
            # updater того же потока (get_or_create — тоже атомарная
            # операция этого же хранилища; RLock реентерабелен).
            other = store.get_or_create("s_b", "FIGI_X",
                                        config_hash=HASH_A)
            assert other is not None
            store.update_state("s_b", "FIGI_X", config_hash=HASH_A,
                               data={"seen": current.data["n"]})
            return {"n": current.data["n"] + 1}

        st = store.update_state("s_a", "FIGI_X", config_hash=HASH_A,
                                updater=reentrant_updater)
        assert st.data["n"] == 2
        assert dict(store.get_state("s_b", "FIGI_X").data) == {"seen": 1}

    def test_concurrent_operations_survive_repeated_scheduling(
            self, store):
        """Повтор серии конкурентных смешанных операций даёт тот же
        инвариант: итог каждой пары зависит только от её операций."""
        for _ in range(2):
            store.reset_state("s_a", "FIGI_X")
            store.reset_state("s_b", "FIGI_X")

            def worker(task):
                kind, i = task
                sid = "s_a" if i % 2 == 0 else "s_b"
                if kind == "inc":
                    store.update_state(sid, "FIGI_X", config_hash=HASH_A,
                                       updater=increment_updater)
                else:
                    st = store.get_state(sid, "FIGI_X",
                                         config_hash=HASH_A)
                    assert st.data.get("n", 0) >= 0

            tasks = ([("inc", i) for i in range(24)] +
                     [("read", i) for i in range(12)])
            with ThreadPoolExecutor(max_workers=6) as pool:
                list(pool.map(worker, tasks))
            # 12 инкрементов на каждую пару за каждый повтор.
            assert store.get_state("s_a", "FIGI_X").data["n"] == 12
            assert store.get_state("s_b", "FIGI_X").data["n"] == 12


# ---------------------------------------------------------------------------
# Контракт Stage B не сломан (интеграция Stage A без изменений)
# ---------------------------------------------------------------------------


class TestStageBContractPreserved:
    def test_public_interface_unchanged(self):
        """Минимальный интерфейс StateStore (ТЗ Stage B §3.2) сохранён;
        атомарные get_or_create/update_state — ДОПОЛНЕНИЕ Stage B.1."""
        for method in ("get_state", "save_state", "create_state",
                       "reset_state", "list_states"):
            assert callable(getattr(ss.StateStore, method))
        for method in ("get_or_create", "update_state"):
            assert callable(getattr(ss.StateStore, method))

    def test_filename_encoding_documented_constants(self):
        """Алгоритм кодирования фиксируется функциями модуля и
        обратим (контракт Stage B.1 §3.1)."""
        name = ss.encode_state_filename("s_a", "FIGI_X")
        assert name.endswith(".json")
        assert ss.decode_state_filename(name) == ("s_a", "FIGI_X")
