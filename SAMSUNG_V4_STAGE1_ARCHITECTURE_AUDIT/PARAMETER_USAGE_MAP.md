# PARAMETER_USAGE_MAP.md

## Карта прохождения параметров: от конфигурации до участка торговой логики

**Мандаты:**

```
STRATEGY LOGIC: UNCHANGED
RESEARCH ONLY
NO THRESHOLD IS OPTIMIZED
NO FILTER IS INSTALLED
NO LIVE ORDERS
```

Документ отвечает на вопрос ТЗ §2.1 «все места чтения и использования» для
каждого параметра и показывает полный путь «конфигурация → участок кода →
торговое решение». Все ссылки — ФАКТ по commit `main@884cefd`.
Инвентаризация значений/типов — STRATEGY_PARAMETERS_INVENTORY.md; здесь —
топология использования.

---

## 1. Общая топология чтения конфигурации (ФАКТ)

```
.env / переменные окружения
        │ os.getenv (config.py:14-19, 144)
        ▼
   config.py  ──(import при старте каждого модуля)──►  потребители
        │
        ├── strategy.py  (import config, strategy.py:27)
        ├── risk_manager.py (risk_manager.py:32)
        ├── execution.py (execution.py:201)
        ├── tinkoff_client.py (tinkoff_client.py:134)
        ├── screener.py (screener.py:32)
        ├── logger.py (logger.py:96)
        └── main.py (main.py:565) + build_safety/safe_start
```

**ФАКТ:** `config` импортируется как модуль — все потребители читают ОДИН и
тот же экземпляр значений, зафиксированный на момент импорта. Динамической
переконфигурации нет: `load_dotenv()` выполняется один раз (config.py:11),
PROFILE-ветвление выполняется один раз (config.py:78-119).

**ФАКТ (два исключения из «каждый раз читаем config»):**
- `strategy.py:32` — `self.min_candles_required = config.MIN_CANDLES_FOR_SIGNAL`
  кэшируется в конструкторе `StrategyManager` (создаётся один раз,
  main.py:5663) — последующие изменения атрибута config внутри процесса
  сигналами НЕ подхватываются (актуально для тестов, где monkeypatch
  подменяет config.MIN_CANDLES_FOR_SIGNAL ДО создания менеджера).
- `COMMISSION_PER_SIDE` вычисляется при импорте из COMMISSION_MODE
  (config.py:60) — изменение `config.COMMISSION_MODE` в рантайме ставку не
  меняет.

## 2. Путь параметров стратегии A: от свечей до сигнала

### 2.1. Подготовка данных (таймфрейм, окно истории)

```
main.py:3289 _build_candles_df(client, figi)
  ├─ config.CANDLES_LOOKBACK_DAYS      main.py:3296   окно истории, дней
  ├─ CANDLE_INTERVAL_5_MIN (хардкод)   main.py:3297   таймфрейм сигналов
  ├─ get_historical_candles(...)       tinkoff_client.py:240-251
  │     └─ config.API_CALL_DELAY_SECONDS  tinkoff_client.py:242  пауза перед запросом
  ├─ len(candles) < config.MIN_CANDLES_FOR_SIGNAL → None   main.py:3299
  └─ DataFrame(open/high/low/close/volume/is_complete)      main.py:3301-3310
```

Тот же `_build_candles_df` используется и для входов (main.py:5255), и для
расчёта SL/TP при промоции RECOVERY (main.py:4803), и для экстремумов
безубытка (main.py:1121 — при BE_TRAIL_ENABLED=True).

### 2.2. Сигнал (strategy.py)

```
main.py:5260  signal, reason = sm.get_signal(df, price, drop_incomplete=True)
   strategy.py:177-219 get_signal
   ├─ self.min_candles_required (=config.MIN_CANDLES_FOR_SIGNAL)  strategy.py:32,197
   ├─ _prepare_dataframe (сортировка, дедуп, числовые типы,
   │     удаление незакрытой свечи при явном False)               strategy.py:391-427
   ├─ regime = get_market_regime(prepared)                        strategy.py:202
   │     ├─ len < config.ADX_PERIOD + 1 → UNKNOWN                 strategy.py:58-59
   │     ├─ ta.adx(length=config.ADX_PERIOD)                      strategy.py:61-66
   │     ├─ колонка f"ADX_{config.ADX_PERIOD}"                    strategy.py:71
   │     ├─ tail(config.ADX_HYSTERESIS_CANDLES)                   strategy.py:81-85
   │     ├─ порог: value > config.ADX_TREND_THRESHOLD             strategy.py:92-95
   │     ├─ гистерезис по уникальным свечам (_regime_streak)      strategy.py:116-170
   │     └─ TREND / RANGE / UNKNOWN                               strategy.py:97, 204-211
   ├─ TREND → _ma_crossover_signal                                strategy.py:204-205
   │     ├─ len < config.MA_SLOW_PERIOD + 2 → HOLD                strategy.py:258-259
   │     ├─ ta.sma(length=config.MA_FAST_PERIOD)                  strategy.py:261-264
   │     ├─ ta.sma(length=config.MA_SLOW_PERIOD)                  strategy.py:266-269
   │     ├─ пересечение pf<ps && lf>ls → BUY; pf>ps && lf<ls → SELL  strategy.py:288-304
   │     └─ фильтр MA100: _trend_filter_ok                        strategy.py:289, 298
   ├─ RANGE → _bb_rsi_signal                                      strategy.py:207-208
   │     ├─ len < config.BB_PERIOD + config.RSI_PERIOD → HOLD     strategy.py:317-318
   │     ├─ ta.bbands(length=BB_PERIOD, std=BB_STD_DEV)           strategy.py:320-324
   │     ├─ ta.rsi(length=config.RSI_PERIOD)                      strategy.py:326-329
   │     ├─ close < BBL && rsi < config.RSI_OVERSOLD → BUY        strategy.py:353-367
   │     └─ close > BBU && rsi > config.RSI_OVERBOUGHT → SELL     strategy.py:369-383
   ├─ _trend_filter_ok (общий для обоих режимов):
   │     len < config.TREND_FILTER_MA_PERIOD → False              strategy.py:231-232
   │     ta.sma(length=config.TREND_FILTER_MA_PERIOD)             strategy.py:234-237
   │     BUY: close ≥ MA; SELL: close ≤ MA                        strategy.py:245-251
   └─ BUY/SELL → _volume_confirmation                            strategy.py:213-218
         ├─ окно min(config.VOLUME_CONFIRMATION_WINDOW, len)      strategy.py:439-442
         ├─ окно < 3 → отказ                                      strategy.py:444-446
         └─ last ≥ avg * config.VOLUME_SPIKE_FACTOR → ок          strategy.py:458-465
```

### 2.3. Потребление сигнала (main.py, входы)

```
trading_cycle main.py:5115
  шаг 1: цены — config.* не используются; figi_set = позиции + top_instruments  main.py:5124-5128
  шаги 2-4: SL/TP, закрытия, poll, recovery — см. §3-4
  шаг 5: блокировки входов (trading.flag/reconcile/monitoring_error/state/ledger) main.py:5186-5225
  шаг 6: свежий портфель client.get_positions()                                  main.py:5228
  шаг 7: для inst in top_instruments:
    ├─ сигнал "SELL" без позиции → игнор («шорт запрещён»), STRATEGY_SELL_IGNORED main.py:5270-5276
    ├─ lots = rm.calculate_position_size(figi, price, df)                         main.py:5278
    ├─ trade_id = uuid4().hex[:12]; order_id = uuid4()                            main.py:5288-5291
    ├─ log_event("SIGNAL", …)                                                     main.py:5293-5298
    ├─ ledger.record_intent (fail-closed)                                         main.py:5308-5321
    ├─ client.post_market_order(figi, lots, BUY, order_id)                        main.py:5327
    └─ ветки PARTIALLYFILL / не-FILL / FILL → register_executed_buy               main.py:5369-5612
```

**ВЫВОД:** параметры A-категории напрямую определяют момент и сторону входа;
вход возможен ТОЛЬКО на BUY (SELL-сигналы без позиции отбрасываются,
main.py:5270-5276) — выход позиции сигналами стратегии не выполняется вообще
(только SL/TP/BE/TRAIL и оператор).

## 3. Путь параметров риска B: размер позиции и SL/TP

### 3.1. Размер позиции

```
risk_manager.py:87 calculate_position_size(figi, last_price, candles_df)
  ├─ daily_trade_counts ≥ config.MAX_TRADES_PER_INSTRUMENT_PER_DAY → 0     risk_manager.py:91-92
  ├─ get_account_balance() → None/≤0 → 0 (блокировка)                      risk_manager.py:96-102
  ├─ risk_amount = balance * config.RISK_PER_TRADE                         risk_manager.py:104
  ├─ instrument_info / lot_size (get_instrument_info)                      risk_manager.py:109-117
  ├─ base_risk = price * max(STOP_LOSS_PERCENT, MIN_STOP_LOSS_PERCENT)     risk_manager.py:124
  ├─ friction  = price * (COMMISSION_PER_SIDE*2 + SLIPPAGE_PERCENT)        risk_manager.py:125
  ├─ atr_risk = _calculate_volatility_risk(df)                             risk_manager.py:128
  │     └─ ta.atr(length=config.ATR_PERIOD_INTRADAY) * ATR_STOP_MULTIPLIER risk_manager.py:215-228
  ├─ atr_risk = min(atr_risk, price*MAX_ATR_STOP_PERCENT)                  risk_manager.py:130-131
  ├─ per_share_risk = max(base_risk, atr_risk + friction)                  risk_manager.py:126-132
  ├─ position_size_by_risk = risk_amount / (per_share_risk * lot_size)     risk_manager.py:137
  ├─ position_size_by_capital = balance*MAX_POSITION_SHARE_PER_INSTRUMENT
  │                                / (price*lot_size)                      risk_manager.py:142-143
  ├─ экспозиция: для каждой позиции брокера lots*lot_size*price            risk_manager.py:149-196
  │     (get_positions/get_instrument_info/get_last_prices; None → 0)
  ├─ кап по MAX_TOTAL_EXPOSURE: allowed = balance*MAX_TOTAL_EXPOSURE − exposure  risk_manager.py:198-201
  └─ size = min(by_risk, by_capital); ≤0 → 0                               risk_manager.py:203-204
```

### 3.2. SL/TP

```
risk_manager.py:233 calculate_sl_tp(entry_price, direction, candles_df)
  ├─ base_stop_distance = entry * max(STOP_LOSS_PERCENT, MIN_STOP_LOSS_PERCENT)  risk_manager.py:238
  ├─ atr_risk (как выше) → min(atr_risk, entry*MAX_ATR_STOP_PERCENT)             risk_manager.py:239-242
  ├─ base_stop_distance = max(base, atr_risk)                                    risk_manager.py:243
  ├─ take_profit_distance = base_stop_distance * TAKE_PROFIT_RATIO               risk_manager.py:244
  ├─ BUY: sl = entry − dist; tp = entry + dist (sl≥entry → None,None)            risk_manager.py:245-249
  ├─ SELL: зеркально (sl≤entry → None,None)                                      risk_manager.py:250-254
  └─ sl≤0 или tp≤0 → (None,None)                                                 risk_manager.py:257-258

Потребители: main.py:4072 (register_executed_buy при входе),
             main.py:4808 (promote_recovery_positions при промоции RECOVERY).
Результат: monitor.register(... sl_price, tp_price ...) main.py:4091-4101;
           initial_sl/initial_tp фиксируются execution.py:484-487 (С1).
```

### 3.3. Срабатывание SL/TP (выход)

```
trading_cycle шаг 2:
  (только при BE_TRAIL_ENABLED=True) экстремумы/ATR: main.py:5138-5143
  to_close = monitor.check_all(prices, extremes, atrs)                main.py:5144
    execution.py:978-1022 check_all:
      ├─ цены пустые → monitoring_error=True                          execution.py:988-990
      ├─ update_extremes по 5-мин свече                               execution.py:999-1002
      ├─ (BE_TRAIL_ENABLED) _update_sl: BE_TRIGGER_R / TRAIL_ATR_MULTIPLIER
      │    / буфер 2*COMMISSION_PER_SIDE+SLIPPAGE_PERCENT             execution.py:913-966, 872-875
      ├─ BUY: hit_tp = price ≥ tp; hit_sl = price ≤ sl                execution.py:1005-1007
      ├─ SELL: зеркально                                              execution.py:1008-1010
      └─ причина: TP / _classify_sl_exit (SL|BE|TRAIL)                execution.py:1011-1020
  для каждой to_close: price≤0 → UNCERTAIN; иначе close_position      main.py:5145-5152
close_position main.py:2224:
  ├─ _sell_block_reason (повторная SELL запрещена)                    main.py:2235-2252
  ├─ INTENT в ledger + add_close_order (fail-closed)                  main.py:2258-2313
  └─ client.post_market_order(... direction=SELL/BUY, market)         main.py:2315
```

## 4. Путь параметров движка C

| Параметр | Путь |
|---|---|
| TRADING_CYCLE_SECONDS | main.py:5729 — `asyncio.sleep` между циклами; main.py:645 — возраст заявки в циклах; main.py:1952-1953 — fallback для RECONCILE_CONFIRM_MIN_AGE_SECONDS |
| RECONCILE_CONFIRM_MIN_AGE_SECONDS | main.py:1952-1958 — минимальный разнос двух снимков В3 (двойное подтверждение внешнего закрытия) |
| CANDLES_LOOKBACK_DAYS + 5-мин интервал | main.py:3296-3297 — все расчёты по свечам |
| ORDER_POLL_MAX_AGE_CYCLES (хардкод 10) | main.py:4356 (`need_cancel` для PARTIALLYFILL/NEW), main.py:4465 (NEW без исполнения) — отмена остатка по возрасту |
| BE_TRAIL_ENABLED / BE_TRIGGER_R / TRAIL_ATR_* | main.py:5139 (сбор данных), 1134 (_atr_from_df, TRAIL_ATR_PERIOD); execution.py:923 (гейт), 935/958 (BE_TRIGGER_R), 946/964 (TRAIL_ATR_MULTIPLIER) |
| BUILD_VERSION | logger.py:188 — в каждое событие JSONL; main.py:3011 — колонка CSV `build_version` |
| имена файлов (хардкод) | main.py:596-601 (trading.flag/state.json/order_ledger.jsonl); logger.py:98-99 (research_events.jsonl/research_trades.csv) |

## 5. Путь параметров брокера D и скринера E

```
E-параметры (скринер, ОДИН раз при старте):
main.py:5704 instruments = await screener.select_top_volatile()
  screener.py:56-117 select_top_volatile
    ├─ _cache_valid: age_hours < config.VOLATILITY_REFRESH_HOURS         screener.py:49-54
    ├─ 2 попытки (range(1,3) — хардкод, НЕ API_RETRY_COUNT)              screener.py:68
    │     паузы config.API_RETRY_DELAY_SECONDS                           screener.py:83,90,106
    └─ _do_scan                                                          screener.py:119-198
        ├─ AsyncClient(config.TINKOFF_READONLY_TOKEN)                    screener.py:130
        ├─ фильтры: real_exchange==REAL_EXCHANGE_MOEX(1), currency=="rub",
        │   buy/sell_available_flag                                      screener.py:134-139
        ├─ свечи: config.VOLATILITY_PERIOD_DAYS, DAY-интервал            screener.py:151-155
        ├─ мин. свечей: config.VOLATILITY_PERIOD_DAYS - 1                screener.py:159
        ├─ ta.atr(length=config.ATR_PERIOD)                              screener.py:169-172
        ├─ оборот: volume.tail(20)*close.tail(20) ≥ MIN_DAILY_TURNOVER_RUB screener.py:179-181
        └─ сортировка по volatility, срез [:TOP_VOLATILE_INSTRUMENTS_COUNT] screener.py:196-197
  при ошибке → None → main.py:5705-5712: вечный цикл сна 60 с, входы запрещены

D-параметры (клиент):
main.py:5653 TinkoffClient(config.TINKOFF_API_TOKEN, config.USE_SANDBOX)
  tinkoff_client.py:182-184 — use_sandbox=False → SandboxRequiredError
  __aenter__: config.API_RETRY_COUNT/API_RETRY_DELAY_SECONDS             tinkoff_client.py:195-207
  get_positions: timeout=config.API_REQUEST_TIMEOUT_SECONDS              tinkoff_client.py:340-343
  get_historical_candles/get_last_prices: config.API_CALL_DELAY_SECONDS  tinkoff_client.py:242,260
  post_market_order: market-only (ORDER_TYPE_MARKET хардкод)             tinkoff_client.py:580-584
  get_sandbox_order_state/cancel_order: timeout + order_id_type          tinkoff_client.py:634-644, 664-679
```

## 6. Параметры, попадающие в журналы и state.json (происхождение решений)

**ФАКТ:** каждое событие `research_events.jsonl` содержит
`config_profile`, `commission_mode`, `build_version` (logger.py:183-189).
**ФАКТ:** CSV-строка сделки содержит `build_version` (main.py:3087) и
`signal_reason` (main.py:3048), но НЕ содержит полный срез параметров
(MA/RSI/ADX-значений, PROFILE-переопределений) и НЕ содержит
идентификатор стратегии (его не существует — см.
STRATEGY_SWITCH_ARCHITECTURE.md).

**ФАКТ:** `state.json` (main.py:1144-1171) сохраняет: positions
(включая sl_price/tp_price/initial_*/mae/mfe — execution.py:303-306,
1302-1313), closed_entry_order_ids, pending_csv_recoveries,
monitoring_error, `risk` (rm.export_state — daily_trade_counts,
last_reset_date — risk_manager.py:49-54), срез open_orders.
Параметры конфигурации в state.json НЕ сохраняются — при рестарте они
читаются из config.py заново; «воспроизводимость сделки с теми же
настройками» сейчас обеспечивается только по BUILD_VERSION/PROFILE в
событиях (ВЫВОД; требование ТЗ §3 выполняется частично).

## 7. Сводная таблица «параметр → потребители» (полный список config.*)

| Параметр | Потребители (файл:строка) |
|---|---|
| TINKOFF_API_TOKEN | main.py:5653; safe_start.py:129; config.py:149 |
| TINKOFF_READONLY_TOKEN | screener.py:130; config.py:151 |
| TINKOFF_ACCOUNT_ID | tinkoff_client.py:217-218 |
| TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID / TELEGRAM_ALLOWED_USER_ID | main.py:946-947, 5634-5635; telegram_bot.py:24-44; config.py:153-159 |
| USE_SANDBOX | main.py:5653, 5659; safe_start.py:120, 129; tinkoff_client.py:182-184; config.py:162 |
| ENABLE_TELEGRAM | main.py:583, 942, 965, 5631 |
| TOP_VOLATILE_INSTRUMENTS_COUNT | screener.py:197 |
| VOLATILITY_PERIOD_DAYS | screener.py:153, 159 |
| VOLATILITY_REFRESH_HOURS | screener.py:54 |
| MIN_DAILY_TURNOVER_RUB | screener.py:180 |
| RISK_PER_TRADE | risk_manager.py:104 |
| STOP_LOSS_PERCENT, MIN_STOP_LOSS_PERCENT | risk_manager.py:124, 238 |
| TAKE_PROFIT_RATIO | risk_manager.py:244 |
| ATR_STOP_MULTIPLIER | risk_manager.py:228 |
| ATR_PERIOD_INTRADAY | risk_manager.py:215 |
| ATR_PERIOD | screener.py:171 |
| MAX_ATR_STOP_PERCENT | risk_manager.py:130-131, 241-242 |
| MAX_POSITION_SHARE_PER_INSTRUMENT | risk_manager.py:142 |
| MAX_TOTAL_EXPOSURE | risk_manager.py:198 |
| MAX_TRADES_PER_INSTRUMENT_PER_DAY | risk_manager.py:91 |
| COMMISSION_MODE | config.py:60; logger.py:187 |
| COMMISSION_PER_SIDE | risk_manager.py:125; execution.py:875; main.py:2470, 2950 |
| SLIPPAGE_PERCENT | risk_manager.py:125; execution.py:875 |
| BUILD_VERSION | logger.py:188; main.py:3011 |
| BE_TRAIL_ENABLED | main.py:5139; execution.py:923, 1003 |
| BE_TRIGGER_R | execution.py:935, 958 |
| TRAIL_ATR_PERIOD | main.py:1134 |
| TRAIL_ATR_MULTIPLIER | execution.py:946, 964 |
| POSITION_QUANTITY_IS_LOTS | **не используется** (только комментарий risk_manager.py:12) |
| MA_FAST_PERIOD | strategy.py:263, 294 |
| MA_SLOW_PERIOD | strategy.py:258, 268, 294, 303 |
| TREND_FILTER_MA_PERIOD | strategy.py:231, 236 |
| BB_PERIOD | strategy.py:317, 322 |
| BB_STD_DEV | strategy.py:323 |
| RSI_PERIOD | strategy.py:317, 328 |
| RSI_OVERBOUGHT | strategy.py:371, 382 |
| RSI_OVERSOLD | strategy.py:355, 366 |
| MIN_CANDLES_FOR_SIGNAL | strategy.py:32 (кэш), 197; main.py:3299, 5257 |
| ADX_PERIOD | strategy.py:58, 65, 71 |
| ADX_TREND_THRESHOLD | strategy.py:93 |
| ADX_HYSTERESIS_CANDLES | strategy.py:84, 87, 147 |
| PROFILE | logger.py:186; config.py:78-119 |
| VOLUME_SPIKE_FACTOR | strategy.py:458, 464 |
| VOLUME_CONFIRMATION_WINDOW | strategy.py:440 |
| API_RETRY_COUNT | tinkoff_client.py:195, 205 |
| API_RETRY_DELAY_SECONDS | tinkoff_client.py:206; screener.py:83, 90, 106 |
| API_REQUEST_TIMEOUT_SECONDS | tinkoff_client.py:342, 451, 640 |
| API_CALL_DELAY_SECONDS | tinkoff_client.py:242, 260; screener.py:149 |
| TRADING_CYCLE_SECONDS | main.py:5729, 645, 1953 |
| CANDLES_LOOKBACK_DAYS | main.py:3296 |
| RECONCILE_CONFIRM_MIN_AGE_SECONDS | main.py:1952 (getattr + fallback) |
| STARTING_BALANCE | **не используется** (только safe_start.py:48, список имён) |

**ВЫВОД:** каждый параметр имеет ровно один-два потребителя; дублирующего
чтения одного и того же параметра из разных файлов с разной семантикой нет
(исключение — параметры-дубликаты и хардкоды, см.
HARDCODED_LOGIC_AND_DEPENDENCIES.md).
