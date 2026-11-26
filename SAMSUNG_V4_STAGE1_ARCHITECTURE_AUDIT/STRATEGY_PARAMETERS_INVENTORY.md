# STRATEGY_PARAMETERS_INVENTORY.md

## Полный перечень параметров Samsung V4 (commit `main@884cefd`)

**Мандаты:**

```
STRATEGY LOGIC: UNCHANGED
RESEARCH ONLY
NO THRESHOLD IS OPTIMIZED
NO FILTER IS INSTALLED
NO LIVE ORDERS
```

Настоящий документ — ФАКТ-ориентированная инвентаризация. Ничего не
оптимизировалось, не исправлялось и не предлагалось изменять в коде; значения
приведены такими, какими они существуют в коде на коммите `884cefd`.

---

## 1. Как параметры объявляются и загружаются (ФАКТ)

Существует ровно **три механизма** задания значений:

1. **Переменные окружения / `.env`** — читаются в `config.py` через
   `os.getenv(...)` при импорте модуля: `TINKOFF_API_TOKEN`,
   `TINKOFF_READONLY_TOKEN`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`,
   `TINKOFF_ACCOUNT_ID`, `TELEGRAM_ALLOWED_USER_ID`
   (`config.py:14-19`), `STARTING_BALANCE` (`config.py:144`).
   Загрузка `.env` — `python-dotenv`, `config.py:9-11`.
2. **Литеральные константы в `config.py`** — все числовые и строковые
   параметры стратегии/риска/движка (`config.py:22-53, 56-73, 121-131, 141`).
3. **PROFILE-переопределение** — ветвление `if PROFILE == "FORCE_TRADE": …`
   переприсваивает 9 значений после их базового объявления
   (`config.py:76-119`). Неизвестный профиль → `RuntimeError`
   (`config.py:118-119`).

**ФАКТ (ключевой для архитектуры):** кроме 7 env-переменных, **ни один
параметр не может быть изменён без правки Python-кода** — все они —
константы модуля `config.py`, который и сам является `.py`-файлом.
Внешних файлов конфигурации (YAML/JSON/TOML), CLI-аргументов или
переключателей через переменные окружения для торговых параметров не
существует (grep по `candidate/*.py`: `os.getenv` встречается только в
`config.py`; `argparse`/`sys.argv` — только `--no-api` в `safe_start.py:236`).

**ФАКТ:** `config.validate()` (`config.py:147-163`) проверяет ТОЛЬКО
наличие токенов/Telegram-переменных и запрет `USE_SANDBOX=False`.
Типы, диапазоны, знаки и взаимные зависимости числовых параметров НЕ
проверяются.

**ФАКТ (противоречие комментарий/код, §7 ТЗ):** комментарий
`config.py:4` утверждает «ИЗМЕНЕНО: PROFILE = "CONSERVATIVE"», фактически
`config.py:76` — `PROFILE = "FORCE_TRADE"`. Зафиксировано, НЕ исправлялось.
`docs/CONFIGURATION_TEMPLATE.md:54` подтверждает: `PROFILE = "FORCE_TRADE"`
— исходное значение Samsung.

**ВЫВОД:** фактические значения индикаторов = FORCE_TRADE-переопределения,
а не базовые значения из раздела «Стратегия (НЕ меняется)».

## 2. Фактическая активная конфигурация (FORCE_TRADE, ФАКТ)

| Параметр | База (config.py) | Фактически (PROFILE=FORCE_TRADE) |
|---|---|---|
| MA_FAST_PERIOD | 9 (стр.64) | **2** (стр.82) |
| MA_SLOW_PERIOD | 21 (стр.65) | **3** (стр.83) |
| TREND_FILTER_MA_PERIOD | 100 (стр.66) | **5** (стр.84) |
| RSI_OVERSOLD | 30 (стр.71) | **50** (стр.85) |
| RSI_OVERBOUGHT | 70 (стр.70) | **50** (стр.86) |
| MIN_CANDLES_FOR_SIGNAL | 60 (стр.72) | **10** (стр.87) |
| ADX_TREND_THRESHOLD | — (только в профилях) | **5** (стр.79) |
| ADX_HYSTERESIS_CANDLES | — | **1** (стр.80) |
| VOLUME_SPIKE_FACTOR | — | **0.0** (стр.81) |

Без переопределения остаются: `BB_PERIOD=20`, `BB_STD_DEV=2`, `RSI_PERIOD=14`,
`ADX_PERIOD=14`, `VOLUME_CONFIRMATION_WINDOW=20`.

## 3. Классификация по назначению (категории ТЗ §2.3)

- **A. Параметры стратегии** (сигналы, индикаторы, фильтры, подтверждения):
  MA_FAST/MA_SLOW/TREND_FILTER_MA, BB_PERIOD/BB_STD_DEV, RSI_PERIOD/
  RSI_OVERSOLD/RSI_OVERBOUGHT, ADX_PERIOD/ADX_TREND_THRESHOLD/
  ADX_HYSTERESIS_CANDLES, VOLUME_SPIKE_FACTOR/VOLUME_CONFIRMATION_WINDOW,
  MIN_CANDLES_FOR_SIGNAL, PROFILE.
- **B. Общий риск-менеджмент**: RISK_PER_TRADE, STOP_LOSS_PERCENT,
  MIN_STOP_LOSS_PERCENT, TAKE_PROFIT_RATIO, ATR_STOP_MULTIPLIER,
  ATR_PERIOD_INTRADAY, MAX_ATR_STOP_PERCENT,
  MAX_POSITION_SHARE_PER_INSTRUMENT, MAX_TOTAL_EXPOSURE,
  MAX_TRADES_PER_INSTRUMENT_PER_DAY.
  *ВЫВОД:* SL/TP-формула технически расположена в `RiskManager.calculate_sl_tp`
  (`risk_manager.py:233-259`) — то есть параметрически категория B, но по
  смыслу («расчёт SL/TP — только штатной стратегией», `main.py:4068-4088`)
  относится к стратегии; это разделение учтено в
  STRATEGY_SWITCH_ARCHITECTURE.md.
- **C. Торговый движок**: TRADING_CYCLE_SECONDS, CANDLES_LOOKBACK_DAYS,
  RECONCILE_CONFIRM_MIN_AGE_SECONDS, BUILD_VERSION, BE_TRAIL_ENABLED
  (включая BE_TRIGGER_R/TRAIL_ATR_PERIOD/TRAIL_ATR_MULTIPLIER),
  POSITION_QUANTITY_IS_LOTS (не используется), хардкод-константы движка
  (ORDER_POLL_MAX_AGE_CYCLES — `main.py:605`).
- **D. Брокерское подключение**: USE_SANDBOX, TINKOFF_API_TOKEN,
  TINKOFF_READONLY_TOKEN, TINKOFF_ACCOUNT_ID, API_RETRY_COUNT,
  API_RETRY_DELAY_SECONDS, API_REQUEST_TIMEOUT_SECONDS,
  API_CALL_DELAY_SECONDS.
- **E. Скринер/торговая вселенная**: TOP_VOLATILE_INSTRUMENTS_COUNT,
  VOLATILITY_PERIOD_DAYS, VOLATILITY_REFRESH_HOURS, MIN_DAILY_TURNOVER_RUB.
- **Прочее**: ENABLE_TELEGRAM, Telegram-токены/ID, COMMISSION_MODE,
  COMMISSION_PER_SIDE, SLIPPAGE_PERCENT (используются и риск-модулем B,
  и безубытком C — cross-cutting), STARTING_BALANCE (не используется).

## 4. Полная таблица параметров

Обозначения: «объявл.» — файл:строка объявления; «использование» — все места
чтения; «диапазон» — только то, что определено в коде; если диапазон не
определён — прямо указано «в коде не определён». «Без правки .py» — можно ли
изменить значение, не редактируя Python-файлы (только env).

### 4.1. Режим и подключение (категория D)

| # | Параметр | Значение | Тип/ед. | Объявление | Использование | Диапазон/валидация | Без правки .py | При недопустимом значении |
|---|---|---|---|---|---|---|---|---|
| D1 | TINKOFF_API_TOKEN | из env | str | config.py:14 | main.py:5653; safe_start.py:129; validate config.py:149-150 | непустой — validate | **да** (env) | validate() → RuntimeError, старт прерван (fail-closed) |
| D2 | TINKOFF_READONLY_TOKEN | из env | str | config.py:15 | screener.py:130; validate:151-152 | непустой — validate | да | RuntimeError, старт прерван |
| D3 | TINKOFF_ACCOUNT_ID | из env, пусто | str | config.py:18 | tinkoff_client.py:217-218 (`_ensure_account`) | **валидации нет** | да | **ФАКТ:** пусто/неверно → молча берётся первый аккаунт (`accounts.accounts[0].id`, tinkoff_client.py:220-222) или создаётся новый sandbox-аккаунт (стр.224-225); никакого предупреждения |
| D4 | USE_SANDBOX | True | bool | config.py:22 | main.py:5653,5659; safe_start.py:120,129; tinkoff_client.py:182-184; validate:162-163 | False запрещён (3 независимых уровня) | нет | False → RuntimeError в validate() И SandboxRequiredError в клиенте; старт прерван |
| D5 | API_RETRY_COUNT | 3 | int, шт. попыток | config.py:124 | tinkoff_client.py:195,205 | в коде не определён | нет | 0 → подключение без ретраев; 1 → одна попытка; отрицательное → `range()` пуст → «Не удалось подключиться» без единой попытки |
| D6 | API_RETRY_DELAY_SECONDS | 5 | int, сек | config.py:125 | tinkoff_client.py:206; screener.py:83,90,106 | в коде не определён | нет | ≤0 → мгновенные ретраи (нагрузка на API) |
| D7 | API_REQUEST_TIMEOUT_SECONDS | 10 | int, сек | config.py:126 | tinkoff_client.py:342 (get_positions), 451 (get_sandbox_orders), 640 (order_state) — через `asyncio.wait_for` | в коде не определён | нет | ≤0 → wait_for мгновенно бросает TimeoutError → fail-closed: `get_positions()=None`, учёт не меняется |
| D8 | API_CALL_DELAY_SECONDS | 0.03 | float, сек | config.py:127 | tinkoff_client.py:242,260; screener.py:149 | в коде не определён | нет | ≤0 → без пауз между запросами (риск rate-limit) |

### 4.2. Telegram (категория D/прочее)

| # | Параметр | Значение | Тип/ед. | Объявление | Использование | Диапазон/валидация | Без правки .py | При недопустимом значении |
|---|---|---|---|---|---|---|---|---|
| T1 | ENABLE_TELEGRAM | True | bool | config.py:23 | main.py:583 (import TelegramBot), 942, 965, 5631 | в коде не определён | нет | False → TelegramBot=None; робот работает без уведомлений (ФАКТ main.py:585-586, 964-966) |
| T2 | TELEGRAM_BOT_TOKEN | из env | str | config.py:16 | main.py:946, 5634; validate:153-155 | обязателен при ENABLE_TELEGRAM=True | да | RuntimeError при старте |
| T3 | TELEGRAM_CHAT_ID | из env | str | config.py:17 | main.py:946, 5634; telegram_bot.py:42; validate | обязателен при ENABLE_TELEGRAM | да | RuntimeError при старте |
| T4 | TELEGRAM_ALLOWED_USER_ID | из env | str→int | config.py:19 | main.py:947, 5635; telegram_bot.py:44-48 (`int()` в try) | обязателен при ENABLE_TELEGRAM; парсинг int с fallback None | да | не-int → allowed_user_id=None → **ФАКТ telegram_bot.py:47-48, 74: все команды будут отклонены** («Нет прав») |
| T5 | (хардкод) таймауты Telegram | pool=8, connect=30, read=60, write=60, pool=30 с | int/float, сек | telegram_bot.py:27-34 | там же | — | нет | — |
| T6 | (хардкод) watchdog | 60 с интервал, 15 с timeout, 3 неудачи | — | telegram_bot.py:120-127; main.py:969-984 | там же | — | нет | — |

### 4.3. Скринер и торговая вселенная (категория E)

| # | Параметр | Значение | Тип/ед. | Объявление | Использование | Диапазон/валидация | Без правки .py | При недопустимом значении |
|---|---|---|---|---|---|---|---|---|
| E1 | TOP_VOLATILE_INSTRUMENTS_COUNT | 10 | int, шт. | config.py:26 | screener.py:197 (`volatility_data[:N]`) | в коде не определён | нет | ≤0: **ФАКТ** — при 0 → пусто → `_do_scan` вернёт None → входы заблокированы (main.py:5705-5712); при **отрицательном** — срез `[:-N]` вернёт список БЕЗ N самых волатильных (семантика Python-среза) — поведение меняется незаметно |
| E2 | VOLATILITY_PERIOD_DAYS | 30 | int, дней | config.py:27 | screener.py:153 (от`from_`), 159 (мин. свечей = DAYS-1) | в коде не определён | нет | <2 → фильтр «len(candles) < DAYS-1» становится бессмысленным; большие значения → больше пропусков инструментов |
| E3 | VOLATILITY_REFRESH_HOURS | 24 | int, часов | config.py:28 | screener.py:54 (`_cache_valid`) | в коде не определён | нет | **ВЫВОД:** скринер вызывается ОДИН раз при старте (main.py:5704, вне while-цикла 5723-5729), поэтому кэш/рефреш внутри процесса практически не срабатывают; изменение вселенной требует перезапуска робота |
| E4 | MIN_DAILY_TURNOVER_RUB | 10 000 000 | int, RUB/день | config.py:29 | screener.py:180 | в коде не определён | нет | ≤0 → фильтр оборота пропускает всё |
| E5 | (хардкод) REAL_EXCHANGE_MOEX | 1 | — | screener.py:36 | screener.py:136 | — | нет | — |
| E6 | (хардкод) валюта «rub» | — | — | screener.py:137 | там же | — | нет | — |
| E7 | (хардкод) окно оборота | tail(20) дней | — | screener.py:179 | там же | — | нет | см. HARDCODED_LOGIC_AND_DEPENDENCIES.md |

### 4.4. Стратегия: сигналы, режим рынка, фильтры (категория A)

| # | Параметр | Значение (факт.) | Тип/ед. | Объявление | Использование | Диапазон/валидация | Без правки .py | При недопустимом значении |
|---|---|---|---|---|---|---|---|---|
| A1 | PROFILE | "FORCE_TRADE" | str | config.py:76 | switch config.py:78-119; logger.py:186 (мета каждого события) | только 4 значения; иначе RuntimeError | нет (правка строки в config.py) | неизвестное → RuntimeError при импорте config — fail-closed (config.py:118-119) |
| A2 | MA_FAST_PERIOD | 2 (было 9) | int, свечей 5-мин | config.py:64, 82 | strategy.py:263 (ta.sma), 294 | в коде не определён | нет | 0/отриц. → ta.sma(length≤0) → исключение → перехват strategy.py:308-310 → «Ошибка MA» → HOLD |
| A3 | MA_SLOW_PERIOD | 3 (было 21) | int, свечей | config.py:65, 83 | strategy.py:258 (проверка len≥SLOW+2), 268, 294, 303 | в коде не определён | нет | см. A2; также «Мало данных для MA» при len<SLOW+2 |
| A4 | TREND_FILTER_MA_PERIOD | 5 (было 100) | int, свечей | config.py:66, 84 | strategy.py:231-236 (`_trend_filter_ok`) | в коде не определён | нет | больше MIN_CANDLES_FOR_SIGNAL → **ФАКТ** все сигналы отклоняются «фильтр MA100 не пройден» (strategy.py:245-249, 288-300) — скрытая взаимозависимость |
| A5 | BB_PERIOD | 20 | int, свечей | config.py:67 | strategy.py:317 (len≥BB+RSI), 322 | в коде не определён | нет | ta.bbands(length≤0) → исключение → «Ошибка BB+RSI» (strategy.py:387-389) |
| A6 | BB_STD_DEV | 2 | float, σ | config.py:68 | strategy.py:323 | в коде не определён | нет | ≤0 → полосы вырождаются; ta-библиотека может вернуть NaN → HOLD |
| A7 | RSI_PERIOD | 14 | int, свечей | config.py:69 | strategy.py:317, 328 | в коде не определён | нет | ≤0 → исключение → HOLD |
| A8 | RSI_OVERSOLD | 50 (было 30) | float, пункты RSI 0-100 | config.py:71, 85 | strategy.py:355, 366 | в коде не определён | нет | ≥RSI_OVERBOUGHT → противоречивая логика; при 50/50 (FORCE_TRADE) — нейтральная точка |
| A9 | RSI_OVERBOUGHT | 50 (было 70) | float | config.py:70, 86 | strategy.py:371, 382 | в коде не определён | нет | см. A8 |
| A10 | ADX_PERIOD | 14 | int, свечей | config.py:73 | strategy.py:58 (len≥ADX+1), 65 (ta.adx), 71 (колонка f"ADX_{N}") | в коде не определён | нет | ≤0 → ta.adx исключение → перехват → «ADX error» → UNKNOWN → HOLD (strategy.py:172-174) |
| A11 | ADX_TREND_THRESHOLD | 5 | float, пункты ADX | config.py:79 | strategy.py:93 | в коде не определён | нет | 0 → всегда TREND (любой ADX>0); очень большое → всегда RANGE |
| A12 | ADX_HYSTERESIS_CANDLES | 1 | int, свечей | config.py:80 | strategy.py:84, 87, 147-158 | в коде не определён | нет | 0 → `recent` пуст → len(recent)<0 ложь... фактически `tail(0)`→пусто → `len(recent) < 0` = False → `all()` по пустому = True → TREND всегда; механизм гистерезиса деградирует |
| A13 | VOLUME_SPIKE_FACTOR | 0.0 | float, ×средний объём | config.py:81 | strategy.py:458, 464 | в коде не определён | нет | **ФАКТ:** 0.0 → условие `last >= avg*0.0` истинно при любом объёме (avg>0 проверяется стр.455-456) → подтверждение объёмом ФАКТИЧЕСКИ ОТКЛЮЧЕНО в FORCE_TRADE и SANDBOX_TEST |
| A14 | VOLUME_CONFIRMATION_WINDOW | 20 | int, свечей | config.py:121 | strategy.py:440-447 (окно среднего объёма) | в коде не определён | нет | <3 → «мало свечей для объёма» → сигналы отклоняются (strategy.py:444-446); > длины df → срезается до len(df) (стр.439-442) |
| A15 | MIN_CANDLES_FOR_SIGNAL | 10 (было 60) | int, свечей | config.py:72, 87 | **стратегия.py:32 (кэшируется в self.min_candles_required при создании StrategyManager)**; main.py:3299 (_build_candles_df), 5257 (лог) | в коде не определён | нет | ≤0 → сигналы считаются на любом df; слишком большое → main.py:3299 отбрасывает все инструменты («мало свечей») |
| A16 | (хардкод) минимум окна объёма | 3 свечей | — | strategy.py:444-446 | там же | — | нет | — |
| A17 | (хардкод) требование len≥SLOW+2 | — | — | strategy.py:258 | там же | — | нет | — |
| A18 | (хардкод) требование len≥BB+RSI | — | — | strategy.py:317 | там же | — | нет | — |
| A19 | (хардкод) drop_incomplete=True при входе | bool | main.py:5260 | там же | — | нет | правило удаления незакрытой свечи — strategy.py:412-425 (только явный False удаляет) |

### 4.5. Риск-менеджмент и SL/TP (категория B)

| # | Параметр | Значение | Тип/ед. | Объявление | Использование | Диапазон/валидация | Без правки .py | При недопустимом значении |
|---|---|---|---|---|---|---|---|---|
| B1 | RISK_PER_TRADE | 0.01 | float, доля баланса | config.py:32 | risk_manager.py:104 (`risk_amount = balance * RISK`) | в коде не определён | нет | ≤0 → risk_amount≤0 → return 0 → **молча ни одной сделки**; >1 → размер позиции не ограничен сверху по риску |
| B2 | STOP_LOSS_PERCENT | 0.012 | float, доля цены | config.py:34 | risk_manager.py:124, 238 (`max(STOP_LOSS, MIN_STOP_LOSS)`) | в коде не определён | нет | меньше MIN → вытесняется min-порогом; 0 → базовый стоп 0 (останется ATR-компонента) |
| B3 | MIN_STOP_LOSS_PERCENT | 0.005 | float | config.py:33 | risk_manager.py:124, 238 | в коде не определён | нет | 0 → floor исчезает; > STOP_LOSS_PERCENT → min-порог становится фактическим SL |
| B4 | TAKE_PROFIT_RATIO | 2.0 | float, ×дистанция SL | config.py:35 | risk_manager.py:244 | в коде не определён | нет | ≤0 → tp≤0 → calculate_sl_tp вернёт (None,None) → **позиция уходит в RECOVERY («no_sl_tp»)** — main.py:4089-4121, 4125-4136 |
| B5 | ATR_STOP_MULTIPLIER | 1.5 | float, ×ATR | config.py:36 | risk_manager.py:228 | в коде не определён | нет | ≤0 → atr_risk≤0 → ветка `if atr_risk is not None` сработает, но max(base, atr_risk) не изменит стоп (atr≤base) |
| B6 | ATR_PERIOD_INTRADAY | 20 | int, свечей 5-мин | config.py:37 | risk_manager.py:215-222 (`_calculate_volatility_risk`) | в коде не определён | нет | > длины df → `len(candles) < period` → None → риск считается только по процентному стопу; ≤0 → ta.atr исключение → перехват → None (risk_manager.py:229-231) |
| B7 | ATR_PERIOD | 14 | int, **дневных** свечей | config.py:38 | screener.py:171 (ATR для ранжирования волатильности) | в коде не определён | нет | ≤0 → исключение → инструмент пропускается (screener.py:173-174); **НЕ путать с B6 и C5** — три разных ATR-периода |
| B8 | MAX_ATR_STOP_PERCENT | 0.03 | float, доля цены | config.py:39 | risk_manager.py:130-131 (кап риска в размере позиции), 241-242 (кап в SL) | в коде не определён | нет | 0 → atr-компонента стопа обнуляется (min(atr, 0)); очень большое → кап не действует |
| B9 | MAX_POSITION_SHARE_PER_INSTRUMENT | 0.2 | float, доля баланса | config.py:40 | risk_manager.py:142-145 | в коде не определён | нет | >1 → позиция может превысить баланс (верхнего капа нет); ≤0 → position_size_by_capital≤0 → **молча ни одной сделки** |
| B10 | MAX_TOTAL_EXPOSURE | 0.6 | float, доля баланса | config.py:41 | risk_manager.py:198-201 | в коде не определён | нет | ≤0 → allowed_value=max(0,…) → 0 лотов; >1 → неограниченная экспозиция |
| B11 | MAX_TRADES_PER_INSTRUMENT_PER_DAY | 5 | int, сделок/день/FIGI | config.py:42 | risk_manager.py:91 (`calculate_position_size` — ранний return 0) | в коде не определён | нет | ≤0 → ни одной сделки по любому инструменту (молча); счётчики персистентны (state.json `risk` — main.py:1160, 1231-1233) |
| B12 | COMMISSION_MODE | "TRADER" | str | config.py:59 | config.py:60 (выбор ставки); logger.py:187 (мета событий) | в коде не определён | нет | **ФАКТ:** любое значение ≠ "INVESTOR" даёт 0.0005 — опечатка меняет ставку комиссии молча |
| B13 | COMMISSION_PER_SIDE | 0.0005 (TRADER) | float, доля оборота | config.py:60 | risk_manager.py:125 (friction), execution.py:875 (буфер безубытка), main.py:2470, 2950 (модельная комиссия CSV) | в коде не определён | нет | влияет на размер позиции, P&L и безубыток; отрицательное → friction уменьшается, модельная комиссия отрицательная |
| B14 | SLIPPAGE_PERCENT | 0.0002 | float, доля цены | config.py:61 | risk_manager.py:125; execution.py:875 | в коде не определён | нет | влияет на friction и буфер безубытка |

### 4.6. Безубыток/трейлинг (категория C; С1, выключено)

| # | Параметр | Значение | Тип/ед. | Объявление | Использование | Диапазон/валидация | Без правки .py | При недопустимом значении |
|---|---|---|---|---|---|---|---|---|
| C1 | BE_TRAIL_ENABLED | False | bool | config.py:50 | main.py:5139 (сбор экстремумов/ATR); execution.py:923 (_update_sl), 1003 (check_all) | в коде не определён | нет | **ФАКТ:** проверка `if getattr(config, "BE_TRAIL_ENABLED", False)` — истинностная: непустая строка "False" или 1 ВКЛЮЧАТ механику; при True — доп. запрос свечей на каждую OPEN-позицию каждый цикл (config.py:45-48) |
| C2 | BE_TRIGGER_R | 1.0 | float, ×R | config.py:51 | execution.py:935, 958 | в коде не определён | нет | активен только при C1=True; ≤0 → перенос в безубыток при первом же экстремуме |
| C3 | TRAIL_ATR_PERIOD | 14 | int, свечей 5-мин | config.py:52 | main.py:1134 (`_atr_from_df`) | в коде не определён | нет | активен только при C1=True; > доступных свечей → ATR=None → трейлинг не двигается (main.py:1106-1109) |
| C4 | TRAIL_ATR_MULTIPLIER | 3.0 | float, ×ATR | config.py:53 | execution.py:946, 964 | в коде не определён | нет | активен только при C1=True; ≤0 → SL прижмётся к mfe сразу |
| C5 | BUILD_VERSION | "v2.3.2-stage1" | str | config.py:49 | logger.py:188 (каждое событие), main.py:3011 (CSV-колонка build_version), test_stage1_s1_telemetry.py:255 | — | нет | — |

### 4.7. Движок: цикл, данные, сверка (категория C)

| # | Параметр | Значение | Тип/ед. | Объявление | Использование | Диапазон/валидация | Без правки .py | При недопустимом значении |
|---|---|---|---|---|---|---|---|---|
| C6 | TRADING_CYCLE_SECONDS | 30 | int, сек | config.py:130 | main.py:5729 (сон цикла), 645 (`_age_in_cycles`), 1952-1953 (getattr-fallback для D10) | в коде не определён | нет | 0 → цикл без пауз (шквал API-запросов); большое → медленная реакция SL/TP и старение заявок в циклах удлиняется |
| C7 | CANDLES_LOOKBACK_DAYS | 2 | int, дней | config.py:131 | main.py:3296 (`get_historical_candles`, 5-мин свечи) | в коде не определён | нет | маленькое → `_build_candles_df` возвращает None (len<MIN_CANDLES_FOR_SIGNAL, main.py:3299) → **инструменты молча перестают торговаться**; большое — дольше загрузка |
| C8 | RECONCILE_CONFIRM_MIN_AGE_SECONDS | 30 (=TRADING_CYCLE_SECONDS) | int, сек | config.py:141 (присвоено от C6) | main.py:1952-1953 (`getattr(config, ..., config.TRADING_CYCLE_SECONDS)`) | в коде не определён | нет | 0 → двойное подтверждение внешнего закрытия (В3) теряет смысл: два снимка одного цикла засчитываются; negative → то же |
| C9 | ORDER_POLL_MAX_AGE_CYCLES | 10 (≈5 мин при 30 с) | int, циклов | **main.py:605 (хардкод, вне config)** | main.py:4356, 4465 (отмена остатка заявки по возрасту) | в коде не определён | нет | 0 → остаток отменяется немедленно даже у молодой заявки |
| C10 | (хардкод) интервал свечей | CANDLE_INTERVAL_5_MIN | enum | main.py:3297; screener.py:154 — DAY | — | — | нет | таймфрейм сигналов 5-мин захардкожен; конфигурируемого таймфрейма НЕ существует |
| C11 | (хардкод) имена runtime-файлов | trading.flag, state.json, state.json.tmp, order_ledger.jsonl | str | main.py:596-601; logger.py:98-99 (research_events.jsonl, research_trades.csv); safe_start.py:42-43 (дублирует имена) | — | — | нет | — |
| C12 | POSITION_QUANTITY_IS_LOTS | True | bool | config.py:56 | **НЕ ИСПОЛЬЗУЕТСЯ** (grep: только комментарий risk_manager.py:12 «удалён») | — | нет | — |

### 4.8. Неиспользуемые и «мертвые» объявления (ФАКТ)

| # | Объявление | Статус |
|---|---|---|
| X1 | `STARTING_BALANCE = os.getenv("STARTING_BALANCE")` — config.py:144 | Читается, но нигде в логике не используется (grep: только список имён env в safe_start.py:48 для диагностики). Тип str — число не парсится. |
| X2 | `POSITION_QUANTITY_IS_LOTS = True` — config.py:56 | Не используется ни одним модулем; в risk_manager.py:12 комментарий фиксирует: «POSITION_QUANTITY_IS_LOTS удалён (get_positions() уже возвращает лоты)». Объявление осталось. |
| X3 | `TINKOFF_ACCOUNT_ID` (config.py:18) | Используется (tinkoff_client.py:217), но **не проверяется** в `config.validate()` — единственная env-переменная подключения, отсутствие которой обрабатывается «молча» (см. D3). |

## 5. Параметры/состояния, изменяющиеся ВО ВРЕМЯ исполнения (ФАКТ, §2.2 ТЗ)

| Сущность | Кто меняет | Где |
|---|---|---|
| `pos.sl_price` | безубыток/трейлинг `_update_sl` (только при BE_TRAIL_ENABLED=True) | execution.py:913-966; в текущей конфигурации (False) SL/TP фиксированы с момента входа |
| `rm.daily_trade_counts` | `record_trade` после каждой регистрации BUY | risk_manager.py:261-263; вызов main.py:4138; сброс по дате risk_manager.py:45-47; персистентность main.py:1160/1231-1233 |
| `client.uncertain_state` | практически каждый fail-closed путь | например main.py:1650, 2046, 2185, 2321-2322, 3498, 5337, 5517, 5570; сброс только при полном успехе reconcile main.py:2210 |
| `monitor.monitoring_error` | пустые цены / check_all | main.py:5131-5132; execution.py:987-996 |
| `state_save_failed` | `_save_state_checked` | main.py:1174-1189 |
| `reconcile_done`, `_last_reconcile_confirmed_utc` | reconcile | main.py:2041-2216 |
| `top_instruments` | **один раз при старте** (main.py:5714); во время цикла только читается | скринер вызывается вне цикла |
| `instrument_info_cache` | tinkoff_client.py:271-297 | растёт по FIGI |
| `_external_close_candidates`, `_strategy_event_keys`, `_promote_throttle` | runtime-словари main.py:838-844; **намеренно НЕ персистятся** (комментарий main.py:841-843) | после рестарта двойное подтверждение В3 начинается заново |

## 6. Взаимные зависимости параметров (ФАКТ/ВЫВОД)

1. **COMMISSION_MODE → COMMISSION_PER_SIDE** — config.py:60 (вычисление при
   импорте; позже изменить MODE отдельно нельзя — ставка уже зафиксирована).
2. **TRADING_CYCLE_SECONDS → RECONCILE_CONFIRM_MIN_AGE_SECONDS** —
   config.py:141 (присвоение значения при импорте) + fallback
   main.py:1952-1953; также цикл входит в знаменатель `_age_in_cycles`
   (main.py:645) и в эффективное время жизни заявки
   `ORDER_POLL_MAX_AGE_CYCLES × TRADING_CYCLE_SECONDS` (main.py:605).
3. **MIN_CANDLES_FOR_SIGNAL ≥ max(MA_SLOW_PERIOD+2, BB_PERIOD+RSI_PERIOD,
   ADX_PERIOD+1)** — иначе сигналы деградируют: проверка len в
   strategy.py:197, 258, 317, 58.
4. **MIN_CANDLES_FOR_SIGNAL vs TREND_FILTER_MA_PERIOD** —
   **ФАКТ-ПРОТИВОРЕЧИЕ в профилях TECH_CHECK и CONSERVATIVE:**
   MIN_CANDLES_FOR_SIGNAL=60 (config.py:107, 117) < TREND_FILTER_MA_PERIOD=100
   (config.py:104, 114). `_trend_filter_ok` требует len≥100
   (strategy.py:231-232) → при 60–99 свечах ЛЮБОЙ BUY/SELL отклоняется с
   причиной «фильтр MA100 не пройден» (strategy.py:288-300, 357-378).
   В этих профилях торговые сигналы фактически невозможны на историческом
   окне из CANDLES_LOOKBACK_DAYS=2 (~210 5-мин свечей не хватает только если
   данные короче 100 свечей). Зафиксировано, НЕ исправлялось.
5. **BE_TRAIL_ENABLED — гейт для BE_TRIGGER_R, TRAIL_ATR_MULTIPLIER,
   TRAIL_ATR_PERIOD** (config.py:45-53; execution.py:923-966;
   main.py:5139→1134).
6. **MAX_ATR_STOP_PERCENT — общий кап** для риск-модели размера позиции
   (risk_manager.py:130-131) и для SL (risk_manager.py:241-242).
7. **STOP_LOSS_PERCENT и MIN_STOP_LOSS_PERCENT** — фактический базовый стоп =
   `max(STOP_LOSS_PERCENT, MIN_STOP_LOSS_PERCENT)` (risk_manager.py:124, 238).
8. **VOLUME_SPIKE_FACTOR=0.0 обесценивает VOLUME_CONFIRMATION_WINDOW** —
   окно считается (strategy.py:439-449), но порог всегда истин (стр.458).
9. **CANDLES_LOOKBACK_DAYS → MIN_CANDLES_FOR_SIGNAL** — достаточность данных;
   проверка единственная — main.py:3299; несоответствие = молчаливый
   пропуск всех инструментов (main.py:5256-5258).
10. **PROFILE переписывает 9 значений A-категории** — config.py:78-117; любые
    будущие правки базовых значений (стр.64-72) в FORCE_TRADE не вступят в
    силу, пока не изменены и в ветке профиля. **ВЫВОД:** фактический источник
    значений — ветка профиля, а не «базовый» раздел.

## 7. Сводное суждение (ВЫВОД)

- Все параметры, влияющие на сигналы/входы/выходы/риск/вселенную/цикл,
  живут в одном модуле `config.py` без разделения по категориям A–E и без
  схем валидации (кроме PROFILE и env-обязательности).
- Изменение любого параметра = правка Python-кода → нет воспроизводимой
  фиксации конфигурации запуска (только `BUILD_VERSION` и `PROFILE`
  пишутся в каждое событие — logger.py:186-188).
- Скрытые зависимости (п.6) не проверяются ни на старте, ни при изменении —
  недопустимое сочетание значений не детектируется (пример: п.6.4).
- Полная карта прохождения каждого параметра до участка торговой логики —
  PARAMETER_USAGE_MAP.md; жёстко зашитые значения, не попавшие в config.py,
  — HARDCODED_LOGIC_AND_DEPENDENCIES.md.
