# IMPLEMENTATION_REPORT_STAGE_C.md
# SAMSUNG V4 — NEW STRATEGY ENGINE. STAGE C
# ТИПИЗИРОВАННЫЕ КОНТРАКТЫ ВХОДА/ВЫХОДА И ДЕТЕРМИНИРОВАННОЕ
# ОБЪЕДИНЕНИЕ ВЫХОДОВ

Дата: 2026-11-28.
Репозиторий: cristal-hub/Samsung-V4-BASELINE.
Использованные принятые ссылки (не изменены, см.
STAGE_C_IMMUTABILITY_PROOF.txt):

* Baseline: `884cefd6f12a99f6adc14b5ed4c9eeda21d32e04`;
* принятая Stage A.2.1: `103d22d34d483fbb7179d1fef07dd0e24b51dfcd`;
* принятый пакет Stage B.1: commit
  `e413c5bd6bdec436ffd7aeece4c28b5e969c6306`.

Режим: READ ONLY DATA / RESEARCH ONLY / OFFLINE TESTS ONLY /
NO LIVE ORDERS / NO REAL MONEY. Сетевых запросов к брокеру, Sandbox или
LIVE нет; заявок нет; торговое исполнение не изменено.

---

## 1. Выполненная работа (ТЗ §2)

Stage C реализован как контрактный слой поверх принятых Stage A.2.1 и
Stage B.1. Добавлен РОВНО ОДИН новый модуль
`candidate/strategy_contracts.py` и два файла тестов; ни один
существующий файл не изменён (побайтовая сверка всех 223 файлов пакета с
принятым ZIP: 223 совпадают, 0 изменены, 0 отсутствуют —
STAGE_C_IMMUTABILITY_PROOF.txt).

| Требование ТЗ | Реализация | Где |
|---|---|---|
| §3.1 Entry contract | `EntryEvaluation` (6 явных состояний) + `EntryEvaluationRunner` | strategy_contracts.py |
| §3.2 Exit contract | `ExitEvaluation` (4 исхода × 3 источника решений) + `ExitEvaluationRequest` | strategy_contracts.py |
| §3.3 Exit merging | `merge_exit_evaluations` + `ExitMergeResult` — чистая функция, явная таблица истинности | strategy_contracts.py |
| §3.4 Missing price fail-closed | `PriceData` (цена > 0 строго), `check_price` (MISSING/INVALID/STALE/OK), блокировка ДО вызова оценщиков | strategy_contracts.py |
| §3.5 State integration | `ExitDecisionCoordinator` — только через `StrategyStateManager` Stage B.1, атомарный `update_state` | strategy_contracts.py |
| §6 Тесты | 123 новых теста (91 + 32) | tests/test_stage_c_contracts.py, tests/test_stage_c_exit_service.py |
| §7 Проверка | diff, manifest, логи до/после, proof-файлы | корень пакета |

## 2. Entry contract (ТЗ §3.1)

`EntryEvaluation` — типизированный неизменяемый результат проверки
входа. Однозначно различает (ТЗ §3.1):

* `ENTRY_ALLOWED` — разрешённый вход (ЕДИНСТВЕННОЕ состояние,
  допускающее вход);
* `NO_SIGNAL` — отсутствие сигнала;
* `ENTRY_FORBIDDEN` — запрет входа;
* `DATA_INSUFFICIENT` — недостаточность/некорректность исходных данных
  (свечи отсутствуют, цена NaN/Infinity/<=0/не число);
* `INVALID_STRATEGY_RESULT` — некорректный результат стратегии
  (не точный тип Signal, подмена strategy_id/config_hash, чужой figi,
  неизвестное направление);
* `EVALUATION_ERROR` — исключение стратегии при вычислении.

Атрибуция каждого результата: `strategy_id`, `config_hash`, `figi`,
`outcome`, `reason_code` (машиночитаемый код `[A-Z][A-Z0-9_]*`),
`diagnostics` (JSON-совместимые, замороженные).

Запрет неявного разрешения входа (ТЗ §3.1): все пять не-разрешающих
состояний покрывают ошибки, отсутствие данных и некорректные результаты
стратегии; тест `TestEntryContractStates::test_only_allowed_state_permits_entry`
проверяет, что ни одно другое состояние не может быть истолковано как
разрешение; `TestEntryRunner` проверяет конвертацию исключений и
подделок.

Смысл принятого контракта Stage A не меняется: стратегия вызывается как
в Stage A (`Strategy.evaluate_entry(EntrySignalInput, StrategyConfig) ->
Signal`); Stage C добавляет типизированную границу результата.

## 3. Exit contract (ТЗ §3.2)

`ExitEvaluation` — типизированный неизменяемый результат оценки выхода:

* исходы: `STRATEGIC_EXIT`, `PROTECTIVE_EXIT`, `NO_EXIT`,
  `EVALUATION_BLOCKED`;
* источники решений (`ExitDecisionSource`): `STRATEGIC`, `PROTECTIVE`,
  `PRICE_GATE` — стратегический и защитный выходы остаются РАЗНЫМИ
  источниками решений;
* согласованность проверяется при создании: STRATEGIC_EXIT исходит
  только от STRATEGIC, PROTECTIVE_EXIT — только от PROTECTIVE;
  NO_EXIT — от слоя оценки (STRATEGIC/PROTECTIVE), EVALUATION_BLOCKED —
  от цены (PRICE_GATE) или от слоя;
* `exit_type` обязателен ТОЛЬКО у реальных выходов и запрещён у
  NO_EXIT/EVALUATION_BLOCKED (несуществующий выход не типизируется);
* обязательная атрибуция (ТЗ §3.2): strategy_id, config_hash, figi,
  источник решения, причина (reason_code), тип выхода, diagnostics,
  decided_at (ISO-8601 с часовым поясом).

`ExitEvaluationRequest` — типизированный запрос оценщику: атрибуция
проверена, данные состояния — ImmutableMapping из StrategyState
Stage B.1, цена — только прошедшая fail-closed проверку `PriceData`.

## 4. Exit merging (ТЗ §3.3)

`merge_exit_evaluations(strategic, protective) -> ExitMergeResult` —
ЧИСТАЯ функция (без времени, случайности, обращения к состоянию).
Явные правила приоритета (`EXIT_MERGE_RULES_VERSION =
"exit_merge_rules_v1"`), таблица истинности:

| защитный \ стратегический | STRATEGIC_EXIT | NO_EXIT | EVALUATION_BLOCKED |
|---|---|---|---|
| **PROTECTIVE_EXIT** | PROTECTIVE_EXIT | PROTECTIVE_EXIT | PROTECTIVE_EXIT |
| **NO_EXIT** | STRATEGIC_EXIT | NO_EXIT | INCOMPLETE_STRATEGIC_EVALUATION |
| **EVALUATION_BLOCKED** | INCOMPLETE_PROTECTIVE_EVALUATION | INCOMPLETE_PROTECTIVE_EVALUATION | INCOMPLETE_PROTECTIVE_EVALUATION |

Свойства (ТЗ §3.3) и их проверка тестами:

* защитный выход нельзя потерять: PROTECTIVE_EXIT побеждает во ВСЕХ
  трёх случаях (§6.5);
* стратегический выход не может отменить/подавить защитный: при двух
  выходах побеждает защитный; в diagnostics пишется
  `note=PROTECTIVE_PRIORITY_OVER_STRATEGIC_EXIT` (§6.6);
* отсутствие стратегического выхода не отменяет защитный (§6.6);
* конфликтующие результаты — по таблице выше, никакого скрытого
  приоритета (§6.8: обе причины сохраняются в diagnostics —
  `strategic.reason_code` и `protective.reason_code`);
* итог сохраняет источник и причину: decision_source/reason_code/
  exit_type победившего решения либо код незавершённости (§6.5–§6.8);
* детерминированность: 10 повторов дают равные результаты,
  включая diagnostics (§6.7);
* объединение результатов с НЕсогласованной атрибуцией (другой
  strategy_id/config_hash/figi) запрещено — ExitMergeViolationError;
  все ошибки входа merge дают единый тип ExitMergeViolationError.
* незавершённая оценка любого слоя подавляет ИСПОЛНИМЫЙ итог
  (INCOMPLETE_*): fail-closed — итоговое решение не выносится, при этом
  информация стратегического слоя сохраняется в diagnostics (ничего не
  отбрасывается молча).

## 5. Missing price — fail-closed (ТЗ §3.4)

`PriceData` — единственная форма цены в контракте: конечное число
СТРОГО больше нуля (NaN/Infinity/0/отрицательные/bool отклоняются
при создании), ISO-8601 метка с часовым поясом, непустой источник.
Нулевая цена не может попасть в контракт ни при каких обстоятельствах.

`check_price(price, *, expected_figi, now, max_age_seconds)`:

* `price is None` -> PRICE_MISSING (никакой подстановки нулём или
  «последней известной ценой» — такого механизма в контракте НЕ
  существует);
* не точный тип PriceData -> PRICE_INVALID/PRICE_WRONG_TYPE
  (подклассы и duck-typing отклоняются);
* чужой FIGI -> PRICE_INVALID/PRICE_FOREIGN_FIGI (чужая цена не
  используется);
* метка в будущем -> PRICE_INVALID/PRICE_FROM_FUTURE (рассинхрон часов
  не проходит молча);
* возраст > явно заданного max_age_seconds -> PRICE_STALE;
  max_age_seconds — ЯВНЫЙ обязательный параметр; None означает
  отключённую проверку устаревания явным решением оператора (скрытого
  порога по умолчанию нет).

Координатор: при `price_required=True` и непройденной проверке цены —
оценщики НЕ вызываются, состояние НЕ изменяется, возвращается отчёт с
итогом `INCOMPLETE_PRICE_EVALUATION`, диагностикой и явным
`evaluators_called=False`. Переданная, но некорректная/устаревшая цена
блокируется даже при `price_required=False` (мусорные данные не доходят
до оценщиков молча). Отсутствие цены НЕ приводит к молчаливому
продолжению расчёта (ТЗ §3.4): это отдельный типизированный результат.

## 6. Интеграция состояния (ТЗ §3.5)

`ExitDecisionCoordinator(manager, strategic_evaluator,
protective_evaluator, clock)`:

* `manager` принимается ТОЛЬКО точного типа `StrategyStateManager`
  (Stage B.1); состояние изолировано по (strategy_id, FIGI);
* `config_hash` проверяется: конфиг принимается ТОЛЬКО точного типа
  `StrategyConfig`; `AttributionContext.from_config` ПЕРЕПРОВЕРЯЕТ хеш
  ИСХОДНЫМ алгоритмом Stage A.2.1 по фактическим параметрам ДО любой
  оценки (подмена config_hash отклоняется; тест
  `test_fabricated_config_hash_rejected_by_stage_a2_1_recheck`);
* несовпадение config_hash сохранённого состояния —
  StateConfigMismatchError из Stage B.1 без автопереноса;
* глобальное изменяемое состояние не используется; вторая система
  хранения не создаётся (только StateStore через менеджер);
* обновления состояния — ТОЛЬКО через существующий атомарный API
  `manager.update_state(..., updater=...)` (read-modify-write под
  замком хранилища Stage B.1); ошибки состояния пробрасываются как
  есть (StateCorruptionError при повреждённой записи — тест
  `test_corrupted_state_error_propagates_unmasked`);
* при исполнимом итоге (PROTECTIVE_EXIT / STRATEGIC_EXIT / NO_EXIT) в
  данные состояния пары записывается ключ `last_exit_evaluation`
  (сводка решения с полной атрибуцией); при INCOMPLETE_* состояние НЕ
  изменяется вовсе — нельзя менять состояние «как будто выход
  состоялся» (ТЗ §3.4);
* запись — КОНТРАКТНОЕ решение, не исполнение: заявок нет.

Реализация Stage B.1 НЕ менялась (в этом не было необходимости:
атомарный API Stage B.1 полностью покрывает потребности Stage C).

## 7. Защита от обхода проверок (ТЗ §5)

* Все контрактные объекты — frozen dataclass с валидацией в
  `__post_init__` (setattr/delattr отклоняются).
* ВСЕ потребители контрактов (merge, координатор, валидаторы
  `validate_entry_evaluation`/`validate_exit_evaluation`) принимают
  объекты ТОЛЬКО точного типа (`type(x) is X`) — подкласс с ослабленным
  `__post_init__` не проходит границу потребителя. Это покрыто тестами
  (`test_validator_rejects_subclass`, `test_merge_rejects_subclasses`,
  `test_subclass_result_from_evaluator_rejected`).
* Атрибуция перепроверяется на каждой границе: валидаторы (expected_*),
  merge (попарное равенство), отчёт (результаты слоёв против отчёта),
  координатор (Stage A.2.1 перепроверка config_hash).
* Граница безопасности оценщиков — ПРОВЕРКА РЕЗУЛЬТАТА, а не тип
  оценщика: исключение или некорректный/чужой результат конвертируется
  в EVALUATION_BLOCKED этого источника (ничего не исполняется).

## 8. Проверка изменений (ТЗ §7)

До реализации зафиксировано (STAGE_C_PRE_IMPLEMENTATION_BASELINE.md,
STAGE_C_PRE_BASELINE_FILES.txt, STAGE_C_PRE_BASELINE_SHA256.txt):

* полный перечень файлов Stage B.1 (223 файла);
* SHA256 всех 174 файлов candidate/;
* точный список планируемых изменений: ДОБАВИТЬ 3 файла
  (candidate/strategy_contracts.py, candidate/tests/test_stage_c_contracts.py,
  candidate/tests/test_stage_c_exit_service.py), НЕ ИЗМЕНЯТЬ ни одного
  существующего файла.

После реализации предоставлено:

* полный diff: DIFF_STAGE_B_1_VS_C.md + DIFF_STAGE_B_1_VS_C.patch
  (реальный unified diff);
* перечень изменённых/добавленных файлов: CHANGED_FILES_STAGE_C.md
  (изменённых — 0, добавленных — 3);
* SHA256 manifest: FILE_MANIFEST_SHA256_STAGE_C.txt;
* подтверждение неизменности Stage A.2.1 и Stage B.1:
  STAGE_C_IMMUTABILITY_PROOF.txt (223/223 файла побайтово совпадают с
  принятым ZIP);
* полный лог pytest до и после: appendix_stage_c/pytest_before_full.log,
  pytest_before_canonical.log, pytest_after_full.log,
  pytest_after_canonical.log (сводка — TEST_RESULTS_STAGE_C.txt):
  ДО 1261/741 passed, ПОСЛЕ 1384/864 passed, 0 failed;
* список всех новых тестов: appendix_stage_c/new_tests_list.txt
  (123 теста с полными именами из реального лога);
* список всех известных ограничений: KNOWN_LIMITATIONS_STAGE_C.md;
* отдельное доказательство, что Stage C не изменил торговое исполнение
  и не добавил брокерских действий: STAGE_C_NO_EXECUTION_CHANGES_PROOF.md;
* инструкция проверки: VERIFICATION_INSTRUCTIONS_STAGE_C.md;
* инструкция отката: ROLLBACK_INSTRUCTIONS_STAGE_C.md.

## 9. Тестирование (ТЗ §6)

123 новых теста покрывают все 19 обязательных сценариев ТЗ §6
(полная таблица соответствия — TEST_RESULTS_STAGE_C.txt, раздел 1).
Прогоны (реальные логи в appendix_stage_c/):

| Прогон | До Stage C | После Stage C |
|---|---|---|
| полный набор (`python -m pytest`) | 1261 passed | 1384 passed |
| канонический набор (`python -m pytest tests`) | 741 passed | 864 passed |

Ни один старый тест не удалён, не пропущен и не ослаблен; golden
fixtures не перегенерированы (tests/fixtures/legacy_golden_signals.json
побайтово неизменен).

## 10. Формат результата (ТЗ §9)

Один полный ZIP-архив возвращён непосредственно в чат: полный candidate,
исходники Stage C, тесты, отчёты, diff, manifest, полный лог
тестирования, инструкция проверки, инструкция отката. Файлы на GitHub
не загружались; коммиты/ветки/PR не создавались; в пользовательские
папки ничего не записано.

## 11. Финальное условие (ТЗ §10)

Конфликтов с принятыми решениями Stage A.2.1 или Stage B.1 НЕ
обнаружено: Stage C потребляет принятые контракты через их публичные
API без изменения смысла. Stage D (strategy-specific risk sizing) и
Stage E (исторический event-driven simulator) в рамках этой задачи НЕ
начинались.
