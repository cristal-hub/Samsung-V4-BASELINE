# ROLLBACK_INSTRUCTIONS.md
# SAMSUNG V4 — NEW STRATEGY ENGINE. STAGE A

Откат Этапа A прост по построению: ни один существующий файл baseline не
изменён — вся функциональность добавлена 18 новыми файлами. Полный откат =
удаление добавленных файлов.

## 1. Что нужно знать перед откатом

- Baseline-коммит: `884cefd6f12a99f6adc14b5ed4c9eeda21d32e04`
  (cristal-hub/Samsung-V4-BASELINE).
- Список добавленных файлов — см. `BASELINE_VS_CANDIDATE.md` §3 (18 файлов).
- Изменённых/удалённых файлов baseline НЕТ: `BASELINE_VS_CANDIDATE.md` §1
  (155 идентичны / 0 изменены / 0 удалены).
- `candidate/orders.zip` в поставке отсутствует (запрещённые ТЗ §14
  пользовательские данные внутри), но в вашей рабочей копии он остаётся
  нетронутым — НЕ удаляйте его при откате.

## 2. Полный откат (candidate вернется к baseline 1:1)

Из корня проекта (каталог, где лежит `candidate/`):

```bash
# Linux/macOS
rm -f  candidate/engine.json \
       candidate/strategy_api.py \
       candidate/engine_config.py \
       candidate/attribution.py
rm -rf candidate/strategies
rm -f  candidate/tests/test_stage_a_strategy_api.py \
       candidate/tests/test_stage_a_engine_config.py \
       candidate/tests/test_stage_a_schema.py \
       candidate/tests/test_stage_a_legacy_profiles.py \
       candidate/tests/test_stage_a_legacy_adapter.py \
       candidate/tests/test_stage_a_attribution.py \
       candidate/tests/stage_a_golden_tools.py
rm -rf candidate/tests/fixtures
```

```powershell
# Windows PowerShell
Remove-Item -Force `
  candidate\engine.json, `
  candidate\strategy_api.py, `
  candidate\engine_config.py, `
  candidate\attribution.py
Remove-Item -Recurse -Force candidate\strategies
Remove-Item -Force `
  candidate\tests\test_stage_a_strategy_api.py, `
  candidate\tests\test_stage_a_engine_config.py, `
  candidate\tests\test_stage_a_schema.py, `
  candidate\tests\test_stage_a_legacy_profiles.py, `
  candidate\tests\test_stage_a_legacy_adapter.py, `
  candidate\tests\test_stage_a_attribution.py, `
  candidate\tests\stage_a_golden_tools.py
Remove-Item -Recurse -Force candidate\tests\fixtures
```

После удаления проверьте откат:

```bash
cd candidate && python -m pytest      # ожидается 771 passed / 0 failed
cd candidate && python -m pytest tests # ожидается 251 passed / 0 failed
```

## 3. Проверка, что откат полный (байт-сверка)

Сверьте SHA-256 production-файлов с манифестом в
`BASELINE_VS_CANDIDATE.md` §2 (например, `sha256sum candidate/strategy.py`
или `Get-FileHash` в PowerShell) — значения должны совпасть с указанными.
Полный список baseline-файлов: `git ls-tree -r --name-only 884cefd` в
клонированном репозитории-источнике.

## 4. Частичный откат / отключение отдельных механизмов

- **Отключить конфигурацию движка, оставив остальное:** значение
  `ACTIVE_STRATEGY` в `engine.json` уже `null` (UNCONFIGURED) — торговый
  режим заблокирован. Никаких дополнительных действий не требуется.
- **Запретить regression-адаптер:** после удаления `candidate/strategies`
  реестр пуст; `engine_config` вернёт CONFIG_ERROR для любого непустого
  ACTIVE_STRATEGY (fail-closed).
- **Удалить только тесты Stage A:** удалить 7 файлов из §2
  (`test_stage_a_*.py`, `stage_a_golden_tools.py`, `tests/fixtures/`) —
  остальная функциональность Этапа A продолжит работать.

## 5. Откат данных пользователя

Не требуется: Stage A не создавал, не изменял и не мигрировал
пользовательские данные (state.json, research_trades.csv,
research_events.jsonl, order_ledger.jsonl, runtime.env/.env) — эти файлы
функциональностью Этапа A не затрагиваются.

## 6. Откат окружения (опционально)

Пакеты, установленные при прогоне тестов (pandas-ta-classic 0.3.15,
python-telegram-bot 21.11.1, setuptools<81), не требуются для работы
baseline-кода без тестов; при желании их можно удалить стандартным
`pip uninstall`. Изменений в `requirements.txt` не вносилось.

## 7. После отката

Этап A считается полностью откаченным, когда:
1) 18 файлов удалены; 2) полный regression suite возвращает результат
baseline (771 passed / 0 failed в окружении с pandas-ta-classic; 753/18
в окружении чистых заглушек — известные ошибки baseline); 3) SHA-256
production-файлов совпадают с baseline.

Этап B не начинался и не должен начинаться без отдельного подтверждения
владельца (ТЗ §17).
