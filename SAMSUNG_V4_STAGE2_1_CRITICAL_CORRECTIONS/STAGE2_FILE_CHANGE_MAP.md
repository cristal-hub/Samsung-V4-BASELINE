# STAGE2_FILE_CHANGE_MAP.md

## SAMSUNG V4 — STAGE 2: карта изменений файлов

**Статус:** `STAGE 2.1 — DESIGN CORRECTIONS ONLY / SOURCE CODE: UNCHANGED`
(версия 2.1: исправлена по замечаниям независимой проверки; изменённые
строки помечены «Stage 2.1»; см. STAGE2_1_CHANGELOG.md). Всё содержимое
— ПРОЕКТ будущих изменений; ни один файл не изменён. Ссылки `файл:строка`
действительны для commit `884cefd…` (проверены по рабочему дереву Stage 2).

Правила чтения карты:

- **НОВЫЙ** — файла не существует; создаётся при реализации.
- **ИЗМЕНЕНИЕ** — существует; правки перечислены по конкретным областям.
- **БЕЗ ИЗМЕНЕНИЙ** — правки не планируются; причина фиксируется.
- Колонка «Риск» оценивает вероятность регрессии и меру защиты
  (golden-тесты — G, негативные тесты — N, контрактные тесты — K;
  нумерация тестов — STAGE2_TEST_MATRIX.md).

---

## 1. Сводная таблица изменений (§7 ТЗ)

| Файл / модуль | Текущее назначение | Планируемое изменение | Причина | Риск |
|---|---|---|---|---|
| `main.py` | торговый движок: цикл, входы, регистрация BUY, close_position, reconcile, В2/В3, persistence, recovery | ИЗМЕНЕНИЕ (точечное, 6 областей — §2.1) | подключение реестра стратегий, per-pair состояние, exit-конвейер двух списков выходов (§6.2, Stage 2.1), stop-distance в sizing + контроль фактического риска (§7.4), clock-инъекция | Средний. Наибольший diff проекта; защищается golden-тестами G-1…G-4, T-14/T-15 и сохранением всех защитных механизмов |
| `strategy.py` | логика Tsclp_v2.0: ADX regime/hysteresis, MA/BB+RSI, объём | ИЗМЕНЕНИЕ (фасад) — тело переносится в `strategies/legacy_samsung_v4/strategy.py`; старый файл становится делегирующим фасадом на переходный период | контракт стратегии + FROZEN-статус legacy (§8 blueprint) | Низкий-средний. Golden-тест G-1: сигналы идентичны байт-в-байт |
| `risk_manager.py` | sizing, SL/TP, hard caps, daily counts | ИЗМЕНЕНИЕ (3 области — §2.2) | контракт стоп-дистанции (§7 blueprint), делегирование SL/TP стратегии, атрибуция | Средний. Formula-тесты F-1…F-3: при legacy-дистанции результат идентичен текущему |
| `execution.py` | учёт позиций: TrackedPosition, check_all, per-order cursor, BE/TRAIL | ИЗМЕНЕНИЕ (2 области — §2.3) | атрибуция позиций strategy_id; маршрутизация exit-политики по автору позиции | Низкий. Поле в конец dataclass (asdict-совместимо); учётные механики не трогаются |
| `order_ledger.py` | append-only реестр заявок INTENT/SENT/… | ИЗМЕНЕНИЕ (1 область — §2.4) | атрибуция заявок strategy_id (INHERIT-режим, аудит) | Низкий. Поле добавляется В КОНЕЦ RECORD_FIELDS — практика уже применялась (commission, order_request_id) |
| `config.py` | конфигурация: env-токены, риск, стратегия, PROFILE-ветвление | ИЗМЕНЕНИЕ (3 области — §2.5) | категории A–E; PROFILE-ветвление уходит в legacy profiles.py; валидатор расширяется | Средний. Golden-тест G-5: фактические значения каждого профиля == текущим |
| `logger.py` | research_events.jsonl + research_trades.csv | ИЗМЕНЕНИЕ (1 область — §2.6) | strategy_id/config_hash в шапке событий и колонках CSV | Низкий. Авто-миграция шапки уже реализована (logger.py:160-172) |
| `tinkoff_client.py` | SDK-клиент: fail-closed контракт, sandbox-only, пост заявки | БЕЗ ИЗМЕНЕНИЙ | адаптер оборачивает клиент; контракт уже соответствует ExecutionAdapter | Нулевой |
| `build_safety.py` | Режим A/B, guard заявок, sandbox-only | БЕЗ ИЗМЕНЕНИЙ | тройной запрет LIVE сохраняется во всех ветках архитектуры | Нулевой |
| `screener.py` | TOP-10 волатильных MOEX | БЕЗ ИЗМЕНЕНИЙ | вселенная параметризуется категорией E без смены логики; сортировка (196-197) остаётся — порядок обхода более не влияет на сигналы (изоляция состояния) | Нулевой |
| `telegram_bot.py` | /start /stop /status, watchdog | БЕЗ ИЗМЕНЕНИЙ (опционально: /status дополнит вывод полем ACTIVE_STRATEGY) | управление trading.flag не зависит от стратегий | Нулевой |
| `safe_start.py` | Режим A: READ-ONLY проверка сборки | ИЗМЕНЕНИЕ (1 область — §2.7) | проверка ACTIVE_STRATEGY/реестра/схемы в стартовой диагностике | Низкий. Не влияет на движок |
| `enable_sandbox_execution.py` | инструмент включения Режима B | БЕЗ ИЗМЕНЕНИЙ | процедура включения не меняется | Нулевой |
| `conftest.py` + `tests/` | тестовая инфраструктура | ИЗМЕНЕНИЕ (только добавление новых файлов тестов) | матрица тестирования Stage 2 | Низкий. Существующие тесты не изменяются |
| `strategies/` (каталог) | — | НОВЫЙ (§3) | контракт, реестр, legacy-стратегия | — |
| `strategy_api.py` | — | НОВЫЙ (§3.1) | интерфейсы StrategyBase/Decision/Manifest/EngineContext | — |
| `engine_config.py` | — | НОВЫЙ (§3.2) | загрузка/валидация runtime.env + engine.json + params.json (fail-closed) | — |
| `state_store.py` | — | НОВЫЙ (§3.3) | strategy_state per-(id, figi): чтение/запись/миграция | — |
| `execution_adapter.py` | — | НОВЫЙ (§3.4) | ExecutionAdapter ABC + SandboxExecutionAdapter | — |
| `backtest/` (пакет) | — | НОВЫЙ (§3.5) | детерминированный симулятор + модели заполнения | — |
| новые тесты | — | НОВЫЙ (§3.6) | изоляция, контракты, backtest-детерминизм, fail-closed конфиг | — |

---

## 2. Детализация изменяемых файлов (§7 ТЗ: конкретные области)

### 2.1. `main.py` — шесть областей

| # | Область (текущие строки) | Изменение | Причина |
|---|---|---|---|
| M-1 | 5663 (`sm = StrategyManager()`), 5653-5671 (зона старта) | создание стратегии через `STRATEGY_REGISTRY[engine_config.active_strategy]` + проверка манифеста против capabilities; дополнительно — вторая стратегия в режиме сопровождения (INHERIT) | §3.1 ТЗ: одна настройка; §6 blueprint |
| M-2 | 5237-5310 (цикл входов), точка 5260 | `get_signal` вызывается у стратегии пары (id, figi); состояние per-pair берётся/возвращается через `state_store`; результат нормализуется в EntryDecision (§4.3 blueprint) | изоляция состояния; контракт входа |
| M-3 | 5135-5152 (шаг 2 цикла: SL/TP) | ИСПРАВЛЕНО Stage 2.1 (замечание №1): конвейер ДВУХ списков (§6.2 blueprint): (1) check_all ПЕРВЫМ — защитные SL/TP/BE/TRAIL без изменений; (2) evaluate_exit для оставшихся OPEN — маркировка CLOSING + reason_code + событие STRATEGY_EXIT_DECISION; (3) объединение ДОБАВЛЕНИЕМ списков с assert-инвариантом INV-1 (без дубликатов; в редакции 2.0 присваивание to_close = check_all(...) теряло стратегические решения); (4) единый цикл закрытия 5145-5152: UNCERTAIN при отсутствии цены (5147-5151) для обоих списков, close_position без изменений | §3.3 ТЗ; замечание №1 проверки Stage 2.1 |
| M-4 | 5278 (`calculate_position_size`), 4072/4808 (`calculate_sl_tp`), 4091-4105 (регистрация позиции) | ИЗМЕНЕНО Stage 2.1 (замечание №3): 5278 — передача `planned_stop_distance` (единицы — цена/акцию; санитарный инвариант 0 < stop < last_price, §7.4 blueprint); при регистрации 4091-4105 — расчёт actual_per_share_risk/actual_risk_total, события STOP_SIZING_MISMATCH и RISK_BUDGET_EXCEEDED (режим наблюдения v1; жёсткий допуск — после D-14; реакция — D-15); 4072/4808: вызов `strategy.compute_exit_levels` (risk_manager остаётся делегатом); регистрация подтверждённого исполнения не блокируется (Дефект №7, 4068-4084) | §3.4 ТЗ; замечание №3 проверки Stage 2.1 |
| M-5 | 1144-1238 (`_save_state`/`_load_state`) | +раздел `strategy_state` (запись в конце цикла, восстановление до первого цикла); +`config_snapshot`/`config_hash` + проверка совпадения при рестарте | §3.2 ТЗ; §10.4 blueprint |
| M-6 | clock-инъекция: прямые `datetime.now(timezone.utc)` — main.py:645, 854, 1500, 1935, 1957, 1988, 2269, 3033, 3074, 5292 и др. (верифицированный Stage 2 список) | замена на `context.clock()` | backtest-детерминизм (T-1.3 Stage 1) |

НЕ изменяются в main.py: INTENT-before-send (5300-5325), partial-ветка
(5369-5471), close_position (2224-2376), reconcile/В2/В3 (2018-2223,
1932-2011), startup_recovery (4831-5108), блокировки входов (5186-5225),
trading.flag (847-868), запрет автозакрытия RECOVERY (151-153).

### 2.2. `risk_manager.py` — три области

| # | Область (строки) | Изменение | Причина |
|---|---|---|---|
| R-1 | 87-207 (`calculate_position_size`) | новая сигнатура c `planned_stop_distance: float` (обязательный параметр; None -> отказ); тело: `per_share_risk = planned_stop + friction`; hard caps 91-92, 142-145, 198-201 и инварианты (stop>0) сохраняются; ATR-ветка 128-132 удаляется из sizing (ATR теперь внутри дистанции стратегии); `daily_trade_counts` — ключ `(strategy_id, figi)` | контракт стоп-дистанции (§7.2 blueprint); соответствие RISK_PER_TRADE |
| R-2 | 233-259 (`calculate_sl_tp`) | делегирование в контракт стратегии: `RiskManager.calculate_sl_tp` вызывает `strategy.compute_exit_levels` (сохранение сигнатуры для внешних вызовов); инварианты sl>0/tp>sl (257-258) проверяются движком ДО применения | SL/TP — решение стратегии, проверка — движок |
| R-3 | 261-263 (`record_trade`), 49-85 (export/import_state) | ключ `record_trade(strategy_id, figi)`; `export_state` совместим: старый формат читается (ключ figi -> ключ (id, figi) при одном legacy-стратеге) | атрибуция; совместимость state.json |

Golden-инвариант: при `planned_stop_distance = entry*max(0.012, 0.005)`
(= текущая база) и том же ATR-расчёте внутри legacy результат sizing
совпадает с текущим байт-в-байт (тест F-1).

### 2.3. `execution.py` — две области

| # | Область (строки) | Изменение | Причина |
|---|---|---|---|
| E-1 | 242-346 (`TrackedPosition`) | + поле `strategy_id: str = "legacy_samsung_v4"` В КОНЕЦ dataclass; `from_dict` — setdefault("strategy_id", "legacy_samsung_v4") для старых state.json | атрибуция позиций; маршрутизация exit-политики |
| E-2 | 978-1022 (`check_all`), 362-377 (init) | без логических изменений; helper `open_positions()` и read-only `view()` теперь ОБЯЗАТЕЛЬНЫ для конвейера выходов (§6.2 Stage 2.1: шаги 2б/2в); фильтр итерации по `pos.state == OPEN` сохраняется | §6.2 blueprint; замечание №1; учёт не трогается |

НЕ изменяются: PositionState/ACTIVE_STATES (204-215), per-order cursor
(656-861), resolve_closing/resolve_uncertain (1024-1246), BE/TRAIL
(872-976), export/import_state (1290-1342, 1713-1756).

### 2.4. `order_ledger.py` — одна область

| # | Область (строки) | Изменение | Причина |
|---|---|---|---|
| L-1 | 73-83 (`RECORD_FIELDS`) | + `"strategy_id"` В КОНЕЦ списка (после "commission"); `record_intent`/`record_sent`/`record_status`/`record_uncertain` (341-412) — передача поля kwarg с default "legacy_samsung_v4" | атрибуция заявок; append-only не нарушается; старые записи: поле None |

НЕ изменяются: load/_append_raw/append (143-341), identity-поля
(85-86), figi_blocks_buy/has_unknown_figi_open_orders (577-592),
prepare/commit_application (440-504).

### 2.5. `config.py` — три области

| # | Область (строки) | Изменение | Причина |
|---|---|---|---|
| C-1 | 63-119 (стратегические константы + PROFILE-ветвление) | блок переносится в `strategies/legacy_samsung_v4/params.json` + `profiles.py` (значения НЕ меняются); в config.py остаётся `raise RuntimeError` для неизвестного имени — теперь в engine_config (fail-closed сохранён) | категории A–E; §5 ТЗ |
| C-2 | 31-42 (риск) + 44-53 (BE/TRAIL) | переносятся в `engine.json` (значения не меняются); параметр `max_execution_price_deviation` добавляется в engine.json ТОЛЬКО после решения D-14 (до решения — режим наблюдения без лимита, §7.4 blueprint, молчаливого дефолта нет); config.py сохраняет env-токены (14-19) и validate() 147-163 | единый движковый конфиг; замечание №3 |
| C-3 | 147-163 (`validate`) | расширение: +проверка ACTIVE_STRATEGY задан и присутствует в реестре; +валидация engine.json/params.json при старте через engine_config | §5 ТЗ: отказ при некорректной конфигурации |

Golden-инвариант (G-5): для каждого из 4 профилей фактические значения
после переноса == config.py:78-117 байт-в-байт.

### 2.6. `logger.py` — одна область

| # | Область (строки) | Изменение | Причина |
|---|---|---|---|
| G-1 | 180-192 (`log_event` шапка), 6-15/101-172 (CSV-шапка и авто-миграция) | шапка события + `strategy_id`, `config_hash`; CSV + колонки `strategy_id`, `config_hash` В КОНЕЦ (авто-миграция уже поддержана) | атрибуция; воспроизводимость |

### 2.7. `safe_start.py` — одна область

| # | Область | Изменение | Причина |
|---|---|---|---|
| S-1 | секции проверок (61-275) | +проверки: ACTIVE_STRATEGY задан; имя найдено в STRATEGY_REGISTRY; params.json проходит schema-валидацию; engine.json валиден (без сети) | стартовая диагностика новой конфигурации |

---

## 3. Новые файлы (§7 ТЗ: имя, назначение, интерфейс, зависимости, вызывающие)

### 3.1. `strategy_api.py` — НОВЫЙ

| Атрибут | Значение |
|---|---|
| Назначение | Единый контракт: StrategyBase (ABC), EntryDecision, ExitDecision, DecisionType, StrategyManifest, EngineContext, normalize_signal() |
| Интерфейс | см. blueprint §4.1 (полный листинг) |
| Зависимости | стандартная библиотека (abc, dataclasses, enum, typing); НЕ зависит от pandas (типизация аннотациями), config, SDK |
| Кто вызывает | strategies/* (реализуют), main.py (M-2/M-3/M-4), state_store.py, backtest/* |
| Обоснование имени/места | один файл = один контракт; импорт из движка и из стратегий не создаёт циклов |

### 3.2. `engine_config.py` — НОВЫЙ

| Атрибут | Значение |
|---|---|
| Назначение | Загрузка runtime.env + engine.json + params.json активной стратегии; слияние варианта (profile); строгая валидация схемы; построение config_snapshot/config_hash; fail-closed: неизвестная стратегия, неизвестный ключ, невалидное значение, отсутствующий критический параметр -> RuntimeError со списком ВСЕХ ошибок |
| Интерфейс | `load_runtime() -> RuntimeConfig`; `load_engine() -> EngineConfig`; `load_strategy_params(strategy_id) -> Mapping`; `build_snapshot() -> (dict, str)`; объекты иммутабельны (MappingProxyType) |
| Зависимости | json, os, hashlib; strategies/__init__ (только список имён); schema.py выбранной стратегии |
| Кто вызывает | main.py (M-1), safe_start.py (S-1), backtest/run.py |
| Важно | НЕТ значений по умолчанию для критических параметров; getattr-fallback не воспроизводится (требование §5 ТЗ; Stage 1 BACKTEST T-6.2) |

### 3.3. `state_store.py` — НОВЫЙ

| Атрибут | Значение |
|---|---|
| Назначение | Хранилище runtime-состояния стратегий: `get(strategy_id, figi)`, `set(strategy_id, figi, state, candle_time)`, `export_state() -> dict`, `import_state(data) -> None`; миграция: старый state.json без раздела -> пустое состояние; конфликт strategy_version -> маркер «входы запрещены» |
| Интерфейс | потокобезопасность не требуется (один event-loop); записи атомарны вместе с _save_state (tmp + os.replace) |
| Зависимости | стандартная библиотека; используется из main.py M-2/M-5 |
| Кто вызывает | main.py; backtest (тот же интерфейс — одинаковая механика состояния в live и backtest) |

### 3.4. `execution_adapter.py` — НОВЫЙ

| Атрибут | Значение |
|---|---|
| Назначение | ExecutionAdapter (ABC) с точным набором операций T-4 (blueprint §9.1) + SandboxExecutionAdapter (делегирование TinkoffClient 1:1, без изменений клиента) |
| Интерфейс | ИЗМЕНЕНО Stage 2.1 (замечание №5): 10 операций таблицы §9.1 (9 сетевых + health-флаг is_uncertain/uncertain_state); инвентаризация покрывает вызовы main.py, execution.py И risk_manager.py (96/109/149/165/181); методы клиента без производственных вызовов (get_all_tradable_shares 227, get_positions_debug 523, get_sandbox_max_lots 458) НЕ входят; screener использует отдельное read-only SDK-соединение (screener.py:130) — вне адаптера; fail-closed семантика фиксируется K-1 (полнота относительно инвентаризации) |
| Зависимости | tinkoff_client.py (только SandboxExecutionAdapter) |
| Кто вызывает | main.py (движок получает adapter вместо сырого клиента —逐步, начиная с этапа E), backtest/simulator.py |

### 3.5. Пакет `backtest/` — НОВЫЙ

| Файл | Назначение | Интерфейс | Зависимости |
|---|---|---|---|
| `backtest/simulator.py` | ИЗМЕНЕНО Stage 2.1 (замечание №4): детерминированный event-driven движок: лента 5-мин свечей, порядок шагов как live (защитные SL/TP -> стратегические выходы §6.2 -> closing -> poll -> promote -> reconcile -> входы), консервативное правило A-13; ВИРТУАЛЬНЫЕ заявки BacktestOrder существуют только внутри пакета — SDK/сетевых импортов нет (§9.6 blueprint, тест S-6); маркер execution_model=backtest_v1 + оговорка backtest_v1_not_profitability_verdict | `BacktestSimulator(adapter, engine_cfg, strategy, candles_feed).run() -> BacktestResult` (события, заявки, CSV-строки) | strategy_api, engine_config, state_store, risk_manager, ExecutionAdapter |
| `backtest/fill_model.py` | Модели заполнения: комиссия A-1, проскальзывание A-2, спред A-3, гэпы A-4, частичное исполнение A-5, тик A-8, лот A-9; ликвидность/market impact — явные заглушки «не моделируется» (A-6/A-7) | `FillModel(params).fill(order, bar, static) -> FillReport` | статическая таблица инструментов |
| `backtest/clock.py` | Инъекция времени: `SimClock(start, bar_step)` — единственный источник времени симуляции | `clock() -> datetime` | — |
| `backtest/instrument_static.py` | Статическая таблица инструментов (lot, tick, spread) из зафиксированного файла (без сетевых вызовов) | `load(path) -> dict[figi]` | — |
| `backtest/run.py` | CLI-обёртка запуска прогона: чтение backtest.json (A-1…A-13), фиксация config_hash, маркировка результатов `execution_model: backtest_v1` | `python -m backtest.run --config backtest.json --feed feed/` | simulator, engine_config |

Явные НЕ-модели v1: ликвидность (A-6), market impact (A-7), корпоративные
события (A-11), задержка данных (A-12) — параметры присутствуют в
backtest.json со значением «none» и задокументированным ограничением
(§9.2 blueprint); молчаливого включения нет.

### 3.6. Каталог `strategies/` — НОВЫЙ

| Файл | Назначение | Содержание |
|---|---|---|
| `strategies/__init__.py` | реестр | `STRATEGY_REGISTRY = {"legacy_samsung_v4": <модуль>}` — явный dict, без рефлексии/сканирования каталогов (Stage 1 STRATEGY_SWITCH §4) |
| `strategies/legacy_samsung_v4/strategy.py` | логика legacy (FROZEN) | построчный перенос strategy.py (465 строк) под StrategyBase; get_signal возвращает (str, str) через legacy-адаптер §4.3; state per-pair через get_state/set_state; алгоритм 1:1 |
| `strategies/legacy_samsung_v4/params.json` | категория A | значения базы = config.py:64-73 (FACT) |
| `strategies/legacy_samsung_v4/profiles.py` | варианты | 4 профиля = config.py:78-117 (значения НЕ меняются) |
| `strategies/legacy_samsung_v4/schema.py` | схема валидации | типы/диапазоны/кроссы по HARDCODED §6 Stage 1; ловушка MIN_CANDLES(60) vs TREND_FILTER_MA(100) для TECH_CHECK/CONSERVATIVE фиксируется как известная конфигурация с доказуемым эффектом (фильтр всегда требует len>=100) — НЕ «оптимизируется», только документируется (Stage 1.1 V-46) |

### 3.7. Новые тестовые файлы — НОВЫЕ

| Файл | Покрытие (номера — STAGE2_TEST_MATRIX.md) |
|---|---|
| `test_state_isolation.py` | T-01, T-02, T-03, T-05 |
| `test_state_persistence.py` | T-04 |
| `test_entry_exit_contract.py` | T-06, T-07, T-08 |
| `test_stop_sizing_consistency.py` | T-09 (F-1…F-3) |
| `test_backtest_model.py` | T-10, детерминизм, A-13 |
| `test_config_failclosed.py` | T-11 |
| `test_safety_invariants.py` | T-12 (расширение test_safety.py) |
| `test_ledger_compat.py` | T-13 (старые журналы/state.json) |
| `test_adapter_contract.py` | K-1 (SandboxExecutionAdapter соответствует ABC; полнота относительно инвентаризации §9.1 Stage 2.1) |
| `test_exit_merge.py` | T-14 (два списка выходов: защитный приоритет, без повторного закрытия, UNCERTAIN, reason_code) |
| `test_actual_risk_control.py` | T-15 (фактический риск после исполнения; STOP_SIZING_MISMATCH/RISK_BUDGET_EXCEEDED) |
| `test_order_class_isolation.py` | S-6 (изоляция виртуальных/Sandbox/LIVE заявок; запрет сетевых импортов в backtest/) |

---

## 4. Порядок применения карты

Карта реализуется этапами A–G (STAGE2_IMPLEMENTATION_ROADMAP.md); каждой
строке этой карты соответствует конкретный этап в колонке «Файлы» roadmap.
Полный diff любого этапа не смешивается с другими (принцип Stage 1
IMPLEMENTATION_ROADMAP §0.4).

---

```
STAGE 2 — DESIGN ONLY
SOURCE CODE: UNCHANGED
```
