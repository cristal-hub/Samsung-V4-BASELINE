# ROLLBACK_INSTRUCTIONS_STAGE_A_2_1.md
# SAMSUNG V4 — NEW STRATEGY ENGINE. STAGE A.2.1

Откат Stage A.2.1 к Stage A.2 (полный, безопасный, offline).

## Вариант 1 — восстановление исходных файлов из поставки Stage A.2

Stage A.2.1 изменил ровно 3 файла и добавил 1:

| Файл | Действие для отката |
|---|---|
| `candidate/strategy_api.py` | заменить на версию Stage A.2 |
| `candidate/attribution.py` | заменить на версию Stage A.2 |
| `candidate/tests/test_stage_a_attribution.py` | заменить на версию Stage A.2 |
| `candidate/tests/test_stage_a2_1_context_integrity.py` | удалить (новый) |

Исходные версии — в поставке Stage A.2 (`Samsung_V4_STAGE_A_2.zip`):

```bash
# из каталога, где лежит Samsung_V4_STAGE_A_2.zip
python - <<'PY'
import zipfile
z = zipfile.ZipFile('Samsung_V4_STAGE_A_2.zip')
root = 'Samsung_V4_STAGE_A_2/candidate/'
for name in ('strategy_api.py', 'attribution.py'):
    data = z.read(root + name)
    open('candidate/' + name, 'wb').write(data)
data = z.read(root + 'tests/test_stage_a_attribution.py')
open('candidate/tests/test_stage_a_attribution.py', 'wb').write(data)
import os
os.remove('candidate/tests/test_stage_a2_1_context_integrity.py')
PY
```

Либо применить обратный патч:

```bash
git apply -R DIFF_STAGE_A_2_VS_A_2_1.patch   # в корне пакета candidate/...
```

Примечание: обратный патч также удалит новый тестовый файл Stage A.2.1 —
это ожидаемое поведение отката.

## Вариант 2 — полное восстановление Stage A.2

Распаковать поставку `Samsung_V4_STAGE_A_2.zip` целиком и продолжить работу
в ней. Пакет Stage A.2.1 (`Samsung_V4_STAGE_A_2_1`) при этом не затрагивается.

## Проверка после отката

```bash
cd candidate
python -m pytest            # ожидается: 1037 passed (Stage A.2)
python -m pytest tests      # ожидается: 517 passed
```

## Что откат НЕ затрагивает

* baseline и production-файлы (main.py, execution.py, logger.py,
  order_ledger.py, config.py, strategy.py, risk_manager.py, engine_config.py,
  engine.json, strategies/legacy_samsung_v4/*) — в Stage A.2.1 не менялись,
  откат их не касается;
* пакеты Stage A / Stage A.1 / Stage A.2 — не изменялись;
* golden fixtures и профили — не менялись.
