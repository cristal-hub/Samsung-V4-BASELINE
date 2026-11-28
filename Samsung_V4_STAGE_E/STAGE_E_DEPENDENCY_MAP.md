# STAGE E — КАРТА ЗАВИСИМОСТЕЙ

Составлена ДО реализации (ТЗ Stage E §10). Направление стрелок:
«A → B» = A импортирует/использует B.

## 1. Новые файлы Stage E → принятые контракты

| Новый файл | Использует (принято) |
|---|---|
| `historical_engine/models.py` | — (стандартная библиотека) |
| `historical_engine/data_feed.py` | models (Candle/CandleSeries/EngineConfig), pandas (только локальные данные) |
| `historical_engine/ledger.py` | models |
| `historical_engine/risk_integration.py` | **strategy_risk** (AttributionContext, RiskPolicy, SizingInput, TradeSide, calculate_position_size) — Stage D; **strategy_api** (StrategyConfig) — Stage A; models |
| `historical_engine/execution.py` | ledger, models, risk_integration; **strategy_risk** (SizingOutcome) — Stage D |
| `historical_engine/strategy_runner.py` | **strategy_api** (EntrySignalInput, Strategy, StrategyConfig) — Stage A; **strategy_contracts** (EntryEvaluation*, ExitDecisionCoordinator, ExitEvaluation*, PriceData) — Stage C; **strategy_state** (StateStore, StrategyStateManager) — Stage B.1; data_feed, models |
| `historical_engine/event_engine.py` | strategy_api (Strategy, StrategyConfig); data_feed, execution, ledger, models, strategy_runner |
| `historical_engine/report.py` | data_feed, ledger, models; **strategy_api** (StrategyConfig) — Stage A |
| `historical_engine/engine.py` | strategy_api (Strategy, StrategyConfig); data_feed, event_engine, execution, ledger, models, report, risk_integration, strategy_runner |
| `historical_engine/__init__.py` | публичный реэкспорт всех компонентов |

Внешние сторонние зависимости новых файлов: **pandas** (только
преобразование локальных свечей в DataFrame для контракта Stage A
EntrySignalInput; никакой сети).

## 2. Принятые контракты, задействованные Stage E (как есть, без изменений)

| Этап | Модуль | Что используется |
|---|---|---|
| A | `strategy_api.py` | Strategy, StrategyConfig, EntrySignalInput, Signal, SignalDirection, ParamSpec/ParamType, compute_config_hash |
| B.1 | `strategy_state.py` | StateStore (memory-режим path=None), StrategyStateManager, StateConfigMismatchError |
| C | `strategy_contracts.py` | EntryEvaluationRunner, EntryEvaluation/EntryOutcome, ExitDecisionCoordinator, ExitDecisionReport, ExitEvaluation/ExitOutcome/ExitDecisionSource, ExitEvaluationRequest, PriceData, check_price (внутри price gate), merge_exit_evaluations (внутри координатора) |
| D | `strategy_risk.py` | calculate_position_size, RiskPolicy, SizingInput, SizingResult, SizingOutcome, TradeSide, AttributionContext |

## 3. ЧТО НЕ ИСПОЛЬЗУЕТСЯ И НЕ ИЗМЕНЯЕТСЯ Stage E

* legacy исполнение: `execution.py`, `main.py`, `risk_manager.py`,
  `tinkoff_client.py`, `telegram_bot.py`, `screener.py`, `safe_start.py`,
  `order_ledger.py`, `build_safety.py`, `enable_sandbox_execution.py`,
  `engine_config.py`, `logger.py`, `config.py` (baseline) — НЕ
  импортируются новыми файлами, НЕ изменяются (проверено статически и
  байт-в-байт);
* FORCE_TRADE — отсутствует (не используется, не возвращается);
* брокерские SDK/сеть — отсутствуют (проверено сканом);
* стратегическая логика legacy (`strategy.py`, StrategyManager) — не
  копируется; legacy-адаптер Stage A вызывается как есть ТОЛЬКО через
  `build_regression_config` (REGRESSION_ONLY, origin=regression_harness).

## 4. Отсутствие циклических зависимостей

Граф новых модулей — DAG:

```
models ─→ data_feed ─→ strategy_runner ─→ event_engine ─→ engine
   │            │                              │
   ├─→ ledger ──┼─→ execution ─────────────────┤
   │            │        │                     │
   └─→ risk_integration ┘                     │
report ───────────────────────────────────────┘ (data_feed, ledger, models)
```

`risk_integration` → strategy_risk (Stage D); `strategy_runner` →
strategy_api/strategy_contracts/strategy_state (Stage A/B/C). Ни один
принятый модуль не импортирует Stage E — зависимости строго однонап-
равленны «новое → принятое».

## 5. Тесты Stage E → тестируемые компоненты

| Тест-файл | Покрывает |
|---|---|
| `tests/test_stage_e_data_feed.py` | data_feed, models (валидация, пропуски, отсутствие будущего) |
| `tests/test_stage_e_execution_ledger.py` | execution, ledger, risk_integration (издержки, SL/TP/гэпы, границы лотов/лимитов, инварианты) |
| `tests/test_stage_e_engine_decisions.py` | event_engine, strategy_runner, engine, risk_integration (look-ahead, next-open, детерминизм, Stage D-интеграция, изоляция, IS/VALIDATION/OOS) |
| `tests/test_stage_e_integration.py` | Stage B.1+C интеграция, защитный оценщик, бандл, legacy-прогон |
| `tests/test_stage_e_report.py` | report, ledger (статистика, PF, просадка, канонический JSON, SHA-256) |
| `tests/stage_e_tools.py` | вспомогательные детерминированные стратегии/данные (не test-*) |
