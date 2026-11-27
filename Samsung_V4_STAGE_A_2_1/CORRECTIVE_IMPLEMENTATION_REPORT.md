# CORRECTIVE_IMPLEMENTATION_REPORT.md
# SAMSUNG V4 — NEW STRATEGY ENGINE. STAGE A.1 (CORRECTIVE)

**Дата:** 2026-11-27
**Исходный пакет:** Samsung_V4_STAGE_A (Stage A; рабочая версия, изолированная копия)
**Baseline:** commit `884cefd6f12a99f6adc14b5ed4c9eeda21d32e04` (`cristal-hub/Samsung-V4-BASELINE`, READ-ONLY; работа велась в изолированной копии, baseline не изменялся)
**Цель Stage A.1:** закрыть три замечания независимого аудита Stage A без повторной реализации Stage A и без изменения существующей торговой системы.
**Результат:** 980 passed / 0 failed (771 baseline + 128 Stage A + 81 corrective). Новых регрессий нет. Production-код Samsung V4 не изменён (байт-идентичен baseline).

---

## 1. ОБЪЁМ И ОГРАНИЧЕНИЯ (выполнено / не выполнено)

Stage A.1 — ТОЛЬКО корректировка Stage A. Не выполнено (по запрету ТЗ):

* не изменены торговые сигналы, параметры/пороги, риск-менеджмент, BUY/SELL,
  исполнение заявок, мониторинг и закрытие позиций (production-файлы
  байт-идентичны baseline — SHA256-проверка, см. п. 8);
* не реализованы Этапы B–H (нет изоляции состояния (strategy_id, FIGI),
  evaluate_exit, нового риск-менеджмента, симулятора, Sandbox-adapter);
* нет подключений к брокеру, нет Sandbox/LIVE-запусков, нет заявок,
  нет миграции пользовательских данных;
* baseline не изменён; результат не загружался в GitHub; ветки/коммиты/PR/issue
  не создавались (работа в изолированной копии пакета);
* оригинальный пакет Samsung_V4_STAGE_A не перезаписывался.

## 2. ЗАМЕЧАНИЕ №1 — НЕИЗМЕНЯЕМОСТЬ StrategyConfig (ИСПРАВЛЕНО)

### 2.1. Суть проблемы (подтверждена)

`@dataclass(frozen=True)` защищает только атрибуты верхнего уровня. `params` и
`metadata` были обычными `Mapping`, полученными снаружи: после вычисления
`config_hash` внешний код мог изменить вложенный словарь/список по ссылке,
и объект переставал соответствовать собственной идентификации.

### 2.2. Решение (strategy_api.py)

Введены глубоко неизменяемые структуры (рекурсивное immutable-представление +
`MappingProxyType` с глубокой защитой):

* **`ImmutableMapping`** (наследник `collections.abc.Mapping`) — отображение
  БЕЗ операций записи: класс не реализует `__setitem__/__delitem__/update/pop/
  clear/setdefault` (Mapping ABC содержит только чтение); присвоение атрибутов
  запрещено (`__setattr__` → `TypeError`); внутреннее хранилище —
  `MappingProxyType` поверх **собственной копии** данных, поэтому запись через
  приватный атрибут `_data` также отклоняется на уровне C (`TypeError`);
  ключи — только строки (fail-closed); равенство семантическое
  (`ImmutableMapping == dict` с тем же содержимым); хеш согласован с
  равенством (требуется для `hash(StrategyConfig)`).
* **`ImmutableList`** (подкласс `tuple`) — C-уровневая неизменяемость: у типа
  не существует операций записи вообще; значения заморожены рекурсивно;
  семантическое равенство с `list`/`tuple`; срез возвращает `ImmutableList`.
* **`deep_freeze(value)`** — рекурсивная глубокая заморозка-КОПИЯ:
  `Mapping → ImmutableMapping`, `list/tuple → ImmutableList`,
  `set → frozenset`, скаляры — как есть; никаких скрытых преобразований
  значений.
* **`unfreeze(value)`** — точная глубокая модифицируемая копия (обратная
  операция; множества возвращаются как `set`).

`StrategyConfig`:

* `__post_init__` валидирует `strategy_id`, `strategy_version`, `config_hash`,
  `origin` (непустые строки), типы `params`/`metadata` (Mapping) — fail-closed;
* `params` и `metadata` при создании **копируются и замораживаются**
  (`object.__setattr__` с `ImmutableMapping(...)`): изменение исходных
  словарей после создания конфигурации не влияет на её содержимое (требование
  7 задания);
* `recompute_config_hash()` — config_hash, вычисленный по **фактически
  сохранённым** параметрам (требование 9: config_hash соответствует
  фактическому содержимому; обнаруживает рассинхронизацию при ручном
  конструировании);
* `as_dict()` — глубокая модифицируемая **JSON-совместимая** копия
  (множества → отсортированные списки — та же нормализация, что и в расчёте
  config_hash), поэтому JSON round-trip сохраняет и значения, и config_hash;
  точная копия params/metadata доступна через `params.to_mutable()` /
  `metadata.to_mutable()`.

Та же природа дефекта внутри того же файла исправлена для носителей контракта:
`Signal.metadata` и `EntrySignalInput.extra` замораживаются в `__post_init__`
(`None → пустое отображение`, совместимо с прежним поведением, при котором
`None` не читался). Поведение существующих потребителей не изменилось
(все 899 прежних тестов проходят без правок, кроме адаптации проверок
глобального контекста — см. п. 4).

Сериализация для hash (`canonical_config_payload`) не изменена:
`ImmutableMapping`/`ImmutableList` прозрачно обрабатываются существующими
ветками `_normalize_for_json` (Mapping/(list, tuple)/frozenset) — детерминизм
сохранён (требование 8).

### 2.3. Что невозможно блокировать принципиально (зафиксировано)

`object.__setattr__` на уровне интерпретатора может обойти защиту ЛЮБОГО
Python-объекта (включая frozen-dataclass и MappingProxyType). Это свойство
платформы, а не контракта; на уровне API операций записи не существует
(проверено тестами). Хостильный обход интерпретатора остаётся вне модели
угроз контракта.

### 2.4. Обязательные тесты (замечание №1) — ВСЕ PASS

Файл `tests/test_stage_a1_config_immutability.py` (48 тестов):

| Требование задания | Тесты | Статус |
|---|---|---|
| попытка изменить верхнеуровневый params | `test_params_field_assignment_blocked`, `test_params_item_assignment_blocked`, `test_params_item_deletion_blocked`, `test_params_is_immutable_mapping` | PASS |
| попытка изменить вложенный словарь | `test_nested_dict_*` (4 теста, в т.ч. запись в `_data`) | PASS |
| попытка изменить вложенный список | `test_nested_list_*` (assignment/append/внутренние списки) | PASS |
| попытка изменить metadata | `test_metadata_*` (field/item/nested/тип) | PASS |
| изменение исходного словаря после создания | `test_source_*` (3 теста, config_hash не меняется) | PASS |
| попытка изменить config_hash | `test_config_hash_assignment_blocked` | PASS |
| одинаковая конфигурация после сериализации → одинаковый hash | `test_same_config_after_json_roundtrip_same_hash`, `test_hash_independent_of_json_key_order` | PASS |
| изменение значимого параметра → новый hash | `test_meaningful_param_change_creates_new_hash`, `test_nested_param_change_creates_new_hash` | PASS |
| round-trip сериализация не меняет семантику | `test_round_trip_*`, `test_json_roundtrip_preserves_config_hash_even_for_sets`, `test_as_dict_is_deep_mutable_copy` | PASS |

Тесты проверяют реальное поведение (реальные операции мутации и реальные
сериализации), а не только наличие `frozen=True`.

## 3. ЗАМЕЧАНИЕ №2 — АТРИБУЦИЯ ПРОИЗВОДСТВЕННЫХ ОБЪЕКТОВ (ИСПРАВЛЕНО)

### 3.1. Разделение трёх подсистем (требование задания)

| Подсистема | Статус в Stage A.1 |
|---|---|
| Старая система Samsung V4 (main.py, execution.py, logger.py, order_ledger.py, config.py, strategy.py) | **НЕ ИЗМЕНЕНА** — байт-идентична baseline 884cefd; старые журналы/ордера/позиции полностью совместимы; никакая атрибуция в них не внедрялась |
| Самостоятельный новый движок | **Атрибуция реализована как самостоятельный, полностью протестированный интерфейс** (attribution.py): каждый новый объект нового движка получает strategy_id + config_hash через явную зависимость |
| Регрессионный адаптер старой стратегии | Без изменений: regression-only, origin='regression_harness', `strategies/legacy_samsung_v4/` не активируется торговым режимом (проверено 128 Stage A тестами) |

### 3.2. Единый явный механизм передачи контекста

* **`AttributionContext`** — неизменяемая (frozen) валидированная пара
  `(strategy_id, config_hash)`; `AttributionContext.from_config(config)` —
  явный вывод контекста из `StrategyConfig` (None/пустые значения →
  `AttributionError`).
* **`stamp(record, context)`** — контекст ОБЯЗАТЕЛЕН (явная передача);
  принимает `AttributionContext` или `StrategyConfig` (вывод контекста
  единым механизмом `_resolve_context`); контекст не передан →
  `AttributionRequiredError` (при `None`) / `TypeError` (при пропущенном
  аргументе).
* **`AttributionFactory`** — фабрика атрибутированных объектов, привязанная
  к одному неизменяемому контексту (явное внедрение зависимости):
  * `new_event` — новые объекты событий;
  * `new_virtual_order` — новые виртуальные ордера;
  * `new_virtual_position` — новые виртуальные позиции;
  * `append_csv_row` / `append_jsonl_row` — новые строки исследовательского
    CSV/JSONL;
  * `stamp` — произвольная новая запись.
* Никаких фиктивных значений (`UNKNOWN`, пустых строк, случайных заглушек);
  конфликт переданных полей атрибуции с контекстом → объект **не создаётся**
  (`AttributionError`); входные записи не мутируются.

### 3.3. Граница Stage A.1 — ЧЕСТНО (обязательное требование задания)

**Что уже работает (реализовано и протестировано):**

1. Неизменяемый `AttributionContext` + вывод из `StrategyConfig`.
2. `AttributionFactory` — единая точка создания атрибутированных объектов
   нового движка для всех четырёх типов объектов (события, виртуальные
   ордера, виртуальные позиции, исследовательские CSV/JSONL-строки).
3. Журналы нового движка: `append_attributed_csv_row`,
   `append_attributed_jsonl_row` (только новые записи).
4. Безопасное чтение старых записей: `legacy_attribution_view`,
   `read_csv_attribution_report`, `read_jsonl_attribution_report` —
   без миграции, без дописывания атрибуции, файлы байт-неизменны.

**Какие типы новых объектов атрибутируются:** события, виртуальные ордера,
виртуальные позиции, строки исследовательского CSV/JSONL — через
`AttributionFactory`/`stamp` с явным контекстом.

**Какие интерфейсы готовы для будущих компонентов движка:**
`EngineConfig.attribution` (неизменяемый контекст CONFIGURED-конфигурации) →
`AttributionFactory(context)` → создание всех новых объектов. Архитектурно
подключение предусмотрено: компонент Этапа B получает фабрику как явную
зависимость при инициализации.

**Какие подключения будут выполнены на следующих этапах (Этап B+):**

1. Добавление `strategy_id`/`config_hash` в конец `TRADE_FIELDS` логгера
   `research_trades.csv` (существующий механизм авто-миграции шапки сохранит
   старый журнал как `research_trades_<timestamp>.bak.csv`) —bloker Stage A
   остаётся в силе и НЕ устранялся в A.1 (требует изменения производственной
   схемы CSV; вне объёма корректировки).
2. Передача `AttributionFactory` в компоненты исполнения/позиций нового
   движка (Этап B) при их создании.
3. Подключение записи событий движка через `append_jsonl_row` в
   runtime-контуры Этапа B.

**Что НЕ сделано (и не выдаётся за внедрённое):** атрибуция НЕ встроена в
старый production-поток (main.py/execution.py/logger.py/order_ledger.py);
тест `test_attribution_module_does_not_touch_production_flow` фиксирует, что
эти модули не ссылаются на атрибуцию нового движка.

## 4. ЗАМЕЧАНИЕ №3 — УБРАТЬ ГЛОБАЛЬНЫЙ КОНТЕКСТ АТРИБУЦИИ (ИСПРАВЛЕНО)

### 4.1. Что сделано

* Из `attribution.py` **удалены** глобальное состояние и его API:
  `_current_context`, `set_current_context()`, `get_current_context()`,
  `clear_current_context()`. В модуле не осталось ни глобальной, ни
  потоковой переменной «текущей стратегии».
* Выбран **явный механизм внедрения зависимостей** (предпочтительный по
  заданию): `AttributionContext` передаётся в функции создания объектов
  явно или привязывается к `AttributionFactory` при её создании.
* ContextVar НЕ используется — явная передача надёжнее и проще для
  доказательства корректности при параллельной работе.
* `engine_config.py` несёт контекст в `EngineConfig.attribution`
  (неизменяемое поле результата загрузки) — тоже явная передача, без
  глобальных переменных.

### 4.2. Обязательные тесты (замечание №3) — ВСЕ 8 PASS

Файл `tests/test_stage_a1_attribution_explicit.py` (33 теста):

1. Две стратегии с разными `strategy_id`/`config_hash` —
   `test_two_strategies_have_different_ids_and_hashes` — PASS.
2. Одновременное создание объектов обеих стратегий — чередование
   (`test_interleaved_creation_keeps_own_attribution`) + параллельные потоки
   4×50 объектов (`test_concurrent_threads_no_cross_contamination`) — PASS.
3. Объекты получают только собственную атрибуцию — PASS.
4. Отсутствие перекрёстного загрязнения — PASS (включая одну запись,
   штампованную обеими стратегиями; исходная запись не мутируется).
5. Отсутствие контекста → явная ошибка — PASS (`None → AttributionRequiredError`;
   пропущенный аргумент → `TypeError`; фабрика с недопустимым контекстом →
   `AttributionRequiredError`).
6. Вложенные вызовы не меняют контекст вызывающего кода — PASS.
7. Исключение при создании объекта не оставляет устаревший контекст — PASS
   (контекст фабрики неизменяем по построению; после `AttributionError`
   фабрика продолжает работу со своим контекстом).
8. Повторный запуск не зависит от порядка предыдущих тестов — PASS
   (сценарий в двух порядках даёт идентичные результаты; оба файла
   прогонялись в обоих порядках и по отдельности — 81 passed в каждом
   прогоне).

Дополнительно: структурная проверка, что глобального API больше не существует
(`test_global_context_api_removed`), и проверка отсутствия фиктивных значений.

## 5. ИЗМЕНЁННЫЕ И НОВЫЕ ФАЙЛЫ (полный список с причинами)

| Файл | Тип | Причина (замечание) | Содержание изменения | Совместимость | Тесты |
|---|---|---|---|---|---|
| `candidate/strategy_api.py` | изменён | №1 | ImmutableMapping/ImmutableList/deep_freeze/unfreeze; валидация полей StrategyConfig; глубокая заморозка params/metadata; recompute_config_hash(); as_dict() (JSON-совместимая); заморозка Signal.metadata/EntrySignalInput.extra (та же природа замечания №1 в том же файле) | Полная: все прежние потребители (get_config, engine_config, legacy adapter) работают без изменений; существующие тесты проходят | 48 новых + 22 Stage A strategy_api |
| `candidate/attribution.py` | изменён | №2, №3 | Удалены set_current_context/get_current_context/clear_current_context/_current_context; stamp(context) обязателен; AttributionContext.from_config; AttributionFactory (new_event/new_virtual_order/new_virtual_position/append_csv_row/append_jsonl_row); append_attributed_jsonl_row; read_jsonl_attribution_report; честная документация границы Этапа A в шапке модуля | Чтение старых записей без изменений (функции сохранены); старые журналы не трогаются; production-поток не зависит от модуля | 33 новых + 22 Stage A attribution |
| `candidate/engine_config.py` | изменён | №2 (единый механизм) | Конструирование контекста через AttributionContext.from_config(config) (единая явная точка); комментарий в шапке об явной передаче атрибуции | Поведение идентично прежнему (контекст формируется из тех же полей) | 24 Stage A engine_config |
| `candidate/tests/test_stage_a_attribution.py` | изменён | №2, №3 (адаптация тестов) | Удалены импорт/фикстура глобального контекста; test_current_context_is_used_when_set → test_explicit_context_is_the_only_source; проверки «нет контекста» приведены к новой сигнатуре (None → AttributionRequiredError; пропуск → TypeError; context=None для CSV) | Количество тестов сохранено (22); эталоны golden/профилей НЕ менялись | 22 Stage A attribution |
| `candidate/tests/test_stage_a1_config_immutability.py` | новый | №1 | 48 corrective-тестов неизменяемости (см. п. 2.4) | — | PASS 48 |
| `candidate/tests/test_stage_a1_attribution_explicit.py` | новый | №2, №3 | 33 corrective-теста явной атрибуции и изоляции (см. п. 4.2) | — | PASS 33 |

Машинный diff: `APPENDIX_FULL_DIFF.patch` (полный, 6 файлов, +1758/−88 строк).
Файлы, не относящиеся к трём замечаниям, НЕ менялись (в candidate/ 163 файла
байт-неизменны; 14 production-файлов байт-идентичны baseline; в корне пакета
без изменений остались отчёты Stage A: README_STAGE_A.md,
IMPLEMENTATION_REPORT.md, CHANGELOG.md, BASELINE_VS_CANDIDATE.md).

## 6. ОБРАТНАЯ СОВМЕСТИМОСТЬ (раздел 5 ТЗ Stage A.1) — проверено

| Проверка | Результат |
|---|---|
| Старые baseline-файлы не изменены | PASS — 14 production-файлов байт-идентичны 884cefd (SHA256) |
| Старые профили идентичны baseline | PASS — test_stage_a_legacy_profiles (11) |
| FORCE_TRADE не появился в новой архитектуре | PASS — G-5 (запрос профиля → ValueError), config.PROFILE baseline не изменён |
| Старая стратегия остаётся regression-only | PASS — test_stage_a_legacy_adapter (31) |
| ACTIVE_STRATEGY не получает автоматического значения | PASS — test_stage_a_engine_config (24; UNCONFIGURED без значения, CONFIG_ERROR для неизвестного) |
| engine.json работает как раньше | PASS — N-01…N-04 |
| Environment override работает как раньше | PASS — приоритет env > JSON (24 теста) |
| Существующие golden tests не изменились по смыслу и результатам | PASS — G-1 (15 эталонов), G-5; файлы эталонов не менялись (SHA256) |
| Старые журналы читаются без миграции | PASS — CSV/JSONL-файлы байт-неизменны после чтения; `legacy_attribution_view` возвращает явные None/False |

Тестовые эталоны НЕ менялись ради получения PASS: единственные правки тестов —
адаптация к удалённому глобальному API (см. TEST_RESULTS.txt п. 5).

## 7. ДОПОЛНИТЕЛЬНЫЕ НАБЛЮДЕНИЯ (зафиксированы отдельно, НЕ исправлялись)

1. **Интерпретаторный обход защиты** (`object.__setattr__`) технически возможен
   для любого Python-объекта — свойство платформы, вне модели угроз контракта
   (см. п. 2.3). Не является дефектом Stage A.1.
2. **Stage B blocker из отчёта Stage A остаётся в силе:** внедрение атрибуции
   в `research_trades.csv` требует изменения схемы логгера (авто-ротация
   шапки) — сознательно не выполнялось в A.1 (вне объёма корректировки,
   относится к Этапу B).
3. **`ImmutableMapping` не является `dict`:** прямое `json.dumps(config.params)`
   вызовет TypeError; документированный путь — `config.as_dict()` /
   `params.to_mutable()`. Это контракт, а не дефект (в тестах зафиксирован).
4. **`fields as _dc_fields`** импорт в strategy_api.py остаётся неиспользуемым
   со Stage A — не трогался (вне объёма корректировки; не влияет на поведение).

## 8. ЦЕЛОСТНОСТЬ И ЦИФРЫ

* Полный regression suite после корректировки: **980 passed / 0 failed /
  0 skipped** (baseline 771 + Stage A 128 + corrective 81; дельта +81 = только
  новые corrective-тесты).
* Канонический поднабор: `python -m pytest tests` → **460 passed / 0 failed**.
* Смешанный запуск старых/новых тестов: 200 passed / 0 failed.
* В коде пакета (candidate/) изменено 4 файла, добавлено 2; остальные
  163 файла candidate/ + отчёты Stage A в корне + docs/ — байт-неизменны
  (SHA256 в `FILE_MANIFEST_SHA256.txt`; итог по манифесту: 188 файлов =
  6 [M] + 9 [A] + 173 [ ]).
* SKIP-тестов нет; фиктивных заглушек нет; среда соответствует «окружению 1»
  отчёта Stage A (Python 3.12.16, pytest 9.0.2, pandas 2.2.3, numpy 2.1.3,
  pandas-ta-classic 0.3.15, python-dotenv 1.2.2, python-telegram-bot 21.11.1,
  штатная заглушка t-tech-investments из tests/conftest.py).

## 9. ИЗВЕСТНЫЕ ОГРАНИЧЕНИЯ И НЕОТЛОЖЕННЫЕ ВОПРОСЫ

1. Атрибуция нового движка не встроена в производственный поток baseline —
   это ГРАНИЦА Этапа A/A.1, а не дефект: внедрение запланировано на Этап B
   (см. п. 3.3).
2. Мульти-стратегическая параллельность доказана на уровне фабрик и потоков
   (threading); asyncio-контуры будут покрываться на Этапе B, когда появятся
   асинхронные компоненты движка.
3. `config_hash` по-прежнему не включает metadata (задокументировано со
   Stage A): две конфигурации, отличающиеся только metadata, имеют один hash
   и различаются содержимым metadata — зафиксировано тестом.

## 10. СТАТУС

**STAGE A.1: COMPLETE — все три замечания аудита закрыты.**
Все критерии приёмки раздела 9 ТЗ Stage A.1 выполнены (см. TEST_RESULTS.txt
п. 9). Следующий этап — независимая проверка результата; Stage B не начинался.
