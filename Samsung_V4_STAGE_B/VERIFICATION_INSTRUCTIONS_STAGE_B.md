# VERIFICATION_INSTRUCTIONS_STAGE_B.md
# Инструкции проверки Stage B

Дата: 2026-11-28. Пакет: `Samsung_V4_STAGE_B`.

## 1. Целостность пакета

```bash
# 1.1. SHA256-манифест: все файлы candidate/ идентичны принятой A.2.1,
#      кроме двух новых; запрещённые области — «НЕ ИЗМЕНЁН».
#      Файл FILE_MANIFEST_SHA256_STAGE_B.txt содержит готовые хеши;
#      выборочная перепроверка:
sha256sum candidate/strategy_state.py
sha256sum candidate/main.py          # сравнить с манифестом (НЕ ИЗМЕНЁН)
sha256sum candidate/engine.json      # сравнить с манифестом (НЕ ИЗМЕНЁН)

# 1.2. Отсутствие изменений в существующих файлах (на машине с копиями
#      Stage A.2.1 и Stage B):
diff -rq Samsung_V4_STAGE_A_2_1/candidate Samsung_V4_STAGE_B/candidate
# ожидаемо: только «Only in Samsung_V4_STAGE_B/candidate: strategy_state.py»
#           и «Only in .../tests: test_stage_b_state_isolation.py»

# 1.3. Применение полного diff (проверка воспроизводимости):
cp -a Samsung_V4_STAGE_A_2_1/candidate /tmp/verify_b && cd /tmp/verify_b
patch -p1 --dry-run < .../DIFF_STAGE_A_2_1_VS_STAGE_B.patch   # без ошибок
```

## 2. Регрессия (offline)

```bash
cd Samsung_V4_STAGE_B/candidate
python -m pytest            # полный набор: ожидается 1228 passed
python -m pytest tests      # канонический поднабор: ожидается 708 passed
```

Требования регрессии ТЗ §6 и их проверка:

* все тесты Stage A.2.1 проходят — см. разделы 1–2
  `TEST_RESULTS_STAGE_B.txt` (до: 1113; после: 1228; полный список
  node id в логах `-v`);
* ни один старый тест не удалён и не ослаблен — сравнение полных
  списков тестов «до»/«после»: удалено 0, изменено 0 (дерево тестов
  Stage A.2.1 побайтово не менялось — diff п.1.2);
* golden fixtures не перегенерировались — SHA256
  `candidate/tests/fixtures/*` совпадают с принятым Stage A.2.1
  (манифест, раздел III);
* старые профили сохранены — `strategies/legacy_samsung_v4/`
  НЕ ИЗМЕНЁН (манифест, раздел IV);
* config_hash Stage A не меняется — тесты
  `tests/test_stage_a2_config_hash_integrity.py` (57) и
  `tests/test_stage_a2_1_context_integrity.py` (76) проходят без
  изменений;
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

* Все тесты Stage B выполняют файловый ввод/вывод ТОЛЬКО в
  `tmp_path` pytest и явный путь хранилища; сетевые сокеты не
  открываются (в `strategy_state.py` нет сетевого кода).
* `grep -rn "FORCE_TRADE\|sandbox\|place_order\|requests\|urllib" \
  candidate/strategy_state.py` — совпадений нет.
* Старые файлы Samsung не затрагиваются — тест
  `test_store_does_not_touch_old_samsung_files` создаёт state.json и
  проверяет их SHA256 до/после операций Stage B.
