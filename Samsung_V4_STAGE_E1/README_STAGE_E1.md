# SAMSUNG V4 — STAGE E.1 — HISTORICAL ENGINE CORRECTIONS

Этап корректировки и укрепления Stage E: три архитектурных исправления
исторического симулятора. Существующая архитектура Stage E сохранена;
Stage A–D не изменены; стратегия и её пороги не тронуты; никакой
оптимизации параметров.

РЕЖИМ: READ-ONLY / RESEARCH ONLY / VIRTUAL EXECUTION ONLY.
Только исторические данные и виртуальная симуляция. Нет брокерских SDK,
сети, Telegram, Sandbox/LIVE, реальных и тестовых ордеров, FORCE_TRADE.

## Состав поставки

```
Samsung_V4_STAGE_E1/
├── README_STAGE_E1.md                        ← этот файл
├── STAGE_E1_CHANGES_DESCRIPTION.md           ← описание изменений (§8.6)
├── STAGE_E1_KNOWN_LIMITATIONS.md             ← известные ограничения (§8.7)
├── STAGE_E1_TEST_RESULTS.txt                 ← отчёт pytest + no-test-loss (§8.3)
├── STAGE_E1_NO_CHANGES_ABCD_PROOF.txt        ← неизменность Stage A–D (§8.4)
├── STAGE_E1_NO_BROKER_SDK_PROOF.txt          ← нет Broker SDK и сети (§8.5)
├── STAGE_E1_SHA256_MANIFEST.txt              ← SHA-256 manifest поставки (§8.8)
├── STAGE_E1_CHANGED_AND_NEW_FILES.txt        ← изменённые/новые файлы, SHA до/после
├── STAGE_E1_PYTEST_FULL_LOG.txt              ← полный verbose-лог pytest
├── STAGE_E1_PYTEST_CANONICAL_LOG.txt         ← канонический лог pytest
└── candidate/
    ├── historical_engine/                    ← полный исправленный пакет (11 файлов)
    │   ├── __init__.py        (M)  экспорты Stage E.1
    │   ├── models.py          (M)  GapIncident, EngineConfig.calendar, константы
    │   ├── calendar.py        (A)  TradingCalendar (Correction №1)
    │   ├── data_feed.py       (M)  календарно-корректный контроль пропусков
    │   ├── execution.py       (M)  раздельный учёт slippage/improvement (№2)
    │   ├── ledger.py          (M)  improvement-поля, total_execution_cost
    │   ├── report.py          (M)  costs/gap_verification/metadata
    │   ├── engine.py          (M)  согласованность конфигураций (№3)
    │   ├── risk_integration.py     (без изменений, Stage D интеграция)
    │   ├── strategy_runner.py      (без изменений)
    │   └── event_engine.py         (без изменений)
    └── tests/
        ├── stage_e_tools.py                    (без изменений)
        ├── test_stage_e_data_feed.py           (без изменений)
        ├── test_stage_e_engine_decisions.py    (без изменений)
        ├── test_stage_e_execution_ledger.py    (без изменений)
        ├── test_stage_e_integration.py         (без изменений)
        ├── test_stage_e_report.py              (без изменений)
        ├── test_stage_e1_calendar.py           (A)  19 тестов
        ├── test_stage_e1_slippage.py           (A)  16 тестов
        └── test_stage_e1_config_consistency.py (A)  11 тестов
```

(A) — новый файл, (M) — изменён относительно принятого Stage E.
Все прочие файлы дерева candidate совпадают байт-в-байт с Stage E
(179 файлов проверено, 0 нарушений — см. NO_CHANGES_ABCD_PROOF).

## Три исправления (кратко)

1. **Календарно-корректное обнаружение пропусков** — новый компонент
   `TradingCalendar` из явно переданных сессий различает: подтверждённый
   пропуск ожидаемой торговой свечи (A), перерыв сессии (B), выходной/
   праздник (C), невозможность проверки (D). STRICT отклоняет только
   подтверждённые пропуски; отсутствие календаря ЯВНО помечается как
   ограниченная проверка (без ложного подтверждения полноты).
2. **Раздельный учёт slippage** — неблагоприятное проскальзывание (>= 0)
   и улучшение цены (>= 0) разделены по направлению сделки; прежняя
   отрицательная запись «slippage» на TP после гэпа устранена;
   `total_execution_cost = total_commission + total_adverse_slippage_cost`
   (документировано); комиссия отдельна; цена исполнения НЕ изменена.
3. **Согласованность конфигураций** — `BacktestEngine` fail-closed
   проверяет совместимость с конфигурацией фида: интервал, gap_policy,
   календарь (включая представление часового пояса); диагностика
   перечисляет все различия с обоими значениями.

## Как прогнать тесты (офлайн)

Требования: Python 3.12+, pandas; остальные зависимости тестовой среды
ставятся заглушками (conftest). Из каталога, содержащего `candidate/`
(например, корень репозитория, в который размещены файлы поставки):

```bash
cd <repo-root>/candidate
python -m pytest tests -q            # канонический: 1176 passed
python -m pytest -q                  # полный:      1696 passed
```

## Критерии приёмки E.1 — статус

* [x] календарные перерывы не считаются пропущенными свечами
* [x] реальные пропуски внутри сессии обнаруживаются
* [x] STRICT отклоняет только подтверждённые пропуски
* [x] отсутствие календаря не создаёт ложного подтверждения полноты
* [x] проскальзывание и улучшение цены учитываются раздельно
* [x] adverse slippage неотрицателен
* [x] комиссии учитываются отдельно
* [x] PnL и денежный инвариант корректны
* [x] Feed и Engine проверяют совместимость конфигураций
* [x] все прежние тесты Stage E проходят (80/80, ожидания не менялись)
* [x] все тесты Stage A–D проходят (1570/1570, файлы байт-в-байт те же)
* [x] нет изменений Stage A–D (179 файлов, 0 нарушений)
* [x] нет Broker SDK / сетевых запросов / LIVE ордеров / реальных денег
