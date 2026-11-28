# CHANGED FILES — STAGE C (base) -> STAGE C.1

Дата: 2026-11-28. Основание: ТЗ Stage C.1 §3-§5.

## Изменённые файлы (2 — ровно границы ТЗ §5)

| # | Файл | Что изменено |
|---|---|---|
| 1 | `candidate/strategy_contracts.py` | `ExitDecisionCoordinator.evaluate_and_record()`: price gate (`check_price`) перенесён ДО `manager.get_state()`; при блокирующей цене — возврат `INCOMPLETE_PRICE_EVALUATION` без вызова `get_state`, без оценщиков, без создания/изменения записи состояния; дополнены docstring класса/метода и шапка модуля правилом порядка Stage C.1. Правила цены, проверки и все остальные методы — без изменений. |
| 2 | `candidate/tests/test_stage_c_exit_service.py` | добавлен импорт `os`; в шапку — описание Stage C.1; добавлены `_json_file_names()` и класс `TestPriceGateBeforeStateAccess` (7 новых тестов ТЗ §4). Существующие тесты не изменены, не удалены, не ослаблены. |

## Добавленные файлы (0 в candidate/)

Отдельный тестовый файл признан не требующимся (допускался ТЗ §5 —
«если действительно необходимо»); сценарии добавлены в существующий
файл. Документы Stage C.1 в корне пакета и `appendix_stage_c1/` —
отчётные артефакты, не код.

## Удалённые файлы

Нет.

## Пруфы

* точный diff: `DIFF_STAGE_C_VS_C1.patch` (только 2 файла);
* побайтовое сравнение всех 247 файлов: `STAGE_C1_IMMUTABILITY_PROOF.txt`
  (245 IDENTICAL + 2 CHANGED-allowed + 0 нарушений);
* список с проверкой границ: `STAGE_C1_CHANGED_FILES.txt`.
