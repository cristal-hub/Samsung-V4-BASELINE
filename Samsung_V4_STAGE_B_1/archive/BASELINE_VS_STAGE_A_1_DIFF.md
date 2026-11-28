# BASELINE_VS_STAGE_A_1_DIFF.md
# ПОЛНЫЙ DIFF: исходный Stage A → Stage A.1 (corrective)

**База сравнения:** пакет `Samsung_V4_STAGE_A` (Stage A, поставленный ранее)
**Сравниваемая версия:** пакет `Samsung_V4_STAGE_A_1` (Stage A.1)
**Точка отсчёта более низкого уровня:** baseline commit
`884cefd6f12a99f6adc14b5ed4c9eeda21d32e04` (production-файлы Stage A.1
байт-идентичны baseline — проверено SHA256).

Машинный diff (полный, 2113 строк): `APPENDIX_FULL_DIFF.patch` в корне пакета.

---

## 1. СВОДКА ИЗМЕНЕНИЙ

```
 candidate/strategy_api.py                       | 293 ++++++++++++
 candidate/attribution.py                        | 333 ++++++++++++---------
 candidate/engine_config.py                      |  14 ++-
 candidate/tests/test_stage_a_attribution.py     |  54 ++++---
 candidate/tests/test_stage_a1_config_immutability.py     | 568 ++++++++++++++++ (НОВЫЙ)
 candidate/tests/test_stage_a1_attribution_explicit.py    | 584 +++++++++++++++++++++ (НОВЫЙ)
 6 files changed, 1758 insertions(+), 88 deletions(-)
```

Все остальные файлы пакета **байт-неизменны** относительно исходного
Stage A: в `candidate/` — 163 файла (включая все production-файлы main.py,
execution.py, logger.py, order_ledger.py, strategy.py, config.py,
risk_manager.py, screener.py, telegram_bot.py, tinkoff_client.py,
safe_start.py, build_safety.py, enable_sandbox_execution.py), strategies/
(весь legacy-адаптер и профили), engine.json; в корне — отчёты Stage A
(README_STAGE_A.md, IMPLEMENTATION_REPORT.md, CHANGELOG.md,
BASELINE_VS_CANDIDATE.md); docs/ и golden-фикстура
`tests/fixtures/legacy_golden_signals.json` — SHA256 не изменился.
(Итог по манифесту: 188 файлов = 6 [M] + 9 [A] + 173 [ ].)

## 2. ФАЙЛ №1: `candidate/strategy_api.py` (+293 строки)

**Замечание аудита:** №1 — неизменяемость StrategyConfig.

**Причина изменения:** `@dataclass(frozen=True)` не защищает вложенные
структуры params/metadata; объект мог разойтись с собственным config_hash.

**Содержание изменения:**

1. Новые типы (раздел «Глубоко неизменяемые структуры»):
   * `ImmutableMapping` — Mapping-ABC без операций записи; хранилище —
     `MappingProxyType` поверх собственной копии; запрет `__setattr__`/
     `__delattr__`; строковые ключи (fail-closed); семантическое равенство
     с dict; согласованный `__hash__`; `__reduce__` для copy/deepcopy/pickle
     с восстановлением через `__init__` (заморозка сохраняется);
     `to_mutable()` — точная глубокая модифицируемая копия.
   * `ImmutableList` — подкласс tuple (C-уровневая неизменяемость);
     рекурсивная заморозка элементов; семантическое равенство с list/tuple;
     согласованный `__hash__`; срезы возвращают ImmutableList; `to_mutable()`.
   * `deep_freeze(value)` — рекурсивная глубокая заморозка-копия;
   * `unfreeze(value)` — точная обратная конверсия.
2. `StrategyConfig`:
   * `__post_init__` — валидация strategy_id/strategy_version/config_hash/
     origin (непустые строки), params/metadata (Mapping) → StrategyConfigError;
   * глубокая заморозка-копия params/metadata через `object.__setattr__`;
   * новый метод `recompute_config_hash()` — hash по фактически сохранённым
     параметрам;
   * новый метод `as_dict()` — глубокая модифицируемая JSON-совместимая копия
     (множества → отсортированные списки = нормализация config_hash).
3. `EntrySignalInput.extra` и `Signal.metadata` — та же природа замечания №1
   в том же файле: заморозка в `__post_init__` (None → пустое отображение).
4. Шапка модуля дополнена описанием гарантий Stage A.1.

**Влияние на обратную совместимость:**
* Все прежние вызовы работают: `Strategy.get_config`, `engine_config.load_engine_config`,
  legacy-мост (`params.items()`, `config.metadata.get("profile")`) — ImmutableMapping
  предоставляет полный read-API (`[]`, `get`, `items`, `keys`, `values`,
  `__contains__`, итерация, равенство с dict).
* `canonical_config_payload`/`compute_config_hash` не изменены: frozen-типы
  прозрачно обрабатываются `_normalize_for_json` — config_hash всех
  существующих конфигураций не изменился (byte-stable).
* Единственное новое ограничение: `StrategyConfig(params=None)` / не-Mapping /
  metadata не-Mapping теперь отклоняются при создании (ранее — падали позже
  при использовании); прямое `json.dumps(config.params)` требует `as_dict()`.
  Ни один существующий тест/потребитель этими путями не пользуется
  (проверено: 899 прежних тестов проходят).

**Соответствующие тесты:** `tests/test_stage_a1_config_immutability.py` (48),
а также без изменений `tests/test_stage_a_strategy_api.py` (22),
`tests/test_stage_a_legacy_adapter.py` (31), `tests/test_stage_a_engine_config.py` (24).

## 3. ФАЙЛ №2: `candidate/attribution.py` (+333/−старая логика)

**Замечания аудита:** №2 (атрибуция не встроена в производственный поток) и
№3 (глобальный контекст).

**Причина изменения:** глобальное состояние `_current_context` могло
присвоить объекту одной стратегии контекст другой; отдельные функции stamp/CSV
не образовывали явного интерфейса атрибуции нового движка.

**Содержание изменения:**

1. **УДАЛЕНО:** `_current_context`, `set_current_context()`,
   `get_current_context()`, `clear_current_context()` — глобального изменяемого
   состояния больше не существует; ContextVar не используется (явный DI).
2. `AttributionContext`: неизменяемая валидированная пара; новый classmethod
   `from_config(config)` — единый явный вывод контекста из StrategyConfig
   (валидация, ошибки без фиктивных значений).
3. `stamp(record, context, *, overwrite=False)` — контекст ОБЯЗАТЕЛЕН
   (AttributionContext или StrategyConfig; `_resolve_context` единый механизм);
   None → `AttributionRequiredError`; конфликт полей → объект не создаётся;
   вход не мутируется; проверка типа record.
4. **НОВОЕ:** `AttributionFactory` — фабрика атрибутированных объектов нового
   движка, привязанная к одному неизменяемому контексту:
   `new_event`, `new_virtual_order`, `new_virtual_position`, `append_csv_row`,
   `append_jsonl_row`, `stamp`; запрет замены контекста (`__setattr__` → TypeError).
5. **НОВОЕ:** `append_attributed_jsonl_row(path, record, *, context)` — журнал
   JSONL новых событий движка (allow_nan=False — fail-closed).
6. `append_attributed_csv_row(..., *, context, delimiter)` — context стал
   обязательным keyword-only параметром.
7. **НОВОЕ:** `read_jsonl_attribution_report(path)` — безопасное чтение старых
   JSONL (симметрично CSV-версии).
8. Шапка модуля: честная документация границы Этапа A.1 (что работает, какие
   типы объектов, какие интерфейсы, что подключается на Этапе B).

**Влияние на обратную совместимость:**
* Чтение старых записей: `legacy_attribution_view`, `record_has_attribution`,
  `read_csv_attribution_report` — без изменений.
* Старые файлы/производственный поток не затронуты (модуль по-прежнему не
  импортируется production-кодом — проверено тестом).
* Изменившаяся сигнатура `stamp`/`append_attributed_csv_row` затронула только
  тест Stage A, использовавший глобальный API (адаптация — Файл №4);
  все вызовы с явным `context=...` продолжают работать.

**Соответствующие тесты:** `tests/test_stage_a1_attribution_explicit.py` (33),
`tests/test_stage_a_attribution.py` (22).

## 4. ФАЙЛ №3: `candidate/engine_config.py` (+14 строк)

**Замечание аудита:** №2 (единый явный механизм передачи контекста).

**Причина изменения:** консолидация создания контекста атрибуции в одну
явную точку.

**Содержание изменения:**

1. `attribution=AttributionContext(strategy_id=..., config_hash=...)` →
   `attribution=AttributionContext.from_config(config)` — идентичный результат
   через единый механизм.
2. Комментарий в шапке модуля: явная передача атрибуции, отсутствие
   глобального контекста, путь подключения AttributionFactory на Этапе B.

**Влияние на обратную совместимость:** поведение идентично прежнему
(контекст формируется из тех же полей той же конфигурации); все 24 теста
engine_config проходят без правок.

**Соответствующие тесты:** `tests/test_stage_a_engine_config.py` (24),
`tests/test_stage_a1_attribution_explicit.py::TestUnifiedExplicitMechanism`.

## 5. ФАЙЛ №4: `candidate/tests/test_stage_a_attribution.py` (+54/−88 строк)

**Замечания аудита:** №2, №3 — адаптация тестов к исправленной архитектуре.

**Причина изменения:** тесты использовали удалённый глобальный API
(set_current_context и autouse-фикстура очистки).

**Содержание изменения:**

1. Удалены импорты `set_current_context/get_current_context/clear_current_context`
   и autouse-фикстура `_clean_current_context`.
2. `test_current_context_is_used_when_set` → `test_explicit_context_is_the_only_source`
   (проверяет отсутствие глобального API + корректность явной передачи;
   семантика «контекст определяет атрибуцию» сохранена).
3. `test_missing_context_fails_closed` / `test_missing_context_error_message_explains`
   — новая сигнатура: `stamp(record, None) → AttributionRequiredError`,
   `stamp(record) → TypeError`.
4. `test_no_context_no_row` — `context=None` явно (CSV), файл не создаётся.
5. `test_unconfigured_produces_no_attribution` — `stamp({}, None)`.

**Влияние на обратную совместимость:** количество тестов сохранено (22);
эталоны (golden signals, профили) НЕ менялись; все содержательные проверки
атрибуции/чтения старых записей сохранены 1:1.

**Соответствующие тесты:** сам файл — 22 passed.

## 6. ФАЙЛ №5 (НОВЫЙ): `candidate/tests/test_stage_a1_config_immutability.py`

**Причина:** обязательные corrective-тесты замечания №1 (9 обязательных
проверок задания + сервисные). 48 тестов. Перечень см.
CORRECTIVE_IMPLEMENTATION_REPORT.md п. 2.4 и TEST_RESULTS.txt п. 6.1.

## 7. ФАЙЛ №6 (НОВЫЙ): `candidate/tests/test_stage_a1_attribution_explicit.py`

**Причина:** обязательные corrective-тесты замечаний №2/№3 (8 обязательных
проверок + интерфейсы типов объектов + журналы + чтение старых записей +
граница Этапа A). 33 теста. Перечень см. TEST_RESULTS.txt п. 6.2.

## 8. ФАЙЛЫ, КОТОРЫЕ НЕ ИЗМЕНИЛИСЬ (контроль целостности)

* в candidate/ — 163 файла байт-неизменны (SHA256); в корне пакета —
  4 отчёта Stage A + docs/ (6 файлов); итого по манифесту 173 [ ];
* 14 production-файлов baseline — байт-идентичны коммиту 884cefd;
* `tests/fixtures/legacy_golden_signals.json` — SHA256 не изменился
  (эталон G-1 не переснимался);
* `strategies/legacy_samsung_v4/*` — без изменений (профили == baseline);
* `engine.json` — без изменений (ACTIVE_STRATEGY: null — UNCONFIGURED);
* FORCE_TRADE в новой архитектуре отсутствует (как и в Stage A).
