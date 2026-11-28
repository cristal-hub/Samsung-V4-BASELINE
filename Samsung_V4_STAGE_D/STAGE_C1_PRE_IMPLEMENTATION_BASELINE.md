# STAGE C.1 — PRE-IMPLEMENTATION BASELINE (ТЗ §7: фиксация ДО реализации)

Дата фиксации: 2026-11-28
Момент фиксации: ДО правки какого-либо файла Stage C (скрипт
scripts/stage_c1_pre_baseline.py выполнен до первого изменения
candidate/strategy_contracts.py).

## 1. Исходная база

* Исходный пакет: Stage C candidate (исходный commit
  `9a69a300e6759f9264d5feb1a6b54ea80f615e4a` — как возвращён в чат; доступ к
  GitHub отсутствует, поэтому источником истины является доставленный пакет
  `Samsung_V4_STAGE_C`).
* Подтверждение идентичности: все 246 файлов manifest
  `FILE_MANIFEST_SHA256_STAGE_C.txt` доставленного ZIP совпали с
  извлечённым содержимым (246/246 OK, 0 mismatch); рабочая копия также
  177/177 candidate-файлов OK.
* Принятые неизменяемые этапы (не пересматриваются):
  * Stage A.2.1: `103d22d34d483fbb7179d1fef07dd0e24b51dfcd`;
  * Stage B.1: `e413c5bd6bdec436ffd7aeece4c28b5e969c6306`.
* Stage C НЕ принят — Stage C.1 исправляет найденный дефект кандидата.

## 2. Полный перечень файлов Stage B.1 / Stage C (фиксация)

* `STAGE_C1_PRE_BASELINE_FILES.txt` — полный список 247 файлов пакета
  Stage C (246 из manifest +1 сам manifest в него не входит... полный
  обход каталога: 247 файлов).
* `STAGE_C1_PRE_BASELINE_SHA256.txt` — SHA256 всех 177 файлов
  `candidate/` на момент ДО правки.

## 3. Найденный дефект (ТЗ Stage C.1 §2)

`ExitDecisionCoordinator.evaluate_and_record()` в
`candidate/strategy_contracts.py` вызывал `manager.get_state(...)`
(Шаг 3) ДО fail-closed проверки цены (Шаг 4). `StrategyStateManager
.get_state()` Stage B.1 при отсутствии записи СОЗДАЁТ новое состояние
(`StateStore.get_or_create`). Следовательно, при отсутствующей/
некорректной/устаревшей цене координатор изменял хранилище (создавал
запись состояния) ещё до блокировки оценки — противоречит заявленному
fail-closed поведению Stage C.

## 4. Планируемые изменения (фиксация ДО реализации, ТЗ §5)

Разрешено ТЗ Stage C.1 §5 — и фактически ограничено ровно этим списком:

| Файл | Действие |
|---|---|
| `candidate/strategy_contracts.py` | изменить: переставить price gate до `manager.get_state()`; при блокирующей цене — возврат `INCOMPLETE_PRICE_EVALUATION` без `get_state`, без оценщиков, без записи состояния |
| `candidate/tests/test_stage_c_exit_service.py` | дополнить: 7 обязательных сценариев §4, проверяющих фактическое состояние StateStore |

Отдельный тестовый файл НЕ требуется (сценарии добавлены классом
`TestPriceGateBeforeStateAccess` в существующий файл).

## 5. Запрещено и не сделано

Stage A.2.1, Stage B.1 `strategy_state.py`, старые тесты Stage A/B/B.1,
торговые runtime-файлы, `execution.py`, `risk_manager.py`, `main.py`,
`legacy_samsung_v4`, брокерские действия, Sandbox/LIVE, Stage D —
не изменялись (доказательство: `STAGE_C1_IMMUTABILITY_PROOF.txt`,
`STAGE_C1_NO_EXECUTION_CHANGES_PROOF.md`).

## 6. Ожидаемая база прогонов ДО исправления (ТЗ §6)

* полный набор: 1384 passed; канонический набор: 864 passed —
  подтверждено реальными логами
  `appendix_stage_c1/pytest_before_full.log` (1384 passed, 0 failed,
  0 skipped) и `appendix_stage_c1/pytest_before_canonical.log`
  (864 passed, 0 failed, 0 skipped).
