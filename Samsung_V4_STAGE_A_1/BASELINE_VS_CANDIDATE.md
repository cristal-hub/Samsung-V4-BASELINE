# BASELINE_VS_CANDIDATE.md
# SAMSUNG V4 — NEW STRATEGY ENGINE. STAGE A

Сравнение baseline (commit `884cefd6f12a99f6adc14b5ed4c9eeda21d32e04`)
и candidate (Stage A). Метод: SHA-256 каждого файла baseline против
соответствующего файла candidate; перечень добавленных файлов.

## 1. Сводка

| Метрика | Значение |
|---|---|
| Файлов в baseline (tracked, commit 884cefd) | 156 |
| Файлов в candidate (без `__pycache__`, `.pytest_cache`) | 174 |
| **Байт-идентичны** | **155** (все файлы baseline, кроме исключённого из поставки `orders.zip`, который также байт-идентичен — см. §4) |
| **Изменены** | **0** |
| **Добавлены** | **18** (только новые файлы Этапа A) |
| **Удалены** | **0** |

Вывод: candidate = baseline + 18 новых файлов. Ни один существующий файл
не изменён.

## 2. Требование ТЗ §13: торговая логика не изменилась

Так как все production-файлы байт-идентичны baseline, каждое поведение из
списка ТЗ §13 гарантированно не изменено:

| Поведение | Где определено | Файл байт-идентичен baseline | Вывод |
|---|---|---|---|
| Условия BUY | `strategy.py` | да | UNCHANGED |
| Условия SELL | `strategy.py` | да | UNCHANGED |
| Расчёт RSI | `strategy.py` (pandas_ta) | да | UNCHANGED |
| Расчёт ADX | `strategy.py` (pandas_ta) | да | UNCHANGED |
| Расчёт MA | `strategy.py` (pandas_ta) | да | UNCHANGED |
| Параметры индикаторов | `config.py` | да | UNCHANGED |
| Стоп-лосс | `config.py`, `risk_manager.py`, `execution.py` | да | UNCHANGED |
| Тейк-профит | `config.py`, `risk_manager.py`, `execution.py` | да | UNCHANGED |
| ATR | `config.py`, `risk_manager.py` | да | UNCHANGED |
| Расчёт позиции | `risk_manager.py`, `config.py` | да | UNCHANGED |
| Лимиты риска | `config.py`, `risk_manager.py` | да | UNCHANGED |
| Комиссии | `config.py`, `execution.py` | да | UNCHANGED |
| Проскальзывание | `config.py`, `execution.py` | да | UNCHANGED |
| Исполнение заявок | `execution.py`, `tinkoff_client.py`, `main.py` | да | UNCHANGED |
| Закрытие позиций | `main.py`, `execution.py`, `order_ledger.py` | да | UNCHANGED |
| Логика мониторинга | `main.py`, `screener.py` | да | UNCHANGED |
| Исторический `PROFILE = "FORCE_TRADE"` | `config.py` | да | UNCHANGED (не расширяется, не переносится) |

SHA-256 ключевых production-файлов (одинаковы в baseline и candidate):

| Файл | SHA-256 |
|---|---|
| `candidate/strategy.py` | `43906866a226aabae0fff266dde77d88345ae27f87b0948689929aa37171537f` |
| `candidate/config.py` | `6c4df6e4768b31b78e1daa1cbbe0e2961d5de68918f5856888e2c1be8422afae` |
| `candidate/risk_manager.py` | `d1c72c2ee09dc877803661c25028442413ffc13b2b9168efa59f99255e5982b8` |
| `candidate/execution.py` | `b2e63fdd386ecb9075a78310c4022ed281f793f248006531990ff174e0df725d` |
| `candidate/main.py` | `549ab619bf05aa3d5e25ca40eea7444ddf4bb7bf0c4fb95e28443f9658c9380b` |
| `candidate/order_ledger.py` | `4991f35ad2f2d38e96a500fbef9f3b6149bd916684a1364ab6be811a39bed783` |
| `candidate/screener.py` | `6db12eb1da4434fba2bb9997a676b86b7431b67bb0f9ae1e85b56db11d8341c9` |
| `candidate/logger.py` | `df22ed916cb2eda10473cb78c2f93846d0be00c8a7ad5913a6bab8d9ee8ad4c5` |
| `candidate/tinkoff_client.py` | `fe69b045e9ec3d415c43e71a0effe62fbfb38d2309d30c01d0b1d03155b569d7` |
| `candidate/telegram_bot.py` | `8a98ab4c5b5fe5070813e3ac4bf0f57f592c0d9ce5483df826ad1f2cd1ca1f6e` |
| `candidate/safe_start.py` | `34363dada2cb67c30937e908df09413a233e5e8d82ad0cc8ed6359532af97703` |
| `candidate/build_safety.py` | `0d47bcc97031f006114ae984b0de5028b372aa9cdc52fcc490608b4a9b333815` |
| `candidate/enable_sandbox_execution.py` | `628eb3fc44fc831b2c77420d4a55fd5246f0742be0de793fa1907ee63ab0f535` |
| `candidate/conftest.py` | `6c71b3acdcead539941a0a68b43be30d1a0f96e71b3582317b0c749d16ca8ec8` |

Полные манифесты — `FILE_MANIFEST_SHA256.txt` (candidate) и сверка с
baseline в §4 ниже.

## 3. Добавленные файлы (18)

```
candidate/engine.json
candidate/strategy_api.py
candidate/engine_config.py
candidate/attribution.py
candidate/strategies/__init__.py
candidate/strategies/legacy_samsung_v4/__init__.py
candidate/strategies/legacy_samsung_v4/strategy.py
candidate/strategies/legacy_samsung_v4/params.json
candidate/strategies/legacy_samsung_v4/profiles.py
candidate/strategies/legacy_samsung_v4/schema.py
candidate/tests/test_stage_a_strategy_api.py
candidate/tests/test_stage_a_engine_config.py
candidate/tests/test_stage_a_schema.py
candidate/tests/test_stage_a_legacy_profiles.py
candidate/tests/test_stage_a_legacy_adapter.py
candidate/tests/test_stage_a_attribution.py
candidate/tests/stage_a_golden_tools.py
candidate/tests/fixtures/legacy_golden_signals.json
```

Назначение каждого файла — `IMPLEMENTATION_REPORT.md` §3 и `CHANGELOG.md`.

## 4. Особый случай: candidate/orders.zip

Файл `candidate/orders.zip` присутствует в baseline-коммите и в candidate
**байт-идентичен** baseline (`dd1d00c0c5624848c1d2547f524f513fc99e0c82966285aa02e91ac19adac845`
в обеих копиях — файл не изменялся). Однако он ИСКЛЮЧЁН из поставки (ZIP):
внутри архива — реальные пользовательские runtime-файлы владельца
(`state.json`, `order_ledger.jsonl`, `research_events.jsonl`,
`research_trades.csv`, `main_console.txt`), включение которых прямо
запрещено ТЗ §14. Его отсутствие в поставке НЕ является изменением кода:
при развёртывании поверх существующей копии владельца файл уже есть;
SHA-256 для сверки приведён здесь.

## 5. Изменённые файлы

Отсутствуют. «Изменять только то, что необходимо для подключения
контрактов, конфигурации и атрибуции» (ТЗ §11): подключение контрактов и
конфигурации выполнено новыми модулями; безопасное встраивание атрибуции в
производственный поток требует изменения схемы журналов у пользователей —
зафиксировано как блокер с минимальным решением
(`IMPLEMENTATION_REPORT.md` §13.3), объём самостоятельно не расширялся.

## 6. Тесты: baseline → candidate

| Прогон | baseline | candidate |
|---|---|---|
| `python -m pytest` (полный) | 771 passed / 0 failed | 899 passed / 0 failed (+128 новых тестов Этапа A) |
| `python -m pytest tests` | 251 passed / 0 failed | 379 passed / 0 failed (+128) |

Новых ошибок нет; ни один baseline-тест не изменил исход; удаления/переименования
тестов baseline отсутствуют.
