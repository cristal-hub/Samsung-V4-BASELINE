# VERIFICATION INSTRUCTIONS — STAGE D

SAMSUNG V4 NEW STRATEGY ENGINE — STRATEGY-SPECIFIC RISK SIZING

Независимая проверка пакета Samsung_V4_STAGE_D. Все шаги offline,
без сети и брокера. Ожидаемое окружение: Python 3.12, pytest 9.x
(пакет самодостаточен: при отсутствии SDK t_tech.invest /
pandas_ta_classic / python-telegram-bot используются встроенные
заглушки candidate/conftest.py — поведение тестов не меняется).

---

## 1. Структура и целостность пакета

```bash
# SHA-256 всего пакета; сравнить с FILE_MANIFEST_SHA256_STAGE_D.txt
cd Samsung_V4_STAGE_D
find . -type f ! -path "*__pycache__*" ! -name "*.pyc" \
  -exec sha256sum {} \; | sort -k2 > /tmp/manifest_actual.txt
diff /tmp/manifest_actual.txt FILE_MANIFEST_SHA256_STAGE_D.txt
# Ожидание: различий нет (пути в manifest даны относительно корня пакета)
```

## 2. Точный список изменений против Stage C.1

`STAGE_D_CHANGED_FILES.txt`: добавлены РОВНО 2 файла
(candidate/strategy_risk.py, candidate/tests/test_stage_d_strategy_risk.py);
изменённых 0; удалённых 0. Независимая перепроверка: распаковать
эталонный Samsung_V4_STAGE_C_1.zip и сравнить candidate:

```bash
diff -ru --exclude=__pycache__ --exclude=*.pyc \
  <C1_unpacked>/Samsung_V4_STAGE_C/candidate Samsung_V4_STAGE_D/candidate
# Ожидание: только "Only in .../candidate: strategy_risk.py"
#           и ".../tests: test_stage_d_strategy_risk.py"
```

## 3. Прогоны тестов

```bash
cd Samsung_V4_STAGE_D/candidate
python -m pytest tests/ -v        # ожидание: 1033 passed, 0 failed, 0 skipped
python -m pytest -v               # ожидание: 1553 passed, 0 failed, 0 skipped
python -m pytest tests/test_stage_d_strategy_risk.py -v   # 162 passed
```

Сверить с приложенными логами `appendix_stage_d/pytest_after_full.log`
и `appendix_stage_d/pytest_after_canonical.log` (и базовыми
`pytest_before_*.log`: 1391 / 871).

## 4. Проверка неизменности прошлых этапов

```bash
# Ключевые файлы принятых этапов — сверить SHA-256 с базой Stage C.1
sha256sum candidate/attribution.py candidate/strategy_api.py \
          candidate/config.py candidate/strategy_state.py \
          candidate/strategy_contracts.py candidate/execution.py \
          candidate/main.py candidate/risk_manager.py
# Сверить с STAGE_D_IMMUTABILITY_PROOF.txt (там базовые хеши) или с
# манифестом эталонного Stage C.1 пакета.
```

## 5. Функциональная проверка примеров из отчёта

```bash
cd candidate && python3 - <<'EOF'
import sys; sys.path.insert(0, '.')
from strategy_api import StrategyConfig, compute_config_hash
from attribution import AttributionContext
from strategy_risk import (RiskPolicy, SizingInput, TradeSide,
                           calculate_position_size, validate_sizing_result,
                           SizingOutcome)
config = StrategyConfig(strategy_id="alpha", strategy_version="1.0.0",
                        params={"n": 3},
                        config_hash=compute_config_hash("alpha","1.0.0",{"n":3}))
policy = RiskPolicy("alpha", config.config_hash, 0.01, 0.2)
inp = SizingInput(attribution=AttributionContext.from_config(config),
                  figi="FIGI1", side=TradeSide.LONG,
                  available_equity=100000.0, buying_power_limit=50000.0,
                  entry_price=100.0, protective_stop_price=95.0,
                  lot_size=10, contract_multiplier=1.0,
                  entry_cost_per_unit=0.05, stop_exit_cost_per_unit=0.05)
r = calculate_position_size(policy=policy, config=config, sizing_input=inp)
assert r.outcome is SizingOutcome.SIZED and r.quantity == 190
validate_sizing_result(r, expected_policy=policy, expected_config=config,
                       expected_input=inp)
print("OK:", r.quantity, r.lot_count, r.total_position_risk)
EOF
# Ожидание: OK: 190 19 969.0
```

## 6. Проверка fail-closed вручную (выборочно)

```python
# SHORT блокируется:
calculate_position_size(policy=policy, config=config,
                        sizing_input=SizingInput(..., side=TradeSide.SHORT))
# -> SizingOutcome.UNSUPPORTED_SIDE / SIDE_UNSUPPORTED_SHORT, quantity == 0

# NaN не создаёт вход:
SizingInput(..., available_equity=float("nan"))
# -> SizingInputViolationError

# Tamper политики перехватывается:
object.__setattr__(policy, "risk_per_trade_fraction", 0.5)
calculate_position_size(...)  # -> POLICY_INVALID / POLICY_HASH_MISMATCH
policy.verify_policy_hash()   # -> RiskPolicyViolationError
```

## 7. Проверка отсутствия broker/execution изменений

`STAGE_D_NO_EXECUTION_CHANGES_PROOF.txt`: SHA-256 execution.py,
main.py, risk_manager.py и остальных runtime-файлов совпадают с
Stage C.1; код-уровневые broker-маркеры в новых файлах отсутствуют.

## 8. Если что-то не сходится

Остановить приёмку. Отличия тестовых счётчиков, лишние изменённые
файлы или несовпадение манифестов = пакет не соответствует отчёту.
Эталон для сравнения — приложенный DIFF_STAGE_C1_VS_D.patch и
FILE_MANIFEST_SHA256_STAGE_D.txt.
