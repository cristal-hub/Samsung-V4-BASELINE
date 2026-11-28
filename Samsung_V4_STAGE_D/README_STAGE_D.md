# README — STAGE D (SAMSUNG_V4_STAGE_D)

SAMSUNG V4 NEW STRATEGY ENGINE — STRATEGY-SPECIFIC RISK SIZING
База: Samsung_V4_STAGE_C_1 (Stage C.1 принят), commit
ee5080828dc71af5091d172568c7f6072c91196a
Статус: РЕАЛИЗОВАНО, на независимой проверке (не принято)

---

## Что нового в Stage D

Новый изолированный модуль `candidate/strategy_risk.py`: чистый,
детерминированный, строго-типизированный расчёт теоретического объёма
позиции по риск-политике, жёстко привязанной к точной паре
(strategy_id, config_hash). Никакого брокера, никакой сети, никаких
заявок, никакого состояния.

## Быстрая проверка

```bash
cd candidate
python -m pytest tests/ -v          # canonical: 1033 passed (871 + 162)
python -m pytest -v                 # full:      1553 passed (1391 + 162)
```

Быстрый пример:

```python
from strategy_api import StrategyConfig, compute_config_hash
from attribution import AttributionContext
from strategy_risk import (RiskPolicy, SizingInput, TradeSide,
                           calculate_position_size)

config = StrategyConfig(strategy_id="alpha", strategy_version="1.0.0",
                        params={"n": 3},
                        config_hash=compute_config_hash(
                            "alpha", "1.0.0", {"n": 3}))
policy = RiskPolicy(strategy_id="alpha", config_hash=config.config_hash,
                    risk_per_trade_fraction=0.01,
                    max_position_notional_fraction=0.2)
sizing_input = SizingInput(
    attribution=AttributionContext.from_config(config),
    figi="FIGI1", side=TradeSide.LONG,
    available_equity=100000.0, buying_power_limit=50000.0,
    entry_price=100.0, protective_stop_price=95.0,
    lot_size=10, contract_multiplier=1.0,
    entry_cost_per_unit=0.05, stop_exit_cost_per_unit=0.05)

result = calculate_position_size(policy=policy, config=config,
                                 sizing_input=sizing_input)
print(result.outcome, result.reason_code,
      result.quantity, result.lot_count)   # SIZED SIZED_LONG 190 19
```

## Файлы Stage D

| Файл | Назначение |
|---|---|
| `candidate/strategy_risk.py` | реализация (RiskPolicy / SizingInput / SizingOutcome / SizingResult / calculate_position_size / validate_sizing_result) |
| `candidate/tests/test_stage_d_strategy_risk.py` | 162 offline-теста (§10.1–§10.17 + fail-closed §8 + негативные) |
| `IMPLEMENTATION_REPORT_STAGE_D.md` | итоговый отчёт §13 |
| `STAGE_D_ARCHITECTURE_REPORT.md` | архитектура |
| `KNOWN_LIMITATIONS_STAGE_D.md` | ограничения |
| `VERIFICATION_INSTRUCTIONS_STAGE_D.md` | инструкция проверки |
| `ROLLBACK_INSTRUCTIONS_STAGE_D.md` | откат |
| `STAGE_D_PRE_IMPLEMENTATION_BASELINE.md` | база до работ |
| `STAGE_D_CHANGED_FILES.txt` | точный список добавленного (2 файла) |
| `STAGE_D_IMMUTABILITY_PROOF.txt` | неизменность прошлых этапов (0 нарушений) |
| `STAGE_D_NO_EXECUTION_CHANGES_PROOF.txt` | broker/execution не тронуты |
| `STAGE_D_NO_TEST_LOSS_CHECK.txt` | 0 потерянных тестов |
| `STAGE_D_NEW_TESTS_LIST.txt` | список 162 новых тестов |
| `TEST_RESULTS_STAGE_D.txt` | сводка прогонов |
| `DIFF_STAGE_C1_VS_D.patch` | точный diff Stage C.1 -> Stage D |
| `FILE_MANIFEST_SHA256_STAGE_D.txt` | SHA-256 manifest пакета |
| `CANDIDATE_SHA256_STAGE_D.txt` | SHA-256 manifest candidate/ |
| `appendix_stage_d/` | полные pytest-логи до/после |

## Гарантии

* Только 2 НОВЫХ файла; 177 файлов candidate Stage C.1 — byte-for-byte
  без изменений; 269 файлов всего пакета — без изменений.
* full: 1391 -> 1553 passed; canonical: 871 -> 1033 passed;
  zero failed; zero skipped; старые тесты не потеряны/не ослаблены;
  golden fixtures не перегенерировались.
* Fail-closed: любые недостаточные/некорректные/несогласованные/
  нефинитные входы -> блокирующий типизированный результат или
  исключение создания объекта; ноль/последняя цена/умолчания никогда
  не подставляются; блокирующий результат никогда не несёт
  положительный объём.
* Округление СТРОГО вниз до целого лота точной целочисленной
  математикой (Decimal; без float в решениях).
* Legacy Samsung V4 остаётся REGRESSION_ONLY. Stage E не начинался.
