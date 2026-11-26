# STAGE1_1_VERIFICATION_MATRIX.md

## Матрица верификации Stage 1.1

**Мандаты:**

```
STRATEGY LOGIC: UNCHANGED
RESEARCH ONLY
NO THRESHOLD IS OPTIMIZED
NO FILTER IS INSTALLED
NO LIVE ORDERS
```

```
STAGE 1.1 — DOCUMENTATION ONLY
SOURCE CODE UNCHANGED
```

Статусы: **CONFIRMED** (подтверждено исходным кодом/документом),
**PARTIALLY CONFIRMED** (подтверждено частично/с уточнением),
**NOT CONFIRMED** (не подтвердилось), **UNKNOWN** (недостаточно данных).
Все ссылки `файл:строка` действительны для commit `884cefd…` (код) и
`c409221…` (документы Stage 1); код в обоих commit идентичен
(`git diff --name-only` — ровно 9 новых .md-файлов аудита).

| ID | Проверяемый вопрос | Результат | Источник | Статус |
|---|---|---|---|---|
| V-01 | Один экземпляр `StrategyManager` создаётся на процесс | `sm = StrategyManager()` — единственный экземпляр | main.py:5663 | CONFIRMED |
| V-02 | Один и тот же экземпляр передаётся в каждый повторяющийся `trading_cycle` | `while True: await trading_cycle(client, rm, sm, …)` — `sm` не пересоздаётся | main.py:5723-5729 (вызов — 5725) | CONFIRMED |
| V-03 | Сигнал получается одним экземпляром для каждого инструмента в общем цикле обхода | `for inst in top_instruments:` → `sm.get_signal(df, …)` | main.py:5237, 5260 | CONFIRMED |
| V-04 | Изменяемое внутреннее состояние ADX regime/hysteresis уровня экземпляра | `_last_regime`, `_regime_streak`, `_last_regime_candidate`, `_last_regime_candle_time` (+ диагностика `last_adx_value`, `last_signal_candle_time`) | strategy.py:34-43 | CONFIRMED |
| V-05 | `get_market_regime()` мутирует состояние при каждом вызове | присваивания полей на всех ветках автомата | strategy.py:90, 104-107, 124-125, 130, 135-136, 141-145, 159-163 | CONFIRMED |
| V-06 | Состояние НЕ сбрасывается при переходе к другому FIGI | `get_signal()` сбрасывает только диагностику (`last_adx_value`, `last_signal_candle_time`); в цикле обхода сброса нет | strategy.py:188-190; main.py:5236-5310 | CONFIRMED |
| V-07 | «Та же свеча» распознаётся глобально по времени, без привязки к FIGI | `candle_time == self._last_regime_candle_time` → короткое замыкание, режим возвращается без оценки смены по данным текущего инструмента | strategy.py:100, 118-127 | CONFIRMED |
| V-08 | Первый инструмент после старта устанавливает общий режим немедленно; остальные наследуют | ветка `_last_regime == "UNKNOWN"` выполняется только для первого вызова | strategy.py:102-114 | CONFIRMED |
| V-09 | Режим определяет ветку сигнальной логики (следовательно, влияет на сигнал) | `TREND → _ma_crossover_signal`; `RANGE → _bb_rsi_signal` | strategy.py:202-208 | CONFIRMED |
| V-10 | Механизм влияния состояния одного FIGI на сигнал другого существует | совокупность V-04…V-09: общее состояние + глобальная метка свечи + выбор ветки логики | strategy.py:34-43, 100-170, 202-208; main.py:5663, 5725, 5237, 5260 | CONFIRMED (FACT уровня кода) |
| V-11 | Результат сигнала инструмента фактически зависит от порядка обработки и данных других инструментов | сценарии §1.3 addendum (инициализация; короткое замыкание «той же свечи»; сброс серии чужим кандидатом; «старая» свеча) | addendum §1.3 | CONFIRMED (INFERENCE из FACT) |
| V-12 | Фактическая частота влияния в эксплуатации | зависит от совпадения меток свечей/задержек данных у реальных инструментов; runtime-данных нет | — | UNKNOWN |
| V-13 | Runtime-состояние гистерезиса не персистится; после рестарта режим определяется заново | `_save_state` не содержит полей стратегии; ветка инициализации срабатывает после рестарта | main.py:1144-1171; strategy.py:102-114 | CONFIRMED |
| V-14 | Ссылки Stage 1 на строки для 4.1 точны | 5663, 5260, 34-43 — точно; диапазон «5714–5729» уточнён (цикл 5723-5729, вызов 5725) | Stage 1 docs; main.py; strategy.py | CONFIRMED (с уточнением диапазона) |
| V-15 | Формула sizing: `base_risk = last_price * max(STOP_LOSS_PERCENT, MIN_STOP_LOSS_PERCENT)` | литерально в коде | risk_manager.py:124 | CONFIRMED |
| V-16 | Формула sizing: `friction = last_price * (COMMISSION_PER_SIDE*2 + SLIPPAGE_PERCENT)` | литерально в коде | risk_manager.py:125 | CONFIRMED |
| V-17 | Без ATR: `per_share_risk = base_risk + friction` | литерально в коде | risk_manager.py:126 | CONFIRMED |
| V-18 | При наличии ATR: `per_share_risk = max(per_share_risk, atr_risk + friction)` (≡ `max(base_risk, atr_risk) + friction`) | литерально в коде; ATR капится `MAX_ATR_STOP_PERCENT` | risk_manager.py:128-132 | CONFIRMED |
| V-19 | SL/TP использует те же компоненты дистанции: база max(STOP_LOSS, MIN_STOP_LOSS), ATR-кап, `base = max(base, atr)` | та же `_calculate_volatility_risk` и те же константы | risk_manager.py:238-244 | CONFIRMED |
| V-20 | Sizing вычисляется от `last_price`, SL/TP — от фактической цены исполнения | вызовы sizing (`main.py:5278`, price от `get_last_prices`) и SL/TP (`main.py:4072` от `exec_price`; `main.py:4808` при промоции, свечи пересобираются `main.py:4803`) | main.py:5255, 5278, 4072, 4803, 4808 | CONFIRMED |
| V-21 | Запись Stage 1 `per_share_risk = max(base_risk, atr_risk + friction)` неточна (friction потерян на базовой ветке) | Stage 1 строка 149 != фактический код (контрпример: base=10, atr=8, fr=3 → 13 vs 11) | PARAMETER_USAGE_MAP.md:149 vs risk_manager.py:123-132 | CONFIRMED (ошибка Stage 1 подтверждена) |
| V-22 | Формула встречается в Stage 1 ровно один раз | grep `per_share` по каталогу аудита — только PARAMETER_USAGE_MAP.md:149-150 | каталог аудита Stage 1 | CONFIRMED |
| V-23 | Общие hard caps движка: лимит на инструмент/день, доля на инструмент, тотальная экспозиция | ранний return 0 по счётчику; кап по доле; кап экспозиции | risk_manager.py:91-92, 142-145, 198-201 | CONFIRMED |
| V-24 | SELL-сигнал при отсутствии позиции игнорируется («шорт запрещён»), не закрывает LONG | ветка SELL → `continue` + событие STRATEGY_SELL_IGNORED | main.py:5270-5276 | CONFIRMED |
| V-25 | Выходы из позиции: только SL/TP (причины TP/SL/BE/TRAIL), оператор/внешнее закрытие (В3) и штатное полное закрытие | `check_all` → to_close; `close_position` закрывает всё `pos.quantity` | execution.py:978-1022 (1011-1020); main.py:2224-2228, 2315; main.py:1932-2011 | CONFIRMED |
| V-26 | Безубыток/трейлинг существуют, но выключены по умолчанию | гейт `BE_TRAIL_ENABLED` (False) | config.py:50; execution.py:913-966, 1003 | CONFIRMED |
| V-27 | Частичное закрытие отсутствует в коде | grep `partial_close/PARTIAL_CLOSE/close_partial` — 0 совпадений | main.py, execution.py, strategy.py, risk_manager.py | CONFIRMED |
| V-28 | Интерфейс оценки выхода (`evaluate_exit` или аналог) отсутствует; стратегия не получает позицию | стратегия — только сигналы; `TrackedPosition` не имеет strategy_id/exit-контракта; поле источника — только `signal_reason: str` | strategy.py (весь); execution.py:241-306 | CONFIRMED |
| V-29 | Движок long-only на входах; SHORT поддержан только в учёте (зеркальные ветки/адопция), вход SHORT не генерируется | SELL без позиции игнорируется; комментарий «зеркало для SHORT… адопция SHORT-позиций» | main.py:5270-5276; execution.py:953-966, 1008-1010 | CONFIRMED |
| V-30 | `TrackedPosition` не хранит strategy_id | состав полей dataclass | execution.py:241-306 | CONFIRMED |
| V-31 | Профили — только переприсвоение 9 констант одной логики; отдельных стратегий не образуют | ветвление `if PROFILE == …` переопределяет константы; strategy.py без ветвления по профилю | config.py:76-119 | CONFIRMED |
| V-32 | Противоречие комментарий config.py:4 vs фактический PROFILE config.py:76 | комментарий «CONSERVATIVE», факт «FORCE_TRADE» | config.py:4, 76 | CONFIRMED |
| V-33 | Требование `legacy_samsung_v4` (FROZEN, regression only, не default, не рейтинг) реализовано в коде | реализации не существует — это PROPOSAL/требование к Stage 2 | addendum §4.2 | NOT CONFIRMED (ожидаемо: документирование, не реализация) |
| V-34 | Отдельная детерминированная event-driven модель backtest описана в Stage 1 | в Stage 1 только интерфейс T-4 и гранулярность T-5.3; модели событий нет | BACKTEST_COMPATIBILITY_REQUIREMENTS.md (Stage 1) | NOT CONFIRMED (пробел подтверждён; добавлено в исправленную версию) |
| V-35 | Набор допущений модели (комиссия, проскальзывание, spread, гэпы, частичное исполнение, ликвидность, market impact, tick/lot, сессии, корп. действия, задержки данных) определён в Stage 1 | не определён (упомянуты только комиссия/проскальзывание T-4.2) | BACKTEST_COMPATIBILITY_REQUIREMENTS.md (Stage 1) | NOT CONFIRMED (пробел подтверждён; добавлено A-1…A-13) |
| V-36 | Консервативное правило «SL первым внутри одной свечи» присутствует в Stage 1 | отсутствует; добавлено в исправленную версию (T-8) | BACKTEST_COMPATIBILITY_REQUIREMENTS.md (Stage 1); addendum §6.3.3 | NOT CONFIRMED (пробел подтверждён; добавлено) |
| V-37 | Утверждение Stage 1 T-2 «гистерезис — функция последовательности уникальных свечей» корректно для backtest | корректно ТОЛЬКО при изолированном состоянии per-FIGI; при текущем общем состоянии гистерезис — функция чередующейся последовательности вызовов всех инструментов | Stage 1 T-2 vs addendum §1 | PARTIALLY CONFIRMED |
| V-38 | Live работает на 5-мин свечах: MAE/MFE и SL/TP от свечных high/low, поллинг 30 с пропускает внутрибарные экстремумы | комментарий и код `update_extremes`; проверка SL/TP по price-опросу | execution.py:884-888, 991-1022 | CONFIRMED |
| V-39 | Fail-closed контракт клиента: `None` = неизвестно, `{}` = достоверно пусто; order_id сохраняется при потере ответа | docstring и код `get_positions`/`post_market_order` | tinkoff_client.py:315-325, 555-577 | CONFIRMED |
| V-40 | Код в commit Stage 1 идентичен коду проверяемого commit | diff между commit — ровно 9 новых .md-файлов аудита, 0 .py | `git diff --name-only 884cefd c409221` | CONFIRMED |
| V-41 | Структура репозитория соответствует описанию Stage 1 (candidate/, docs/) | каталоги и состав подтверждены | дерево репозитория; REPOSITORY_SCOPE §2 | CONFIRMED |
| V-42 | `.env` и токены в репозитории отсутствуют; токены только из env | git ls-files без `.env`; чтение env | config.py:14-19; REPOSITORY_SCOPE §4 | CONFIRMED |
| V-43 | Содержимое `orders.zip` | бинарный артефакт, в коде не упоминается; не извлекался | candidate/orders.zip; HARDCODED §5.3; Q-08 Stage 1 | UNKNOWN |
| V-44 | Семантика protobuf-полей SDK 1.51.0 (сырые статусы, executed_order_price, order_request_id) | SDK недоступен в среде аудита; принято по контрактам кода | tinkoff_client.py:54-74 (комментарии); N-01 Stage 1 | UNKNOWN |
| V-45 | Достижимость ветки EXPIRED=6 как нетерминального статуса | код подтверждает рассинхрон маппингов (main включает 6; execution inline — нет; `_TERMINAL_SELL_STATUSES` без "6"); практическая достижимость зависит от SDK | main.py:609-612; execution.py:220, 1075; R-01 Stage 1 | PARTIALLY CONFIRMED (рассинхрон — FACT; достижимость — UNKNOWN) |
| V-46 | Взаимное противоречие MIN_CANDLES_FOR_SIGNAL=60 < TREND_FILTER_MA_PERIOD=100 в TECH_CHECK/CONSERVATIVE | значения в ветках профилей; фильтр требует len≥периода | config.py:104-117; strategy.py:231-232 | CONFIRMED |
| V-47 | Тесты изоляции состояния (A не влияет на B, независимость от порядка, восстановление per-FIGI) пройдены | тесты не запускались на Stage 1.1 — зафиксированы как требования | addendum §1.4, §8 (R-S1.1-b) | NOT CONFIRMED (не выполнялись — так и заявлено) |
| V-48 | Stage 1 заявляет «реализация не выполнялась» — проверено | в commit c409221 отсутствуют изменения .py; каталога `strategies/` нет; `ACTIVE_STRATEGY` в коде отсутствует | `git diff 884cefd c409221`; дерево репозитория | CONFIRMED |

## Сводка по статусам (всего 48 позиций: V-01…V-48)

- CONFIRMED — 38 позиций (в т.ч. V-14, V-21 — подтверждены с уточнениями);
- PARTIALLY CONFIRMED — 2 (V-37, V-45);
- NOT CONFIRMED — 5 (V-33, V-34, V-35, V-36, V-47 — все «ожидаемо не
  подтверждены»: это требования/пробелы, а не опровержение фактов;
  V-47 — тесты не запускались и не заявлялись как запущенные);
- UNKNOWN — 3 (V-12, V-43, V-44).

Позиции NOT CONFIRMED не опровергают выводы Stage 1 — они фиксируют
отсутствие в Stage 1 требований, добавляемых Stage 1.1 (исправленные
версии документов прилагаются).
