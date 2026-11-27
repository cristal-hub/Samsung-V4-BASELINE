# STAGE2_SOURCE_TRACEABILITY.md

## SAMSUNG V4 — STAGE 2: трассировка выводов в исходный код

**Статус:** `STAGE 2.3.2 — FINAL ARCHITECTURE CONSISTENCY CORRECTIONS /
SOURCE CODE: UNCHANGED` (версия 2.3.2: добавлен §2.11 — дозверификация
трёх коррекций согласованности аудита Stage 2.3.1 [единственный маршрут
SELL — сценарии A/B/C; конфигурационная защита D-24/D-27;
exit_exec_price-терминология]; обновлены §1 и шапка; правки
2.1/2.2/2.3/2.3.1 сохранены; см. STAGE2_3_2_CHANGELOG.md).

Назначение (§12 ТЗ): подтверждение ключевых выводов Stage 2 ссылками на
конкретные файлы и строки исходного кода. Все ссылки проверены
самостоятельным чтением рабочего дерева на commit
`884cefd6f12a99f6adc14b5ed4c9eeda21d32e04` в рамках Stage 2 (не
перенесены из документов Stage 1/1.1 без перепроверки). Обозначения:
FACT — подтверждено кодом/документом; PROPOSAL — проект Stage 2
(в коде не существует).

---

## 1. Метод

1. READ-ONLY клон репозитория; `git checkout 884cefd…`; проверка SHA
   (`git rev-parse`); проверка идентичности кода между `884cefd` и HEAD
   (`git diff 884cefd HEAD -- candidate/ docs/` — пусто; различия только
   каталоги документов Stage 1 / Stage 1.1).
2. Построчное чтение модулей: strategy.py (465), risk_manager.py (262),
   config.py (162), execution.py (1756 — зоны: 204-460, 470-980, 978-1030,
   1024-1350), main.py (5737 — зоны: 430-620, 840-1090, 1144-1250,
   1930-2390, 2460-2500, 3280-3330, 4040-4160, 4630-4830, 5115-5737),
   order_ledger.py (603 — зоны 70-120, 341-610), screener.py (197),
   telegram_bot.py (140), build_safety.py (123), safe_start.py (274,
   фрагмент), enable_sandbox_execution.py (70), tinkoff_client.py (681 —
   карта методов).
3. Каждый вывод Stage 1.1 (V-01…V-48), использованный в проекте,
   перепроверен независимо (§3).
4. Код не запускался; тесты не выполнялись; API не вызывался.
5. Stage 2.1 (§2.7): для замечаний независимой проверки выполнена
   точечная дозверификация — grep-инвентаризация всех вызовов `client.`
   в main.py, execution.py, risk_manager.py; карта публичных методов
   tinkoff_client.py:182-681; проверка методов без производственных
   вызовов (get_all_tradable_shares, get_positions_debug,
   get_sandbox_max_lots); повторное чтение зон exits/sizing/конфигурации.
6. Stage 2.2 (§2.8): ПРОВЕРКА ВЕРСИЙ ДОКУМЕНТАЛЬНОЙ ОСНОВЫ — commit
   `f5db0d6` подтверждён на origin/main READ-ONLY-операциями git (fetch
   обновил ТОЛЬКО remote-tracking ссылки; рабочее дерево НЕ
   переключалось); `git ls-tree` всех четырёх каталогов документов на
   соответствующих коммитах; `git diff 884cefd f5db0d6 -- candidate/
   docs/` — пусто (код идентичен — все ссылки `файл:строка` действительны
   для обеих версий); локальный клон остаётся на `884cefd`, содержимое
   candidate/ и docs/ без изменений. Все 7 документов Stage 2.1
   прочитаны ПОЛНОСТЬЮ из commit `f5db0d6`. Точечная дозверификация зон
   правок 2.2: снимок цен (tinkoff_client.py:253-268), check_all
   (execution.py:978-1022), isfinite-прецеденты (execution.py:1255-1288),
   комиссия/регистрация (main.py:2455-2509, 4060-4119), sizing/SL-TP
   (risk_manager.py:87-263), условия валидации (strategy.py:50-90,
   177-219, 222-251, 253-310, 312-389, 391-465), config.py (полностью,
   163 строки).

7. Stage 2.3 (§2.9): ПРОВЕРКА ВЕРСИЙ ДОКУМЕНТАЛЬНОЙ ОСНОВЫ — комплект
   Stage 2.2 подтверждён на origin/main READ-ONLY-операциями git
   (`git fetch origin` обновил ТОЛЬКО remote-tracking ссылки
   `f5db0d6..1f252db main -> origin/main`; рабочее дерево НЕ
   переключалось); каталог `Samsung_V4_STAGE2_2` (7 документов) на
   commit `1f252dbc1f77d17bbe09e314714812176cc85c6b` сверён с локальной
   копией ПОБАЙТОВО (`git hash-object` — 7/7 MATCH);
   `git diff 884cefd 1f252db -- candidate/ docs/` — пусто (код идентичен
   — все ссылки `файл:строка` действительны для всех четырёх версий).
   Точечная дозверификация зон коррекций: типы заявок (grep
   post_limit/LIMIT/STOP по 5 файлам — 0 совпадений; post_market_order
   tinkoff_client.py:555-599, ORDER_TYPE_MARKET 582), карта статусов
   (main.py:604-620), защита дубликатной SELL (main.py:738-767,
   2224-2260), check_all (execution.py:978-1022), статусы/частичные
   исполнения (execution.py:220, 1250-1257, 788/830), отмена/позиции
   (main.py:4385-4392; tinkoff_client.py:315-330, 437-456, 646-680),
   RSI/тренд-фильтр (strategy.py:197-198, 222-251, 353-389),
   Stage 1 PARAMETER_GAPS (окно данных, строки 58-60).


---

## 2. Трассировка ключевых выводов Stage 2

### 2.1. Архитектура текущего кода

| Вывод Stage 2 | Источник (файл:строка) | Статус |
|---|---|---|
| Один экземпляр StrategyManager создаётся в main() | main.py:5663 (`sm = StrategyManager()`); создание rm — 5661, monitor — 5664, ledger — 5669 | FACT |
| Один и тот же sm передаётся в каждый trading_cycle бесконечного цикла | main.py:5723-5729 (`while True:` 5723, вызов `trading_cycle(client, rm, sm, monitor, ledger)` — 5725) | FACT |
| Сигнал для каждого инструмента — от того же экземпляра, в общем цикле обхода | main.py:5237 (`for inst in top_instruments:`), 5260 (`sm.get_signal(df, float(price), drop_incomplete=True)`) | FACT |
| Изменяемое состояние уровня экземпляра (не FIGI) | strategy.py:32 (`min_candles_required`), 34 (`_last_regime`), 35 (`_regime_streak`), 38 (`_last_regime_candidate`), 39 (`_last_regime_candle_time`), 42-43 (диагностика) | FACT |
| get_market_regime мутирует состояние на всех ветках | strategy.py:90, 104-107, 124-125, 130, 135-136, 141-145, 158-163 | FACT |
| Между FIGI состояние не сбрасывается; get_signal сбрасывает только диагностику | strategy.py:188-190; отсутствие сброса в main.py:5236-5310 | FACT |
| «Та же свеча» — глобальное сравнение времени без FIGI | strategy.py:100 (`candle_time = candles_df.index[-1]`), 118 (`if candle_time == self._last_regime_candle_time:`) | FACT |
| Первый инструмент после старта задаёт режим немедленно | strategy.py:102-114 (ветка `_last_regime == "UNKNOWN"`) | FACT |
| Режим выбирает ветку сигнальной логики | strategy.py:202-208 (TREND→MA 205, RANGE→BB/RSI 208, иначе HOLD 211) | FACT |
| Порядок обхода — сортировка по волатильности | screener.py:196-197 (`sort(key=volatility, reverse=True)`, срез TOP-N); фиксация вселенной main.py:5704-5714 | FACT |
| Runtime-состояние не персистится | main.py:1144-1171 (`_save_state`: positions/closed_entry_order_ids/pending_csv_recoveries/monitoring_error/risk/open_orders — полей стратегии нет); после рестарта — ветка инициализации strategy.py:102-114 | FACT |
| Диагностика читает общие поля экземпляра | main.py:1055-1064 (`regime`, `regime_candidate`, `regime_streak` из sm) | FACT |

### 2.2. Сигналы, входы, SELL-семантика

| Вывод Stage 2 | Источник | Статус |
|---|---|---|
| Сигнальный контракт (BUY\|SELL\|HOLD, reason) | strategy.py:177-219 (сигнатура 177-182) | FACT |
| SELL при отсутствии позиции игнорируется («шорт запрещён») | main.py:5270-5276 (`continue` + STRATEGY_SELL_IGNORED) | FACT |
| SELL НЕ закрывает существующую LONG: при открытой позиции весь входной блок пропускается | main.py:5244 (`if (pos_data is not None and pos_data.lots != 0) or monitor.has_active_position(figi): continue`) | FACT |
| Движок long-only на входах; зеркальные SHORT-ветки — только учёт | main.py:5270-5276; execution.py:953-966 (комментарий «зеркало для SHORT… адопция SHORT-позиций»), 1008-1010 (зеркальная проверка) | FACT |
| Частичное закрытие отсутствует | grep `partial_close/PARTIAL_CLOSE/close_partial` по main.py/execution.py/strategy.py/risk_manager.py — 0 совпадений | FACT |
| Обработка неполных свечей: удаляется только свеча с явным False | strategy.py:412-425 (`_prepare_dataframe`, `drop_incomplete`) | FACT |
| Свечи 5-минутные, окно CANDLES_LOOKBACK_DAYS | main.py:3289-3310 (3297 `CANDLE_INTERVAL_5_MIN`), config.py:131 | FACT |

### 2.3. Риск и sizing

| Вывод Stage 2 | Источник | Статус |
|---|---|---|
| risk_amount = balance * RISK_PER_TRADE | risk_manager.py:104 | FACT |
| base_risk = last_price * max(STOP_LOSS_PERCENT, MIN_STOP_LOSS_PERCENT) | risk_manager.py:124 | FACT |
| friction = last_price * (COMMISSION_PER_SIDE*2 + SLIPPAGE_PERCENT) | risk_manager.py:125; значения config.py:59-61 | FACT |
| Без ATR: per_share_risk = base_risk + friction | risk_manager.py:126 | FACT |
| С ATR: per_share_risk = max(per_share_risk, atr_risk + friction) ≡ max(base_risk, atr_risk) + friction | risk_manager.py:128-132 (cap 130-131); _calculate_volatility_risk 209-231 (множитель 228) | FACT |
| lots = int(risk_amount / (per_share_risk * lot_size)) | risk_manager.py:137 | FACT |
| Кап по доле на инструмент | risk_manager.py:142-145 | FACT |
| Тотальная экспозиция | risk_manager.py:149-201 (агрегация 156-196; кап 198-201) | FACT |
| Лимит сделок на инструмент/день | risk_manager.py:91-92, 261-263 (record_trade по figi) | FACT |
| SL/TP: та же база, ATR-кап, TP = база * TAKE_PROFIT_RATIO; отбраковка sl<=0/tp<=0 и неверных направлений | risk_manager.py:233-259 (238-243; 244; 245-256; 257-258) | FACT |
| Sizing от last_price (снимок до заявки); SL/TP от exec_price | risk_manager.py:87,124 + main.py:5255,5278 (цена из get_last_prices, main.py:5128); main.py:4072, 4803-4808 (exec_price) | FACT |
| Hard caps не имеют обхода из стратегии (стратегия не участвует в sizing) | risk_manager.py:87-207 — параметры только (figi, last_price, candles_df) | FACT |
| Значения конфигурации риска | config.py:32-42 (RISK_PER_TRADE=0.01, STOP_LOSS_PERCENT=0.012, MIN=0.005, TAKE_PROFIT_RATIO=2.0, ATR_STOP_MULTIPLIER=1.5, MAX_ATR_STOP_PERCENT=0.03, MAX_POSITION_SHARE=0.2, MAX_TOTAL_EXPOSURE=0.6, MAX_TRADES_PER_DAY=5) | FACT |

### 2.4. Выходы, учёт, восстановление

| Вывод Stage 2 | Источник | Статус |
|---|---|---|
| Выходы SL/TP: check_all помечает CLOSING с причинами TP/SL/BE/TRAIL; TP приоритетнее SL при одном снимке | execution.py:978-1022 (1005-1010 проверка, 1011-1020 причины; 992 фильтр OPEN) | FACT |
| При точечном опросе SL и TP не могут сработать одновременно (BUY: sl<entry<tp) | execution.py:1005-1010 | FACT (вывод арифметики уровней risk_manager.py:245-249) |
| BE/TRAIL существуют, выключены; SL никогда не ослабляется | config.py:50 (`BE_TRAIL_ENABLED=False`); execution.py:913-966 (гейт 923; инвариант в докстринге 914-922 и логике 937/947), 872-882 (_be_buffer, _risk_per_share), 884-911 (экстремумы из свечей — 885-888 комментарий про поллинг 30 с) | FACT |
| close_position закрывает ВСЁ количество; направление по pos.direction | main.py:2224-2228 (2225-2228), 2315 (`post_market_order(pos.figi, pos.quantity, direction, ...)`) | FACT |
| Запрет повторной SELL по неопределённой позиции | main.py:2235-2252 (_sell_block_reason, UNCERTAIN при блоке); 738-767 | FACT |
| INTENT-before-send для BUY и SELL; order_id генерируется до сети | main.py:5288-5292 (uuid), 5300-5325 (BUY INTENT), 2254-2280 (SELL INTENT); комментарий P0-1/P0-2 5289-5291 | FACT |
| Partial-ветка BUY: отмена остатка, регистрация подтверждённых лотов, RECOVERY при отсутствии цены | main.py:5369-5471 (5369 PARTIALLYFILL, 5379 cancel, 5391 state, 5401-5471 регистрация) | FACT |
| Регистрация BUY: SL/TP считаются только штатной стратегией; ошибка -> RECOVERY (не фиктивные уровни) | main.py:3433, 3473 (комментарий), 4068-4084 (4072 вызов; RECOVERY-fallback), 4138 (record_trade) | FACT |
| Промоция RECOVERY: пересборка свечей, SL/TP от exec_price | main.py:4803-4808 | FACT |
| RECOVERY не закрывается автоматически | main.py:151-153 (комментарий), 4684-4686 («закрытие только вручную оператором») | FACT |
| Внешнее (ручное) закрытие — двойное подтверждение В3 | main.py:1932-2011 (1932-1940 кандидат); RECONCILE_CONFIRM_MIN_AGE config.py:133-141 | FACT |
| state.json: состав и атомарная запись | main.py:1144-1171 (1165-1167 tmp+os.replace); _load_state 1192-1238 (совместимость: отсутствующие ключи -> значения по умолчанию 1212, 1219) | FACT |
| Ledger append-only; поля добавляются в конец; блокировки по FIGI | order_ledger.py:73-83 (RECORD_FIELDS с полями «В КОНЕЦ»), 143-198 (load), 199-341 (append), 341-412 (record_*), 577-591 (figi_blocks_buy), 592-594 (has_unknown_figi_open_orders); блокировки входов main.py:5247-5253, 5216-5225 | FACT |
| Fail-closed клиент: None=неизвестно, {}=достоверно пусто; UUID сохраняется при потере ответа | tinkoff_client.py:315-435 (get_positions), 555-599 (post_market_order); использование main.py:5229-5234, 5332-5351 | FACT |
| Экспозиция: валютные позиции исключаются; неизвестная стоимость -> блокировка | risk_manager.py:156-196 (159-160 фильтр RUB/USD/EUR; 166-194 блокировки) | FACT |

### 2.5. Профили и конфигурация

| Вывод Stage 2 | Источник | Статус |
|---|---|---|
| Профили — переприсвоение 9 констант одной логики | config.py:76-119 (FORCE_TRADE 78-87, SANDBOX_TEST 88-97, TECH_CHECK 98-107, CONSERVATIVE 108-117; else raise 118-119); strategy.py без ветвления по профилю (весь файл) | FACT |
| Активный профиль FORCE_TRADE; комментарий config.py:4 («CONSERVATIVE») противоречит | config.py:76 vs 4 | FACT |
| Противоречие MIN_CANDLES_FOR_SIGNAL=60 < TREND_FILTER_MA_PERIOD=100 в TECH_CHECK/CONSERVATIVE | config.py:104-117 (60/100); фильтр требует len>=периода strategy.py:231-232 | FACT |
| Fail-closed validate(); LIVE запрещён | config.py:147-163 (162-163); tinkoff_client.py:182-184 (SandboxRequiredError); build_safety.py:78-83 | FACT |
| Режим A/B; guard подменяет post_market_order/cancel_order на экземпляре клиента | build_safety.py:36-62 (detect_mode), 86-113 (install_order_guard), 44-45 (ошибка) | FACT |
| BE/TRAIL параметры | config.py:44-53 (50 False; 51-53) | FACT |

### 2.6. Инфраструктура совместимости

| Вывод Stage 2 | Источник | Статус |
|---|---|---|
| Telegram: команды управляют trading.flag; авторизация одним user_id | telegram_bot.py:52-54, 70-107; main.py:847-868 (is_trading_enabled/start/stop) | FACT |
| Скринер: ошибки сканирования блокируют входы; кэш не подменяется | screener.py:56-117 (None при ошибке), main.py:5704-5712 | FACT |
| Test-инфраструктура: conftest-изоляция, 789 тестов | conftest.py:187-227; docs/INSTALLATION_RU.md §4 (документ владельца) | FACT (документ) |
| Маппинг статусов; EXPIRED=6 включён defensively в main, отсутствует в _TERMINAL_SELL_STATUSES | main.py:609-612; execution.py:220 | FACT (рассинхрон); достижимость — UNKNOWN (Stage 1.1 V-45) |
| Комиссия: фактическая от брокера с модельной заменой | execution.py:1271-1289 (_extract_commission; 0.0 — достоверное значение); main.py:2464-2489 (model_total_commission, commission_source) | FACT |
| Стартовая диагностика Режима A без сети | safe_start.py:1-29, 61-80 | FACT |

### 2.7. Дозверификация Stage 2.1 (пять замечаний независимой проверки)

| Замечание / вывод | Источник (файл:строка, commit 884cefd) | Статус |
|---|---|---|
| **№1. Точка потери стратегических выходов**: to_close присваивается результату check_all | main.py:5144 (`to_close = await monitor.check_all(...)`); execution.py:986 (`to_close = []`), 1022 (`return to_close`) | FACT |
| check_all обрабатывает только OPEN; помечает CLOSING с причинами TP/SL/BE/TRAIL | execution.py:992 (фильтр state), 1011-1020 (причины и маркировка) | FACT |
| Единый цикл закрытия с UNCERTAIN при отсутствии цены | main.py:5145-5152 (5147-5151 UNCERTAIN) | FACT |
| close_position: полное количество, INTENT-before-send SELL, запрет повторной SELL, reason в INTENT | main.py:2315 (post_market_order), 2254-2280 (SELL INTENT), 2271-2275 (reason=f"close:{pos.close_reason}"), 2235-2252 (_sell_block_reason), 738-767 (def _sell_block_reason) | FACT |
| process_closing — штатная обработка закрытий | main.py:2835 (def), 5155 (вызов) | FACT |
| RECOVERY не закрывается автоматически | main.py:151-153 (комментарий), 4684-4686 | FACT |
| **№2. Активный профиль FORCE_TRADE** | config.py:76 (`PROFILE = "FORCE_TRADE"`); комментарий config.py:4 противоречит факту | FACT |
| Эффективные значения FORCE_TRADE | config.py:78-87 (ADX_TREND_THRESHOLD=5, ADX_HYSTERESIS_CANDLES=1, VOLUME_SPIKE_FACTOR=0.0, MA_FAST=2, MA_SLOW=3, TREND_FILTER=5, RSI 50/50, MIN_CANDLES=10); не перекрываемые профилем: BB 20/2 (67-68), RSI_PERIOD 14 (69), ADX_PERIOD 14 (73), VOLUME_CONFIRMATION_WINDOW 20 (121) | FACT |
| Остальные профили; else -> RuntimeError | config.py:88-97 (SANDBOX_TEST), 98-107 (TECH_CHECK), 108-117 (CONSERVATIVE), 118-119 (else raise) | FACT |
| **№3. Ценовая база sizing — last_price** | risk_manager.py:87 (сигнатура), 124 (base_risk от last_price); main.py:5128 (get_last_prices), 5278 (вызов с float(price)) | FACT |
| SL/TP от exec_price при регистрации и промоции | main.py:4072, 4808 (calculate_sl_tp(exec_price,...)); risk_manager.py:238 (base_stop_distance от entry_price); exec_price из отчётов брокера: main.py:4348, 4799, 5414, 5458, 5474, 5539, 5598 | FACT |
| Фактическая комиссия (модель/факт, commission_source) | main.py:2464-2489; execution.py:1271 (def _extract_commission), 1079 (использование) | FACT |
| Регистрация позиции при подтверждённом исполнении; Дефект №7 | main.py:4068-4084 (RECOVERY-fallback), 4091-4105 (register; execution_price 4102; entry_actual_commission 4105) | FACT |
| **№5. Инвентаризация вызовов клиента — main.py** | get_sandbox_order_state: 716, 718, 2678, 2681, 4704, 5391, 5511, 5556; get_instrument_info: 1613, 2080, 4346, 4909, 4968, 5083, 5283; get_last_prices: 1969, 5128; get_positions: 2042, 2862, 5070, 5228, 5401; get_historical_candles: 3295; cancel_order: 4385, 4474, 5379; post_market_order: 2315, 5327; get_sandbox_orders: 5006; is_uncertain(): 5181 | FACT (полный grep `client.` по main.py) |
| execution.py — только get_sandbox_order_state | execution.py:1059, 1064 | FACT |
| risk_manager.py — прямая зависимость от клиента (в редакции 2.0 §9.1 не отражена — исправлено) | risk_manager.py:96 (get_account_balance), 109, 165 (get_instrument_info), 149 (get_positions), 181 (get_last_prices) | FACT |
| Методы клиента БЕЗ производственных вызовов | tinkoff_client.py:227 (get_all_tradable_shares), 458 (get_sandbox_max_lots; только тесты tests/test_tinkoff_client.py:246-301), 523 (get_positions_debug) | FACT (grep по candidate/) |
| Screener — собственное read-only SDK-соединение | screener.py:130 (`AsyncClient(config.TINKOFF_READONLY_TOKEN)`), 131 (instruments.shares), 151 (get_all_candles) | FACT |
| Health-флаг недостоверности | tinkoff_client.py:681 (def is_uncertain); присваивания client.uncertain_state в main.py (напр. 5150, 5231, 5337, 5693) | FACT |
| **№4. Существующие гарантии запрета LIVE (основа изоляции backtest)** | тройной запрет: config.py:162-163, tinkoff_client.py:182-184 (SandboxRequiredError), build_safety.py:78-83 (def assert_sandbox_only 78); guard Режима A: build_safety.py:86-113 (def install_order_guard 86; OrderSubmissionDisabledError 44; raise 105); guard ставится на клиенте: main.py:5659-5660 | FACT |

### 2.8. Дозверификация Stage 2.2 (три замечания проверки + решение FORCE_TRADE)

| Замечание / вывод | Источник (файл:строка, commit 884cefd) | Статус |
|---|---|---|
| **№2. Снимок цен может законно НЕ содержать ключа FIGI** | tinkoff_client.py:253-268 (докстринг: dict при успехе, None при ошибке, {} при пустом ответе); 262-265 (компоновка `if p.price is not None` — ключи FIGI без цены ОТСУТСТВУЮТ в dict) | FACT |
| prices={} в цикле штатен | main.py:5130-5133 (prices is None -> monitoring_error=True, prices={}) | FACT |
| Защитный слой использует безопасный доступ | execution.py:988-990 (пустой снимок -> пустой список + monitoring_error); 994-997 (`price = prices.get(pos.figi)`; `None or <= 0` -> monitoring_error + continue); OPEN-фильтр 992 | FACT |
| Существующие проверки НЕ отсекают NaN/±Inf | execution.py:995 (`price <= 0` — сравнения с NaN ложны); main.py:5148-5151 (та же проверка на шаге закрытия); прецеденты isfinite-обработки: execution.py:1264 (`not math.isfinite(price) or price <= 0 -> None`), 1271-1288 (_extract_commission: NaN/±Inf -> None; 0.0 — ДОСТОВЕРНОЕ значение) | FACT |
| Небезопасный образец шага 2б — документ ред. 2.1 | STAGE2_IMPLEMENTATION_BLUEPRINT.md ред. 2.1 §6.2 (`df_for_exit[pos.figi]`, `prices[pos.figi]`, `float(prices[pos.figi])`) | FACT (документ) |
| **№3. Компоненты однозначной формулы фактического риска** | гейт exec_price: main.py:4066 (`if exec_price is not None and exec_price > 0`); регистрация: main.py:4091-4105 (register 4091; execution_price 4102; executed_lots 4103; entry_actual_commission 4105); извлечение комиссии: execution.py:1271-1288 (0.0 — достоверный факт, NaN/±Inf -> None); модельная комиссия и классификация: main.py:2470-2489 (model_total_commission 2470; деление стороны 2475/2479; commission_source actual/mixed/model 2484-2489); lot_size: risk_manager.py:114-117; плановый friction с SLIPPAGE_PERCENT: risk_manager.py:125 | FACT |
| friction_actual не был определён в ред. 2.1 | STAGE2_IMPLEMENTATION_BLUEPRINT.md ред. 2.1 §7.4 (`actual_per_share_risk = |exec_price - sl| + friction_actual` — член БЕЗ определения состава/источника) | FACT (документ) |
| **№1. Условия валидации legacy-конфигурации (заново из кода)** | ADX: strategy.py:58 (`len < ADX_PERIOD + 1 -> UNKNOWN`); окно hysteresis: 81-88 (`tail(ADX_HYSTERESIS_CANDLES)` после dropna; `len(recent) < ... -> UNKNOWN`); штатная деградация: 197-198 (`len < min_candles_required -> HOLD "Недостаточно данных"`); фильтр MA: 231-232 (`len < TREND_FILTER_MA_PERIOD -> False`); MA: 258 (`len < MA_SLOW_PERIOD + 2 -> HOLD`), 274-297 (сравнение prev/last 275: равенство периодов -> идентичные серии -> `pf < ps and lf > ls` недостижимо); BB+RSI: 317 (`len < BB_PERIOD + RSI_PERIOD -> HOLD`); RSI: 353-372 (BUY `rsi_val < RSI_OVERSOLD` — 355, SELL `rsi_val > RSI_OVERBOUGHT` — 371, СТРОГИЕ неравенства; равенство порогов работоспособно); объём: 439-458 (`window = min(WINDOW, len)` — 439; `window < 3 -> False` — 444; `last >= avg * FACTOR` — 458; FACTOR=0.0 -> всегда True) | FACT |
| RSI-правило Stage 1 избыточно | Stage 1 HARDCODED_LOGIC_AND_DEPENDENCIES §6 (правило «RSI_OVERSOLD < RSI_OVERBOUGHT», цитировалось в §10.1 ред. 2.0/2.1) vs strategy.py:353-372 (строгие неравенства; rsi < 50 и rsi > 50 не пересекаются — равенство порогов работоспособно) | FACT (исправлено Stage 2.2) |
| TAKE_PROFIT_RATIO > 0 | risk_manager.py:244 (`take_profit_distance = base_stop_distance * config.TAKE_PROFIT_RATIO`), 257-258 (отбраковка sl <= 0 / tp <= 0) | FACT |
| **Решение FORCE_TRADE. Исключаемый профиль — FACT исходного кода** | config.py:76 (`PROFILE = "FORCE_TRADE"`), 78-87 (значения FORCE_TRADE), 88-119 (SANDBOX_TEST/TECH_CHECK/CONSERVATIVE + else raise); перенос НЕ меняет исходник (candidate/ не правится — diff 884cefd↔f5db0d6 пуст, правки Stage 2.2 — только документация) | FACT + решение владельца |
| Профильные наборы — одна логика | config.py:76-119; strategy.py без ветвления по профилю (весь файл) | FACT (подтверждено повторно) |

### 2.9. Дозверификация Stage 2.3 (четыре коррекции аудита Stage 2.2)

| Коррекция / вывод | Источник (файл:строка, commit 884cefd) | Статус |
|---|---|---|
| **№1. RSI: строгие неравенства, равенство порогов работоспособно** | strategy.py:353-372 (BUY `rsi_val < RSI_OVERSOLD` — 355; SELL `rsi_val > RSI_OVERBOUGHT` — 371); при равенстве порогов ветки не пересекаются (rsi не может быть одновременно < 50 и > 50) | FACT (перепроверено Stage 2.3) |
| **№1. Тренд-фильтр: прогрев, а не допуск сигнала** | strategy.py:222-251 (`_trend_filter_ok`: 231-232 `len < TREND_FILTER_MA_PERIOD -> False`; 239 NaN-проверка; 245/248 сравнение close с MA) — при дефиците свечей фильтр ШТАТНО возвращает False (сигнал HOLD); общий гейт 197-198 (`len < min_candles_required -> HOLD "Недостаточно данных"`) | FACT (перепроверено Stage 2.3); правило валидации отменено (коррекция №1.2) |
| **№1. Окно данных** | main.py:3295-3299 (`_build_candles_df` — фиксированное окно CANDLES_LOOKBACK_DAYS, None при нехватке); Stage 1 PARAMETER_GAPS.md:58-60 (скрытая взаимозависимость `TREND_FILTER_MA_PERIOD <= ожидаемый объём данных ≈ CANDLES_LOOKBACK_DAYS × свечей/день`; рекомендация — предупреждение при загрузке) | FACT (документ Stage 1 + код) |
| **№2. Модель риска: члены и источники** | гейт exec_price main.py:4066; регистрация main.py:4091-4105 (executed_lots 4103; entry_actual_commission 4105); комиссия execution.py:1271-1288 (0.0 — достоверный факт, NaN/±Inf -> None); модельная комиссия main.py:2470-2489; lot_size risk_manager.py:114-117; плановый friction с SLIPPAGE_PERCENT risk_manager.py:125 (входное проскальзывание); учёт закрытия main.py:2464-2489 (realized); avg_exec_price execution.py:788/830, main.py:2754 | FACT (перепроверено Stage 2.3) |
| **№3. Профили — одна логика, выбор не требуется** | config.py:76-119 (PROFILE-ветвление: FORCE_TRADE 76-87; SANDBOX_TEST 88-97; TECH_CHECK 98-107; CONSERVATIVE 108-117; else raise 118-119); strategy.py БЕЗ ветвления по профилю (весь файл); перенос НИЧЕГО не меняет в исходнике (diff 884cefd↔1f252db по candidate/ пуст) | FACT + решение владельца (F-28) |
| **№4. Типы заявок: только рыночные** | post_market_order — tinkoff_client.py:555 (докстринг 10, ORDER_TYPE_MARKET — 582); лимитные/стоп-заявки ОТСУТСТВУЮТ: grep post_limit/LIMIT_ORDER/STOP_ORDER/ORDER_TYPE_LIMIT по main.py, execution.py, risk_manager.py, tinkoff_client.py, order_ledger.py — 0 совпадений; OrderType импортирован из SDK (tinkoff_client.py:88), но клиент его не экспонирует | FACT (проверка Stage 2.3) |
| **№4. SL/TP — программный поллинг, БЕЗ биржевого стоп-ордера** | execution.py:978-1022 (check_all: сравнение цены с sl/tp — 995-1010; `hit_tp/hit_sl`); никакой стоп-заявки не существует (см. строку выше) | FACT (проверка Stage 2.3) |
| **№4. Статусы заявок** | main.py:604-620 (ORDER_POLL_MAX_AGE_CYCLES 605; карта `{1: FILL, 2: REJECTED, 3: CANCELLED, 4: NEW, 5: PARTIALLYFILL, 6: EXPIRED}` 608-611; `_TERMINAL_ORDER_STATUSES` 612); execution.py:220 (`_TERMINAL_SELL_STATUSES` без "5"/"6" — рассинхрон V-45 Stage 1.1) | FACT (проверка Stage 2.3) |
| **№4. Частичные исполнения** | накопительное lots_executed в отчётах (main.py:128-290 — комментарии механики residual/повторов); executed_order_price execution.py:1250-1257 (защита от 0); avg_exec_price execution.py:788, 830; partial-ветка BUY main.py:5369-5471 | FACT (проверка Stage 2.3) |
| **№4. Отмена и остаток позиции** | cancel_order tinkoff_client.py:646-680; неподтверждённая отмена -> record_uncertain main.py:4385-4392; get_positions tinkoff_client.py:315-330 (лоты со знаком; None = неизвестно, {} = пусто; частичный снимок недопустим); get_sandbox_orders tinkoff_client.py:437-456 | FACT (проверка Stage 2.3) |
| **№4. Защита от повторной SELL** | _sell_block_reason main.py:738-767; SELL_DUPLICATE_BLOCKED main.py:2244; INTENT-before-send close_order_request_id = uuid4 ДО сети main.py:2254-2260 | FACT (проверка Stage 2.3; переиспользуется контроллером) |
### 2.10. Дозверификация Stage 2.3.1 (две критические коррекции аудита Stage 2.3)

Проверка выполнена Stage 2.3.1 самостоятельным чтением рабочего дерева
на commit `884cefd` (файлы main.py/execution.py/risk_manager.py/
tinkoff_client.py байт-идентичны baseline — `git diff 884cefd --
candidate/*.py` пуст; коммиты 2.1/2.2/2.3 на origin добавляли ТОЛЬКО
документацию — `git diff 884cefd..430a31b -- candidate/` пуст).

| Коррекция / вывод | Источник (файл:строка, commit 884cefd) | Статус |
|---|---|---|
| **№1. Последовательность выхода: обнаружение → отправка рыночной SELL ДО контроллера** | main.py:5144 (`to_close = await monitor.check_all(...)`) → main.py:5145-5152 (цикл: валидная цена → `await close_position(client, pos, price)`) → main.py:2315 (`result = await client.post_market_order(...)`) внутри close_position (INTENT 2254-2280; _sell_block_reason 738-767, проверка 2235) | FACT (проверка Stage 2.3.1) — подтверждает ошибку ред. 2.3: контроллер ПОСЛЕ шага защитных выходов получал позицию с уже отправленной рыночной SELL |
| **№1. check_all — ТОЛЬКО обнаружение (заявок не отправляет)** | execution.py:978-1022: сравнение цен (1005-1010), маркировка CLOSING/close_reason/цены (1017-1020), append + return (1021-1022); внутри НЕТ post-вызовов; fail-ветка None/<=0 → monitoring_error + пропуск (994-997) | FACT (проверка Stage 2.3.1) — запрет обхода контроллера фиксируется на уровне ЦИКЛА (шаг 2г), контракт check_all сохраняется |
| **№1. Возможности адаптера для инцидента** | post_market_order tinkoff_client.py:555-599; cancel_order 646-680; get_positions 315-330; get_sandbox_orders 437-456; get_sandbox_order_state 601; лимитные заявки ОТСУТСТВУЮТ (grep 0 — F-22) | FACT (проверка Stage 2.3.1) — «реализовано / предстоит реализовать» — STAGE2_EMERGENCY_EXIT_ARCHITECTURE.md §5 |
| **№2. SL рассчитывается ОТ exec_price** | main.py:4072 (`sl_price, tp_price = rm.calculate_sl_tp(exec_price, "BUY", df)`); risk_manager.py:238 (`base_stop_distance = entry_price * max(...)`), 246 (`sl = entry_price - base_stop_distance`); регистрация main.py:4091-4105 (execution_price 4102, entry_actual_commission 4105) | FACT (проверка Stage 2.3.1) — основание коррекции №2: расстояние \|exec−sl\| = exec_price*max(...) содержит от входного проскальзывания только долю, пропорциональную стоп-проценту; обоснование ред. 2.3 НЕВЕРНО (STAGE2_RISK_MODEL_FORMULAS.md §2) |
| **№2. Sizing-база и единственность SLIPPAGE_PERCENT** | main.py:5128 (снимок цен цикла), 5278 (`lots = await rm.calculate_position_size(figi, float(price), df)`); risk_manager.py:104 (risk_amount), 124 (base_risk от last_price), 125 (friction = price*(COMMISSION*2 + SLIPPAGE_PERCENT)), 126-137 (per_share_risk, лоты) | FACT (проверка Stage 2.3.1) — SLIPPAGE_PERCENT входит ТОЛЬКО в sizing-знаменатель (DC-1) |
| **№2. Существующие slippage-поля учёта закрытия** | main.py:2464-2466 (`entry_slippage = (entry_price - price_before_order) * shares`; `exit_slippage = (close_price_before_order - exit_price) * shares`); gross/net P&L 2467-2469, 2490; commission_source 2484-2489 | FACT (проверка Stage 2.3.1) — пер-шарные поля ред. 2.3.1 согласованы по знаку с существующим CSV-учётом (F-33) |
| **№2. Арифметика числового примера** | числовой пример STAGE2_RISK_MODEL_FORMULAS.md §8 просчитан программой (Decimal) — все декомпозиции сходятся: realized−open = stop_execution_slippage − дельта баз выходной комиссии; realized−estimated = (фактич.дистанция−плановая) + stop_execution_slippage + дельты комиссий; доля проскальзывания внутри расстояния = стоп-процент | VERIFIED (скрипт Stage 2.3.1; условные данные, НЕ торговые параметры) |

---

### 2.11. Дозверификация Stage 2.3.2 (три коррекции согласованности аудита Stage 2.3.1)

Проверка выполнена Stage 2.3.2 самостоятельным чтением рабочего дерева
на commit `884cefd` (код байт-идентичен baseline; правки
Stage 2.1–2.3.2 — только документация; Stage 2.3.2 исходный код НЕ
изменяет).

| Коррекция / вывод | Источник (файл:строка, commit 884cefd) | Статус |
|---|---|---|
| **№1. В3 НЕ отправляет заявок — только обнаружение и закрытие учёта** | main.py:1932-2011 (`reconcile`: кандидат внешнего закрытия → двойное подтверждение с разносом RECONCILE_CONFIRM_MIN_AGE_SECONDS (config.py:133-141) → `POSITION_CLOSED_EXTERNAL`); `_finalize_position_closed` main.py:1462-1492 (закрытие УЧЁТА: quantity=0, execution_price, exit_price_confirmed=price_confirmed; post-вызовов НЕТ) | FACT (проверка Stage 2.3.2) — устраняет противоречие ред. 2.3.1 «close_position как механизм В3/операторских закрытий»: В3 — отдельный механизм обнаружения, не маршрут отправки |
| **№1. Инвентаризация вызовов close_position** | определение main.py:2224; ЕДИНСТВЕННЫЙ вызов main.py:5152 (торговый цикл, шаг защитных закрытий — удаляется этапом H); В3 к close_position НЕ обращается | FACT (проверка Stage 2.3.2) |
| **№1. Единственная точка отправки SELL в текущем коде** | post_market_order — main.py:2315 (внутри close_position — SELL) и main.py:5327 (BUY вход); иных post-вызовов SELL нет (grep) | FACT (проверка Stage 2.3.2) — инвариант ALL_BOT_SELL_SUBMISSIONS ⊆ process_incidents() проектируется на существующую топологию отправок |
| **№1. Telegram-интерфейс БЕЗ команд закрытия** | telegram_bot.py:52-107 — ТОЛЬКО /start /stop /status (управление trading.flag; set_my_commands 60-66); команд закрытия позиций НЕТ (grep — 0) | FACT (проверка Stage 2.3.2) — сценарий C (команда закрытия через интерфейс бота) — ПРОЕКТ этапа H; прямой SELL из обработчика запрещён запретами №8-9 EEA §3 |
| **№1. Частичная внешняя продажа обнаруживаема** | reconcile-механики В2: get_positions как источник истины остатка (tinkoff_client.py:315-330; None=неизвестно, {}=пусто); расходимость → UNCERTAIN (main.py:2018-2223); B2 close accounting (apply_close_execution — execution.py:656-861) | FACT (проверка Stage 2.3.2) — сценарий EE-26 опирается на существующие механики |
| **№2. D-24/D-27 — решения документации, исходный код не содержит** | конфигурация политики аварийного выхода в коде ОТСУТСТВУЕТ (grep emergency_exit/D-24/D-27 по candidate/*.py — 0; политика — PROPOSAL этапа H); fail-closed прецеденты для конфигурационной защиты: config.validate config.py:147-163 (отказ при некорректной конфигурации); else-raise PROFILE config.py:118-119; getattr-fallback не воспроизводится (FILE_CHANGE_MAP §3.2 «Важно») | FACT + PROPOSAL (проверка Stage 2.3.2) — механизм §3а OPEN_DECISIONS опирается на существующие fail-closed паттерны |
| **№3. Двузначность pos.execution_price (вход/выход)** | регистрация: main.py:4091-4105 (execution_price 4102 — цена ВХОДА); закрытие учёта: main.py:2462 (`exit_price = float(pos.execution_price)` — цена ВЫХОДА из avg_exec_price cursor'а execution.py:788/830); В3: _finalize_position_closed main.py:1488-1492 | FACT (проверка Stage 2.3.2) — обоснование КОРРЕКЦИИ №3: контракт разделяет фазы именами exec_price (вход) и exit_exec_price (выход); поле кода НЕ переименовывается |
| **№3. Цена выхода подтверждена ТОЛЬКО отчётом исполненного ордера** | маркер `exit_price_confirmed` — execution.py:789-790, 831-833 (avg_exec_price is not None); `_finalize_position_closed` main.py:1477-1492 (price_confirmed=True ТОЛЬКО из реального исполненного ордера; В3 — price_confirmed=False); В3-CSV без P&L при неизвестной цене — main.py:1975-2011 («цена исполнения неизвестна — P&L не рассчитан») | FACT (проверка Stage 2.3.2) — правила §5.5 RMF (цена заявки ≠ исполнение; неизвестная цена НЕ заменяется) опираются на существующий инвариант |
| **№3. Частичные исполнения — накопительная механика** | per-order cursor: lots_executed накопительно, avg_exec_price, close_applications (execution.py:656-861, 820-833); executed_order_price с защитой от 0 — execution.py:1248-1263; повторный терминальный отчёт идемпотентен (execution.py:780-800) | FACT (проверка Stage 2.3.2) — средневзвешенная цена и «не терять подтверждённые части» (§5.5 RMF) реализуемы существующими механиками |
| **№3. Существующие денежные slippage-поля** | main.py:2464-2466 (`entry_slippage`, `exit_slippage` — ДЕНЕЖНЫЕ, на позицию; знак: положительное = неблагоприятное) | FACT (проверка Stage 2.3.2) — пер-шарные поля контракта exit_slippage_ps/entry_slippage_ps согласованы по знаку; конфликт имён исключён суффиксом _ps |

## 3. Независимая перепроверка матрицы Stage 1.1 (ключевые строки)

| ID Stage 1.1 | Заявленный источник | Перепроверка Stage 2 | Итог |
|---|---|---|---|
| V-01 | main.py:5663 | подтверждено (§2.1) | совпадает |
| V-02 | main.py:5723-5729 (вызов 5725) | подтверждено | совпадает |
| V-03 | main.py:5237, 5260 | подтверждено | совпадает |
| V-04 | strategy.py:34-43 | подтверждено | совпадает |
| V-05 | strategy.py:90, 104-107, 124-125, 130, 135-136, 141-145, 159-163 | подтверждено | совпадает |
| V-06 | strategy.py:188-190; main.py:5236-5310 | подтверждено | совпадает |
| V-07 | strategy.py:100, 118-127 | подтверждено | совпадает |
| V-13 | main.py:1144-1171; strategy.py:102-114 | подтверждено | совпадает |
| V-15…V-18 | risk_manager.py:124-132 | подтверждено (§2.3) | совпадает |
| V-19 | risk_manager.py:238-244 | подтверждено | совпадает |
| V-20 | main.py:5278, 4072, 4803, 4808 | подтверждено | совпадает |
| V-21 | PARAMETER_USAGE_MAP.md:149 vs risk_manager.py:123-132 | формула Stage 1 неточна — подтверждено по коду (friction на базовой ветке присутствует) | совпадает |
| V-23 | risk_manager.py:91-92, 142-145, 198-201 | подтверждено | совпадает |
| V-24 | main.py:5270-5276 | подтверждено | совпадает |
| V-25 | execution.py:978-1022; main.py:2224-2228, 2315, 1932-2011 | подтверждено | совпадает |
| V-26 | config.py:50; execution.py:913-966, 1003 | подтверждено (гейт — 923) | совпадает |
| V-28 | strategy.py (весь); execution.py:241-306 | подтверждено; TrackedPosition действительно без strategy_id (242-346) | совпадает |
| V-29 | main.py:5270-5276; execution.py:953-966, 1008-1010 | подтверждено | совпадает |
| V-30 | execution.py:241-306 | подтверждено | совпадает |
| V-31 | config.py:76-119 | подтверждено | совпадает |
| V-32 | config.py:4, 76 | подтверждено | совпадает |
| V-38 | execution.py:884-888, 991-1022 | подтверждено | совпадает |
| V-39 | tinkoff_client.py:315-325, 555-577 | подтверждено | совпадает |
| V-45 | main.py:609-612; execution.py:220, 1075 | рассинхрон подтверждён (§2.6); достижимость остаётся UNKNOWN | совпадает (частично) |
| V-46 | config.py:104-117; strategy.py:231-232 | подтверждено | совпадает |

Расхождений с матрицей Stage 1.1 не обнаружено. Строка 1003 в V-26
уточнена: гейт BE_TRAIL_ENABLED в check_all — execution.py:1003
(`if getattr(config, "BE_TRAIL_ENABLED", False):`), в _update_sl — 923;
оба подтверждены.

---

## 4. Трассировка проектных решений (PROPOSAL → обоснование FACT)

| Проект (blueprint §) | Опирается на FACT |
|---|---|
| §4 контракт StrategyBase | strategy.py:177-182 (сигнатура сохраняется); main.py:5260, 4072, 4808 (точки вызова); risk_manager.py:233-259 (перенос SL/TP) |
| §4.1 DecisionType | main.py:5270-5276 (long-only), частичное закрытие отсутствует (grep), execution.py:953-966 |
| §5 state per (id, figi) | strategy.py:34-43, 100, 118-127, 188-190; main.py:1144-1171; screener.py:196-197 |
| §6 exit-хук | execution.py:978-1022 (точка интеграции до check_all); main.py:2224-2376 (close_position не меняется) |
| §7 stop-distance контракт | risk_manager.py:124-132, 137, 233-259; main.py:4072 (exec_price) vs 5278 (last_price) |
| §8 legacy_samsung_v4 | config.py:76-119; strategy.py 1:1; Stage 1.1 §4 |
| §9.1 ExecutionAdapter | tinkoff_client.py:240-268, 270-301, 303-435, 437-456, 555-679 (точный набор операций) |
| §9.2 A-1…A-13 | config.py:59-61 (friction-параметры); execution.py:884-888 (5-мин гранулярность); main.py:5369-5471 (partial); main.py:2464-2489 (комиссия модель/факт) |
| §9.3 консервативное правило | execution.py:1005-1010 (одновременно невозможно при точечной цене — правило для внутрибарной неоднозначности) |
| §6.2 два списка выходов (Stage 2.1) | main.py:5144, 5145-5152, 2235-2252, 2254-2280, 2271-2275, 2315, 2835; execution.py:978-1022 (992, 1011-1020) |
| §7.4 единицы/база/фактический риск (Stage 2.1) | risk_manager.py:124-126, 137, 238; main.py:5128, 5278, 4072, 4808, 4091-4105, 2464-2489; execution.py:1271 |
| §9.1 инвентаризация 10 операций (Stage 2.1) | таблица §2.7 (main.py / execution.py / risk_manager.py / tinkoff_client.py / screener.py) |
| §9.6 классы заявок (Stage 2.1) | config.py:162-163; tinkoff_client.py:182-184; build_safety.py:44, 78-83, 86-113; main.py:5659-5660 |
| §10.3 профиль FORCE_TRADE (Stage 2.1) | config.py:76, 78-87, 64-73, 121; противоречие комментария — config.py:4 |
| §6.2 шлюз валидности цены (Stage 2.2) | tinkoff_client.py:253-268 (262-265); main.py:5130-5133, 5145-5152; execution.py:978-1022 (988-990, 992, 994-997), 1264, 1271-1288 |
| §7.4 однозначная формула фактического риска (Stage 2.2) | main.py:4066, 4091-4105, 2464-2489; execution.py:1271-1288; risk_manager.py:114-117, 125 |
| §10.1 условия валидации конфигурации (Stage 2.2) | strategy.py:58, 81-88, 197-198, 231-232, 258, 274-297, 317, 353-372, 439-458; risk_manager.py:244, 257; config.py:147-163 (образец fail-closed) |
| §8/§10.2/§10.3 исключение FORCE_TRADE (Stage 2.2) | config.py:76-119 (FACT-источник, НЕ изменяется); решение владельца — STAGE2_2_CHANGELOG.md §2 |
| §10.1 единая таблица правил + отмена правила TREND_FILTER (Stage 2.3) | strategy.py:197-198, 222-251 (231-232), 258, 274-297, 317, 353-389, 439-458, 58, 81-88; main.py:3295-3299; Stage 1 PARAMETER_GAPS:58-60 |
| §7.4 модель расчётного риска с резервом исполнения стопа (Stage 2.3) | main.py:4066, 4091-4105, 2464-2489; execution.py:1271-1288, 788/830; risk_manager.py:114-117, 125; решение D-16 — OPEN_DECISIONS (значение НЕ изобретается) |
| §8 п. 2 / §10.3 «движок НЕ требует выбора старого профиля» (Stage 2.3) | config.py:76-119; strategy.py без ветвления по профилю; решение владельца — STAGE2_3_CHANGELOG.md (F-28, D-13 ред. 2.3) |
| §16 / STAGE2_EMERGENCY_EXIT_ARCHITECTURE.md гибридный аварийный выход (Stage 2.3) | post_market_order tinkoff_client.py:555-599 (лимитных НЕТ — F-22); check_all execution.py:978-1022 (программный SL/TP — F-23); статусы main.py:604-620 (F-24); partial main.py:128-290, 5369-5471, execution.py:1250-1257 (F-25); cancel/positions main.py:4385-4392, tinkoff_client.py:315-330, 437-456, 646-680 (F-26); защита дублей main.py:738-767, 2244, 2254-2260 (F-27) |
| §9.4 clock-инъекция | main.py:645, 854, 1500, 1935, 1957, 1988, 2269, 3033, 3074, 5292 (прямые datetime.now(timezone.utc) — верифицировано grep'ом; список Stage 1 T-1.3 уточнён: вызов в зоне close_position — 2269, строка 2359 вызовом не является) |
| §10 конфигурация | config.py:76-119 (перенос), 147-163 (fail-closed образец); main.py:1952-1953, 5139 (getattr-fallback — не воспроизводить) |
| §11 совместимость | §2.4 настоящей таблицы (все механизмы сохраняются) |

---

## 5. Ограничения трассировки

1. Строки действительны для commit `884cefd…`; при изменении кода в
   будущих этапах номера сместятся — пересчитывать по символам, а не по
   строкам.
2. Поведение SDK (protobuf-поля, сырые статусы) принято по контрактам
   кода и комментариям (N-01 Stage 1 остаётся открытым — V-1 в
   STAGE2_OPEN_DECISIONS.md).
3. Runtime-файлы владельца (state.json, журналы, CSV) недоступны —
   выводы о фактической частоте/объёме (V-2, V-5) не делаются.
4. Тесты не запускались на Stage 2; «789 passed» — факт владельца из
   docs/INSTALLATION_RU.md §4, не результат прогона Stage 2.
5. Инвентаризация вызовов (§2.7) выполнена статическим анализом
   исходника; поведение SDK в рантайме не проверялось (T-Invest API не
   вызывался — ограничение ТЗ).
6. Документальная основа Stage 2.2 (commit `f5db0d6`) проверена
   READ-ONLY-операциями git (fetch remote-tracking + ls-tree + diff);
   рабочее дерево НЕ переключалось на `f5db0d6`; локальный клон остаётся
   на `884cefd` с неизменённым содержимым candidate/ и docs/ (diff
   файлов — только атрибуты прав файловой системы, 0 вставок/0 удалений).
7. Документальная основа Stage 2.3 (комплект Stage 2.2, commit `1f252db`
   на origin/main) проверена READ-ONLY-операциями git (fetch
   remote-tracking + ls-tree + побайтовое сравнение 7/7 hash-object);
   рабочее дерево НЕ переключалось; локальный клон остаётся на `884cefd`.
   Поведение лимитных/рыночных заявок в граничных режимах биржи кодом
   НЕ доказуемо (в коде только рыночные заявки) — вынесено в V-10.
8. Stage 2.3.2 — документальная корректировка комплекта 2.3.1: исходный
   код НЕ изменялся и НЕ запускался; тесты не выполнялись; API не
   вызывался; все правки — только документация (КОРРЕКЦИИ №1-№3 ТЗ
   Stage 2.3.2).

---

```
STAGE 2.3.2 — FINAL ARCHITECTURE CONSISTENCY CORRECTIONS
DESIGN ONLY
SOURCE CODE: UNCHANGED
TRADING: NOT EXECUTED
T-INVEST API: NOT ACCESSED
GITHUB: READ-ONLY
NO LIVE ORDERS
STRATEGY LOGIC: UNCHANGED
RESEARCH ONLY
NO THRESHOLD IS OPTIMIZED
NO FILTER IS INSTALLED
EMERGENCY EXIT ARCHITECTURE — DESIGN ONLY
NO BROKER EXECUTION
NO PYTHON CODE CHANGES
```
