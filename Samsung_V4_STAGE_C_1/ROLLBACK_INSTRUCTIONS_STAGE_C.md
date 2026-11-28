# ROLLBACK_INSTRUCTIONS_STAGE_C.md
# SAMSUNG V4 — STAGE C — ИНСТРУКЦИЯ ОТКАТА

Дата: 2026-11-28. Откат Stage C — полностью аддитивная операция:
Stage C добавляет файлы и НЕ изменяет ни одного существующего, поэтому
откат сводится к удалению добавленных файлов.

## 1. Что откатывать

Stage C-файлы (исходники и тесты):

```
candidate/strategy_contracts.py
candidate/tests/test_stage_c_contracts.py
candidate/tests/test_stage_c_exit_service.py
```

Stage C-отчёты и доказательства (корень пакета):

```
README_STAGE_C.md
IMPLEMENTATION_REPORT_STAGE_C.md
STAGE_C_ARCHITECTURE_REPORT.md
TEST_RESULTS_STAGE_C.txt
DIFF_STAGE_B_1_VS_C.md
DIFF_STAGE_B_1_VS_C.patch
CHANGED_FILES_STAGE_C.md
KNOWN_LIMITATIONS_STAGE_C.md
FILE_MANIFEST_SHA256_STAGE_C.txt
ROLLBACK_INSTRUCTIONS_STAGE_C.md
VERIFICATION_INSTRUCTIONS_STAGE_C.md
STAGE_C_PRE_IMPLEMENTATION_BASELINE.md
STAGE_C_PRE_BASELINE_FILES.txt
STAGE_C_PRE_BASELINE_SHA256.txt
STAGE_C_IMMUTABILITY_PROOF.txt
STAGE_C_NO_EXECUTION_CHANGES_PROOF.md
appendix_stage_c/  (каталог целиком)
```

## 2. Процедура отката (безопасная)

```bash
PKG=/путь/к/пакету            # корень пакета (каталог с candidate/)
cd "$PKG"

# 2.1 (опционально) сохранить Stage C-файлы в архив на случай возврата
mkdir -p /tmp/stage_c_removed
cp -r candidate/strategy_contracts.py \
      candidate/tests/test_stage_c_contracts.py \
      candidate/tests/test_stage_c_exit_service.py \
      README_STAGE_C.md IMPLEMENTATION_REPORT_STAGE_C.md \
      STAGE_C_ARCHITECTURE_REPORT.md TEST_RESULTS_STAGE_C.txt \
      DIFF_STAGE_B_1_VS_C.md DIFF_STAGE_B_1_VS_C.patch \
      CHANGED_FILES_STAGE_C.md KNOWN_LIMITATIONS_STAGE_C.md \
      FILE_MANIFEST_SHA256_STAGE_C.txt \
      ROLLBACK_INSTRUCTIONS_STAGE_C.md \
      VERIFICATION_INSTRUCTIONS_STAGE_C.md \
      STAGE_C_PRE_IMPLEMENTATION_BASELINE.md \
      STAGE_C_PRE_BASELINE_FILES.txt STAGE_C_PRE_BASELINE_SHA256.txt \
      STAGE_C_IMMUTABILITY_PROOF.txt \
      STAGE_C_NO_EXECUTION_CHANGES_PROOF.md \
      appendix_stage_c /tmp/stage_c_removed/

# 2.2 удалить Stage C-файлы
rm -f candidate/strategy_contracts.py \
      candidate/tests/test_stage_c_contracts.py \
      candidate/tests/test_stage_c_exit_service.py
rm -f README_STAGE_C.md IMPLEMENTATION_REPORT_STAGE_C.md \
      STAGE_C_ARCHITECTURE_REPORT.md TEST_RESULTS_STAGE_C.txt \
      DIFF_STAGE_B_1_VS_C.md DIFF_STAGE_B_1_VS_C.patch \
      CHANGED_FILES_STAGE_C.md KNOWN_LIMITATIONS_STAGE_C.md \
      FILE_MANIFEST_SHA256_STAGE_C.txt \
      VERIFICATION_INSTRUCTIONS_STAGE_C.md \
      STAGE_C_PRE_IMPLEMENTATION_BASELINE.md \
      STAGE_C_PRE_BASELINE_FILES.txt STAGE_C_PRE_BASELINE_SHA256.txt \
      STAGE_C_IMMUTABILITY_PROOF.txt \
      STAGE_C_NO_EXECUTION_CHANGES_PROOF.md
rm -rf appendix_stage_c
rm -rf candidate/__pycache__ candidate/tests/__pycache__ .pytest_cache

# 2.3 свериться с принятым пакетом Stage B.1 (должно быть 0 расхождений)
#     см. раздел 3
```

Вариант «гарантированно чистый откат»: распаковать принятый ZIP
Stage B.1 заново и работать в нём — Stage C в принятый пакет Stage B.1
не входил.

## 3. Проверка после отката

```bash
# 3.1 побайтовая сверка с принятым Stage B.1
python - <<'PY'
import zipfile, hashlib, os, sys
ZIP = "Samsung_V4_STAGE_B_1.zip"   # принятый Stage B.1
PKG = "."                          # корень распакованного пакета
def fix(n):
    try: return n.encode("cp437").decode("utf-8")
    except Exception: return n
with zipfile.ZipFile(ZIP) as zf:
    bad = 0
    for n in zf.namelist():
        if n.endswith("/"): continue
        rel = fix(n)
        rel = rel.split("/", 1)[1] if rel.startswith("Samsung_V4_STAGE_B_1/") else rel
        cur = os.path.join(PKG, rel)
        if not os.path.isfile(cur) or \
           hashlib.sha256(zf.read(n)).hexdigest() != \
           hashlib.sha256(open(cur, "rb").read()).hexdigest():
            print("DIFF:", rel); bad += 1
    print("OK" if bad == 0 else f"{bad} расхождений")
PY

# 3.2 регрессия принятой базы
cd candidate
python -m pytest        # ожидается: 1261 passed
python -m pytest tests  # ожидается: 741 passed
```

## 4. Что остаётся неизменным при откате

* Stage A.2.1 и Stage B.1 (все файлы побайтово);
* golden fixtures;
* legacy_samsung_v4 (REGRESSION_ONLY);
* baseline-файлы торговли (execution.py, risk_manager.py и т.д.);
* конфигурация окружения.

## 5. Возврат Stage C после отката

Вернуть файлы из /tmp/stage_c_removed (или из ZIP-пакета Stage C) на
прежние места и выполнить проверку из VERIFICATION_INSTRUCTIONS_STAGE_C.md.
Скрытых миграций состояния Stage C не существует — откат/возврат
никак не затрагивает данные состояния (Stage C пишет только ключ
last_exit_evaluation в данные состояния пар; при откате эти ключи
просто перестают читаться слоем Stage C; удалять их не требуется,
текущие этапы их не потребляют).
