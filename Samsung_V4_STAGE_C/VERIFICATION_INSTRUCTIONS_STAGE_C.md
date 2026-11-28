# VERIFICATION_INSTRUCTIONS_STAGE_C.md
# SAMSUNG V4 — STAGE C — ИНСТРУКЦИЯ ПРОВЕРКИ

Дата: 2026-11-28. Проверка выполняется OFFLINE, без сети и брокера.

## 0. Требуемое окружение

* Python 3.12+, pytest 9.x, pandas 2.2.3, pandas-ta-classic 0.9.0
  (при отсутствии pandas-ta-classic корневой conftest.py ставит
  заглушку — полный набор падает в тестах strategy/screener, требующих
  реальной библиотеки; это политика, унаследованная от Stage A.2.1);
* pytest plugins в логах: Faker, metadata, asyncio, ddtrace, cov,
  json-report, anyio (не влияют на результат Stage C).

## 1. Быстрая проверка пакета (5 минут)

```bash
PKG=/путь/к/распакованному/пакету
cd "$PKG/candidate"

# 1.1 Тесты Stage C
python -m pytest tests/test_stage_c_contracts.py -v      # ожидание: 91 passed
python -m pytest tests/test_stage_c_exit_service.py -v   # ожидание: 32 passed

# 1.2 Канонический набор (включая Stage A.2.1 + Stage B.1)
python -m pytest tests -v                                 # ожидание: 864 passed

# 1.3 Полный набор
python -m pytest -v                                       # ожидание: 1384 passed
```

## 2. Проверка неизменности принятой базы (Stage A.2.1 + Stage B.1)

```bash
# 2.1 Сверка SHA256 candidate/ с зафиксированным ДО-манифестом
cd "$PKG"
python - <<'PY'
import hashlib, os
bad = missing = 0
for line in open("STAGE_C_PRE_BASELINE_SHA256.txt", encoding="utf-8"):
    if not line.strip() or line.startswith("#"): continue
    digest, rel = line.rstrip("\n").split("  ", 1)
    p = os.path.join(".", rel)
    if not os.path.isfile(p):
        print("MISSING:", rel); missing += 1
    elif hashlib.sha256(open(p, "rb").read()).hexdigest() != digest:
        print("CHANGED:", rel); bad += 1
print("OK" if not bad and not missing else f"changed={bad} missing={missing}")
PY
# ожидание: OK

# 2.2 Полная побайтовая сверка с принятым ZIP Stage B.1 (223 файла)
#     — эталонная процедура в STAGE_C_IMMUTABILITY_PROOF.txt (раздел
#     «ИЗМЕНЁННЫЕ/ОТСУТСТВУЮЩИЕ ФАЙЛЫ» там пусты).
```

## 3. Проверка diff (ТЗ §7)

```bash
# 3.1 Реальный unified diff — DIFF_STAGE_B_1_VS_C.patch (только новые
#     файлы; diff по существующим файлам должен быть пуст):
diff -r --brief /путь/к/принятому/Stage_B_1/candidate "$PKG/candidate" \
  | grep -v "^Only in $PKG/candidate"
# ожидание: только строки "Only in .../candidate: strategy_contracts.py"
# и "Only in .../candidate/tests: test_stage_c_contracts.py
#    test_stage_c_exit_service.py" (плюс pyc-артефакты, если есть —
#    перед сверкой очистить __pycache__)

# 3.2 Новый модуль не импортируется runtime-кодом:
grep -rn "strategy_contracts" "$PKG/candidate" --include="*.py" \
  | grep -v "candidate/strategy_contracts.py:" | grep -v "/tests/"
# ожидание: пусто
```

## 4. Проверка границ Stage C (ТЗ §4/§5)

```bash
# 4.1 Нет брокера/сети/заявок в новом коде:
grep -nE "requests|urllib|socket|grpc|websocket|tinkoff|place_order|post_order|cancel_order|FORCE_TRADE" \
  "$PKG/candidate/strategy_contracts.py"
# ожидание: пусто

# 4.2 Торговое исполнение не затронуто:
sha256sum "$PKG/candidate/execution.py" "$PKG/candidate/risk_manager.py"
# сверить с STAGE_C_PRE_BASELINE_SHA256.txt
```

## 5. Воспроизведение контрольных сценариев ТЗ §6

Таблица «сценарий -> тест» — TEST_RESULTS_STAGE_C.txt (раздел 1).
Ключевые проверки руками:

```bash
python - <<'PY'
# Мини-демонстрация: защитный выход не подавляется стратегическим (§6.5)
import sys; sys.path.insert(0, ".")
from strategy_contracts import (ExitEvaluation, ExitDecisionSource,
                                ExitMergeOutcome, merge_exit_evaluations)
s = ExitEvaluation.strategic_exit("alpha", "0"*64, "F", "TAKE_PROFIT", "TP_HIT")
p = ExitEvaluation.protective_exit("alpha", "0"*64, "F", "STOP_LOSS", "SL_HIT")
r = merge_exit_evaluations(s, p)
print(r.final_outcome)        # ExitMergeOutcome.PROTECTIVE_EXIT
print(r.reason_code)          # SL_HIT (защитная причина)
print(r.diagnostics["note"])  # PROTECTIVE_PRIORITY_OVER_STRATEGIC_EXIT
PY
```

(Для полной демонстрации используйте тесты — они покрывают все 19
сценариев §6.)

## 6. Проверка отчётов на полноту (ТЗ §7/§9)

В корне пакета должны присутствовать и быть актуальными (Stage C):

```
README_STAGE_C.md, IMPLEMENTATION_REPORT_STAGE_C.md,
STAGE_C_ARCHITECTURE_REPORT.md, TEST_RESULTS_STAGE_C.txt,
CHANGED_FILES_STAGE_C.md, KNOWN_LIMITATIONS_STAGE_C.md,
FILE_MANIFEST_SHA256_STAGE_C.txt, DIFF_STAGE_B_1_VS_C.md,
DIFF_STAGE_B_1_VS_C.patch, ROLLBACK_INSTRUCTIONS_STAGE_C.md,
VERIFICATION_INSTRUCTIONS_STAGE_C.md,
STAGE_C_PRE_IMPLEMENTATION_BASELINE.md,
STAGE_C_PRE_BASELINE_FILES.txt, STAGE_C_PRE_BASELINE_SHA256.txt,
STAGE_C_IMMUTABILITY_PROOF.txt, STAGE_C_NO_EXECUTION_CHANGES_PROOF.md,
appendix_stage_c/{pytest_before_full,pytest_before_canonical,
pytest_after_full,pytest_after_canonical}.log,
appendix_stage_c/new_tests_list.txt
```

Логи должны содержать реальные строки итогов:
`1261 passed`, `741 passed`, `1384 passed`, `864 passed`.

## 7. Проверка manifest

```bash
cd "$PKG"
python - <<'PY'
import hashlib, os
bad = 0
for line in open("FILE_MANIFEST_SHA256_STAGE_C.txt", encoding="utf-8"):
    if not line.strip() or line.startswith("#"): continue
    digest, rel = line.rstrip("\n").split("  ", 1)
    if not os.path.isfile(rel) or \
       hashlib.sha256(open(rel, "rb").read()).hexdigest() != digest:
        print("DIFF:", rel); bad += 1
print("OK" if not bad else f"{bad} расхождений")
PY
```

(Файл manifest сам в себя не включён — это ожидаемо.)

## 8. Откат

См. ROLLBACK_INSTRUCTIONS_STAGE_C.md.
