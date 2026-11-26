# STAGE2_SOURCE_TRACEABILITY.md

## SAMSUNG V4 — STAGE 2: трассировка выводов в исходный код

**Статус:** `STAGE 2 — DESIGN ONLY / SOURCE CODE: UNCHANGED`.

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

---

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

---

```
STAGE 2 — DESIGN ONLY
SOURCE CODE: UNCHANGED
TRADING: NOT EXECUTED
T-INVEST API: NOT ACCESSED
GITHUB: READ-ONLY
```
