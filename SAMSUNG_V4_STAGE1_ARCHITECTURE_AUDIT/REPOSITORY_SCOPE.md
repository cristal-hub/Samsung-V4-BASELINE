# REPOSITORY_SCOPE.md

## Границы проведённого аудита Samsung V4 — STAGE 1

**Мандаты (сохраняются во всех документах этапа):**

```
STRATEGY LOGIC: UNCHANGED
RESEARCH ONLY
NO THRESHOLD IS OPTIMIZED
NO FILTER IS INSTALLED
NO LIVE ORDERS
```

Этап 1 — только исследование и документация. Ничего не внедрялось: ни один
`.py`-файл не изменён, ни один параметр не изменён, профиль не менялся,
заявки не отправлялись, брокерские API не вызывались.

---

## 1. Исследованные ветка и commit

| Атрибут | Значение |
|---|---|
| Репозиторий-источник | https://github.com/cristal-hub/Samsung-V4-BASELINE.git |
| Ветка | `main` (единственная локальная ветка; `origin/main` совпадает) |
| Исследованный commit | `884cefd6f12a99f6adc14b5ed4c9eeda21d32e04` (короткий: `884cefd`) |
| Автор последнего коммита | cristal-hub `<84268571+cristal-hub@users.noreply.github.com>` |
| Дата последнего коммита | 2026-11-26 19:02:01 +0300 |
| Сообщение коммита | "Add files via upload" |
| Способ клонирования | `git clone --depth 50` (только чтение; без push/commit/веток/PR) |
| Число файлов под git | 156 |
| Объём рабочего дерева | ~6,7 МБ без `.git` |

**ФАКТ.** Аудит выполнен по одному фиксированному snapshot'у `main@884cefd`.
Все ссылки вида `файл:строка` в остальных документах относятся именно к этому
коммиту.

## 2. Фактическая структура проекта

ТЗ предполагало файлы (`config.py`, `strategy.py`, `main.py`, …) в корне
репозитория. **ФАКТ: структура отличается — весь производственный код
находится в каталоге `candidate/`, документация — в `docs/`.** Корень
репозитория содержит только эти два каталога.

```
Samsung-V4-BASELINE/
├── candidate/                  # производственный код + тесты + отчёты аудитов
│   ├── __init__.py             # пустой (влияет на sys.path при pytest — см. §5)
│   ├── config.py               # конфигурация: env, риск, стратегия, PROFILE (162 строк)
│   ├── strategy.py             # StrategyManager: режим рынка ADX + сигналы MA/BB+RSI (465)
│   ├── main.py                 # торговый цикл, reconcile, закрытия, восстановление (5738)
│   ├── risk_manager.py         # RiskManager: размер позиции, SL/TP, дневные лимиты (263)
│   ├── execution.py            # ExecutionMonitor, TrackedPosition, per-order cursor (1757)
│   ├── tinkoff_client.py       # TinkoffClient: T-Invest SANDBOX API (682)
│   ├── screener.py             # Screener: TOP-10 волатильных MOEX (198)
│   ├── logger.py               # research_events.jsonl + research_trades.csv (582)
│   ├── telegram_bot.py         # TelegramBot: /start /stop /status (141)
│   ├── order_ledger.py         # OrderLedger: append-only реестр заявок (604)
│   ├── build_safety.py         # Режим A/B, guard заявок, sandbox-only (123)
│   ├── safe_start.py           # SAFE START / READ-ONLY диагностика (274)
│   ├── enable_sandbox_execution.py  # интерактивное включение Режима B (70)
│   ├── conftest.py             # заглушки SDK + изоляция тестов (227)
│   ├── requirements.txt        # зафиксированные зависимости (SDK 1.51.0, grpcio 1.85.1)
│   ├── test_*.py               # 39 тестовых файлов в корне candidate/
│   ├── tests/                  # 21 тестовый файл (дубликаты корневых) + conftest.py + __init__.py
│   ├── orders.zip              # БИНАРНЫЙ артефакт (43 КБ), не извлекался (см. §4)
│   └── *.md, *.txt, *.patch, *.pdf, *.docx   # отчёты предыдущих аудитов (B2, P0, BUY, V4)
└── docs/                       # документация поставки V4
    ├── README.md               # отчёт BUY ACCOUNTING AUDIT v1
    ├── CHANGELOG_V4.md         # V4-1..V4-5 относительно V3
    ├── CONFIGURATION_TEMPLATE.md   # шаблон .env, режимы сборки
    ├── INSTALLATION_RU.md      # установка
    ├── LAPTOP_TEST_RUNBOOK_RU.md   # пошаговый RUNBOOK (Режим A/B)
    └── ROLLBACK_RU.md          # откат сборки
```

## 3. Перечень исследованных файлов

### 3.1. Производственный код — изучен ПОЛНОСТЬЮ (построчно, с номерами строк)

| Файл (путь в репозитории) | Строк | Что проверено |
|---|---|---|
| `candidate/config.py` | 163 | все константы, env, PROFILE-ветки, `validate()` |
| `candidate/strategy.py` | 466 | `StrategyManager`: `get_market_regime`, `get_signal`, `_ma_crossover_signal`, `_bb_rsi_signal`, `_trend_filter_ok`, `_volume_confirmation`, `_prepare_dataframe` |
| `candidate/main.py` | 5738 | все 30+ функций: `main`, `trading_cycle`, `reconcile`, `process_closing`, `close_position`, `register_executed_buy`, `poll_open_orders`, `promote_recovery_positions`, `startup_recovery`, `_try_resolve_absent_position`, `_build_candles_df`, persistence (`_save_state`/`_load_state`), флаг `trading.flag`, Telegram-lifecycle |
| `candidate/risk_manager.py` | 263 | `calculate_position_size`, `calculate_sl_tp`, `_calculate_volatility_risk`, `record_trade`, export/import state |
| `candidate/execution.py` | 1757 | `TrackedPosition`, `ExecutionMonitor`: `check_all` (SL/TP), `apply_close_execution`, `resolve_closing`, `resolve_uncertain`, `add_close_order`, `_update_sl` (безубыток/трейлинг), `validate_recovery_identity`, export/import state |
| `candidate/tinkoff_client.py` | 682 | все методы клиента, fail-closed `get_positions`, `post_market_order`, `get_sandbox_order_state`/`cancel_order` с order_id_type |
| `candidate/screener.py` | 198 | `_do_scan`, `select_top_volatile`, кэш, критерии отбора |
| `candidate/logger.py` | 582 | `log_event`, `log_trade`, `update_trade_row`, `find_trade_row`, `_recompute_cumulative`, атомарная запись |
| `candidate/order_ledger.py` | 604 | `append`, `record_intent/sent/status/uncertain/observation`, prepare/commit protocol, `figi_blocks_buy`, `open_orders` |
| `candidate/telegram_bot.py` | 141 | команды, авторизация по user_id, таймауты, watchdog |
| `candidate/build_safety.py` | 123 | `detect_mode`, `install_order_guard`, `assert_sandbox_only` |
| `candidate/safe_start.py` | 274 | проверки Режима A, SELF-TEST блокировки заявок |
| `candidate/enable_sandbox_execution.py` | 70 | включение Режима B (фраза ENABLE-SANDBOX) |
| `candidate/conftest.py` | 227 | заглушки SDK, изоляция глобального состояния main и runtime-путей |
| `candidate/requirements.txt` | 11 | зафиксированные версии |

### 3.2. Тесты — изучены структурно и выборочно

**ФАКТ (проверено побайтовым сравнением `cmp`):** из 39 корневых
`candidate/test_*.py` — 21 файл имеют копию в `candidate/tests/` (19
байт-в-байт идентичны; 2 отличаются — см. ниже), 18 файлов существуют ТОЛЬКО
в корне. Файлов, существующих только в `tests/`, нет (кроме `conftest.py` и
`__init__.py`).

- 19 идентичных пар: `test_main.py`, `test_strategy.py`, `test_risk_manager.py`,
  `test_execution.py`, `test_screener.py`, `test_persistence.py`,
  `test_fail_closed.py`, `test_order_ledger.py`, `test_slippage.py`,
  `test_commission.py`, `test_safety.py`, `test_tinkoff_client*.py`,
  `test_telegram_handlers.py`, `test_trading_flag.py`, `test_main_helpers.py`,
  `test_p0_batch2_late_execution.py`, `test_p0_defect_fixes.py` и др.
- 2 РАЗЛИЧАЮЩИЕСЯ пары (копия в корне новее):
  - `candidate/test_buy_registration_fix2.py` (1044 строки) против
    `candidate/tests/test_buy_registration_fix2.py` (1037): в корневой версии
    блок прямых присваиваний глобального состояния заменён на
    `monkeypatch.setattr(main, "state_save_failed", False)` (различие в районе
    строки 1004);
  - `candidate/test_buy_registration_fix2_FIX2_snapshot.py` (475 против 469) —
    тот же характер различий.
  - Согласуется с `docs/CHANGELOG_V4.md` §V4-3 («копии синхронизированы в V3»)
    и §OOS-2 (двойные копии не устранены). Каноничность — см.
    OPEN_QUESTIONS_AND_RISKS.md, вопрос Q-01.
- 21 файл только в корне (последние аудиты): `test_b2_*.py` (7),
  `test_buy_accounting_audit.py`, `test_corrective_audit_v2/v3.py`,
  `test_manual_close_integration.py`, `test_p0_sell_id_fixes.py`,
  `test_stage1_packet_v.py`, `test_stage1_s1_telemetry.py`,
  `test_v232_close_defects.py`, `test_v233_partial_sell_reopen_defect.py`,
  `test_v4_integration_integrity.py`, `test_v4_order_ledger_first_append.py`,
  `test_v4_safety_build.py`.

Тесты изучены по заголовкам/структуре и по точечным ссылкам на параметры
(например, `test_screener.py:144` monkeypatch `MIN_DAILY_TURNOVER_RUB`;
`test_risk_manager.py:94` — `MAX_TRADES_PER_INSTRUMENT_PER_DAY`);
построчный разбор всех ~15 000 строк тестов в объём этапа 1 не входил.

### 3.3. Документация — изучена полностью

`docs/README.md`, `docs/CHANGELOG_V4.md`, `docs/CONFIGURATION_TEMPLATE.md`,
`docs/INSTALLATION_RU.md`, `docs/LAPTOP_TEST_RUNBOOK_RU.md` (полностью не
цитируется, просмотрены все разделы), `docs/ROLLBACK_RU.md`,
`candidate/README.md`.

### 3.4. Отчётные материалы предыдущих этапов — инвентаризированы, глубоко не изучались

В `candidate/` присутствуют артефакты предыдущих аудитов: `AUDIT_REPORT.md`,
`AUDIT_GLOBAL_MUTATIONS.txt`, `ROOT_CAUSE_ANALYSIS.md`, `KNOWN_LIMITATIONS.md`,
`MERGE_REPORT.md`, `TRANSFER_TABLE.md`, `SAMSUNG_PRESERVED.md`,
`SHA256SUMS*.txt` (6 файлов), `ОТЧЁТ_*.md` (5 файлов), `план.txt`,
`izmenenija*.diff` (5 патчей), `FULL_DIFF.patch`, `BUY_DIFF*.patch`,
логи pytest (`FULL_PYTEST_*.txt`, `appendix_*`), `main_console.txt`.
Они инвентаризированы (имена, назначение по `docs/README.md` §«Состав каталога»);
их содержимое использовалось только как вторичные источники — все существенные
утверждения настоящего аудита проверены по исходному коду (требование §10 ТЗ:
«не делать выводы по комментариям и README»).

## 4. Перечень файлов, которые НЕ удалось изучить

| Файл | Причина |
|---|---|
| `candidate/orders.zip` (43 141 байт) | Бинарный ZIP-артефакт; содержимое не извлекалось, чтобы не создавать «лишние копии» данных в рабочем каталоге аудита. Назначение в коде не упоминается (grep `orders.zip` по `*.py` — 0 совпадений). **НЕИЗВЕСТНО**, являются ли данные в нём runtime-данными (`order_ledger.jsonl`-подобными) или артефактом передачи. Зафиксирован в OPEN_QUESTIONS_AND_RISKS.md (Q-08). |
| `candidate/ОТЧЁТ_..._pytest.pdf`, `candidate/ОТЧЁТ_..._pytest.docx` | Бинарные офисные форматы; изучены только имена (перевод содержимого не требовался для аудита кода). |
| Вложения внутри `appendix_*` | Не проверялись. |

Секреты: **ФАКТ** — файл `.env` в репозитории отсутствует (git ls-files не
содержит `.env`); токены читаются только из переменных окружения
(`config.py:14-19`). Токены не запрашивались и не использовались (§8 ТЗ).

## 5. Ограничения проведённого аудита

1. **Статический анализ только.** Код не запускался: ни `main.py`, ни
   `safe_start.py`, ни pytest. Результаты тестовых прогонов взяты из отчётов
   репозитория (`docs/INSTALLATION_RU.md` §4: «Ожидание: 789 passed») и не
   воспроизводились в среде аудита (установка приватного SDK
   `t-tech-investments==1.51.0` и сетевые вызовы запрещены §8 ТЗ).
2. **Один commit.** Выводы действительны для `main@884cefd`; последующие
   изменения в репозитории аудит не покрывает.
3. **`--depth 50`.** История коммитов ограничена 50 записями; для аудита
   состояния кода этого достаточно, эволюционный анализ истории не проводился.
4. **Тесты не прогонялись**, двойные копии тестов сравнивались побайтово, но
   поведенческая разница двух различающихся пар
   (`test_buy_registration_fix2*`) оценена только по diff (см. §3.2).
5. **`candidate/orders.zip` не извлекался** (см. §4).
6. **Окружение владельца не проверялось**: версия Python/SDK на ноутбуке
   владельца, наличие маркера `sandbox_execution.enabled`, содержимое
   runtime-файлов (`state.json`, `order_ledger.jsonl`,
   `research_trades.csv`, `research_events.jsonl`) — **НЕИЗВЕСТНО**; в git их
   нет (runtime-файлы создаются рядом с `main.py` при работе — ФАКТ:
   `main.py:596-601`, `logger.py:98-99`).
7. **SDK T-Invest доступен только по документации в коде.** Поведение
   protobuf-объектов (`executed_order_price`, `executed_commission`,
   `OrderState.order_request_id`) принято по комментариям в коде
   (`tinkoff_client.py:54-74`) и по контрактам, зафиксированным в
   предыдущих аудитовых отчётах; независимо от SDK не верифицировано.

## 6. Доказательность

Каждое существенное утверждение в документах этапа маркировано:

- **ФАКТ** — подтверждено исходным кодом (файл:строка);
- **ВЫВОД** — следует из нескольких ФАКТОВ;
- **ПРЕДЛОЖЕНИЕ** — рекомендуемое будущее решение (не существует в коде);
- **НЕИЗВЕСТНО** — данных недостаточно.

Утверждения по комментариям/README без подтверждения кодом допускаются
только с явной пометкой источника.
