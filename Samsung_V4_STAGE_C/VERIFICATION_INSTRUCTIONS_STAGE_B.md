# VERIFICATION_INSTRUCTIONS_STAGE_B.md
# Инструкции проверки Stage B (актуально для Stage B.1)

Дата: 2026-11-28. Пакет: `Samsung_V4_STAGE_B` (Stage B + коррекция B.1).

## 1. Целостность пакета

```bash
# 1.1. SHA256-манифест: все файлы candidate/ идентичны пакету Stage B,
#      кроме двух изменённых и одного нового (Stage B.1); файлы Stage
#      A.2.1 и торговые — «НЕ ИЗМЕНЁН». Выборочная перепроверка:
sha256sum candidate/strategy_state.py
sha256sum candidate/main.py          # сравнить с манифестом (НЕ ИЗМЕНЁН)
sha256sum candidate/engine.json      # сравнить с манифестом (НЕ ИЗМЕНЁН)

# 1.2. Отсутствие иных изменений (на машине с копиями Stage B и Stage B.1):
diff -rq Samsung_V4_STAGE_B/candidate Samsung_V4_STAGE_B_1/candidate
# ожидаемо: ровно два «Files ... differ» (strategy_state.py,
# test_stage_b_state_isolation.py) и один «Only in ...:
# test_stage_b1_state_key_and_concurrency.py»

# 1.3. Применение diff Stage B -> B.1 (проверка воспроизводимости):
cp -a Samsung_V4_STAGE_B /tmp/verify_b1 && cd /tmp/verify_b1
patch -p1 --dry-run < DIFF_STAGE_B_VS_B_1.patch     # вперёд: без ошибок
patch -R -p1 --dry-run < DIFF_STAGE_B_VS_B_1.patch  # назад: без ошибок
```

## 2. Регрессия (offline)

```bash
cd Samsung_V4_STAGE_B/candidate
python -m pytest            # полный набор: ожидается 1261 passed
python -m pytest tests      # канонический поднабор: ожидается 741 passed
python -m pytest tests/test_stage_b_state_isolation.py            # 115 passed
python -m pytest tests/test_stage_b1_state_key_and_concurrency.py # 33 passed
```

Числа ДО / ПОСЛЕ Stage B.1 (ТЗ B.1 §8):

| Прогон | До B.1 (Stage B) | После B.1 | Δ |
|---|---|---|---|
| полный (`python -m pytest`) | 1228 passed | **1261 passed** | +33 |
| канонический (`python -m pytest tests`) | 708 passed | **741 passed** | +33 |

Требования регрессии ТЗ §6 (Stage B) и §8 (Stage B.1) и их проверка:

* все тесты Stage A.2.1 проходят — см. разделы 1–2
  `TEST_RESULTS_STAGE_B.txt` (1113 → 1228 → 1261; полный список
  node id в логах `-v`);
* все 115 тестов Stage B сохранены — сравнение полных списков тестов
  «до»/«после»: удалено 0, ослаблено 0, добавлено ровно 33 (все — в
  новом файле B.1); единственные правки старого тестового файла —
  построение имён файлов новым (заданным ТЗ B.1 §3) алгоритмом,
  семантика утверждений сохранена (см. `DIFF_STAGE_B_VS_B_1.md`);
* golden fixtures не перегенерировались — SHA256
  `candidate/tests/fixtures/*` совпадают с принятым Stage A.2.1
  (манифест, раздел III);
* старые профили сохранены — `strategies/legacy_samsung_v4/`
  НЕ ИЗМЕНЁН (манифест, раздел IV);
* config_hash Stage A не меняется — тесты
  `tests/test_stage_a2_config_hash_integrity.py` и
  `tests/test_stage_a2_1_context_integrity.py` проходят без изменений;
* атрибуция Stage A корректна — тесты
  `tests/test_stage_a_attribution.py`, `test_stage_a1_attribution_explicit.py`;
* никаких скрытых fallback/автосбросов — тесты
  `TestNoHiddenPathFallback`, `TestConfigHashMismatch`,
  `TestCorruptionDetection`.

## 3. Проверка обязательных сценариев Stage B (ТЗ §4)

```bash
python -m pytest tests/test_stage_b_state_isolation.py -v
```

16 обязательных сценариев → классы тестов (трассировка —
`STAGE_B_ARCHITECTURE_REPORT.md`, раздел 8):

| ТЗ §4 | Класс тестов |
|---|---|
| 1. Две стратегии на одном FIGI | `TestTwoStrategiesSameFigi` |
| 2. Одна стратегия на двух FIGI | `TestOneStrategyTwoFigi` |
| 3. Изменение одной пары не меняет остальные | `TestChangeOnePairOnly` |
| 4. Создание новой пары изолировано | `TestNewPairDoesNotTouchExisting` |
| 5. Перезапуск/восстановление | `TestRestartPersistence` |
| 6. Детерминированная сериализация | `TestDeterministicSerialization` |
| 7. Повреждённая запись | `TestCorruptionDetection` |
| 8. Неизвестная версия схемы | `TestUnknownSchemaVersion` |
| 9. Несовпадающий config_hash | `TestConfigHashMismatch` |
| 10. Отсутствие записи | `TestMissingRecord` |
| 11. Reset только выбранной пары | `TestExplicitResetScope` |
| 12. Конкурентные операции | `TestConcurrency` |
| 13. Защита возвращённых объектов | `TestReturnedObjectIsolation` |
| 14. Совместимость со Stage A | `TestStageACompatibility` |
| 15. Невалидные ключи | `TestInvalidKeys` |
| 16. Нет скрытого пути | `TestNoHiddenPathFallback` |

## 3.1. Проверка обязательных тестов Stage B.1 (ТЗ B.1 §6)

```bash
python -m pytest tests/test_stage_b1_state_key_and_concurrency.py -v
```

12 обязательных пунктов → тесты (трассировка —
`STAGE_B_ARCHITECTURE_REPORT.md`, раздел 13):

| ТЗ B.1 §6 | Тесты |
|---|---|
| 1. Ранее коллизионные пары независимы | `test_previous_colliding_pairs_are_independent_files`, `test_encode_differs_for_previously_colliding_pairs` |
| 2. Запись первой пары не меняет вторую | `test_write_first_pair_does_not_change_second` |
| 3. Чтение второй пары не возвращает первую | `test_read_second_pair_returns_second_state` |
| 4. list_states возвращает обе пары | `test_list_states_returns_both_pairs` |
| 5. Чужой strategy_id обнаруживается | `test_foreign_strategy_id_detected` |
| 6. Чужой FIGI обнаруживается | `test_foreign_figi_detected` |
| 7. Ошибка проверки не меняет файл | `test_verification_error_does_not_modify_file` |
| 8. Границы без коллизий | `test_boundary_valid_strings_no_collisions` (+ round-trip, лимит длины) |
| 9. Два менеджера, RMW без потерь | `test_two_managers_one_store_parallel_updaters_no_lost_update` |
| 10. Повтор конкурентного теста детерминирован | `test_repeated_concurrent_run_is_deterministic` |
| 11. Ошибка updater не меняет состояние | `test_updater_error_in_store_update_leaves_state_unchanged`, `test_updater_error_via_manager_leaves_state_unchanged` |
| 12. Старые тесты проходят | полный регресс: 1228 → 1261 passed, удалено 0 |
| доп. Независимость разных пар при параллельной работе | `test_parallel_distinct_pairs_two_managers_isolated`, `test_concurrent_updates_of_previously_colliding_pairs` |

## 4. Ручная offline-демонстрация изоляции

```python
# python -i (из каталога candidate/)
import tempfile
from strategy_api import StrategyConfig, compute_config_hash
from strategy_state import StateStore, StrategyStateManager, \
    StateConfigMismatchError, StateCorruptionError

def cfg(sid, length):
    p = {"length": length}
    return StrategyConfig(strategy_id=sid, strategy_version="v1",
                          params=p,
                          config_hash=compute_config_hash(sid, "v1", p))

tmp = tempfile.mkdtemp()
mgr = StrategyStateManager(StateStore(path=tmp))

# Изоляция пар:
mgr.update_state("s_a", "FIGI_X", config=cfg("s_a", 14), data={"n": 1})
mgr.get_state("s_b", "FIGI_X", config=cfg("s_b", 21)).data == {}   # True
mgr.get_state("s_a", "FIGI_Y", config=cfg("s_a", 14)).data == {}   # True

# Перезапуск:
mgr2 = StrategyStateManager(StateStore(path=tmp))
mgr2.get_state("s_a", "FIGI_X", config=cfg("s_a", 14)).data        # {'n': 1}

# Fail-closed при смене конфигурации:
try:
    mgr2.get_state("s_a", "FIGI_X", config=cfg("s_a", 21))
except StateConfigMismatchError as e:
    print(e)   # требуется ЯВНОЕ решение — reset_state или совместимость

# Явный reset снимает конфликт:
mgr2.reset_state("s_a", "FIGI_X")
mgr2.get_state("s_a", "FIGI_X", config=cfg("s_a", 21)).data == {}  # True
```

## 5. Проверка отсутствия сетевых/брокерских действий

* Все тесты Stage B/B.1 выполняют файловый ввод/вывод ТОЛЬКО в
  `tmp_path` pytest и явный путь хранилища; сетевые сокеты не
  открываются (в `strategy_state.py` нет сетевого кода).
* `grep -rn "FORCE_TRADE\|sandbox\|place_order\|requests\|urllib" \
  candidate/strategy_state.py` — совпадений нет.
* Старые файлы Samsung не затрагиваются — тест
  `test_store_does_not_touch_old_samsung_files` создаёт state.json и
  проверяет их SHA256 до/после операций Stage B.

## 6. Проверка исправлений Stage B.1 вручную (offline)

```python
# python -i (из каталога candidate/)
import strategy_state as ss

# Дефект №1: инъективность имён (раньше обе пары давали одно имя):
n1 = ss.encode_state_filename("alpha__beta", "FIGI1")
n2 = ss.encode_state_filename("alpha", "beta__FIGI1")
n1 == n2                       # False (было True у старого шаблона)
ss.decode_state_filename(n1)   # ('alpha__beta', 'FIGI1')

# Дефект №3: два менеджера, один store, параллельные инкременты:
import os, tempfile
from concurrent.futures import ThreadPoolExecutor
with tempfile.TemporaryDirectory() as tmp:
    store = ss.StateStore(path=os.path.join(tmp, "st"))
    m1 = ss.StrategyStateManager(store)
    m2 = ss.StrategyStateManager(store)
    def inc(task):
        m, _ = task
        for _ in range(50):
            m.update_state("s", "F", config_hash="a"*64,
                           updater=lambda c: {"n": c.data.get("n", 0) + 1})
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(inc, [(m1, i) for i in range(4)] +
                           [(m2, i) for i in range(4)]))
    store.get_state("s", "F").data["n"]   # ровно 400: ни одно не потеряно
```
