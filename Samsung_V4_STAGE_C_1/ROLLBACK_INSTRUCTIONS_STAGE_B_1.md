# ROLLBACK_INSTRUCTIONS_STAGE_B_1.md
# Инструкции отката Stage B.1

Дата: 2026-11-28. Откат возвращает рабочую копию от Stage B.1 к полному
пакету Stage B (кандидат Stage B, база — принятая Stage A.2.1
`103d22d34d483fbb7179d1fef07dd0e24b51dfcd`).

## 1. Суть отката

Stage B.1 изменил ровно ДВА файла, добавил ОДИН тестовый файл и
актуализировал отчёты. Откат выполняется восстановлением исходных
содержимого Stage B (см. `DIFF_STAGE_B_VS_B_1.md` — там полный diff с
обеими версиями; исходные строки Stage B восстанавливаются применением
обратного patch) либо заменой файлов из архива Stage B.

Изменённые файлы:

```
candidate/strategy_state.py
candidate/tests/test_stage_b_state_isolation.py
```

Добавленный файл:

```
candidate/tests/test_stage_b1_state_key_and_concurrency.py
```

Перемещённые отчётные документы (актуализация структуры, ТЗ B.1 §7):
отчёты Stage A/A.1/A.2/A.2.1 перенесены в `archive/`; канонические
документы Stage B обновлены. Откат структуры отчётов — необязателен
(документы не влияют на исполнение), но порядок приведён ниже.

## 2. Откат кода Stage B.1 → Stage B

### 2.1. Откат через patch (рекомендуется)

```bash
# Выполняется из КОРНЯ пакета (рядом с каталогом candidate/).
# Полный diff Stage B -> B.1 прикладывается в обратном направлении:
patch -R -p1 < DIFF_STAGE_B_VS_B_1.patch
# -R снимает изменения B.1: candidate/strategy_state.py и
# candidate/tests/test_stage_b_state_isolation.py возвращаются к
# содержимому Stage B, новый тестовый файл B.1 удаляется.
```

### 2.2. Откат заменой файлов (из сохранённого пакета Stage B)

```bash
cp <пакет Stage B>/candidate/strategy_state.py \
   candidate/strategy_state.py
cp <пакет Stage B>/candidate/tests/test_stage_b_state_isolation.py \
   candidate/tests/test_stage_b_state_isolation.py
rm candidate/tests/test_stage_b1_state_key_and_concurrency.py
```

## 3. Откат данных состояния

Данные, записанные ПОСЛЕ Stage B.1, имеют имена нового формата
(`{len(s1)}--{s1}--{len(s2)}--{s2}.json`), которые Stage B НЕ читает
(его `_filename` строит старый шаблон) и `list_states` Stage B отбракует
как имя, не совпадающее с содержимым (`StateCorruptionError`). Поэтому
при откате на Stage B записи нового формата для продолжения работы
нужно удалить (или переименовать вручную, если содержимое требуется
сохранить — скрытой миграции ни в одну сторону нет):

```bash
# Удалить записи формата Stage B.1 из явного каталога хранилища:
find "<значение STATE_STORE_PATH>" -maxdepth 1 -type f \
     -name '[0-9]*--*.json' -print   # сначала просмотреть список
find "<значение STATE_STORE_PATH>" -maxdepth 1 -type f \
     -name '[0-9]*--*.json' -delete  # затем удалить осознанно
```

Записи старого формата Stage B (если сохранились с этапа Stage B)
после отката снова читаемы Stage B. Старые файлы Samsung (state.json и
пр.) не затрагивались ни одним этапом — действий не требуется.

## 4. Возврат структуры отчётов (опционально)

```bash
# Вернуть архивные отчёты в корень (если требуется полностью исходная
# структура Stage B):
mv archive/*.md archive/*.txt archive/*.patch .
rmdir archive
# и восстановить отчёты Stage B из сохранённого пакета Stage B.
```

## 5. Проверка после отката

```bash
cd candidate
python -m pytest              # ожидается 1228 passed (уровень Stage B)
python -m pytest tests        # ожидается 708 passed
python -m pytest tests/test_stage_b_state_isolation.py   # 115 passed
# тестов B.1 быть не должно:
python -m pytest tests/test_stage_b1_state_key_and_concurrency.py
# ожидаемо: ERROR/No such file (файл удалён)
```

## 6. Полный откат к принятой Stage A.2.1

Откат Stage B целиком (B.1 → B → A.2.1) описан в архивном документе
`archive/ROLLBACK_INSTRUCTIONS_STAGE_B.md`: удалить
`candidate/strategy_state.py`,
`candidate/tests/test_stage_b_state_isolation.py`
и (после отката B.1) `candidate/tests/test_stage_b1_state_key_and_concurrency.py`,
после чего проверить: `python -m pytest` → 1113 passed,
`python -m pytest tests` → 593 passed, `diff -rq` с Stage A.2.1 — без
различий.

## 7. Что НЕ откатывается (и не требует отката)

* Baseline и производственные файлы — не изменялись Stage B/B.1.
* Принятые пакеты Stage A / A.1 / A.2 / A.2.1 — не изменялись.
* Golden fixtures — не изменялись и не перегенерировались.
* Профили SANDBOX_TEST / TECH_CHECK / CONSERVATIVE — не изменялись.
* `engine.json` — не изменялся (ключ STATE_STORE_PATH по-прежнему не
  добавлен).
