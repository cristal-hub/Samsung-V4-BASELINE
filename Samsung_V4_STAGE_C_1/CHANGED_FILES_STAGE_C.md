# CHANGED_FILES_STAGE_C.md
# SAMSUNG V4 — NEW STRATEGY ENGINE. STAGE C — ПЕРЕЧЕНЬ ФАЙЛОВ

Дата: 2026-11-28. База: принятый Stage B.1
(`e413c5bd6bdec436ffd7aeece4c28b5e969c6306`).

## 1. Итог

| Категория | Количество |
|---|---|
| ИЗМЕНЁННЫХ существующих файлов | **0** |
| УДАЛЁННЫХ файлов | **0** |
| ДОБАВЛЕННЫХ файлов (исходники Stage C) | **3** |
| ДОБАВЛЕННЫХ файлов (отчёты/доказательства Stage C) | 12 (корень) + 5 (appendix_stage_c/) |

## 2. Изменённые файлы

НЕТ. Побайтовая сверка всех 223 файлов принятого пакета Stage B.1 с
рабочей копией Stage C: 223 совпадают, 0 изменены, 0 отсутствуют
(полный отчёт — STAGE_C_IMMUTABILITY_PROOF.txt). В том числе НЕ
изменены:

* `candidate/strategy_api.py` — контракты Stage A.2.1 (Strategy,
  StrategyConfig, Signal, EntrySignalInput, AttributionContext и др.);
* `candidate/attribution.py` — атрибуция Stage A.2.1;
* `candidate/strategy_state.py` — StrategyState/StateStore/
  StrategyStateManager Stage B.1 (включая исправления дефектов №1–№3);
* `candidate/execution.py`, `candidate/risk_manager.py`,
  `candidate/strategy.py`, `candidate/main.py` и весь остальной
  runtime — торговое исполнение не затронуто;
* `candidate/strategies/legacy_samsung_v4/**` — legacy остаётся
  REGRESSION_ONLY;
* все старые тесты (Stage A/A.1/A.2/A.2.1/B/B.1 и legacy-тесты) —
  не удалены, не ослаблены, не изменены;
* `candidate/tests/fixtures/legacy_golden_signals.json` — golden
  fixtures не перегенерированы.

## 3. Добавленные файлы — исходники Stage C

| Файл | Строк | Содержимое |
|---|---|---|
| `candidate/strategy_contracts.py` | 1716 | Ядро Stage C: ошибки, перечисления, PriceData/check_price, EntryEvaluation/EntryEvaluationRunner, ExitEvaluation/ExitEvaluationRequest, merge_exit_evaluations/ExitMergeResult, ExitDecisionCoordinator/ExitDecisionReport |
| `candidate/tests/test_stage_c_contracts.py` | 829 | 91 тест: состояния Entry/Exit контрактов, отклонение некорректных результатов (включая подклассы), правила merge, детерминированность, конфликтные причины, fail-closed цена |
| `candidate/tests/test_stage_c_exit_service.py` | 683 | 32 теста: координатор end-to-end, fail-closed цена, отсутствие фиктивного исполнения, сохранение состояния, атрибуция/подмена config_hash, изоляция (стратегии/FIGI), конкурентность Stage B.1, misuse |

## 4. Добавленные файлы — отчёты и доказательства Stage C

| Файл | Назначение |
|---|---|
| `README_STAGE_C.md` | точка входа: состав пакета, что читать, как проверить |
| `IMPLEMENTATION_REPORT_STAGE_C.md` | основной отчёт реализации (ТЗ §2–§7) |
| `STAGE_C_ARCHITECTURE_REPORT.md` | архитектура контрактного слоя |
| `TEST_RESULTS_STAGE_C.txt` | сводка до/после + покрытие ТЗ §6 (все 19 сценариев) |
| `DIFF_STAGE_B_1_VS_C.md` | diff-отчёт со сводкой и полным unified diff |
| `DIFF_STAGE_B_1_VS_C.patch` | реальный unified diff (машинный артефакт) |
| `CHANGED_FILES_STAGE_C.md` | настоящий файл |
| `KNOWN_LIMITATIONS_STAGE_C.md` | все известные ограничения |
| `FILE_MANIFEST_SHA256_STAGE_C.txt` | SHA256 manifest всех файлов пакета |
| `ROLLBACK_INSTRUCTIONS_STAGE_C.md` | инструкция отката |
| `VERIFICATION_INSTRUCTIONS_STAGE_C.md` | инструкция проверки |
| `STAGE_C_PRE_IMPLEMENTATION_BASELINE.md` | фиксация ДО реализации (ТЗ §7) |
| `STAGE_C_PRE_BASELINE_FILES.txt` | полный перечень файлов Stage B.1 (223) |
| `STAGE_C_PRE_BASELINE_SHA256.txt` | SHA256 всех 174 файлов candidate/ ДО |
| `STAGE_C_IMMUTABILITY_PROOF.txt` | побайтовая сверка пакета с принятым ZIP |
| `STAGE_C_NO_EXECUTION_CHANGES_PROOF.md` | доказательство: исполнение не изменено, брокерских действий нет |
| `appendix_stage_c/pytest_before_full.log` | полный лог pytest ДО (полный набор, 1261 passed) |
| `appendix_stage_c/pytest_before_canonical.log` | полный лог pytest ДО (канонический, 741 passed) |
| `appendix_stage_c/pytest_after_full.log` | полный лог pytest ПОСЛЕ (полный набор, 1384 passed) |
| `appendix_stage_c/new_tests_list.txt` | список всех 123 новых тестов (имена из реального лога) |

Файлы `appendix_stage_c/` содержат РЕАЛЬНЫЙ вывод pytest
(команды — см. VERIFICATION_INSTRUCTIONS_STAGE_C.md).

## 5. Файлы принятой базы Stage B.1 в корне пакета

Файлы `IMPLEMENTATION_REPORT_STAGE_B.md`, `README_STAGE_B.md`,
`STAGE_B_ARCHITECTURE_REPORT.md`, `TEST_RESULTS_STAGE_B.txt`,
`CHANGED_FILES_STAGE_B.md`, `KNOWN_LIMITATIONS_STAGE_B.md`,
`VERIFICATION_INSTRUCTIONS_STAGE_B.md`, `DIFF_STAGE_B_VS_B_1.md/.patch`,
`ROLLBACK_INSTRUCTIONS_STAGE_B_1.md`, `FILE_MANIFEST_SHA256_STAGE_B.txt`,
`archive/**`, `docs/**` — принадлежат принятому пакету Stage B.1,
сохранены побайтово без изменений и описывают Stage B.1 (НЕ Stage C).
Актуальные отчёты текущего этапа — ТОЛЬКО файлы с суффиксом
`_STAGE_C` в имени.

## 6. SHA256 добавленных файлов Stage C

См. FILE_MANIFEST_SHA256_STAGE_C.txt (полный manifest пакета).
