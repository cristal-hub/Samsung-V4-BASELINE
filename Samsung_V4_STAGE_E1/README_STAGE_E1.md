# SAMSUNG V4 — STAGE E.1 — HISTORICAL ENGINE CORRECTIONS

Этап корректировки и укрепления Stage E: три архитектурных исправления
исторического симулятора + ФИНАЛЬНЫЕ ПРАВКИ (два небольших исправления
существующей поставки E.1, без новой версии/папки) + ЗАЩИТА ОТ ЧИСЛОВОГО
ПЕРЕПОЛНЕНИЯ (точечная защита split_execution_deviation, без новой
версии/папки). Существующая архитектура Stage E сохранена; Stage A–D не
изменены; стратегия и её пороги не тронуты; никакой оптимизации параметров.

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
    │   ├── __init__.py        (M@E.1)  экспорты Stage E.1
    │   ├── models.py          (M@E.1)  GapIncident, EngineConfig.calendar, константы
    │   ├── calendar.py        (A@E.1, M@финал)  TradingCalendar (Correction №1)
    │   ├── data_feed.py       (M@E.1, M@финал)  контроль пропусков + документация покрытия всей серии
    │   ├── execution.py       (M@E.1, M@финал, M@guard)  раздельный учёт slippage/improvement (№2) + валидация чисел + защита от переполнения
    │   ├── ledger.py          (M@E.1)  improvement-поля, total_execution_cost
    │   ├── report.py          (M@E.1)  costs/gap_verification/metadata
    │   ├── engine.py          (M@E.1)  согласованность конфигураций (№3)
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
        ├── test_stage_e1_calendar.py           (A@E.1, M@финал)  28 тестов
        ├── test_stage_e1_slippage.py           (A@E.1, M@финал, M@guard)  44 теста
        └── test_stage_e1_config_consistency.py (A@E.1)  11 тестов
```

(A) — новый файл, (M) — изменён; @E.1 — раунд 1 (первоначальная поставка
E.1 относительно принятого Stage E), @финал — ФИНАЛЬНЫЕ ПРАВКИ (раунд 2
относительно первоначальной поставки E.1: изменено 5 файлов, добавлено 0,
удалено 0), @guard — ЗАЩИТА ОТ ПЕРЕПОЛНЕНИЯ (раунд 3 относительно
состояния после раунда 2: изменено 2 файла — historical_engine/execution.py
и tests/test_stage_e1_slippage.py, добавлено 0, удалено 0 —
см. STAGE_E1_CHANGED_AND_NEW_FILES.txt).
Все прочие файлы дерева candidate совпадают байт-в-байт с Stage E
(179 файлов проверено, 0 нарушений — см. NO_CHANGES_ABCD_PROOF).

## Три исправления (кратко)

1. **Календарно-корректное обнаружение пропусков** — новый компонент
   `TradingCalendar` из явно переданных сессий различает: подтверждённый
   пропуск ожидаемой торговой свечи (A), перерыв сессии (B), выходной/
   праздник (C), невозможность проверки (D). STRICT отклоняет только
   подтверждённые пропуски; отсутствие календаря ЯВНО помечается как
   ограниченная проверка (без ложного подтверждения полноты).
   **Финальные правки:** покрытие календарём проверяется для ВСЕЙ серии
   независимо от наличия отклонений — начало и конец серии проверяются
   ОТДЕЛЬНО; статус FULL только при действительном покрытии всей серии.
2. **Раздельный учёт slippage** — неблагоприятное проскальзывание (>= 0)
   и улучшение цены (>= 0) разделены по направлению сделки; прежняя
   отрицательная запись «slippage» на TP после гэпа устранена;
   `total_execution_cost = total_commission + total_adverse_slippage_cost`
   (документировано); комиссия отдельна; цена исполнения НЕ изменена.
   **Финальные правки:** конечность ВСЕХ числовых аргументов
   `split_execution_deviation` проверяется через `math.isfinite()`
   (NaN / ±Infinity / нули / отрицательные отклоняются fail-closed;
   прежде +Infinity проходил проверку знаком).
   **Защита от переполнения (раунд 3):** конечность ПРОМЕЖУТОЧНЫХ
   результатов (`size = quantity * contract_multiplier`,
   `adverse_slippage_cost`, `favorable_price_improvement`) проверяется
   `math.isfinite()` ДО возврата: произведение конечных аргументов может
   переполниться до ±Infinity (пример: quantity=10**300 при
   contract_multiplier=1e100); переполнение -> `ExecutionError`;
   возврат inf/nan невозможен; формулы и порядок корректных
   float-операций НЕ изменены.
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
python -m pytest tests -q            # канонический: 1213 passed
python -m pytest -q                  # полный:      1733 passed
```

Отдельные группы (тоже из корня candidate):

```bash
# Stage E + E.1 — 8 файлов test_stage_e*/test_stage_e1* в tests/:
#   163 passed
python -m pytest \
  tests/test_stage_e_data_feed.py tests/test_stage_e_engine_decisions.py \
  tests/test_stage_e_execution_ledger.py tests/test_stage_e_integration.py \
  tests/test_stage_e_report.py tests/test_stage_e1_calendar.py \
  tests/test_stage_e1_slippage.py tests/test_stage_e1_config_consistency.py -q

# Stage A–D в ШИРОКОМ смысле — всё дерево без 8 файлов Stage E/E.1
# (всё, что существовало до Stage E; совпадает с полным pytest конца
# этапа D.1): 1570 passed
python -m pytest \
  --ignore=tests/test_stage_e_data_feed.py \
  --ignore=tests/test_stage_e_engine_decisions.py \
  --ignore=tests/test_stage_e_execution_ledger.py \
  --ignore=tests/test_stage_e_integration.py \
  --ignore=tests/test_stage_e_report.py \
  --ignore=tests/test_stage_e1_calendar.py \
  --ignore=tests/test_stage_e1_slippage.py \
  --ignore=tests/test_stage_e1_config_consistency.py -q

# Stage A–D в УЗКОМ смысле — только 15 файлов test_stage_*, добавленных
# в tests/ этапами A–D (без исходных тестов репозитория): 799 passed
python -m pytest \
  tests/test_stage_a_attribution.py tests/test_stage_a_engine_config.py \
  tests/test_stage_a_legacy_adapter.py tests/test_stage_a_legacy_profiles.py \
  tests/test_stage_a_schema.py tests/test_stage_a_strategy_api.py \
  tests/test_stage_a1_attribution_explicit.py \
  tests/test_stage_a1_config_immutability.py \
  tests/test_stage_a2_config_hash_integrity.py \
  tests/test_stage_a2_1_context_integrity.py \
  tests/test_stage_b_state_isolation.py \
  tests/test_stage_b1_state_key_and_concurrency.py \
  tests/test_stage_c_contracts.py tests/test_stage_c_exit_service.py \
  tests/test_stage_d_strategy_risk.py -q
```

Счётчики связаны тождествами: 1733 = 1570 + 163;
1570 = 520 (исходные тесты в корне candidate) + 251 (20 исходных
файлов репозитория в tests/) + 799 (файлы этапов A–D);
1213 (tests/) = 251 + 799 + 163. Подробнее — STAGE_E1_TEST_RESULTS.txt,
раздел «РАЗЪЯСНЕНИЕ СЧЁТЧИКОВ».

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
* [x] все тесты Stage A–D проходят (Stage A–D в широком смысле —
      всё дерево без 8 файлов Stage E/E.1: 1570/1570 = 1733 − 163;
      совпадает с полным pytest конца этапа D.1; из них 15 файлов
      test_stage_*, добавленных этапами A–D, дают 799/799 —
      файлы байт-в-байт те же; состав и команды счётчиков —
      STAGE_E1_TEST_RESULTS.txt, «Отдельные группы» и
      «Разъяснение счётчиков»)
* [x] нет изменений Stage A–D (179 файлов, 0 нарушений)
* [x] нет Broker SDK / сетевых запросов / LIVE ордеров / реальных денег

## Критерии приёмки ФИНАЛЬНЫХ ПРАВОК — статус

* [x] покрытие календаря проверяется для всей серии, независимо от
      наличия обнаруженных пропусков (начало и конец — отдельно)
* [x] при любой части серии вне покрытия статус НЕ FULL
      (PERFORMED_PARTIAL_CALENDAR_COVERAGE_INSUFFICIENT)
* [x] непокрытые даты не считаются выходными или праздниками
* [x] STRICT не отклоняет неподтверждённые инциденты как подтверждённые
* [x] конечность всех числовых аргументов split_execution_deviation
      через math.isfinite: NaN / ±Infinity / нули / отрицательные
      отклоняются (отдельный тест на каждый случай, 23 теста)
* [x] формулы adverse slippage и favorable price improvement НЕ изменены
* [x] все прежние тесты Stage E/E.1 проходят (163/163 с новыми тестами
      раунда 3; ожидания первоначальной поставки не менялись)
* [x] no-test-loss (раунд 2): 1696 -> 1728, потеряно 0
* [x] no-test-loss (раунд 3): 1728 -> 1733, потеряно 0

## Критерии приёмки ЗАЩИТЫ ОТ ПЕРЕПОЛНЕНИЯ (раунд 3) — статус

* [x] конечность size = quantity * contract_multiplier проверяется
      до использования (произведение конечных аргументов может дать inf)
* [x] конечность adverse_slippage_cost проверяется до возврата
* [x] конечность favorable_price_improvement проверяется до возврата
* [x] переполнение -> ExecutionError (возвращать inf/nan запрещено)
* [x] все возвращаемые значения — конечные неотрицательные числа
      без NaN и ±Infinity
* [x] формулы расчёта, порядок корректных float-операций и
      экономическая модель НЕ изменены (точное равенство покрыто тестом)
* [x] календарь, data_feed, PnL/комиссия/ledger, алгоритмы исполнения,
      стратегия, Stage A–D — не затронуты (179 файлов, 0 нарушений)
* [x] прежние тесты не ослаблялись и не удалялись (no-test-loss: 0)
