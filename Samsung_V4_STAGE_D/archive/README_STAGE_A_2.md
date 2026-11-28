# README — STAGE A.2

**SAMSUNG V4 — NEW STRATEGY ENGINE. STAGE A.2 CORRECTIVE**
**Обязательная проверка соответствия config_hash фактической конфигурации**

Дата: 2026-11-28. Исходный пакет: `Samsung_V4_STAGE_A_1` (Stage A.1,
сохранён без изменений). Baseline: commit `884cefd6f12a99f6adc14b5ed4c9eeda21d32e04`
(cristal-hub/Samsung-V4-BASELINE). Работал в изолированной копии;
GitHub/ветки/коммиты/PR не использовались.

---

## 1. Что это

Точечное исправление единственного дефекта, оставшегося после независимой
проверки Stage A.1: можно было создать `StrategyConfig` с корректными
параметрами и **чужим** `config_hash` (и затем записать неверную атрибуцию
в новые объекты движка), потому что:

* `__post_init__` проверял только непустоту хеша;
* `recompute_config_hash()` никто не вызывал при создании;
* `AttributionContext.from_config()` доверял переданному хешу.

После Stage A.2 **невозможно** создать `StrategyConfig` с неправильным,
фиктивным или не соответствующим параметрам `config_hash` через обычный
публичный API — создание отклоняется `StrategyConfigError`.

## 2. Что изменено (ничего больше)

| Файл | Изменение |
|---|---|
| `candidate/strategy_api.py` | при каждом создании `StrategyConfig`: проверка формата (ровно 64 hex-символа `[0-9a-f]`) и равенства `compute_config_hash(...)` по фактическим параметрам; расхождение → `StrategyConfigError` (без тихой замены хеша); NaN/Infinity, неподдерживаемые изменяемые объекты, циклические ссылки → контролируемая `StrategyConfigError` (без бесконечной рекурсии, без частично валидного объекта) |
| `candidate/attribution.py` | `AttributionContext.from_config()` принимает только консистентную `StrategyConfig` (+ перепроверка defense-in-depth); duck-typed объекты с ручными полями отклоняются; `AttributionFactory` из некорректной конфигурации не создаётся |
| `candidate/tests/test_stage_a1_config_immutability.py`, `candidate/tests/test_stage_a_legacy_adapter.py` | тестовые фикстуры переведены с искусственных хешей на реальные (`compute_config_hash`); утверждения тестов не менялись |
| `candidate/tests/test_stage_a2_config_hash_integrity.py` | НОВЫЙ: 57 тестов (все 12 обязательных пунктов задания + дополнительные) |

Торговая логика, параметры, сигналы, риск-менеджмент, исполнение,
`engine_config.py`, `engine.json`, профили, golden-эталон — **не изменены**.
Baseline не изменён (0 изменённых файлов, SHA256-проверка).

## 3. Проверка

```bash
cd candidate
python -m pytest          # 1037 passed, 0 failed (980 Stage A.1 + 57 новых)
python -m pytest tests    # 517 passed, 0 failed
python -m pytest tests/test_stage_a2_config_hash_integrity.py   # 57 passed
```

Краткая демонстрация нового поведения:

```python
from strategy_api import StrategyConfig, StrategyConfigError, compute_config_hash

good = compute_config_hash("s", "v", {"a": 1})
StrategyConfig(strategy_id="s", strategy_version="v",
               params={"a": 1}, config_hash=good)          # OK

StrategyConfig(strategy_id="s", strategy_version="v",
               params={"a": 1},
               config_hash=compute_config_hash("s", "v", {"a": 2}))
# -> StrategyConfigError: config_hash не соответствует фактической
#    конфигурации; объект НЕ создан, автоматическое исправление запрещено

StrategyConfig(strategy_id="s", strategy_version="v",
               params={"a": 1}, config_hash="0" * 63)      # -> StrategyConfigError (формат)
StrategyConfig(strategy_id="s", strategy_version="v",
               params={"a": float("nan")}, config_hash="0" * 64)
                                                            # -> StrategyConfigError (NaN)
```

## 4. Документы Stage A.2

| Файл | Содержание |
|---|---|
| `CORRECTIVE_REPORT_STAGE_A_2.md` | полный отчёт об исправлении (дефект, механика, 12 обязательных тестов, фикстуры, регрессия, ограничения) |
| `DIFF_STAGE_A_1_VS_A_2.md` | пофайловое описание различий A.1 → A.2 |
| `APPENDIX_DIFF_STAGE_A_1_TO_A_2.patch` | полный машинный diff (+1022/−57) |
| `TEST_RESULTS_STAGE_A_2.txt` | результаты pytest до/после, окружение, повторяемость |
| `FILE_MANIFEST_SHA256_STAGE_A_2.txt` | SHA256-манифест всех файлов пакета |
| `ROLLBACK_INSTRUCTIONS_STAGE_A_2.md` | откат A.2 → A.1 |

Документы Stage A и Stage A.1 сохранены в пакете без изменений.

## 5. Границы и ограничения

* Атрибуция по-прежнему не встроена в производственный поток baseline —
  это граница Stage A/A.1/A.2 (встраивание — Этап B; предложение
  задокументировано в отчёте Stage A.1). Stage A.2 границу не расширяет.
* Сборка объекта в обход публичного API (`object.__new__`) не является
  обычным публичным API; для неё оставлен барьер defense-in-depth в
  `AttributionContext.from_config` (перепроверка `recompute_config_hash`).
* Полный перечень ограничений — раздел 7 `CORRECTIVE_REPORT_STAGE_A_2.md`.
* Stage B не начинался. FORCE_TRADE не добавлялся и не использовался.
* Исключены из поставки: `.env`/токены/пароли/account ID, реальные
  runtime-файлы и торговые журналы (в пакете их нет).
