# CURRENT_ARCHITECTURE_MAP.md

## Карта текущего взаимодействия модулей Samsung V4

**Мандаты:**

```
STRATEGY LOGIC: UNCHANGED
RESEARCH ONLY
NO THRESHOLD IS OPTIMIZED
NO FILTER IS INSTALLED
NO LIVE ORDERS
```

Все утверждения — ФАКТ по `main@884cefd`, кроме помеченных ВЫВОД/НЕИЗВЕСТНО.

---

## 1. Модули и их фактические обязанности

| Модуль | Класс/точка входа | Фактическая роль |
|---|---|---|
| `main.py` | `main()` (main.py:5626-5729), `trading_cycle()` (5115-5619) | Оркестратор: сборка объектов, стартовые проверки, бесконечный цикл; **плюс** значительная часть учётной логики (reconcile, close_position, register_executed_buy, восстановление) |
| `strategy.py` | `StrategyManager` (strategy.py:30) | Только сигналы: режим рынка (ADX-гистерезис), MA-кроссовер в TREND, BB+RSI в RANGE, фильтр MA100, подтверждение объёмом. Позициями/ордерами НЕ управляет |
| `risk_manager.py` | `RiskManager` (risk_manager.py:35) | Размер позиции (risk_manager.py:87-207), **расчёт SL/TP** (233-259 — помечен «Без изменений (стратегия)»), дневные лимиты сделок, персистентность счётчиков |
| `execution.py` | `ExecutionMonitor`, `TrackedPosition` (execution.py:242, 349) | Учёт позиций по FIGI, состояния OPEN/CLOSING/CLOSED/UNCERTAIN/RECOVERY, проверка SL/TP (`check_all`), применение исполнений SELL (per-order cursor), безубыток/трейлинг (выключено), экспорт/импорт state |
| `tinkoff_client.py` | `TinkoffClient` (tinkoff_client.py:181) | Единственная точка доступа к T-Invest **Sandbox** API: свечи, цены, инструмент, баланс, позиции (fail-closed), заявки, статусы, отмена; `uncertain_state` |
| `order_ledger.py` | `OrderLedger` (order_ledger.py:103) | Append-only JSONL-реестр заявок: INTENT до сети, статусы, UNCERTAIN, контроль кумулятивного исполнения, блокировки BUY по FIGI, флаг недостоверности |
| `screener.py` | `Screener` (screener.py:39) | Один раз при старте: TOP-N волатильных акций MOEX (ATR-дней / close, оборот, RUB) |
| `logger.py` | функции (logger.py:88+) | `research_events.jsonl` (события) + `research_trades.csv` (сделки, накопительный P&L, атомарные обновления строки) |
| `telegram_bot.py` | `TelegramBot` (telegram_bot.py:23) | /start /stop /status (через колбэки main.py:948), отправка уведомлений, watchdog polling |
| `build_safety.py` | функции (build_safety.py:36+) | Режим A/B (маркер+env), guard `post_market_order`/`cancel_order` на экземпляре клиента, `assert_sandbox_only` |
| `safe_start.py` | `main()` (safe_start.py:226) | Диагностика Режима A (read-only), self-test блокировки заявок |
| `config.py` | модуль | Единственный источник параметров (см. STRATEGY_PARAMETERS_INVENTORY.md) |

## 2. Схема взаимодействия (ФАКТ)

```
                        ┌────────────────────────────────────────────┐
                        │                  config.py                  │
                        │   (env + литералы + PROFILE-ветвление)      │
                        └───────┬────────────────────────────────────┘
                                │ import (все модули читают один снапшот)
   ┌────────────────────────────┼─────────────────────────────────────────┐
   │                            │                                          │
   ▼                            ▼                                          ▼
┌─────────┐   DataFrame   ┌────────────┐  signal,reason  ┌────────────────────┐
│ Screener│──────────────►│ strategy.py│────────────────►│      main.py        │
│ TOP-N   │  (не свечи)   │ Strategy-  │  BUY/SELL/HOLD  │  trading_cycle      │
│ (1 раз) │               │ Manager    │                 │  (оркестратор+учёт) │
└─────────┘               └────────────┘                 └──┬───────┬─────────┘
   ▲                                                        │       │
   │ instruments (main.py:5704)                             │       │
   │                                                        ▼       ▼
   │                                          ┌────────────────┐  ┌────────────────┐
   │                                          │ risk_manager   │  │ execution.py   │
   │                                          │ size, SL/TP,   │  │ check_all(SL/TP│
   │                                          │ дневные лимиты │  │ per-order SELL)│
   │                                          └───────┬────────┘  └───────┬────────┘
   │                                                  │                   │
   ▼                                                  ▼                   ▼
┌──────────────────┐  get_positions / post_market_order / order_state / cancel  ┌──────────┐
│ tinkoff_client.py│◄────────────────────── все сетевые вызовы ────────────────►│ T-Invest │
│ (SANDBOX only)   │                                                            │ Sandbox  │
└───────┬──────────┘                                                            └──────────┘
        │ uncertain_state (fail-closed флаг)
        ▼
┌──────────────────┐  INTENT/SENT/UNCERTAIN  ┌──────────────────┐  сделки   ┌──────────────────┐
│ order_ledger.py  │────────────────────────►│ order_ledger.    │           │ logger.py        │
│ append-only JSONL│◄────────────────────────│ jsonl (на диске) │           │ events.jsonl +   │
│ figi_blocks_buy  │  record_status/sync     │                  │           │ trades.csv       │
└──────────────────┘                         └──────────────────┘           └──────────────────┘
        ▲                                             ▲                          ▲
        │        state.json (positions, risk, ...)    │     build_version/prof   │
        └────────────── main._save_state/_load_state ─┴──────────────────────────┘
                              (атомарно, tmp+os.replace, main.py:1165-1167)

Оператор: trading.flag (вкл/выкл входов) + Telegram /start /stop /status
          (main.py:847-868, 948; telegram_bot.py:52-107)
```

## 3. Торговый цикл — фактическая последовательность шагов (ФАКТ)

`trading_cycle` (main.py:5115-5619), один проход каждые
`TRADING_CYCLE_SECONDS` (main.py:5729):

| Шаг | Строки | Что происходит | Какие параметры работают |
|---|---|---|---|
| 0 | 5119-5122 | `monitor_ref = monitor` (для close_position) | — |
| 1 | 5124-5133 | Цены: объединение FIGI (позиции + top_instruments); `get_last_prices` → None → `monitoring_error=True` | D8 (delay) |
| 2 | 5135-5152 | SL/TP: (BE_TRAIL_ENABLED) экстремумы/ATR по OPEN-позициям → `check_all` → для to_close `close_position` (SELL) | B2-B8, B13-B14, C1-C4 |
| 3 | 5155 | `process_closing`: resolve_closing (CLOSING и UNCERTAIN с close-заявкой), resolve_uncertain, reconcile, запись CSV закрытий, late-CSV-recovery | C8, B13 |
| 3.5 | 5157-5159 | `poll_open_orders`: пошаговый контроль BUY-заявок реестра (одна заявка за проход опрашивается, возраст → отмена) | C9 (хардкод 10), C6 |
| 3.6 | 5161-5163 | `promote_recovery_positions`: восстановление цены входа + SL/TP → RECOVERY→OPEN | B2-B8, C7 |
| 4 | 5165-5184 | `reconcile` (в КАЖДОМ цикле, v2.3.1 ТЗ-1/2): двусторонняя сверка, адопция RECOVERY, В2/В3; `client.is_uncertain()` → входы запрещены | C8, D7 |
| 5 | 5186-5225 | Блокировки входов: trading.flag, reconcile_done, monitoring_error, state_save_failed, ledger.is_reliable, unknown-FIGI | — |
| 6 | 5227-5234 | Свежий портфель перед входами; None → запрет | D7 |
| 7 | 5236-5612 | Входы: на каждый инструмент — цена, позиция/блокировки, `_build_candles_df` (5-мин, 2 дня), `sm.get_signal`, SELL-сигнал игнорируется, `calculate_position_size`, INTENT, post, ветки PARTIALLYFILL/не-FILL/FILL → `register_executed_buy` | A1-A19, B1-B11, C6-C7 |
| финал | 5614-5619 | `_save_state_checked` — безусловное сохранение state.json (пакет В1) | H4 |

`main()` (main.py:5626-5729): validate → Telegram → client+guard(Режим A/B) →
объекты → ledger.load (+ блокировка при недостоверности) → _load_state
(+ запрет входов при отсутствии) → startup_recovery (четырёхсторонняя сверка,
main.py:4831-5108) → скринер (ОДИН раз; провал → вечный сон 60 с) →
первичный reconcile → while(trading_cycle).

## 4. Хранилища состояния (ФАКТ)

| Файл | Пишет | Содержимое | Роль |
|---|---|---|---|
| `state.json` | main `_save_state` (1144-1171), атомарно tmp+os.replace | positions (все поля TrackedPosition), closed_entry_order_ids, pending_csv_recoveries, monitoring_error, risk (daily_trade_counts, last_reset_date), срез open_orders | оперативный учёт, переживает рестарт |
| `order_ledger.jsonl` | OrderLedger `_append_raw` (order_ledger.py:185-197, fsync на запись) | append-only: ORDER_STATUS / APPLY_PREPARED / APPLY_COMMITTED | источник истины по заявкам; повреждение → `_mark_unreliable` → запрет BUY (main.py:5676-5689, 5204-5215) |
| `research_events.jsonl` | logger.log_event (logger.py:179-197) | события: profile/commission_mode/build_version + payload | аудит решений |
| `research_trades.csv` | logger.log_trade / update_trade_row (logger.py:200-226, 491-562) | сделки, P&L, cumulative (хронологический пересчёт) | финансовый журнал |
| `trading.flag` | start_trading/stop_trading (main.py:851-868) | просто факт существования | включение НОВЫХ ВХОДОВ; SL/TP-выходы не блокирует (см. docs/CHANGELOG_V4.md V4-2 — для laptop-сборки это закрыто guard'ом) |

## 5. Жизненный цикл позиции (ФАКТ)

```
                         ┌──────────── OPEN ◄────────────────────┐
        register()       │        │ SL/TP hit (check_all)         │
   (главный путь входа,  │        ▼                               │
    main.py:4091)   ┌────┴─── CLOSING ───► close_position SELL ───┤
                    │        │                   │                │
                    │        │ resolve_closing   │                │
                    │        ▼                   ▼                │
                    │   apply_close_execution (per-order cursor,  │
                    │   execution.py:694-861)                     │
                    │        │                                    │
                    │        ├── quantity==0 ──► CLOSED → CSV    │
                    │        ├── терминал + остаток ──► UNCERTAIN┤
                    │        └── нетерминал ──► CLOSING/UNCERTAIN│
                    │                                            │
   register_recovery│      resolve_uncertain (execution.py:1152- │
   (адопция/неполные├────► 1245): совпадение остатка+нет живой   │
    данные)         │      SELL → OPEN; иначе UNCERTAIN          │
                    │                                            │
                    └──► RECOVERY ── promote_recovery ────────────┘
                         (цена+SL/TP восстановлены, main.py:4636-4828)

UNCERTAIN: SL/TP не действуют (check_all только OPEN, execution.py:991-993),
           новые BUY по FIGI заблокированы (figi_blocks_buy + has_active_position),
           повторная SELL запрещена (_sell_block_reason, main.py:738-767).
```

**ВЫВОД:** закрытие учёта возможно ТОЛЬКО через терминальный отчёт брокера
или двойное подтверждение В3; фиктивный P&L запрещён (exit_price_confirmed —
execution.py:291-294, 788-789, 833; CSV без P&L — main.py:2918-2933, 3099-3106).

## 6. Где «стратегия» и «движок» смешаны сегодня (ВЫВОД из ФАКТОВ)

| Смешение | Факт | Следствие для целевой архитектуры |
|---|---|---|
| Расчёт SL/TP живёт в RiskManager | risk_manager.py:233-259 («Без изменений (стратегия)»), вызывается из main.py:4072, 4808 | SL/TP — часть стратегии: должен переезжать в контракт стратегии (ПРЕДЛОЖЕНИЕ, не реализовано) |
| Оркестратор содержит учётную логику | main.py: 5738 строк; reconcile/close/register/recovery — все в main.py | учёт и исполнение — общие для всех стратегий; сигнальная логика — единственная стратегиеспецифичная часть |
| Стратегия «голая»: только сигналы | strategy.py: 466 строк, без обращений к клиенту (только config + pandas) | уже почти чистый контракт: вход = DataFrame+price, выход = (signal, reason); внутреннее состояние гистерезиса (strategy.py:34-43) — часть стратегии |
| Screener отделён, но его результат — глобальная переменная | main.py:680 `top_instruments=[]`, заполнение 5714 | вселенная — параметр движка/стратегии, не глобал |
| Telegram-команды жёстко привязаны к main-колбэкам | main.py:948 | при мульти-стратегии /status должен показывать активную стратегию (ПРЕДЛОЖЕНИЕ) |

## 7. Механизмы безопасности, существующие сегодня (ФАКТ — «что нельзя потерять»)

1. **Fail-closed на каждом недостоверном факте**: None-снимок портфеля не
   меняет учёт (main.py:2044-2048; tinkoff_client.py:423-429), None-статус
   заявки ≠ отказ (tinkoff_client.py:619-624), противоречивые отчёты →
   UNCERTAIN (main.py:1779-1807; execution.py:739-774; order_ledger.py:287-334).
2. **INTENT до сети + append-only fsync-реестр** (main.py:5300-5325;
   order_ledger.py:185-197) — заявка не отправляется без записи.
3. **Per-order cursor** на SELL (execution.py:656-692, 694-861) — защита от
   повторного применения исполнения.
4. **Четырёхсторонняя стартовая сверка** (startup_recovery, main.py:4831-5108).
5. **Блокировки**: uncertain_state, FIGI-blocks-buy, unknown-FIGI global block,
   ledger reliability, state_save_failed (main.py:5186-5225).
6. **Атомарные записи**: state.json (tmp+os.replace, main.py:1165-1167),
   CSV update (logger.py:414-488).
7. **Guard заявок Режима A** + тройной запрет LIVE (build_safety.py:78-113;
   main.py:5659-5660).
8. **trading.flag** — отдельное разрешение входов (main.py:847-868).
9. **Запрет фиктивного P&L** (см. §5).
10. **Валидация идентичности recovery-задач** (validate_recovery_identity,
    execution.py:1524-1608) + fail-closed конфликт-маркеры.

**ВЫВОД:** эти 10 механизмов составляют «ценность» текущего кода; целевая
архитектура (STRATEGY_SWITCH_ARCHITECTURE.md) проектируется вокруг их
сохранения, а не вокруг переписывания.

## 8. Ограничения текущей архитектуры относительно цели «платформа стратегий»

(перечень — входные данные для STRATEGY_SWITCH_ARCHITECTURE.md; всё — ВЫВОД)

1. Нет понятия «стратегия» как единицы конфигурации/учёта: один
   StrategyManager, один PROFILE, без strategy_id в CSV/ledger/state.
2. Параметры не разделены на категории A-E и не валидируются
   (кроме PROFILE).
3. Знание «какая стратегия открыла позицию» отсутствует: TrackedPosition не
   хранит источника решения (только signal_reason — строка причины сигнала,
   execution.py:260).
4. Смена стратегии сейчас = правка PROFILE/констант config.py в исходниках с
   рестартом; нет механизма запрета смешивания настроек.
5. Screener/вселенная и стратегия не связаны контрактом: стратегия получает
   любые df, которые ей передал движок.
6. Журналы не позволяют однозначно воспроизвести расчёт сигнала по архиву
   (событие SIGNAL содержит сигнал и цену, но не снимок свечей; свечи
   пересчитываемы только при наличии исторических данных брокера).
```
