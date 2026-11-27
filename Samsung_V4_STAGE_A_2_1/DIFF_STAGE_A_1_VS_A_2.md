# DIFF: Stage A.1 → Stage A.2

**SAMSUNG V4 — NEW STRATEGY ENGINE. STAGE A.2 CORRECTIVE**
Полное описание различий между исходной поставкой `Samsung_V4_STAGE_A_1`
и результатом Stage A.2. Машинный diff: `APPENDIX_DIFF_STAGE_A_1_TO_A_2.patch`.

---

## 1. СВОДКА

| Метрика | Значение |
|---|---|
| Файлов в пакете Stage A.1 | 186 |
| Изменено | 4 |
| Добавлено | 1 (новый тестовый файл Stage A.2) |
| Байт-идентичны Stage A.1 | 185 из 186 (SHA256) |
| Изменено относительно baseline commit `884cefd` | **0** |
| Файлов, байт-идентичных baseline | 155 (все не затронутые Stage A/A.1/A.2) |

Строки машинного diff: **+1022 / −57** (включая новый тестовый файл).

## 2. ПОФАЙЛОВОЕ ОПИСАНИЕ

### 2.1. `candidate/strategy_api.py` — изменён

Причина: обязательное исправление Stage A.2 (пункты 3.1–3.3 задания) —
создание `StrategyConfig` обязано отклонять несоответствующий,
фиктивный или невалидный по формату `config_hash`, а также недопустимые
значения параметров (NaN/Infinity, неподдерживаемые изменяемые объекты,
циклические ссылки).

Содержание изменения:

1. Шапка модуля: добавлен раздел STAGE A.2 с описанием обязательной
   проверки.
2. Новый класс `_FreezePath` — отслеживание пути рекурсии заморозки/
   нормализации (обнаружение циклов; ссылки на объекты пути хранятся
   в отображении, чтобы исключить ложные срабатывания от переиспользования
   `id()` после сборки мусора; DAG-структуры не отклоняются).
3. `ImmutableMapping.__init__` / `ImmutableList.__new__` — опциональный
   параметр `_freeze_path` (приватный; публичный API прежний), значения
   замораживаются с прокидыванием пути.
4. `deep_freeze` — цикл по текущему пути → `StrategyConfigError`
   («циклическая структура … отклонено (fail-closed, без бесконечной
   рекурсии)»); публичная сигнатура совместима (новый параметр имеет
   значение по умолчанию).
5. `_normalize_for_json` — та же цикл-детекция для прямых вызовов
   `compute_config_hash` / `canonical_config_payload`.
6. `canonical_config_payload` — параметры, не являющиеся отображением,
   отклоняются контролируемой `StrategyConfigError` (ранее —
   неконтролируемый `TypeError`).
7. Новые `CONFIG_HASH_LENGTH = 64`, `_HEX_DIGITS`,
   `validate_config_hash_format()` — формат SHA-256 hexdigest (ровно
   64 символа `[0-9a-f]`, нижний регистр; иначе fail-closed).
8. `StrategyConfig.__post_init__` — добавлены шаг 2a (формат) и шаг 4:
   вычисление ожидаемого хеша по ФАКТИЧЕСКИ сохранённым параметрам через
   существующий `compute_config_hash` и сравнение с переданным;
   расхождение → `StrategyConfigError` с указанием обоих значений;
   автоматическая замена хеша запрещена.
9. Обновлены докстринги `StrategyConfig` и `recompute_config_hash`.

Совместимость: все существующие потребители (Strategy.get_config,
build_regression_config, engine_config, сериализация as_dict, hash/eq)
работают без изменений — 980 существующих тестов проходят.
Тесты: 57 новых (`tests/test_stage_a2_config_hash_integrity.py`).

Фрагмент ключевого изменения:

```python
# 4. Обязательная проверка соответствия (Stage A.2): ожидаемый хеш
#    вычисляется по ФАКТИЧЕСКИ сохранённым параметрам и сравнивается
#    с переданным. Расхождение -> StrategyConfigError; тихая замена
#    переданного хеша вычисленным ЗАПРЕЩЕНА (fail-closed).
expected_hash = compute_config_hash(
    self.strategy_id, self.strategy_version, self.params)
if expected_hash != self.config_hash:
    raise StrategyConfigError(
        "config_hash не соответствует фактической конфигурации: "
        f"strategy_id={self.strategy_id!r}, "
        f"strategy_version={self.strategy_version!r}: передан "
        f"{self.config_hash!r}, по фактическим параметрам ожидается "
        f"{expected_hash!r}; объект НЕ создан, автоматическое "
        "исправление хеша запрещено (fail-closed)")
```

### 2.2. `candidate/attribution.py` — изменён

Причина: обязательное исправление Stage A.2 (пункт 3.4 задания) —
`AttributionContext.from_config()` не должен мочь выпустить контекст
с несоответствующим хешем.

Содержание изменения:

1. Шапка модуля: добавлен раздел STAGE A.2.
2. Импорт: добавлен `StrategyContractError`.
3. `AttributionContext.from_config()`:
   - None → `AttributionError` (как прежде);
   - принимается ТОЛЬКО `isinstance(config, StrategyConfig)` — duck-typed
     объекты больше не принимаются (не могут доказать соответствие хеша);
   - defense-in-depth: перепроверка `config.recompute_config_hash()`; при
     расхождении или ошибке — `AttributionError`, контекст НЕ выпускается;
   - скрытых значений, fallback и автоматического исправления нет.

Совместимость: `stamp()`, `AttributionFactory`, `engine_config.py`
(точка `AttributionContext.from_config(config)`) работают без изменений —
все существующие тесты атрибуции проходят; чтение старых записей без
атрибуции не изменилось.
Тесты: 9 новых проверок в файле Stage A.2 + 55 регрессионных.

### 2.3. `candidate/tests/test_stage_a1_config_immutability.py` — изменён (только фикстуры)

Причина: требование 5 задания — тестовые фикстуры обязаны вычислять
реальные хеши через `compute_config_hash()`; искусственные хеши
(`"e"*64`, `"c"*64`) больше не проходят проверку при создании.

- `_nested_config()`: хеш вычисляется для фактических параметров
  (`compute_config_hash("nested_demo", "1.0", params)`).
- `test_metadata_non_mapping_rejected`: реальный хеш, чтобы проверяемой
  ошибкой была именно невалидная metadata (смысл теста сохранён).

Утверждения тестов НЕ менялись. 48/48 PASS.

### 2.4. `candidate/tests/test_stage_a_legacy_adapter.py` — изменён (только фикстура)

Причина: то же требование 5 — `test_evaluate_entry_rejects_engine_origin`
создавал конфигурацию с `config_hash="0"*64`.

- Фикстура вычисляет реальный хеш:
  `sa.compute_config_hash("legacy_samsung_v4", strategy.strategy_version,
  normalized)`.

Утверждение теста НЕ менялось (origin="engine" по-прежнему отклоняется
адаптером через `LegacyRegressionError`). PASS.

### 2.5. `candidate/tests/test_stage_a2_config_hash_integrity.py` — НОВЫЙ

57 corrective-тестов обязательной проверки соответствия config_hash
фактической конфигурации — покрытие всех 12 обязательных пунктов
задания (раздел 3 отчёта `CORRECTIVE_REPORT_STAGE_A_2.md`) плюс
дополнительные проверки (запрет обхода через `dataclasses.replace`,
DAG vs циклы, defense-in-depth, повторное создание после отказа).
Тестируется поведение (создание объекта / контролируемая ошибка),
а не наличие строк в исходном коде.

### 2.6. Файлы, НЕ изменённые и проверенные

Относительно Stage A.1 байт-идентичны 185 файлов, включая без изменений
сохранённые отчёты Stage A и A.1 (`README_STAGE_A.md`,
`IMPLEMENTATION_REPORT.md`, `CHANGELOG.md`, `CORRECTIVE_IMPLEMENTATION_REPORT.md`,
`README_STAGE_A_1.md`, `TEST_RESULTS.txt`, `BASELINE_VS_STAGE_A_1_DIFF.md`,
`FILE_MANIFEST_SHA256*.txt`, `ROLLBACK_INSTRUCTIONS*.md` и др.),
весь production-код baseline (`main.py`, `execution.py`, `logger.py`,
`order_ledger.py`, `config.py`, `strategy.py`, `risk_manager.py`,
`screener.py`, `telegram_bot.py`, `tinkoff_client.py`, `safe_start.py`,
`build_safety.py`, `enable_sandbox_execution.py`, `requirements.txt`,
`conftest.py`) и Stage A-компоненты (`engine_config.py`, `engine.json`,
`strategies/legacy_samsung_v4/*`, golden-эталон `legacy_golden_signals.json`).

Торговая логика, параметры, сигналы, риск-менеджмент и исполнение —
без изменений. Миграций журналов нет. FORCE_TRADE не появился.
