# STAGE D.1 — CHANGED FILES

Точный список файлов, изменённых в Stage D.1. База сравнения: Stage D
как поставлен (`Samsung_V4_STAGE_D.zip`); дополнительно проверено
байт-в-байт совпадение всех прочих файлов с принятым Stage C.1.

## 1. Файлы для ЗАМЕНЫ в репозитории (ровно два)

| # | Путь | Статус | Причина | SHA-256 исходной версии (Stage D) | SHA-256 новой версии (Stage D.1) |
|---|---|---|---|---|---|
| 1 | `candidate/strategy_risk.py` | MODIFIED | Дефект D-1: localcontext() переопределял только prec — ambient Emax/Emin/rounding/traps просачивались в расчёт и валидатор (нарушение детерминизма ТЗ §10.17). Исправление: полностью явный `_SIZING_DECIMAL_CONTEXT` | `2a29807e8818158216bffb01be609f8462ad0716e5ef5dc0d8aedff7782a7327` | `7f25b4ef4bf9f2f9b90507caf7b4ff53a20b95f987c337bbf3d95496bcd22d66` |
| 2 | `candidate/tests/test_stage_d_strategy_risk.py` | MODIFIED | Добавлены 17 тестов Stage D.1 (2 класса: изоляция ambient Decimal-контекста — 8 тестов + 5 параметризованных; точные границы notional cap / buying power — 5 тестов). Старые 162 теста не изменены (diff: −0 строк) | `38c550f51eb34d88110dd24db5eeac7306a4df346549ec502dd3dcfafcfad073` | `0cade2967f68fc5bad648460adbec593dbe97a0fbc0771e7130fe2be0915ddf9` |

Оба файла возвращены в ZIP ПОЛНОСТЬЮ (не патчи) с сохранением
относительных путей. Файл, не попавший в этот список, заменять НЕ
нужно.

## 2. Файлы, проверенные и НЕ изменённые

* **Полный байт-в-байт контроль против pristine Stage C.1**: все 177
  файлов candidate совпадают SHA-256 (0 удалений, 0 модификаций);
  единственные отличия пакета от Stage C.1 — два файла Stage D из
  таблицы выше (добавлены в Stage D, скорректированы в D.1).
* **Ключевые контракты принятых этапов** (проверены отдельно):
  `attribution.py`, `strategy_api.py`, `config.py` (Stage A.2.1),
  `strategy_state.py` (Stage B.1), `strategy_contracts.py` (Stage C) —
  не изменены.
* **Тесты принятых этапов**: `tests/test_stage_a*.py`,
  `tests/test_stage_b*.py`, `tests/test_stage_c*.py` — не изменены.
* **Торговое исполнение и инфраструктура**: `execution.py`, `main.py`,
  `risk_manager.py`, `telegram_bot.py`, `screener.py`, `safe_start.py`,
  `order_ledger.py`, `build_safety.py`, `enable_sandbox_execution.py`,
  `engine_config.py`, `strategy.py`, `logger.py` — не изменены.
* **Golden fixtures**: `tests/fixtures/legacy_golden_signals.json` — не
  перегенерировались.
* Прочие отчётные/документационные файлы Stage D
  (IMPLEMENTATION_REPORT_STAGE_D.md, README_STAGE_D.md,
  STAGE_D_*.txt и т.п.) — не изменялись; они остаются в Stage D как
  поставлены. Актуализация их содержимого под D.1 сознательно НЕ
  выполнялась: поставка D.1 самодостаточна через собственные отчёты
  (это позволяет не трогать лишние файлы репозитория).

## 3. Статистика diff (STAGE_D_1_DIFF.patch)

* `candidate/strategy_risk.py`: −6 / +46 строк
  (импорт Decimal-констант; определение `_SIZING_DECIMAL_CONTEXT`;
  два `with localcontext(_SIZING_DECIMAL_CONTEXT):` вместо
  `with localcontext() as ctx: ctx.prec = ...`; docstrings).
* `candidate/tests/test_stage_d_strategy_risk.py`: −0 / +230 строк
  (только ДОБАВЛЕНИЕ двух классов тестов в конец файла).

## 4. Тестовые счётчики после замены

* Full: **1570 passed**, 0 failed, 0 skipped (было 1553);
* Canonical: **1050 passed**, 0 failed, 0 skipped (было 1033);
* Stage D тесты: **179 passed** (было 162);
* по-тестовая сверка verbose-логов: потеряно 0, добавлено ровно 17.
