# HARDCODED_LOGIC_AND_DEPENDENCIES.md

## Жёстко зашитые настройки, скрытые зависимости, дубли и неиспользуемые объявления

**Мандаты:**

```
STRATEGY LOGIC: UNCHANGED
RESEARCH ONLY
NO THRESHOLD IS OPTIMIZED
NO FILTER IS INSTALLED
NO LIVE ORDERS
```

Документ фиксирует **фактическое состояние кода** на `main@884cefd`.
Ничего не исправлялось и не предлагалось исправлять в рамках этапа 1
(§7 и §8 ТЗ); несоответствия перечислены как есть, решения — в
OPEN_QUESTIONS_AND_RISKS.md.

---

## 1. Числовые значения внутри торговой логики (вне config.py)

Это значения, которые **невозможно изменить без правки Python-кода** даже
теоретически — они не имеют имени в конфигурации:

| # | Значение | Место | Влияние |
|---|---|---|---|
| H1 | `ORDER_POLL_MAX_AGE_CYCLES = 10` (≈5 мин при цикле 30 с) | main.py:602-605 | возраст нетерминальной BUY-заявки, после которого остаток отменяется (main.py:4356, 4465) |
| H2 | Таймфрейм сигналов `CANDLE_INTERVAL_5_MIN` | main.py:3297 (`_build_candles_df`) | все сигналы и SL/TP считаются на 5-минутных свечах; конфигурируемого таймфрейма не существует |
| H3 | Таймфрейм скринера `CANDLE_INTERVAL_DAY` | screener.py:154 | ATR-ранжирование вселенной по дневным свечам |
| H4 | Имена runtime-файлов: `trading.flag`, `state.json`, `state.json.tmp`, `order_ledger.jsonl`, `research_events.jsonl`, `research_trades.csv` | main.py:596-601; logger.py:98-99; safe_start.py:42-43 | расположение и состав персистентности |
| H5 | trade_id = `uuid4().hex[:12]` | main.py:2912, 5288 | длина идентификатора сделки CSV = 12 hex-символов (48 бит) |
| H6 | Минимум окна объёма = 3 свечи | strategy.py:444-446 | при коротком df сигналы отклоняются «мало свечей для объёма» |
| H7 | Требование `len ≥ MA_SLOW_PERIOD + 2` | strategy.py:258 | минималка для пересечения MA |
| H8 | Требование `len ≥ BB_PERIOD + RSI_PERIOD` | strategy.py:317 | минималка для BB+RSI |
| H9 | Требование `len ≥ ADX_PERIOD + 1` | strategy.py:58 | минималка для режима рынка |
| H10 | Окно оборота скринера = `tail(20)` дней | screener.py:179 | средний дневной оборот считается по последним 20 торговым дням; не конфигурируется |
| H11 | `REAL_EXCHANGE_MOEX = 1` | screener.py:36, 136 | фильтр биржи |
| H12 | Валюта отбора = `"rub"` | screener.py:137 | фильтр валюты |
| H13 | Только рыночные заявки (`ORDER_TYPE_MARKET`) | tinkoff_client.py:580-584 | лимитных/стоп-заявок в коде не существует |
| H14 | Fallback `lot=1` при недоступной инфо об инструменте | main.py:2086, 4347, 4910, 5086 | расчёт цены исполнения при неизвестном lot_size |
| H15 | Допуск сравнения цен/комиссий `1e-9` | main.py:1536, 3904; execution.py:239; order_ledger.py:324 | «противоречие значений» = расхождение > 1e-9 |
| H16 | Денежные форматы CSV `%.4f`, `%+.2f`, `%+.3f` | main.py:2494-2506, 2979-2988 | точность записей P&L/комиссий |
| H17 | Якорь хронологии `datetime(1,1,1, tzinfo=utc)` | logger.py:284 | сортировка строк CSV с неизвестным временем |
| H18 | `CURSOR_IDENTITY_VERSION = 2` | execution.py:360 | версия формата per-order cursor'а |
| H19 | `_TERMINAL_SELL_STATUSES = {"FILL","CANCELLED","REJECTED","EXPIRED","1","2","3"}` | execution.py:217-220 | терминальность SELL; числовые коды 1/2/3 (FILL/REJECTED/CANCELLED); **кода "6" (EXPIRED) в числовом подмножестве НЕТ** — см. §5.2 |
| H20 | `_TERMINAL_ORDER_STATUSES = {"FILL","REJECTED","CANCELLED","EXPIRED"}` | main.py:612 | терминальность BUY/SELL в main.py |
| H21 | `ACTIVE_STATES = (OPEN, CLOSING, UNCERTAIN, RECOVERY)` | execution.py:212-215 | какие состояния считаются активными |
| H22 | Таймауты Telegram: pool=8, connect/read/write/pool=30/60/60/30 c | telegram_bot.py:27-34 | сетевое поведение TG |
| H23 | Watchdog TG: интервал 60 с, timeout 15 с, 3 неудачи → перезапуск | telegram_bot.py:120-135; main.py:964-984 | восстановление polling |
| H24 | Таймауты lifecycle TG в main: stop 10 с, init/start/polling 20 с, get_me 15 с | main.py:922-930, 950-952, 974 | |
| H25 | 2 попытки скринера (`range(1, 3)`) | screener.py:68 | НЕ использует `config.API_RETRY_COUNT` |
| H26 | Цикл ожидания при провале скринера = 60 с (вечный сон) | main.py:5711-5712 | робот живёт без торговли до рестарта |
| H27 | Буфер безубытка = `entry * (2*COMMISSION_PER_SIDE + SLIPPAGE_PERCENT)` | execution.py:872-875 | формула фиксирована; коэффициент 2 захардкожен |
| H28 | CSV-схема TRADE_FIELDS (33 колонки), разделитель `;` | logger.py:101-116, 153, 216 | смена схемы = миграция журнала (logger.py:160-172) |
| H29 | Реестр-схема RECORD_FIELDS (18 полей), IDENTITY_FIELDS | order_ledger.py:73-84 | |
| H30 | Профиль-независимые правила: сигнал SELL без позиции игнорируется («шорт запрещён») | main.py:5270-5276 | робот открывает только LONG; SELL-сигнал используется движком только как «нет входа» |
| H31 | Одна позиция на FIGI (`has_active_position` + отказ register) | main.py:5244; execution.py:470-478 | |
| H32 | Вселенная фиксируется на старте (`top_instruments` вне цикла) | main.py:5704, 5714, 5723-5729 | обновление вселенной — только рестарт процесса |
| H33 | Минимальное количество лотов для INTENT ≥ 1 (`_positive_int`) | order_ledger.py:91-100, 344-349 | заявка в 0 лотов невозможна |
| H34 | Строгая проверка кратно­сти количества lot_size в `get_positions` (fail-closed снимка) | tinkoff_client.py:400-407 | дробный остаток делает снимок недостоверным (None) |

## 2. Условия входа/выхода, НЕ изменяемые через конфигурацию (ВЫВОД из §1)

1. **Вход только LONG и только рыночной заявкой на всю рассчитанную партию**
   (H13, H30); частичное закрытие позиции конфигурацией не предусмотрено —
   `close_position` отправляет SELL на `pos.quantity` (main.py:2315).
2. **Выход только по SL/TP/BE/TRAIL** (execution.py:1011-1020) либо вручную
   оператором/внешне (В3-механизм, main.py:1932-2011). Стратегия не
   генерирует выходных сигналов вообще: `get_signal` возвращает BUY/SELL/HOLD,
   где SELL — потенциальный вход в шорт (запрещён), а не закрытие LONG.
3. **Отсечение по возрасту заявки** — 10 циклов (H1); **переподписка вселенной**
   — только рестарт (H32); **таймфреймы** — 5-мин/день (H2, H3).
4. **Тройная блокировка LIVE** — USE_SANDBOX=False отклоняется тремя
   независимыми механизмами: config.validate (config.py:162-163),
   TinkoffClient.__init__ (tinkoff_client.py:182-184),
   build_safety.assert_sandbox_only (build_safety.py:78-83, main.py:5659).

## 3. Дублирующиеся значения в разных файлах

| # | Что дублируется | Места | Риск |
|---|---|---|---|
| D-1 | Префиксы валют `("RUB","USD","EUR")` | tinkoff_client.py:174 (константа `CURRENCY_FIGI_PREFIXES`) + проверки figi.startswith в main.py:2050-2051, 2873-2874, 5076-5077, risk_manager.py:159, tinkoff_client.py:366 | константа и литералы существуют параллельно: правка одной копии рассогласует остальные |
| D-2 | Маппинг кодов статусов T-Invest | main.py:609-611 (`_STATUS_NAME_BY_CODE`, содержит `6: "EXPIRED"`) **vs** execution.py:1075 (inline dict в `resolve_closing`, **без** кода 6) | два маппинга уже РАЗЛИЧАЮТСЯ: EXPIRED=6 в resolve_closing не транслируется в имя (останется `str(raw)`), и `"6"` нет в `_TERMINAL_SELL_STATUSES` (execution.py:220) — см. §5.2 |
| D-3 | Множества терминальных статусов | main.py:612 `_TERMINAL_ORDER_STATUSES`; execution.py:220 `_TERMINAL_SELL_STATUSES` (импортируется в main как `_SELL_JOURNAL_TERMINAL_STATUSES`, main.py:572-580); order_ledger.py:38 `TERMINAL_STATUSES` | три множества с разным составом (raw-коды есть только в execution) — при изменении статусов надо править три места |
| D-4 | Имена runtime-файлов | main.py:597-601 vs safe_start.py:42-43 | safe_start проверяет файлы по СВОИМ литералам |
| D-5 | Имя маркер-файла Режима B `"sandbox_execution.enabled"` | build_safety.py:39 vs enable_sandbox_execution.py:25 | рассинхронизация исключит обнаружение маркера |
| D-6 | Проверка «валютная позиция» по instrument_type `"currency"` | tinkoff_client.py:176-178 (константа) + логика 359-375 | одна константа, но fallback-логика (prefix) дублирует D-1 |
| D-7 | Допуск 1e-9 (4 копии) | H15 | изменение точности — 4 правки |
| D-8 | Fallback `lot=1` (4 места) | H14 | |

## 4. Значения, определяемые профилем (ФАКТ)

PROFILE-ветвление config.py:78-119 переопределяет 9 значений (полная таблица —
STRATEGY_PARAMETERS_INVENTORY.md §2). Здесь фиксируются **побочные эффекты**
профиля:

1. **FORCE_TRADE: VOLUME_SPIKE_FACTOR=0.0** (config.py:81) → подтверждение
   объёмом всегда истинно (strategy.py:455-458) → параметр
   VOLUME_CONFIRMATION_WINDOW сохраняется, но НЕ влияет на результат.
2. **FORCE_TRADE: RSI_OVERSOLD=RSI_OVERBOUGHT=50** (config.py:85-86) →
   RSI-условия вырождаются в «RSI ниже/выше середины».
3. **FORCE_TRADE: MA 2/3, фильтр MA100→MA5, MIN_CANDLES_FOR_SIGNAL=10** →
   стратегия фактически «быстрый шумовой» режим; базовые значения 9/21/100/60
   (config.py:64-72) в активной конфигурации НЕ используются.
4. **CONSERVATIVE/TECH_CHECK: MIN_CANDLES_FOR_SIGNAL=60 < TREND_FILTER_MA_PERIOD=100**
   → при 60–99 свечах любой сигнал отклоняется фильтром MA100
   (strategy.py:231-232, 288-300) — см. §6, скрытая зависимость SD-1.
5. **SANDBOX_TEST** — промежуточный профиль (ADX 15, MA 5/13, MA50, RSI 40/60,
   объём выключен).

**ВЫВОД:** «комментарий ≠ значение» (config.py:4 vs 76) + эффекты 1-4
означают, что реальное торговое поведение определяется веткой профиля, а не
разделом «Стратегия (НЕ меняется)» config.py:63-73.

## 5. Объявлено, но фактически не используется (ФАКТ, grep по candidate/*.py)

### 5.1. Параметры

| Объявление | Место | Факт |
|---|---|---|
| `STARTING_BALANCE` | config.py:144 | env читается, значение нигде не используется (только имя в диагностическом списке safe_start.py:48); строка не парсится в число |
| `POSITION_QUANTITY_IS_LOTS` | config.py:56 | ни одного чтения; в risk_manager.py:12 прямо сказано: «POSITION_QUANTITY_IS_LOTS удалён (get_positions() уже возвращает лоты)» — объявление осталось |

### 5.2. Обнаруженная несогласованность (не «параметр», но явный артефакт)

**ФАКТ:** числовое подмножество `_TERMINAL_SELL_STATUSES` в execution.py:220 —
`{"1","2","3"}` (FILL/REJECTED/CANCELLED), код EXPIRED=`"6"` отсутствует, тогда
как строчный состав включает `"EXPIRED"`. Путь воздействия: если брокер вернёт
сырой `execution_report_status=6` и статус не будет транслирован в имя
(`resolve_closing` транслирует через inline-словарь execution.py:1075, который
тоже не содержит 6), `apply_close_execution` и `_SELL_JOURNAL_TERMINAL_STATUSES`
трактуют его как НЕТЕРМИНАЛЬНЫЙ. Все штатные пути в текущем коде передают
имена (main.py:609-611 включает 6), поэтому практическая достижимость ветки —
**НЕИЗВЕСТНО** (зависит от сырых значений SDK). Зафиксировано как риск
(OPEN_QUESTIONS_AND_RISKS.md, R-01); НЕ исправлялось.

### 5.3. Неиспользуемые функции производственных модулей (grep-доказательство)

| Функция | Место | Производственные вызовы |
|---|---|---|
| `TinkoffClient.get_all_tradable_shares` | tinkoff_client.py:227-238 | нет (только объявление; скринер использует свой AsyncClient) |
| `TinkoffClient.get_sandbox_max_lots` | tinkoff_client.py:458-521 | нет (только тесты test_tinkoff_client.py:246-301) |
| `TinkoffClient.get_positions_debug` | tinkoff_client.py:523-553 | нет (комментарий «ДИАГНОСТИКА — не используется в торговой логике», строка 524) |
| `OrderLedger.record_observation` | order_ledger.py:414-432 | нет (только тесты) |
| `OrderLedger.prepare_application` / `commit_application` / `application_state` / `pending_applications` | order_ledger.py:440-541 | нет — протокол prepare/commit реестра не задействован production-кодом: исполнение SELL применяется через per-order cursor `close_orders` в execution.py:694-861 (параллельный механизм) |
| `OrderLedger.figi_is_uncertain` | order_ledger.py:595-597 | нет (используется `figi_blocks_buy`, order_ledger.py:577-590) |

**ВЫВОД:** реестр содержит второй (более строгий, durable) протокол применения
исполнений, который в текущем потоке не вызывается; при рефакторинге под
стратегии это готовая точка расширения, но сейчас это «мёртвый» код с
полным тестовым покрытием (test_order_ledger.py:29-101).

## 6. Скрытые зависимости между настройками (сводка; детали — INVENTORY §6)

| # | Зависимость | Место | Последствие нарушения |
|---|---|---|---|
| SD-1 | MIN_CANDLES_FOR_SIGNAL ≥ TREND_FILTER_MA_PERIOD (фактически нужно ≥ 100) | strategy.py:197, 231-232 | CONSERVATIVE/TECH_CHECK: 60<100 → сигналы отклоняются фильтром при 60–99 свечах |
| SD-2 | MIN_CANDLES_FOR_SIGNAL ≥ MA_SLOW+2; ≥ BB+RSI; ≥ ADX+1 | strategy.py:258, 317, 58 | HOLD «Мало данных» при несоответствии |
| SD-3 | CANDLES_LOOKBACK_DAYS обеспечивает ≥ MIN_CANDLES_FOR_SIGNAL 5-мин свечей | main.py:3296-3299 | маленькое окно → все инструменты «мало свечей», входы молча прекращаются |
| SD-4 | COMMISSION_MODE → COMMISSION_PER_SIDE (вычисление при импорте) | config.py:60 | смена MODE в рантайме ставку не меняет |
| SD-5 | TRADING_CYCLE_SECONDS → RECONCILE_CONFIRM_MIN_AGE_SECONDS (присвоение + fallback) | config.py:141; main.py:1952-1953 | цикл<порога → двойное подтверждение В3 деградирует |
| SD-6 | TRADING_CYCLE_SECONDS × ORDER_POLL_MAX_AGE_CYCLES = реальное время жизни заявки | main.py:605, 645 | изменение цикла молча меняет таймаут отмены заявки |
| SD-7 | BE_TRAIL_ENABLED — гейт трёх параметров | config.py:50-53; execution.py:923-966 | значения BE/TRAIL без гейта ни на что не влияют |
| SD-8 | STOP_LOSS_PERCENT vs MIN_STOP_LOSS_PERCENT (max) | risk_manager.py:124, 238 | min-порог вытесняет основной при противоречивых значениях |
| SD-9 | MAX_ATR_STOP_PERCENT капирует обе ATR-ветки | risk_manager.py:130-131, 241-242 | 0 → ATR-стоп отключён |
| SD-10 | VOLUME_SPIKE_FACTOR=0.0 обесценивает VOLUME_CONFIRMATION_WINDOW | strategy.py:439-465 | окно не влияет |
| SD-11 | Три разных ATR-периода под три потребителя: ATR_PERIOD (день, скринер), ATR_PERIOD_INTRADAY (5-мин, риск), TRAIL_ATR_PERIOD (5-мин, трейлинг) | screener.py:171; risk_manager.py:215; main.py:1134 | путаница имён при правке: изменение «ATR_PERIOD» меняет только скринер |
| SD-12 | USE_SANDBOX проверяется тремя независимыми уровнями | config.py:162-163; tinkoff_client.py:182-184; build_safety.py:78-83 | согласованное ослабление требует правки трёх мест (это ФАКТ-защита, не дефект) |
| SD-13 | ENABLE_TELEGRAM=False не снимает обязательность TG-токенов в safe_start-списке | safe_start.py:45-49 | только косметика диагностики |
| SD-14 | `getattr(config, ..., default)`-паттерн: код деградирует со старым config.py | main.py:1952-1953 (RECONCILE_CONFIRM_MIN_AGE_SECONDS), main.py:5139 (BE_TRAIL_ENABLED), main.py:3011 (BUILD_VERSION), execution.py:923/1003 | прямое указание в коде, что config-модуль исторически версионировался вручную |

## 7. Параметры/состояния, меняющиеся во время исполнения (ФАКТ)

(полная таблица — STRATEGY_PARAMETERS_INVENTORY.md §5; кратко)

- **позиционные**: `pos.sl_price` (execution.py:936-966 — только при
  BE_TRAIL_ENABLED=True), `pos.quantity` (применение исполнений SELL —
  execution.py:814, 822-824; синхронизация RECOVERY — execution.py:558-578),
  `pos.entry_applied_lots`/`executed_lots` (execution.py:614-621, 649-653),
  `pos.state` (весь execution.py);
- **риск**: `rm.daily_trade_counts` (risk_manager.py:261-263; персистентны в
  state.json — main.py:1160), сброс по дате (risk_manager.py:45-47);
- **глобальные флаги**: `client.uncertain_state`, `monitor.monitoring_error`,
  `state_save_failed`, `reconcile_done`, `_last_reconcile_confirmed_utc`
  (main.py:836-844, 1174-1189, 2041-2216);
- **кэш**: `instrument_info_cache` (tinkoff_client.py:271-297);
- **неперсистентные runtime-структуры**: `_external_close_candidates`
  (main.py:841-844 — намеренно; после рестарта двойное подтверждение В3
  начинается заново), `_strategy_event_keys`, `_promote_throttle`.

**ВЫВОД:** «значения, меняющиеся во время исполнения» — это учётные поля
позиций и защитные флаги, а не торговые параметры: ни один параметр
config.py не модифицируется в рантайме (grep присваиваний `config.X =` вне
config.py — 0 совпадений, кроме тестовых monkeypatch).

## 8. Итог

1. Конфигурируемый слой (config.py) покрывает индикаторы, риск, тайминги и
   скринер; **не** покрывает таймфрейм сигналов, возраст заявок, имена файлов,
   схему CSV/реестра, сетевые таймауты Telegram и ряд behavioral-констант
   (H1-H34).
2. Дубли уже породили одно расхождение (D-2/§5.2 — EXPIRED=6) и создают риск
   рассинхронизации при будущих правках.
3. Профиль FORCE_TRADE — единственный источник фактических значений
   сигнальной логики; противоречие комментарий/значение зафиксировано без
   исправления (§7 ТЗ).
4. Неиспользуемые объявления (§5) должны быть учтены при создании
   централизованного конфига, чтобы не «легализовать» мёртвые параметры
   (решения — STRATEGY_SWITCH_ARCHITECTURE.md, IMPLEMENTATION_ROADMAP.md).
