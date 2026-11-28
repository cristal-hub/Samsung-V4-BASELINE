# README_STAGE_C.md
# SAMSUNG V4 — NEW STRATEGY ENGINE. STAGE C
# ТИПИЗИРОВАННЫЕ КОНТРАКТЫ ВХОДА/ВЫХОДА И ДЕТЕРМИНИРОВАННОЕ
# ОБЪЕДИНЕНИЕ ВЫХОДОВ

Дата: 2026-11-28.

## 1. Что это

Полный candidate-пакет Stage C: принятая база Stage B.1
(`e413c5bd6bdec436ffd7aeece4c28b5e969c6306`, побайтово неизменна —
223/223 файла, см. STAGE_C_IMMUTABILITY_PROOF.txt) + контрактный слой
Stage C (ровно 3 новых файла исходников/тестов).

Stage C реализует (ТЗ §2–§3):

1. **Entry contract** — `EntryEvaluation` (6 явных состояний;
   единственное, допускающее вход — `ENTRY_ALLOWED`) + рантайм
   `EntryEvaluationRunner`, конвертирующий ВСЕ проблемы в явные
   НЕ-разрешающие состояния.
2. **Exit contract** — `ExitEvaluation` (стратегический выход /
   защитный выход / отсутствие выхода / невозможность безопасной
   оценки) с разными источниками решений (STRATEGIC / PROTECTIVE /
   PRICE_GATE) и обязательной атрибуцией.
3. **Exit merging** — `merge_exit_evaluations`: чистая функция,
   явная таблица истинности, защитный выход побеждает ВСЕГДА,
   детерминированность покрыта тестами.
4. **Missing price — fail-closed** — `PriceData` (строго > 0) +
   `check_price` (MISSING/INVALID/STALE/OK); подстановок нулём или
   «последней известной ценой» НЕ существует; при провале цены
   оценщики не вызываются, состояние не изменяется.
5. **State integration** — `ExitDecisionCoordinator` работает ТОЛЬКО
   через `StrategyStateManager` Stage B.1 (изоляция по (strategy_id,
   FIGI), перепроверка config_hash алгоритмом Stage A.2.1, атомарный
   `update_state`, ошибки состояния не маскируются).

## 2. Режим

READ ONLY DATA / RESEARCH ONLY / OFFLINE TESTS ONLY / NO LIVE ORDERS /
NO REAL MONEY. Никаких сетевых запросов к брокеру, Sandbox или LIVE.
Торговое исполнение не изменено, брокерские действия не добавлены —
доказательство: STAGE_C_NO_EXECUTION_CHANGES_PROOF.md.

## 3. Состав пакета (что читать в каком порядке)

| Шаг | Файл | Содержимое |
|---|---|---|
| 1 | README_STAGE_C.md | этот файл |
| 2 | IMPLEMENTATION_REPORT_STAGE_C.md | основной отчёт реализации |
| 3 | STAGE_C_ARCHITECTURE_REPORT.md | архитектура контрактного слоя |
| 4 | TEST_RESULTS_STAGE_C.txt | сводка до/после + покрытие ТЗ §6 (19 сценариев) |
| 5 | DIFF_STAGE_B_1_VS_C.md / .patch | реальный diff B.1 -> C |
| 6 | CHANGED_FILES_STAGE_C.md | перечень файлов (изменённых 0, добавлено 3+отчёты) |
| 7 | FILE_MANIFEST_SHA256_STAGE_C.txt | SHA256 manifest пакета |
| 8 | STAGE_C_IMMUTABILITY_PROOF.txt | побайтовая сверка с принятым ZIP Stage B.1 |
| 9 | STAGE_C_NO_EXECUTION_CHANGES_PROOF.md | доказательство неизменности исполнения |
| 10 | KNOWN_LIMITATIONS_STAGE_C.md | все известные ограничения |
| 11 | VERIFICATION_INSTRUCTIONS_STAGE_C.md | как проверить |
| 12 | ROLLBACK_INSTRUCTIONS_STAGE_C.md | как откатить |
| 13 | STAGE_C_PRE_IMPLEMENTATION_BASELINE.md | фиксация ДО (ТЗ §7) |
| 14 | appendix_stage_c/ | полные реальные логи pytest до/после + список 123 новых тестов |

Отчёты предыдущего этапа (Stage B/B.1: `*_STAGE_B*.md`, `archive/`,
`docs/`) сохранены побайтово как часть принятого пакета и описывают
Stage B.1 — НЕ Stage C.

## 4. Быстрый старт проверки

```bash
cd candidate
python -m pytest tests/test_stage_c_contracts.py -v     # 91 passed
python -m pytest tests/test_stage_c_exit_service.py -v  # 32 passed
python -m pytest tests -v                               # 864 passed
python -m pytest -v                                     # 1384 passed
```

Полная инструкция — VERIFICATION_INSTRUCTIONS_STAGE_C.md.

## 5. Итоги

| Прогон | До Stage C | После Stage C |
|---|---|---|
| полный набор | 1261 passed | 1384 passed |
| канонический набор | 741 passed | 864 passed |

Разница — ровно +123 новых тестов Stage C. Ни один старый тест не
удалён/не ослаблен; golden fixtures не перегенерированы; Stage A.2.1,
Stage B.1, legacy_samsung_v4 и baseline-файлы торговли побайтово
неизменны.

## 6. Границы

Stage C — контрактный слой и интеграция состояния. НЕ реализованы:
симулятор, загрузчик исторических данных, Sandbox adapter, заявки,
брокерское исполнение, risk sizing, EmergencyExitController, гибрид
LIMIT→reconcile→MARKET, новая торговая стратегия, оптимизация,
Force Trade, изменения legacy_samsung_v4 (REGRESSION_ONLY).
Stage D (risk sizing) и Stage E (симулятор) не начинались.
