# DIFF_STAGE_A_2_1_VS_STAGE_B.md
# Сводка полного diff: принятая Stage A.2.1 → Stage B

Полный patch: `DIFF_STAGE_A_2_1_VS_STAGE_B.patch` (применение проверено;
содержит только ДОБАВЛЕНИЕ двух новых файлов).

## Статистика

```
diff -rq Samsung_V4_STAGE_A_2_1/candidate Samsung_V4_STAGE_B/candidate
  Only in Samsung_V4_STAGE_B/candidate: strategy_state.py
  Only in Samsung_V4_STAGE_B/candidate/tests: test_stage_b_state_isolation.py
```

* изменённых существующих файлов: **0**
* удалённых файлов: **0**
* добавленных файлов: **2** (исходник Stage B + тесты Stage B)

## Содержимое добавлений

### 1. `candidate/strategy_state.py`

Публичный API:

```python
STATE_SCHEMA_VERSION = 1
STATE_STORE_CONFIG_KEY = "STATE_STORE_PATH"

class StrategyStateError(Exception)          # базовая
class StateValidationError(StrategyStateError)
class StateSchemaError(StrategyStateError)
class StateCorruptionError(StrategyStateError)
class StateConfigMismatchError(StrategyStateError)
class StateAlreadyExistsError(StrategyStateError)
class StateNotFoundError(StrategyStateError)
class StateStoreConfigError(StrategyStateError)

def validate_strategy_id(strategy_id) -> str     # безопасный набор символов
def validate_figi(figi) -> str                   # безопасный набор символов
def resolve_state_store_path(config) -> str      # ЯВНЫЙ ключ, fail-closed

@dataclass(frozen=True)
class StrategyState:
    strategy_id: str; figi: str; config_hash: str; schema_version: int
    data: ImmutableMapping; created_at: str; updated_at: str
    # create(...), with_data(...), to_payload(), to_json(),
    # from_payload(...), key()

class StateStore:
    def __init__(self, *, path: Optional[str] = None)  # None => memory
    mode: str  # "persistent" | "memory"
    path: Optional[str]
    get_state(strategy_id, figi, *, config_hash=None) -> Optional[StrategyState]
    save_state(strategy_id, figi, state) -> None
    create_state(strategy_id, figi, config_hash, data=None) -> StrategyState
    reset_state(strategy_id, figi) -> bool
    list_states() -> List[StrategyState]

class StrategyStateManager:
    def __init__(self, store, *, clock=None)
    get_state(strategy_id, figi, *, config=None, config_hash=None)
    update_state(strategy_id, figi, *, config=None, config_hash=None,
                 data=None, updater=None, now=None)
    reset_state(strategy_id, figi) -> bool
    list_states()
    get_state_for_context(context, figi)          # проверенный AttributionContext
    update_state_for_context(context, figi, ...)
```

### 2. `candidate/tests/test_stage_b_state_isolation.py`

115 тестов в 16 классах — трассировка обязательных сценариев ТЗ §4
(см. таблицу в `STAGE_B_ARCHITECTURE_REPORT.md`, раздел 8).

## Формат записи хранилища (persistent-режим)

Файл `<path>/<strategy_id>__<figi>.json`, канонический JSON
(sort_keys, без пробелов, UTF-8, allow_nan=False):

```json
{"config_hash":"<64 hex>","created_at":"<ISO-8601 UTC>","data":{...},
 "figi":"<FIGI>","schema_version":1,"strategy_id":"<strategy_id>",
 "updated_at":"<ISO-8601 UTC>"}
```

Одно и то же содержимое всегда даёт одинаковые байты
(детерминированная сериализация, ТЗ §4.6 — покрыто тестами).

## Совместимость

* Формат записей Stage B не пересекается со старыми файлами Samsung
  (state.json, research_events.jsonl, orders_registry.json) — отдельные
  имена, отдельный каталог, отдельный ключ конфигурации.
* Схема состояния версионируется (`schema_version`); будущие несовместимые
  изменения требуют повышения версии и ЯВНОГО решения о совместимости.
* Все контракты Stage A (StrategyConfig/config_hash/AttributionContext/
  ActivationMode) используются как есть, без изменений.
