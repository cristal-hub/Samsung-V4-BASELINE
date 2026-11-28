# VERIFICATION INSTRUCTIONS — STAGE C.1

Дата: 2026-11-28. Окружение проверки: Python 3.12.16, pytest 9.0.2.
Все проверки offline, без сети и брокера.

## 1. Целостность пакета

```bash
# SHA256 каждого файла пакета против manifest:
sha256sum -c FILE_MANIFEST_SHA256_STAGE_C1.txt   # (строки-комментарии игнорируются)
# ожидание: все OK, 0 FAILED
```

## 2. Неизменность Stage A.2.1 / Stage B.1 / runtime

```bash
# Побайтовое сравнение с кандидатом Stage C:
# 1) распаковать доставленный Samsung_V4_STAGE_C.zip в ../stage_c_ref
# 2) сравнить все файлы, КРОМЕ двух разрешённых:
diff -r --exclude='__pycache__' --exclude='.pytest_cache' \
     --exclude='DIFF_STAGE_C_VS_C1.patch' \
     --exclude='STAGE_C1_*' --exclude='FILE_MANIFEST_SHA256_STAGE_C1.txt' \
     --exclude='IMPLEMENTATION_REPORT_STAGE_C1.md' \
     --exclude='README_STAGE_C1.md' \
     --exclude='TEST_RESULTS_STAGE_C1.txt' \
     --exclude='CHANGED_FILES_STAGE_C1.md' \
     --exclude='appendix_stage_c1' \
     ../stage_c_ref/candidate candidate
# ожидание: различия ТОЛЬКО в strategy_contracts.py и
# tests/test_stage_c_exit_service.py
```
Ключевые файлы, обязанные быть IDENTICAL (см.
`STAGE_C1_IMMUTABILITY_PROOF.txt`): `attribution.py`, `strategy_api.py`,
`strategy_state.py` (Stage B.1), все тесты `test_stage_a*`,
`test_stage_b*`, `execution.py`, `risk_manager.py`, `main.py`,
`strategies/legacy_samsung_v4/**`,
`tests/fixtures/legacy_golden_signals.json`.

## 3. Прогон тестов

```bash
cd candidate
python -m pytest -v          # полный набор  -> ожидание 1391 passed, 0 failed, 0 skipped
python -m pytest tests -v    # канонический   -> ожидание 871 passed, 0 failed, 0 skipped
```

## 4. Проверка именно исправления (дефект не воспроизводится)

Сценарий: блокирующая цена + ОТСУТСТВУЮЩАЯ запись — хранилище не должно
получить НИКАКИХ следов:

```python
import tempfile
from strategy_state import StateStore, StrategyStateManager
from strategy_api import StrategyConfig, compute_config_hash
from strategy_contracts import ExitDecisionCoordinator, ExitDecisionSource

with tempfile.TemporaryDirectory() as tmp:
    store = StateStore(path=tmp)
    manager = StrategyStateManager(store)
    config = StrategyConfig(strategy_id="alpha", strategy_version="1.0.0",
                            params={"n": 3},
                            config_hash=compute_config_hash("alpha", "1.0.0", {"n": 3}))
    coord = ExitDecisionCoordinator(manager=manager,
                                    strategic_evaluator=NoEval(),
                                    protective_evaluator=NoEval(),
                                    clock=lambda: "2026-11-28T12:00:00.000000+00:00")
    report = coord.evaluate_and_record(config=config, figi="FIGI1",
                                       price_required=True,
                                       price_max_age_seconds=120.0, price=None)
    assert report.merged.final_outcome.value == "INCOMPLETE_PRICE_EVALUATION"
    assert store.get_state("alpha", "FIGI1") is None      # записи НЕТ
    import os; assert not [n for n in os.listdir(tmp) if n.endswith(".json")]
```

Автотесты этого поведения: `tests/test_stage_c_exit_service.py::
TestPriceGateBeforeStateAccess` (7 тестов, ТЗ §4, включая проверку
публичного `StateStore.get_state()` и отсутствия файлов состояния).

## 5. Сверка логов

Полные реальные логи всех прогонов: `appendix_stage_c1/`
(`pytest_before_full.log` 1384 passed, `pytest_before_canonical.log`
864 passed, `pytest_after_full.log` 1391 passed,
`pytest_after_canonical.log` 871 passed; `negative_check_pre_fix.log`
— 3 failed/4 passed против ДО-исправного кода: сценарии 1-3 ловят
дефект; `no_test_loss_check.txt` — 0 потерянных, +7 добавленных).
