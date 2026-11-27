# CORRECTIVE REPORT — STAGE A.2

**SAMSUNG V4 — NEW STRATEGY ENGINE. STAGE A.2 CORRECTIVE**
**Обязательная проверка соответствия config_hash фактической конфигурации**

Дата: 2026-11-28
Исходный пакет: `Samsung_V4_STAGE_A_1` (Stage A.1, использован без изменений; рабочая копия)
Baseline: commit `884cefd6f12a99f6adc14b5ed4c9eeda21d32e04` (cristal-hub/Samsung-V4-BASELINE)
Режим: ТОЛЬКО offline — без сети, без брокера, без Sandbox/LIVE-заявок.
GitHub: не использовался; ветки/коммиты/PR/issue не создавались; файлы в
репозиторий и пользовательские папки не записывались.

---

## 1. ИСХОДНЫЕ ДАННЫЕ И ПОСТАНОВКА

Репозиторий: cristal-hub/Samsung-V4-BASELINE. Работала ТОЛЬКО изолированная
копия пакета Stage A.1 (`Samsung_V4_STAGE_A_1`); исходные пакеты Stage A и
Stage A.1 сохранены без изменений; baseline не изменялся.

Цель — устранить единственный оставшийся дефект независимой проверки
Stage A.1: в `candidate/strategy_api.py`

* `StrategyConfig.__post_init__()` проверял непустоту `config_hash`, но не
  его соответствие параметрам;
* `recompute_config_hash()` вычислял правильный хеш, но не обеспечивал
  автоматическую проверку при создании объекта;
* `AttributionContext.from_config()` доверял переданному `config_hash`.

В результате можно было создать конфигурацию с корректными параметрами и
чужим хешем, а затем записать неверную атрибуцию в новые объекты движка.

---

## 2. ВЫПОЛНЕННОЕ ИСПРАВЛЕНИЕ

### 2.1. Проверка при создании StrategyConfig (требование 3.1)

`candidate/strategy_api.py`, `StrategyConfig.__post_init__()` — после
получения и проверки параметров (шаги 1–3: идентификационные поля,
`params`/`metadata` — Mapping, глубокая заморозка в `ImmutableMapping`)
добавлен шаг 4:

* ожидаемый хеш вычисляется **существующей** функцией
  `compute_config_hash(strategy_id, strategy_version, params)` — по
  ФАКТИЧЕСКИ сохранённым (уже замороженным) параметрам;
* вычисленный хеш сравнивается с переданным `config_hash`;
* при расхождении создание объекта отклоняется `StrategyConfigError`;
  объект НЕ создаётся;
* хеш НЕ исправляется автоматически и НЕ заменяется вычисленным молча:
  в тексте ошибки названы и переданный, и фактически ожидаемый хеш
  (проверяется тестом `test_hash_of_another_config_rejected`).

Порядок проверки в `__post_init__` (все шаги fail-closed):

1. идентификационные поля — непустые строки (`strategy_id`,
   `strategy_version`, `config_hash`, `origin`);
2. `params` и `metadata` — отображения (Mapping);
3. формат `config_hash` — ровно 64 hex-символа (см. 2.2);
4. глубокая заморозка/копирование `params`/`metadata` (Stage A.1);
5. `compute_config_hash(...)` по фактическим параметрам и сравнение с
   переданным `config_hash`.

### 2.2. Проверка формата (требование 3.2)

Добавлена публичная функция `validate_config_hash_format()` и константа
`CONFIG_HASH_LENGTH = 64` (`candidate/strategy_api.py`):

* `config_hash` обязан быть строкой ровно из 64 шестнадцатеричных символов
  `[0-9a-f]` нижнего регистра — каноническая форма
  `hashlib.sha256(...).hexdigest()`;
* любая другая длина, символы вне hex, верхний регистр, не-строка — отказ
  fail-closed (`StrategyConfigError`): такой хеш не мог быть вычислен
  `compute_config_hash`;
* проверка выполняется при КАЖДОМ создании конфигурации, в том числе
  ручном.

### 2.3. Проверка входных параметров (требование 3.3)

Недопустимые значения в `params` (и в `metadata` — там, где применимо)
отклоняются контролируемой `StrategyConfigError` в момент создания;
частично валидный объект не возвращается:

* **NaN / Infinity** — отклоняются нормализацией `_normalize_for_json`
  (в том числе во вложенных dict/list/set);
* **неподдерживаемые изменяемые объекты** (произвольные классы,
  `bytearray`, `complex`, `slice`, `memoryview` и т. п.) — отклоняются
  сообщением «недетерминируемый тип в params: … — в config_hash
  допускаются только JSON-значения»;
* **циклические ссылки** — добавлено отслеживание пути рекурсии
  (`_FreezePath`): объект, содержащий сам себя по текущему пути
  (dict→dict, dict→list→dict, list→list и т. п.), отклоняется
  `StrategyConfigError` с сообщением о циклической структуре; бесконечной
  рекурсии (RecursionError) нет. Один и тот же объект, встречающийся
  дважды как два РАЗНЫХ значения (DAG, без цикла), допустим — тест
  `test_dag_is_not_mistaken_for_cycle`.
* защита распространена и на ПРЯМЫЕ вызовы `compute_config_hash()` /
  `canonical_config_payload()`: не-Mapping параметры, NaN/Infinity,
  недопустимые объекты и циклы дают ту же контролируемую
  `StrategyConfigError` (ранее прямой вызов с циклом/списком падал
  неконтролируемым RecursionError/TypeError).

**Запрет обхода проверки через ручное создание.** Конструктор у
`StrategyConfig` один (сгенерированный dataclass-`__init__`) и всегда
выполняет `__post_init__` — любая сборка через публичный API проходит
проверку. Дополнительные обходные пути закрыты тестами:
`dataclasses.replace(config, config_hash=...)` и
`dataclasses.replace(config, params=...)` с несоответствием отклоняются
(`test_dataclasses_replace_cannot_inject_foreign_hash`). Сборка объекта
в обход публичного API (`object.__new__` + `object.__setattr__`) не
является обычным публичным API; для неё оставлен барьер defense-in-depth
на уровне атрибуции (см. 2.4) — контекст с чужим хешем всё равно не
выпускается (тест `test_from_config_defense_in_depth_recheck`).

### 2.4. Атрибуция (требование 3.4)

`candidate/attribution.py`, `AttributionContext.from_config()`:

* принимается ТОЛЬКО полноценная `StrategyConfig` (isinstance):
  создание `StrategyConfig` уже гарантирует соответствие хеша параметрам;
  дополнительно выполняется перепроверка через
  `config.recompute_config_hash()` (defense-in-depth);
* произвольные duck-typed объекты с полями `strategy_id`/`config_hash`
  больше НЕ принимаются (`AttributionError`): они не могут доказать
  соответствие хеша своей конфигурации, поэтому контекст с
  несоответствующим хешем не может быть выпущен;
* `AttributionFactory` и `stamp()` наследуют защиту автоматически:
  контекст создаётся только через `_resolve_context` →
  `AttributionContext`/`StrategyConfig`; фабрика из некорректного объекта
  не создаётся (`AttributionRequiredError`);
* скрытых значений, fallback и автоматического исправления атрибуции НЕ
  введено.

`engine_config.py` не менялся: точка `AttributionContext.from_config(config)`
(конструирование контекста из конфигурации активной стратегии) получает
только конфигурации, построенные через `Strategy.get_config`, и теперь
дополнительно защищена перепроверкой внутри `from_config`.

### 2.5. Исправленные тестовые фикстуры (требование 5)

Существующие тесты, создававшие `StrategyConfig` с искусственными хешами,
исправлены — они вычисляют реальные хеши через `compute_config_hash()`.
Проверка НЕ ослаблялась ради прохождения старых тестов:

| Файл | Что исправлено | Суть теста сохранена |
|---|---|---|
| `tests/test_stage_a_legacy_adapter.py` | `test_evaluate_entry_rejects_engine_origin`: `config_hash="0"*64` → `sa.compute_config_hash("legacy_samsung_v4", strategy.strategy_version, normalized)` | конфигурация с origin="engine" по-прежнему отклоняется адаптером (`LegacyRegressionError`) |
| `tests/test_stage_a1_config_immutability.py` | `_nested_config()`: `config_hash="e"*64` → `compute_config_hash("nested_demo", "1.0", params)` | все 13 тестов вложенной неизменяемости работают без изменения утверждений |
| `tests/test_stage_a1_config_immutability.py` | `test_metadata_non_mapping_rejected`: `config_hash="c"*64` → реальный хеш | проверяемой ошибкой стала именно невалидная metadata, как и задумано |

Полный перечень мест создания `StrategyConfig` проверен поиском по коду:
все остальные вызовы либо вычисляют хеш через `compute_config_hash`
(`Strategy.get_config`, `LegacySamsungV4Strategy.build_regression_config`,
остальные фикстуры), либо копируют хеш заведомо консистентной
конфигурации, либо восстанавливают его из JSON round-trip.

---

## 3. ОБЯЗАТЕЛЬНЫЕ ТЕСТЫ (12) — ФАКТ ВЫПОЛНЕНИЯ

Новый файл `candidate/tests/test_stage_a2_config_hash_integrity.py`
(57 тестов). Тестируется РЕАЛЬНОЕ поведение (создание объекта /
контролируемая ошибка), а не только наличие проверок в исходном коде.

| № | Требование | Реализующие тесты | Статус |
|---|---|---|---|
| 1 | Корректный config_hash — объект создаётся | `TestCreationWithValidHash::test_valid_config_hash_object_created`, `test_valid_creation_via_strategy_get_config`, `test_valid_creation_via_legacy_regression_config` | PASS |
| 2 | Хеш от другой конфигурации — создание запрещено | `TestMismatchedHashRejected::test_hash_of_another_config_rejected`, `test_hash_of_other_strategy_id_rejected` | PASS |
| 3 | Хеш от изменённого параметра — создание запрещено | `TestMismatchedHashRejected::test_hash_of_modified_param_rejected`, `test_hash_of_nested_modified_param_rejected`, `test_no_silent_substitution_on_public_paths` | PASS |
| 4 | Хеш неправильной длины — создание запрещено | `TestConfigHashFormatEnforced::test_invalid_format_rejected` (63, 65, пустой, короткий), `test_non_string_hash_rejected` | PASS |
| 5 | Хеш с не-hex символами — создание запрещено | `TestConfigHashFormatEnforced::test_invalid_format_rejected` («h»*64, «z»*63+"0", «g»-суффикс, верхний регистр «A»*64, пробелы), `test_format_validator_unit_behavior` | PASS |
| 6 | NaN и Infinity — контролируемая ошибка | `TestNonFiniteValuesRejected` (верхний уровень, вложенные структуры, прямой `compute_config_hash`; конечные float по-прежнему допустимы) | PASS |
| 7 | Неподдерживаемый изменяемый объект — контролируемая ошибка | `TestUnsupportedObjectsRejected` (пользовательский класс, bytearray, memoryview, complex, slice; вложенность; прямой compute; JSON-типы по-прежнему допустимы) | PASS |
| 8 | Циклическая структура — контролируемая ошибка, без бесконечной рекурсии | `TestCyclicStructuresRejected` (dict→self, list→self, dict→list→dict, dict→dict, прямой compute, цикл в metadata; DAG не путается с циклом) | PASS |
| 9 | `AttributionContext.from_config()` принимает только корректную конфигурацию | `TestAttributionGuard::test_from_config_accepts_valid_config`, `test_from_config_rejects_objects_with_foreign_hash`, `test_from_config_rejects_garbage_field_values`, `test_from_config_defense_in_depth_recheck` | PASS |
| 10 | `AttributionFactory` не создаёт объекты на основе некорректной конфигурации | `TestAttributionGuard::test_factory_refuses_inconsistent_config`, `test_factory_from_valid_config_stamps_correctly`, `test_engine_config_attribution_path_is_gated` | PASS |
| 11 | Сериализация и JSON round-trip сохраняют правильный хеш | `TestSerializationHashIntegrity` (round-trip сохраняет хеш; восстановление с изменённым параметром отклоняется; as_dict несёт ровно проверенный хеш; консистентность get_config-пути) | PASS |
| 12 | Старые golden signals и профили остаются идентичными | `TestGoldenSignalsAndProfilesUnchanged::test_golden_signals_reproduce_exactly` (полная перегенерация сигналов по 5 fixture × 3 профиля против эталона `tests/fixtures/legacy_golden_signals.json` + SHA256-целостность fixture), `test_profiles_identical_to_baseline_config_py` (AST-сверка SANDBOX_TEST/TECH_CHECK/CONSERVATIVE с baseline config.py; FORCE_TRADE отсутствует), `test_regression_configs_of_all_profiles_are_consistent` | PASS |

Дополнительно (сверх 12 обязательных): запрет обхода через
`dataclasses.replace` (2 теста), запрет тихой замены хеша (сообщение
ошибки содержит оба значения), проверка «после отклонённого создания
корректное создание работает» (нет частично валидного объекта),
каноничность формата вычисленных хешей, DAG-совместимость.
Итого 57 новых тестов.

---

## 4. РЕГРЕССИЯ И ПОЛНЫЙ ПРОГОН

### 4.1. Окружение

| Компонент | Версия |
|---|---|
| Python | 3.12.16 (Linux x64) |
| pytest | 9.0.2 |
| pandas / numpy | 2.2.3 / 2.1.3 |
| pandas-ta-classic | 0.3.15 (реальные индикаторы; golden-тесты выполнялись, без SKIP) |
| python-telegram-bot | 21.11.1 |
| t-tech-investments | недоступен в публичном PyPI — действует штатная заглушка `conftest.py`, предусмотренная авторами baseline (то же окружение, что у Stage A / A.1) |

Сетевые обращения тестов: нет. Брокерские подключения: нет.
Sandbox/LIVE-заявки: нет. SKIP-тестов: 0; заглушек вместо реальных тестов
нет. Новых SKIP не введено.

### 4.2. Результаты

| Прогон | Команда | Результат |
|---|---|---|
| ДО (исходный Stage A.1, эта среда) | `python -m pytest` | **980 passed**, 0 failed, exit 0 |
| ДО (поднабор tests) | `python -m pytest tests` | 460 passed, 0 failed |
| ПОСЛЕ (Stage A.2) | `python -m pytest` | **1037 passed**, 0 failed, 0 skipped, exit 0 |
| ПОСЛЕ (поднабор tests) | `python -m pytest tests` | 517 passed, 0 failed |
| Новый файл | `python -m pytest tests/test_stage_a2_config_hash_integrity.py` | 57 passed |
| Порядок A.2→A.1 corrective | `python -m pytest tests/test_stage_a2_config_hash_integrity.py tests/test_stage_a1_config_immutability.py tests/test_stage_a1_attribution_explicit.py` | 138 passed |
| Повторный прогон нового файла | тот же файл дважды в одной команде | 57 passed |

Разложение дельты: 771 baseline + 128 Stage A + 81 Stage A.1 corrective +
57 Stage A.2 corrective = **1037**. Все 980 существующих тестов
Stage A.1 продолжили проходить БЕЗ изменения утверждений (изменены только
2 фикстуры с искусственными хешами — см. 2.5; утверждениях/эталонах
изменений нет). Полные тексты прогонов: `TEST_RESULTS_STAGE_A_2.txt`.

---

## 5. ИЗМЕНЁННЫЕ И НОВЫЕ ФАЙЛЫ (Stage A.1 → Stage A.2)

| Файл | Тип | Содержание изменения | Совместимость | Тесты |
|---|---|---|---|---|
| `candidate/strategy_api.py` | изменён | `__post_init__`: проверка формата config_hash (64 hex) и равенства вычисленному хешу; `validate_config_hash_format()` + `CONFIG_HASH_LENGTH`; цикл-детекция `_FreezePath` в `deep_freeze`/`ImmutableMapping`/`ImmutableList`/`_normalize_for_json`; не-Mapping params → контролируемая ошибка в `canonical_config_payload`; обновлены докстринги/шапка | Полная: все прежние потребители (`Strategy.get_config`, `build_regression_config`, engine_config, сериализация) работают без изменений; 980 существующих тестов проходят | 57 новых (файл A.2) + 980 регрессия |
| `candidate/attribution.py` | изменён | `AttributionContext.from_config`: только `StrategyConfig` + перепроверка `recompute_config_hash` (defense-in-depth); обновлены докстринг/шапка | Чтение старых записей и штампование не изменились; `engine_config` использует тот же вызов без правок | 9 новых тестов + 55 регрессия attribution |
| `candidate/tests/test_stage_a1_config_immutability.py` | изменён (фикстуры) | `_nested_config` и `test_metadata_non_mapping_rejected` переведены на реальные хеши | Утверждения не менялись | 48/48 PASS |
| `candidate/tests/test_stage_a_legacy_adapter.py` | изменён (фикстура) | `test_evaluate_entry_rejects_engine_origin` переведён на реальный хеш | Утверждение не менялось | PASS |
| `candidate/tests/test_stage_a2_config_hash_integrity.py` | новый | 57 corrective-тестов обязательной проверки соответствия config_hash | — | PASS 57 |

Машинный diff: `APPENDIX_DIFF_STAGE_A_1_TO_A_2.patch` (полный,
+1022/−57 строк). Больше НИКАКИХ файлов не менялось: 185 файлов пакета
байт-идентичны Stage A.1 (SHA256-проверка); Торговая логика, параметры,
сигналы, риск-менеджмент, исполнение — без изменений.

---

## 6. НЕИЗМЕННОСТЬ BASELINE И СТАРЫХ PRODUCTION-ФАЙЛОВ

Подтверждено SHA256-сравнением с эталонной копией baseline
(commit `884cefd6f12a99f6adc14b5ed4c9eeda21d32e04`):

* **0 файлов изменены относительно baseline** — ни один файл, существовавший
  в baseline, не был изменён (155 файлов байт-идентичны);
* ключевые production-файлы байт-идентичны baseline:
  `main.py`, `execution.py`, `logger.py`, `order_ledger.py`, `config.py`,
  `strategy.py`, `risk_manager.py`, `screener.py`, `telegram_bot.py`,
  `tinkoff_client.py`, `safe_start.py`, `build_safety.py`,
  `enable_sandbox_execution.py`, `requirements.txt`, `conftest.py`
  (полный список 155 файлов — в `FILE_MANIFEST_SHA256_STAGE_A_2.txt`);
* относительно Stage A.1 изменены ТОЛЬКО 4 файла + 1 новый тестовый
  (см. раздел 5); старые журналы и пользовательские данные не
  затрагивались; миграций нет.

Специальные ограничения Stage A.2 соблюдены: торговая логика, параметры,
сигналы, риск-менеджмент и исполнение не менялись; Stage B не начинался;
брокер/Sandbox/LIVE не подключались; старые журналы и пользовательские
данные не изменялись; FORCE_TRADE не добавлялся и не использовался
(тест `test_profiles_identical_to_baseline_config_py` это подтверждает).

---

## 7. ОСТАВШИЕСЯ ОГРАНИЧЕНИЯ (честный перечень)

1. **Сборка объекта в обход публичного API** (`object.__new__` +
   `object.__setattr__`, минуя `__init__`) технически возможна в Python;
   это не обычный публичный API. Барьер для такого случая вынесен на
   уровень атрибуции: `AttributionContext.from_config` перепроверяет
   `recompute_config_hash` и не выпускает контекст с несоответствующим
   хешем (покрыто тестом `test_from_config_defense_in_depth_recheck`).
   Полная невозможность интроспективной сборки в Python недостижима
   принципиально.
2. **Атрибуция по-прежнему НЕ встроена в производственный поток baseline**
   (main.py / execution.py / logger.py / order_ledger.py не изменены —
   это граница Stage A/A.1/A.2, встраивание — Этап B, предложение
   задокументировано в CORRECTIVE_IMPLEMENTATION_REPORT.md Stage A.1).
   Stage A.2 это ограничение сохраняет и не расширяет.
3. **metadata не входит в config_hash** (задокументировано в Stage A):
   метаданные остаются вспомогательным полем и не участвуют в
   идентификации; проверка соответствия выполняется для params.
4. **Наследование StrategyConfig**: `from_config` принимает подклассы
   через isinstance; переопределение `recompute_config_hash` в подклассе
   — теоретический обход перепроверки (не обычный публичный API,
   зафиксировано как известная граница).
5. **Enum с изменяемым значением** хранится как скаляр (поведение
   Stage A.1): хеш покрывает значение Enum в нормализованной форме;
   мутация внутреннего изменяемого значения Enum после создания
   конфигурации не отслеживается (такие Enum в параметрах не используются
   ни одной стратегией).
6. SKIP-механизм golden-теста G-1 сохранён как в Stage A: в среде БЕЗ
   реальных pandas_ta_classic соответствующие golden-проверки честно
   помечаются SKIP (в среде поставки индикаторы реальны — SKIP-ов нет,
   см. раздел 4.1).

---

## 8. КРИТЕРИЙ ЗАВЕРШЕНИЯ (раздел 7 задания)

Stage A.2 считается выполненным, когда невозможно создать StrategyConfig
с неправильным, фиктивным или не соответствующим параметрам config_hash
через обычный публичный API.

**Результат: ВЫПОЛНЕНО.**

* конструктор один и всегда выполняет `__post_init__` (формат 64 hex +
  равенство вычисленному хешу) — чужой/фиктивный/несоответствующий хеш
  отклоняется `StrategyConfigError` (тесты № 2–5);
* `dataclasses.replace` не обходит проверку;
* `AttributionContext.from_config` / `AttributionFactory` не выпускают
  контекст и не создают объекты на основе некорректной конфигурации
  (тесты № 9–10);
* все 980 существующих тестов Stage A.1 проходят без ослабления проверок;
  полный набор: 1037 passed / 0 failed.

После завершения Stage A.2 работа остановлена. Stage B не начинался.
