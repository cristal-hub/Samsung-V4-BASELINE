# SAMSUNG V4 — STAGE C.1 — PRICE GATE BEFORE STATE ACCESS (README)

Дата: 2026-11-28
Статус: кандидат исправления Stage C — НА ПРОВЕРКЕ (Stage C не принят;
Stage C.1 — корректирующий шаг поверх кандидата Stage C).

## Что это

Корректирующая итерация над кандидатом Stage C (типизированные контракты
входа/выхода, детерминированное объединение выходов, интеграция состояния
Stage B.1). Найден и исправлен дефект ПОРЯДКА операций в
`ExitDecisionCoordinator.evaluate_and_record()`:

* **Дефект:** `manager.get_state()` вызывался ДО проверки цены. Так как
  `StrategyStateManager.get_state()` Stage B.1 создаёт запись при
  отсутствии, плохая цена (отсутствующая/некорректная/устаревшая)
  приводила к СОЗДАНИЮ записи состояния ещё до fail-closed блокировки —
  побочный эффект на хранилище, противоречащий §3.4 Stage C.
* **Исправление:** проверка цены выполняется СТРОГО ПЕРВЕЕ доступа к
  состоянию. При блокирующей цене возвращается
  `INCOMPLETE_PRICE_EVALUATION` без `get_state`, без оценщиков, без
  записи/изменения состояния. Только после price gate: состояние →
  оценщики → merge → запись при допустимом итоге.
* **Правила цены сохранены:** `price_required=True` — отсутствие/
  некорректность/устаревание блокируют; `price_required=False` —
  отсутствие допустимо, но переданная некорректная/устаревшая цена
  блокирует; нулевая цена и подстановка последней известной запрещены.

## Изменённые файлы (ровно 2, в границах ТЗ §5)

1. `candidate/strategy_contracts.py` — порядок операций + документация.
2. `candidate/tests/test_stage_c_exit_service.py` — +7 тестов
   (класс `TestPriceGateBeforeStateAccess`, ТЗ §4), старые не тронуты.

## Прогоны (реальные логи в appendix_stage_c1/)

| Набор | ДО C.1 | ПОСЛЕ C.1 |
|---|---|---|
| полный (`python -m pytest`) | 1384 passed | 1391 passed |
| канонический (`python -m pytest tests`) | 864 passed | 871 passed |

0 failed, 0 skipped в обоих наборах; +7 = только новые тесты C.1;
старые не удалены/не ослаблены; golden fixtures не перегенерировались.

## Документы Stage C.1

* `STAGE_C1_PRE_IMPLEMENTATION_BASELINE.md` — фиксация базы ДО правки;
* `IMPLEMENTATION_REPORT_STAGE_C1.md` — отчёт по реализации;
* `DIFF_STAGE_C_VS_C1.patch` — точный diff Stage C → Stage C.1;
* `STAGE_C1_CHANGED_FILES.txt` — список изменённых файлов;
* `FILE_MANIFEST_SHA256_STAGE_C1.txt` — SHA256 manifest полного пакета;
* `STAGE_C1_IMMUTABILITY_PROOF.txt` — побайтовое доказательство
  неизменности A.2.1/B.1 и всех прочих файлов;
* `STAGE_C1_NO_EXECUTION_CHANGES_PROOF.md` — исполнение не затронуто,
  брокерских действий нет;
* `TEST_RESULTS_STAGE_C1.txt` — сводные результаты и покрытие сценариев;
* `KNOWN_LIMITATIONS_STAGE_C1.md`; `VERIFICATION_INSTRUCTIONS_STAGE_C1.md`;
  `ROLLBACK_INSTRUCTIONS_STAGE_C1.md`;
* `STAGE_C1_PRE_BASELINE_FILES.txt` / `STAGE_C1_PRE_BASELINE_SHA256.txt` —
  перечень и хеши ДО реализации;
* `appendix_stage_c1/` — полные логи pytest ДО/ПОСЛЕ (полный и
  канонический наборы), negative-check (новые тесты против старого кода),
  список новых тестов, проверка отсутствия потерь тестов.

## Архив предыдущих этапов

`archive/` и документы Stage A/B/B.1/C сохранены без изменений;
контракты Stage A.2.1 и Stage B.1 не менялись.
