# CHANGED_FILES_STAGE_B.md
# SAMSUNG V4 — STAGE B: отчёт об изменённых файлах

> ПРИМЕЧАНИЕ STAGE B.1: ЧАСТЬ I ниже — исторический отчёт этапа Stage B;
> перечисленные в ней отчётные файлы Stage B (например,
> DIFF_STAGE_A_2_1_VS_STAGE_B.patch/.md, ROLLBACK_INSTRUCTIONS_STAGE_B.md,
> CHANGELOG.md) с этапа B.1 перенесены в каталог `archive/` с пометкой
> «неактуально для Stage B.1». Актуальная структура отчётов — ЧАСТЬ II
> и README_STAGE_B.md. Содержимое кода Stage B эта часть описывает
> корректно.


Дата: 2026-11-28. База: принятая Stage A.2.1 (103d22d34d483fbb7179d1fef07dd0e24b51dfcd).

## 1. Принцип Stage B: только добавления

Stage B реализован БЕЗ изменения ни одного существующего файла.
Проверка выполнена побайтово:

```
diff -rq Samsung_V4_STAGE_A_2_1 Samsung_V4_STAGE_B
  Only in Samsung_V4_STAGE_B/candidate: strategy_state.py
  Only in Samsung_V4_STAGE_B/candidate/tests: test_stage_b_state_isolation.py
```

SHA256-контроль всех 171 существовавших файлов `candidate/`:
совпадение содержимого с принятым Stage A.2.1 — 100%
(см. `FILE_MANIFEST_SHA256_STAGE_B.txt`, раздел III: изменённых 0).

## 2. Новые исходники

| Файл | Строк | Назначение |
|---|---|---|
| `candidate/strategy_state.py` | ~1150 | StrategyState, StateStore, StrategyStateManager, resolve_state_store_path, иерархия ошибок |
| `candidate/tests/test_stage_b_state_isolation.py` | ~1130 | 115 тестов Stage B |

## 3. Новые отчётные файлы пакета

| Файл | Назначение |
|---|---|
| `README_STAGE_B.md` | описание пакета и быстрая проверка |
| `STAGE_B_ARCHITECTURE_REPORT.md` | архитектура Stage B (решения, гарантии, трассировка ТЗ) |
| `CHANGED_FILES_STAGE_B.md` | этот файл |
| `DIFF_STAGE_A_2_1_VS_STAGE_B.patch` | полный diff A.2.1 → B (только добавления) |
| `DIFF_STAGE_A_2_1_VS_STAGE_B.md` | сводка diff |
| `TEST_RESULTS_STAGE_B.txt` | полные логи pytest ДО и ПОСЛЕ |
| `FILE_MANIFEST_SHA256_STAGE_B.txt` | SHA256-манифест + контроль запрещённых областей |
| `VERIFICATION_INSTRUCTIONS_STAGE_B.md` | инструкции проверки |
| `ROLLBACK_INSTRUCTIONS_STAGE_B.md` | инструкции отката |
| `KNOWN_LIMITATIONS_STAGE_B.md` | известные ограничения |
| `CHANGELOG.md` | дополнен разделом Stage B |

## 4. Запрещённые области — НЕ изменены (подтверждение)

Сравнение SHA256 с принятым Stage A.2.1 — все совпадают побайтово:

* `candidate/main.py` — НЕ ИЗМЕНЁН
* `candidate/execution.py` — НЕ ИЗМЕНЁН
* `candidate/logger.py` — НЕ ИЗМЕНЁН
* `candidate/order_ledger.py` — НЕ ИЗМЕНЁН
* `candidate/config.py` — НЕ ИЗМЕНЁН
* `candidate/strategy.py` — НЕ ИЗМЕНЁН
* `candidate/risk_manager.py` — НЕ ИЗМЕНЁН
* `candidate/engine.json` — НЕ ИЗМЕНЁН (ключ STATE_STORE_PATH сознательно
  не добавлен: конфигурация Stage A не меняется без прямой необходимости;
  явное конфигурирование пути реализовано `resolve_state_store_path`)
* `candidate/engine_config.py` — НЕ ИЗМЕНЁН
* `candidate/strategies/legacy_samsung_v4/*` (strategy.py, params.json,
  profiles.py, schema.py) — НЕ ИЗМЕНЕНЫ; legacy остаётся REGRESSION_ONLY
* `candidate/strategy_api.py`, `candidate/attribution.py` — НЕ ИЗМЕНЕНЫ
  (контракты Stage A/A.1/A.2/A.2.1 сохранены; config_hash не изменился)
* Golden fixtures (`candidate/tests/fixtures/*`) — НЕ ИЗМЕНЕНЫ,
  НЕ перегенерировались
* Старые профили SANDBOX_TEST / TECH_CHECK / CONSERVATIVE — НЕ ИЗМЕНЕНЫ
* FORCE_TRADE не добавлялся и не использовался
* Старые логи и runtime-данные не изменялись и не записывались

## 5. Тесты: до / после

| Прогон | До Stage B | После Stage B | Δ |
|---|---|---|---|
| `python -m pytest` (полный) | 1113 passed | **1228 passed** | +115 |
| `python -m pytest tests` (канонический) | 593 passed | **708 passed** | +115 |

Сравнение полных node id списков: удалено 0, ослаблено 0,
добавлено не-Stage-B 0, добавлено Stage B 115.
Golden fixtures не перегенерировались ради PASS; ни один старый тест
не пропущен и не ослаблен; `config_hash` Stage A не изменился;
атрибуция Stage A корректна; скрытых fallback и автоматических сбросов
состояния нет.

---

# ЧАСТЬ II — ИЗМЕНЕНИЯ STAGE B.1

Дата: 2026-11-28. База для сравнения: полный пакет Stage B
(кандидат на основе принятой Stage A.2.1
`103d22d34d483fbb7179d1fef07dd0e24b51dfcd`).

## 6. Изменённые файлы Stage B.1 (относительно Stage B)

| Файл | Тип | Суть изменений |
|---|---|---|
| `candidate/strategy_state.py` | ИЗМЕНЁН | Дефект №1: инъективное длинно-префиксное кодирование имени файла (`encode_state_filename`/`decode_state_filename`, публичные функции с документацией) вместо неинъективного `f"{strategy_id}__{figi}.json"`; Дефект №2: обязательная проверка ключей записи после чтения (`StateStore._load` + `StateStore._verify_loaded_key`) в persistent И memory режимах; Дефект №3: атомарные `StateStore.get_or_create` и `StateStore.update_state` (read-modify-write под одним RLock хранилища), разделяемый RLock каталога (`_StoreDirLockHolder`, реестр по realpath), делегирование `StrategyStateManager.update_state`/`_get_or_create` в хранилище; `list_states` декодирует и сверяет имя и содержимое; обновлены docstring и заголовок модуля |
| `candidate/tests/test_stage_b_state_isolation.py` | ИЗМЕНЁН | Все 115 тестов Stage B сохранены без ослабления: построение имён файлов в проверках переведено на новый заданный алгоритм (`ss.encode_state_filename` через помощник `fname`), добавлена пометка B.1 в заголовок; семантика всех утверждений сохранена |
| `candidate/tests/test_stage_b1_state_key_and_concurrency.py` | ДОБАВЛЕН | 33 новых теста Stage B.1 (ТЗ §6: 12 обязательных пунктов + границы и гонки) |
| `archive/` (30 файлов) + `archive/ARCHIVE_README.md` | ПЕРЕМЕЩЕНЫ | Отчёты Stage A/A.1/A.2/A.2.1 и общие документы прежних пакетов перемещены в архив с явной пометкой «неактуально для Stage B.1» (ТЗ §7: старые отчёты не выдаются за отчёты Stage B) |
| `IMPLEMENTATION_REPORT_STAGE_B.md`, `DIFF_STAGE_B_VS_B_1.md`, `ROLLBACK_INSTRUCTIONS_STAGE_B_1.md` | ДОБАВЛЕНЫ | канонические отчёты Stage B/B.1 (ТЗ §7) |
| `STAGE_B_ARCHITECTURE_REPORT.md`, `CHANGED_FILES_STAGE_B.md`, `KNOWN_LIMITATIONS_STAGE_B.md`, `README_STAGE_B.md`, `TEST_RESULTS_STAGE_B.txt`, `VERIFICATION_INSTRUCTIONS_STAGE_B.md`, `FILE_MANIFEST_SHA256_STAGE_B.txt` | ОБНОВЛЕНЫ | дополнены/актуализированы для Stage B.1 |

## 7. Побайтовое доказательство полноты изменений

`diff -rq <Stage B>/candidate <Stage B.1>/candidate` (все 172 файла
`candidate/`):

```
Files .../candidate/strategy_state.py differ
Files .../candidate/tests/test_stage_b_state_isolation.py differ
Only in .../candidate/tests: test_stage_b1_state_key_and_concurrency.py
```

Остальные 169 файлов — побайтово совпадают с пакетом Stage B, в т.ч.:

* `candidate/main.py`, `execution.py`, `logger.py`, `order_ledger.py`,
  `config.py`, `strategy.py`, `risk_manager.py` — НЕ ИЗМЕНЕНЫ
* `candidate/engine.json`, `engine_config.py`, `strategy_api.py`,
  `attribution.py` — НЕ ИЗМЕНЕНЫ (Stage A/A.1/A.2/A.2.1 без изменений;
  config_hash не изменился)
* `candidate/strategies/legacy_samsung_v4/*` — НЕ ИЗМЕНЕНЫ
  (legacy остаётся REGRESSION_ONLY)
* Golden fixtures `candidate/tests/fixtures/*` — НЕ ИЗМЕНЕНЫ,
  НЕ перегенерировались
* Старые профили SANDBOX_TEST / TECH_CHECK / CONSERVATIVE — НЕ ИЗМЕНЕНЫ
* FORCE_TRADE не добавлялся; старые логи и runtime-данные не изменялись

## 8. Тесты: до / после Stage B.1

| Прогон | До B.1 (Stage B) | После B.1 | Δ |
|---|---|---|---|
| `python -m pytest` (полный) | 1228 passed | **1261 passed** | +33 |
| `python -m pytest tests` (канонический) | 708 passed | **741 passed** | +33 |

Сравнение полных node id списков до/после: удалено 0, ослаблено 0,
добавлено не-B.1 0, добавлено B.1 33 (все — в новом тестовом файле).
Полные реальные логи: `TEST_RESULTS_STAGE_B.txt`.
