# ROLLBACK_INSTRUCTIONS_STAGE_B.md
# Инструкции отката Stage B

Дата: 2026-11-28. Откат возвращает рабочую копию к принятой
Stage A.2.1 (коммит 103d22d34d483fbb7179d1fef07dd0e24b51dfcd).

## 1. Суть отката

Stage B добавил ровно ДВА файла и не изменил ни одного существующего
(подтверждено побайтово, `FILE_MANIFEST_SHA256_STAGE_B.txt`), поэтому
откат — удаление этих двух файлов и отчётных документов Stage B:

```
candidate/strategy_state.py
candidate/tests/test_stage_b_state_isolation.py
```

## 2. Полный откат (возврат к принятой Stage A.2.1)

```bash
# 2.1. Удалить файлы Stage B из candidate:
rm candidate/strategy_state.py
rm candidate/tests/test_stage_b_state_isolation.py

# 2.2. (Опционально) удалить отчётные документы Stage B из корня пакета:
rm README_STAGE_B.md STAGE_B_ARCHITECTURE_REPORT.md \
   CHANGED_FILES_STAGE_B.md DIFF_STAGE_A_2_1_VS_STAGE_B.patch \
   DIFF_STAGE_A_2_1_VS_STAGE_B.md TEST_RESULTS_STAGE_B.txt \
   FILE_MANIFEST_SHA256_STAGE_B.txt VERIFICATION_INSTRUCTIONS_STAGE_B.md \
   ROLLBACK_INSTRUCTIONS_STAGE_B.md KNOWN_LIMITATIONS_STAGE_B.md

# 2.3. Удалить раздел «Stage B» из CHANGELOG.md (раздел в конце файла).

# 2.4. Проверить побайтовую идентичность с принятой Stage A.2.1:
diff -rq Samsung_V4_STAGE_A_2_1/candidate candidate
# ожидаемо: никаких различий
```

## 3. Откат через patch (если дерево изменялось иначе)

```bash
cd candidate
patch -R -p1 < ../DIFF_STAGE_A_2_1_VS_STAGE_B.patch
# -R (reverse) снимает добавления Stage B; существующие файлы
# не затрагиваются, т.к. diff их не содержит.
```

## 4. Откат данных состояния Stage B

Состояние Stage B хранится ТОЛЬКО в явно сконфигурированном каталоге
(ключ `STATE_STORE_PATH`; по умолчанию Stage B путь не задаёт и ничего
на диске не пишет). Откат подсистемы не требует очистки данных, но при
желании удалить накопленное состояние:

```bash
rm -rf "<значение STATE_STORE_PATH>"
```

Старые файлы Samsung (state.json, research_events.jsonl,
orders_registry.json и пр.) Stage B не читал, не писал и не менял —
никаких действий по ним не требуется.

## 5. Проверка после отката

```bash
cd candidate
python -m pytest        # ожидается 1113 passed (уровень Stage A.2.1)
python -m pytest tests  # ожидается 593 passed
```

## 6. Что НЕ откатывается (и не требует отката)

* Baseline и производственные файлы — не изменялись Stage B.
* Принятые пакеты Stage A / A.1 / A.2 / A.2.1 — не изменялись.
* Golden fixtures — не изменялись и не перегенерировались.
* Профили SANDBOX_TEST / TECH_CHECK / CONSERVATIVE — не изменялись.
