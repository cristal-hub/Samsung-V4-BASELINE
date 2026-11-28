# IMPLEMENTATION REPORT — STAGE C.1 — PRICE GATE BEFORE STATE ACCESS

Дата: 2026-11-28
База: Stage C candidate (`9a69a300e6759f9264d5feb1a6b54ea80f615e4a`,
побайтово = доставленный пакет, 246/246 manifest OK).
Принятые неизменяемые этапы: A.2.1 `103d22d34d483fbb7179d1fef07dd0e24b51dfcd`,
B.1 `e413c5bd6bdec436ffd7aeece4c28b5e969c6306` — побайтово не изменены.
Режим: READ ONLY DATA / RESEARCH ONLY / OFFLINE TESTS ONLY /
NO LIVE ORDERS / NO REAL MONEY.

## 1. Дефект и его причина

В `ExitDecisionCoordinator.evaluate_and_record()` порядок был:
1) проверка конфигурации; 2) `manager.get_state(...)`; 3) проверка цены;
4) при плохой цене — возврат `INCOMPLETE_PRICE_EVALUATION`.

`StrategyStateManager.get_state()` Stage B.1 при отсутствии записи
создаёт новое состояние (`_get_or_create` → `StateStore.get_or_create`,
создание — штатное поведение Stage B.1, контракт НЕ меняется). Поэтому
при отсутствующей/некорректной/устаревшей цене координатор создавал
запись состояния ДО блокировки оценки — побочный эффект на хранилище
при fail-closed пути, противоречащий заявленному поведению §3.4 Stage C.

## 2. Исправление (ТЗ §3 — обязательный порядок)

Новый порядок в `evaluate_and_record()`:
1. Проверка типов и атрибуции конфигурации (точный тип `StrategyConfig`,
   `AttributionContext.from_config` — перепроверка config_hash алгоритмом
   Stage A.2.1) — без изменений.
2. Проверка FIGI (`validate_figi` Stage B) — без изменений.
3. Проверка цены `check_price(...)` — ПЕРЕНЕСЕНА ДО доступа к состоянию.
4. Если проверка цены блокирует оценку (`price_required=True` и любой
   исход кроме `PRICE_OK`; `price_required=False` и `PRICE_INVALID`/
   `PRICE_STALE`): возвращается `INCOMPLETE_PRICE_EVALUATION`;
   оценщики НЕ вызываются; `manager.get_state` НЕ вызывается; запись
   состояния не создаётся; существующая не изменяется.
5. Только после прохождения price gate: `manager.get_state(...)` →
   `ExitEvaluationRequest` → вызов оценщиков → `merge_exit_evaluations` →
   запись результата ТОЛЬКО при допустимом итоговом исходе
   (PROTECTIVE_EXIT / STRATEGIC_EXIT / NO_EXIT) через атомарный
   `manager.update_state` Stage B.1.

Сохранённые правила (без изменений семантики):
* `price_required=True`: отсутствие, некорректность или устаревание
  блокируют оценку;
* `price_required=False`: отсутствие цены допускается, но переданная
  некорректная или устаревшая цена блокирует оценку;
* нулевая цена и подстановка последней известной цены запрещены
  (механизма подстановки не существует);
* контракт Stage B.1 не изменён; альтернативное хранилище не создано.

## 3. Изменённые файлы (ровно границы ТЗ §5)

| Файл | Тип изменения | Суть |
|---|---|---|
| `candidate/strategy_contracts.py` | изменён | в `evaluate_and_record()` price gate перенесён до `manager.get_state()`; комментарии и docstring координатора/метода дополнены правилом порядка Stage C.1; логика проверок, проверяемые значения и правила цены НЕ менялись |
| `candidate/tests/test_stage_c_exit_service.py` | дополнен | +1 импорт `os`, +1 блок заголовка, + `_json_file_names()`, + класс `TestPriceGateBeforeStateAccess` — 7 новых тестов (§4); старые тесты не тронуты |

Diff: `DIFF_STAGE_C_VS_C1.patch`. Список:
`STAGE_C1_CHANGED_FILES.txt`. Manifest: `FILE_MANIFEST_SHA256_STAGE_C1.txt`.

## 4. Доказательство того, что тесты ловят дефект (negative check)

7 новых тестов прогнаны против ДО-исправного кода Stage C (исправление
убрано, тесты добавлены):
* сценарии 1-3 (блокирующая цена + отсутствующая запись) — **FAILED**
  на старом коде (запись состояния создавалась), т.е. тесты
  действительно ловят дефект;
* сценарии 4-7 — PASSED на старом коде (эти сценарии фиксируют
  требуемое поведение и защищают от регрессии).
Лог: `appendix_stage_c1/negative_check_pre_fix.log`.

## 5. Прогрессия прогонов (реальные логи, 0 failed / 0 skipped)

| Прогон | ДО C.1 (Stage C) | ПОСЛЕ C.1 |
|---|---|---|
| полный набор (`python -m pytest`) | 1384 passed | **1391 passed** |
| канонический (`python -m pytest tests`) | 864 passed | **871 passed** |

Дельта: +7 новых тестов Stage C.1. Проверка «ни один старый тест не
потерян/не ослаблен» — `appendix_stage_c1/no_test_loss_check.txt`
(0 lost, +7 added в обоих наборах). Golden fixtures не перегенерировались
(файл `candidate/tests/fixtures/legacy_golden_signals.json` побайтово
неизменен — `STAGE_C1_IMMUTABILITY_PROOF.txt`).

## 6. Отсутствие побочных действий

* торговое исполнение не затронуто: `execution.py`, `risk_manager.py`,
  `main.py` и все runtime-файлы побайтово неизменны;
* брокерские действия не добавлены; подключений к брокеру/Sandbox/LIVE
  нет; заявок нет;
* Stage B.1 `strategy_state.py` побайтово неизменен; контракт Stage B.1
  не менялся; вторая система хранения не создавалась;
* Stage D не начата.

## 7. Известные ограничения

См. `KNOWN_LIMITATIONS_STAGE_C1.md`.
