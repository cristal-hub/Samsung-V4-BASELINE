# ROLLBACK INSTRUCTIONS — STAGE A.2

**Откат Stage A.2 → Stage A.1**

Stage A.2 изменяет ровно 4 файла и добавляет 1 тестовый файл. Откат
выполняется восстановлением исходных версий из нетронутой поставки
`Samsung_V4_STAGE_A_1.zip` (исходный пакет Stage A.1 сохранён без
изменений и не должен заменяться рабочей копией Stage A.2).

---

## 1. Что нужно восстановить

| Файл | Действие |
|---|---|
| `candidate/strategy_api.py` | заменить на версию из Stage A.1 |
| `candidate/attribution.py` | заменить на версию из Stage A.1 |
| `candidate/tests/test_stage_a1_config_immutability.py` | заменить на версию из Stage A.1 |
| `candidate/tests/test_stage_a_legacy_adapter.py` | заменить на версию из Stage A.1 |
| `candidate/tests/test_stage_a2_config_hash_integrity.py` | УДАЛИТЬ (новый файл Stage A.2) |

## 2. Порядок отката

```bash
# 1) распаковать исходную поставку Stage A.1 во временный каталог
mkdir /tmp/a1_original
cd /tmp/a1_original
unzip /path/to/Samsung_V4_STAGE_A_1.zip

# 2) скопировать исходные версии четырёх файлов поверх рабочей копии A.2
cp /tmp/a1_original/Samsung_V4_STAGE_A_1/candidate/strategy_api.py        <WORK>/candidate/
cp /tmp/a1_original/Samsung_V4_STAGE_A_1/candidate/attribution.py         <WORK>/candidate/
cp /tmp/a1_original/Samsung_V4_STAGE_A_1/candidate/tests/test_stage_a1_config_immutability.py  <WORK>/candidate/tests/
cp /tmp/a1_original/Samsung_V4_STAGE_A_1/candidate/tests/test_stage_a_legacy_adapter.py        <WORK>/candidate/tests/

# 3) удалить новый тестовый файл Stage A.2
rm <WORK>/candidate/tests/test_stage_a2_config_hash_integrity.py

# 4) очистить кеш интерпретатора
find <WORK>/candidate -name "__pycache__" -type d -exec rm -rf {} +
```

Документы Stage A.2 (`README_STAGE_A_2.md`, `CORRECTIVE_REPORT_STAGE_A_2.md`,
`DIFF_STAGE_A_1_VS_A_2.md`, `TEST_RESULTS_STAGE_A_2.txt`,
`FILE_MANIFEST_SHA256_STAGE_A_2.txt`, `APPENDIX_DIFF_STAGE_A_1_TO_A_2.patch`,
этот файл) при откате можно удалить или сохранить как архив — на поведение
кода они не влияют.

## 3. Проверка после отката

```bash
cd <WORK>/candidate
python -m pytest
# ожидание Stage A.1: 980 passed, 0 failed, exit 0
python -m pytest tests
# ожидание Stage A.1: 460 passed, 0 failed
```

Контроль соответствия Stage A.1 — сверить SHA256 четырёх восстановленных
файлов с `FILE_MANIFEST_SHA256.txt` исходной поставки Stage A.1.

## 4. Границы отката

* Откат НЕ затрагивает baseline и остальные 181 файл пакета — они в
  Stage A.2 не менялись (байт-идентичны Stage A.1).
* Откат НЕ затрагивает старые журналы/данные: Stage A.2 не создавал и не
  менял никаких журналов и пользовательских данных.
* Промежуточные состояния «частично применён Stage A.2» недопустимы:
  либо все 4 файла + новый тест присутствуют (Stage A.2), либо все 4 файла
  восстановлены и новый тест удалён (Stage A.1). Смешанное состояние
  приведёт к падению тестов, создающих конфигурации с искусственными
  хешами (это штатный fail-closed, а не поломка).
