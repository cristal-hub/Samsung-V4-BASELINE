# IMPLEMENTATION_REPORT_STAGE_B.md
# SAMSUNG V4 — NEW STRATEGY ENGINE. STAGE B (+ КОРРЕКЦИЯ STAGE B.1)
## Отчёт о реализации

Дата: 2026-11-28.
Репозиторий: cristal-hub/Samsung-V4-BASELINE.
Baseline: `884cefd6f12a99f6adc14b5ed4c9eeda21d32e04` — НЕ изменён.
Принятая Stage A.2.1: `103d22d34d483fbb7179d1fef07dd0e24b51dfcd` —
использована БЕЗ изменений.
Исходный полный пакет Stage B — НЕ перезаписан; Stage B.1 — корректирующая
реализация поверх него (исправление дефектов №1–№3 изолированного состояния
и конкурентного обновления; Stage B с нуля НЕ переписывался).
Режим: OFFLINE / READ ONLY DATA / RESEARCH ONLY / NO LIVE ORDERS /
NO REAL MONEY. GitHub не использовался; ветки/коммиты/PR/issue не
создавались.

---

## 1. Что реализовано

### 1.1. Stage B (обзор, без изменений в B.1)

Независимое состояние каждой стратегии для каждого инструмента с ключом
изоляции **(strategy_id, FIGI)**:

* **`StrategyState`** (§3.1) — неизменяемая типизированная модель пары:
  strategy_id + FIGI + config_hash (SHA-256/64 hex, Stage A.2), версия
  схемы (`STATE_SCHEMA_VERSION = 1`), глубоко неизменяемые
  JSON-совместимые данные, детерминированная сериализация
  (`to_payload`/`to_json`/`from_payload`), отсутствие общих изменяемых
  объектов между ключами.
* **`StateStore`** (§3.2) — изолированное хранилище: минимальный интерфейс
  ТЗ (`get_state` / `save_state` / `create_state` / `reset_state` /
  `list_states`); persistent-режим ТОЛЬКО с явно переданным путём
  (по одной JSON-записи на ключ, атомарная запись tmp + `os.replace` +
  fsync, детерминированное содержимое); memory-режим явный; проверка
  версии схемы, ключей и config_hash; повреждённые записи обнаруживаются
  и НЕ подменяются пустым состоянием; несовпадение config_hash —
  контролируемая ошибка (автоматической миграции нет).
* **`StrategyStateManager`** (§3.3) — выдаёт стратегии только её
  собственное состояние по паре; создаёт независимое состояние при
  отсутствии записи; сохраняет изменения; без глобального mutable
  context; без «одного состояния на все инструменты».
* **`resolve_state_store_path`** (§3.2/§4.16) — путь persistent-хранилища
  ТОЛЬКО из явного ключа `STATE_STORE_PATH`; отсутствие обязательной
  конфигурации не переключает скрыто на другой путь; старые файлы
  Samsung не читаются и не пишутся.

### 1.2. Stage B.1 — исправления дефектов

**Дефект №1 (ТЗ §3) — коллизия имён файлов.** Шаблон Stage B
`f"{strategy_id}__{figi}.json"` не был инъективным: разделитель `__`
допустим ВНУТРИ значений, поэтому пары `("alpha__beta", "FIGI1")` и
`("alpha", "beta__FIGI1")` получали одно имя файла и затирали состояние
друг друга. Реализовано длинно-префиксное кодирование
(допустимое решение ТЗ, вариант «length-prefixed encoding»):

```
encode_state_filename(s1, s2) = "{len(s1)}--{s1}--{len(s2)}--{s2}.json"
```

* разбор (`decode_state_filename`) строго позиционный: длина читается
  первой, компонент берётся ровно N символов — разделитель внутри
  значения путаницы не создаёт; на «разделитель не появится внутри
  значения» ничего не полагается;
* инъективность доказуема конструктивно: `decode(encode(s1, s2)) == (s1, s2)`
  для всех допустимых значений → разные пары = разные файлы;
* безопасность имён сохранена: компоненты предварительно проверяются
  `validate_strategy_id`/`validate_figi` (`^[A-Za-z0-9][A-Za-z0-9._-]*$`,
  лимиты 128/64); закодированное имя содержит только цифры, `-`, `.` и
  не может быть инструментом path traversal; максимум 206 символов (<255);
* задокументировано: заголовок модуля `strategy_state.py` (блок «Имя
  файла записи»), docstring функций, `STAGE_B_ARCHITECTURE_REPORT.md`
  раздел 11;
* скрытой миграции старого формата НЕТ (ТЗ §3: Stage B не принят,
  пользовательские данные не мигрируются): старые имена не читаются и
  не переписываются; `list_states()` обнаруживает неформатное имя как
  повреждение (`StateCorruptionError`).

**Дефект №2 (ТЗ §4) — проверка ключа после чтения.**
`StateStore._load(strategy_id, figi)` после десериализации ОБЯЗАТЕЛЬНО
выполняет `_verify_loaded_key`:

* `state.strategy_id == strategy_id` и `state.figi == figi`;
* несовпадение → `StateCorruptionError`: состояние НЕ возвращается,
  пустое состояние НЕ создаётся, запись НЕ исправляется автоматически,
  файл НЕ изменяется;
* проверка выполняется НЕЗАВИСИМО от алгоритма имени файла и в ОБОИХ
  режимах — persistent и memory (единый контракт);
* подменённая запись отклоняется всеми путями потребления: `get_state`,
  `get_or_create`, `update_state`, `save_state`, `create_state`,
  `list_states` (последний дополнительно сверяет декодированное имя с
  содержимым).

**Дефект №3 (ТЗ §5) — конкурентное обновление.** Атомарный
read-modify-write вынесен в StateStore — единственного владельца записей:

* `StateStore.get_or_create(...)` — чтение и (при отсутствии) создание
  под ОДНИМ RLock хранилища (окно «проверили, потом создали» исключено);
* `StateStore.update_state(...)` — полный RMW (чтение → [создание] →
  проверка config_hash ДО вызова updater → updater → запись) под ОДНИМ
  RLock хранилища → атомарно относительно ВСЕХ менеджеров, работающих
  через один StateStore (ТЗ §5.1); локальный RLock менеджера больше НЕ
  является механизмом атомарности (ТЗ §5.2);
* усиление: все экземпляры StateStore одного процесса на одном реальном
  каталоге (`os.path.realpath`) разделяют ОДИН RLock (реестр слабых
  ссылок `_STORE_DIR_LOCKS_REGISTRY`) — технически обеспечено, а не
  только написано (тест `test_shared_path_lock_serializes_two_store_instances`);
* защита от частичной записи и повреждения JSON сохранена (tmp +
  `os.replace` + fsync; битый JSON → `StateCorruptionError`) (ТЗ §5.3);
* без взаимных блокировок (ТЗ §5.4): порядок блокировок строго
  manager → store; хранилище никогда не вызывает менеджер; повторный
  вход в то же хранилище из updater разрешён (RLock реентерабелен) и
  покрыт тестом; контракт updater задокументирован в docstring
  (`update_state` должен быть чистой быстрой функцией);
* граница гарантии описана явно (ТЗ §5.5): ОДИН процесс — гарантировано;
  НЕСКОЛЬКО ПРОЦЕССОВ — НЕ поддерживается (межпроцессная блокировка
  сознательно не добавлена; ограничение честно зафиксировано в
  `KNOWN_LIMITATIONS_STAGE_B.md` раздел 5);
* `StrategyStateManager.update_state` и `_get_or_create` делегируют
  атомарным методам хранилища (публичное API менеджера не менялось).

### 1.3. Интеграция с контрактом Stage A (§3.4 ТЗ Stage B)

* Использованы существующие контракты: `Strategy`, `StrategyConfig`,
  `strategy_id`, `config_hash`, `AttributionContext`, `ActivationMode`;
* config — ТОЛЬКО точный тип `StrategyConfig` (решение Stage A.2.1);
  config_hash — формат Stage A.2; противоречие источников →
  `StateValidationError`;
* `AttributionContext` — ТОЛЬКО проверенный (через
  `attribution._resolve_context`, тот же вход, что у factory/stamp);
* публичные интерфейсы Stage A не сломаны: `strategy_api.py`,
  `attribution.py`, `engine_config.py`, `engine.json`, legacy-адаптер и
  профили побайтово не изменились; Stage A config_hash не изменился;
* legacy Samsung V4 остаётся `REGRESSION_ONLY`
  (`test_legacy_strategy_remains_regression_only`).

## 2. Изменённые/добавленные файлы (Stage B.1)

| Файл | Статус | Суть |
|---|---|---|
| `candidate/strategy_state.py` | ИЗМЕНЁН | три дефекта (см. §1.2) |
| `candidate/tests/test_stage_b_state_isolation.py` | ИЗМЕНЁН | имена файлов в проверках → новый алгоритм; 115 тестов сохранены |
| `candidate/tests/test_stage_b1_state_key_and_concurrency.py` | ДОБАВЛЕН | 33 теста B.1 |
| корневые отчёты Stage B (9 канонических + VERIFICATION) | ОБНОВЛЕНЫ | актуализация для B.1 |
| `archive/` (31 файл) | ПЕРЕМЕЩЕНЫ | отчёты Stage A/A.1/A.2/A.2.1 с пометкой «неактуально для B.1» |

Полный diff: `DIFF_STAGE_B_VS_B_1.md` (+ `DIFF_STAGE_B_VS_B_1.patch`).
Больше никаких изменений: остальные 169 файлов `candidate/` побайтово
совпадают с пакетом Stage B — включая все торговые файлы, Stage A.2.1,
golden fixtures и профили (подтверждение — `CHANGED_FILES_STAGE_B.md`
раздел 7, манифест SHA256).

## 3. Тесты

### 3.1. Количество до/после (ТЗ §8)

| Прогон | До B.1 (Stage B) | После B.1 | Δ |
|---|---|---|---|
| `python -m pytest` (полный) | 1228 passed, 0 failed, 0 skipped | **1261 passed, 0 failed, 0 skipped** | +33 |
| `python -m pytest tests` (канонический) | 708 passed, 0 failed, 0 skipped | **741 passed, 0 failed, 0 skipped** | +33 |
| `tests/test_stage_b_state_isolation.py` | 115 passed | 115 passed | 0 (сохранены) |
| `tests/test_stage_b1_state_key_and_concurrency.py` | — | **33 passed** | +33 |

Сравнение полных node id списков до/после: удалено 0, ослаблено 0,
добавлено не-B.1 0, добавлено B.1 — 33. Полные реальные логи обоих
прогонов: `TEST_RESULTS_STAGE_B.txt`.

### 3.2. Обязательные тесты Stage B.1 (ТЗ §6) — все реализованы

1. ранее коллизионные пары независимы → `test_previous_colliding_pairs_are_independent_files`;
2. запись первой пары не меняет вторую → `test_write_first_pair_does_not_change_second`;
3. чтение второй пары не возвращает первую → `test_read_second_pair_returns_second_state`;
4. `list_states()` возвращает обе пары → `test_list_states_returns_both_pairs`;
5. подмена чужим strategy_id обнаруживается → `test_foreign_strategy_id_detected`;
6. подмена чужим FIGI обнаруживается → `test_foreign_figi_detected`;
7. ошибка проверки не изменяет файл → `test_verification_error_does_not_modify_file`;
8. коллизий нет на граничных строках → `test_boundary_valid_strings_no_collisions` (+ round-trip, лимит длины);
9. два менеджера × один store, параллельные updater без потерь → `test_two_managers_one_store_parallel_updaters_no_lost_update` (200 инкрементов);
10. повтор конкурентного теста детерминирован → `test_repeated_concurrent_run_is_deterministic` (байт-в-байт);
11. ошибка updater не меняет состояние → `test_updater_error_in_store_update_leaves_state_unchanged` + через менеджер;
12. старые тесты Stage B проходят → полный регресс (таблица §3.1).

Дополнительно: независимость разных пар при параллельной работе
(`test_parallel_distinct_pairs_two_managers_isolated`,
`test_concurrent_updates_of_previously_colliding_pairs`), проверка ключа
в memory-режиме, отсутствие скрытой миграции, мусорные имена,
`get_or_create` между менеджерами, config_hash до updater, смешанные
manager/store инкременты, разделяемый замок экземпляров, реентерабельность,
повтор серии, сохранение публичного интерфейса ТЗ Stage B.

## 4. Ограничения и запреты (подтверждение)

* Stage C НЕ начат; `evaluate_exit` не реализован; исторический
  симулятор и Sandbox-адаптер не реализованы;
* торговая логика, параметры, сигналы, риск-менеджмент, исполнение
  ордеров — НЕ изменены (побайтовое подтверждение в манифесте);
* подключения к брокеру, Sandbox/LIVE-операции и заявки — отсутствуют;
* FORCE_TRADE не добавлялся; legacy Samsung V4 не активирован
  (REGRESSION_ONLY);
* старые пользовательские данные и runtime-файлы Samsung не изменялись
  и не мигрировались;
* базовая линия, Stage A.2.1 и исходный пакет Stage B не перезаписаны
  (работа в изолированной копии).

Полный список ограничений — `KNOWN_LIMITATIONS_STAGE_B.md`.

## 5. Как проверить

`README_STAGE_B.md` (быстрая проверка) и
`VERIFICATION_INSTRUCTIONS_STAGE_B.md` (полные инструкции, включая
воспроизводимость patch и ручные демонстрации дефектов №1/№3).
