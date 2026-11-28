# README — STAGE E (SAMSUNG_V4_STAGE_E)

SAMSUNG V4 NEW STRATEGY ENGINE — DETERMINISTIC EVENT-DRIVEN
HISTORICAL BACKTEST ENGINE
База: Stage D.1 (strategy_risk.py `7f25b4ef…`,
tests/test_stage_d_strategy_risk.py `0cade296…`; full 1570 / canonical 1050)
Статус: РЕАЛИЗОВАНО, на независимой проверке (не принято)

STRICT RESEARCH ONLY: только исторические данные, только виртуальная
симуляция. Никаких реальных ордеров, Sandbox/LIVE, брокерских SDK,
сетевых запросов. Legacy Samsung V4 — REGRESSION_ONLY. FORCE_TRADE
отсутствует. Автооптимизация стратегических порогов отсутствует.

---

## Что нового в Stage E

Новый изолированный пакет `candidate/historical_engine/` — детермини-
рованный исторический симулятор, использующий ПРИНЯТЫЕ контракты
Stage A/B/C/D без их изменения:

| Компонент | Файл | Назначение |
|---|---|---|
| HistoricalDataFeed | `data_feed.py` | хронологическая подача закрытых свечей; контроль пропусков/некорректных данных; физическая невозможность доступа к будущим свечам |
| Candle/CandleSeries/EngineConfig/SegmentSpec | `models.py` | типизированные неизменяемые модели, канонические хеши |
| EventEngine | `event_engine.py` | фиксированный порядок фаз на каждой свече; без системного времени и случайности |
| StrategyRunner | `strategy_runner.py` | вызов контрактов Stage A/C; EntryDecision/ExitDecision; защитный и стратегический оценщики |
| HistoricalExecutionSimulator | `execution.py` | виртуальное исполнение: next-open, slippage, гэпы, эмуляция SL/TP |
| RiskIntegration | `risk_integration.py` | размер позиции СТРОГО через Stage D `calculate_position_size` (без дублирования формулы) |
| PortfolioLedger | `ledger.py` | виртуальные позиции, кэш, PnL, комиссии, история операций, инвариант сохранения денег |
| BacktestReport | `report.py` | статистика, доходность, просадка, PF, Win Rate, издержки, причины входов/выходов; SHA-256 отчёта |
| BacktestEngine | `engine.py` | фасад; независимые прогоны IS/VALIDATION/OOS |

## Быстрая проверка

```bash
cd candidate
python -m pytest tests/ -q     # canonical: 1130 passed (1050 + 80)
python -m pytest -q            # full:      1650 passed (1570 + 80)
```

Минимальный пример:

```python
from historical_engine import (BacktestEngine, EngineConfig,
                               HistoricalDataFeed)
from tests.stage_e_tools import (AlwaysBuyStrategy, make_candles,
                                 make_strategy_config)

strategy = AlwaysBuyStrategy()
config = make_strategy_config(strategy, {"warmup": 1})
engine_config = EngineConfig(
    figi="TESTFIGI1", ticker="TEST", initial_cash=100000.0,
    commission_rate=0.001, slippage_rate=0.0005,
    stop_loss_fraction=0.02, take_profit_fraction=None,
    lot_size=10, contract_multiplier=1.0,
    risk_per_trade_fraction=0.01, max_position_notional_fraction=0.5)
feed = HistoricalDataFeed.from_candles(
    make_candles([{"o": 100, "h": 100.1, "l": 99.9, "c": 100}] * 40),
    engine_config=engine_config)
engine = BacktestEngine(strategy=strategy, strategy_config=config,
                        engine_config=engine_config, feed=feed)
report = engine.run_full()
print(report["statistics"]["profit_factor"],
      report["report_sha256"][:16])
```

## Запуск legacy-стратегии (regression-only)

```python
from strategies.legacy_samsung_v4.strategy import LegacySamsungV4Strategy
strategy = LegacySamsungV4Strategy()
config = strategy.build_regression_config("SANDBOX_TEST")  # ЯВНЫЙ профиль
# далее — как в примере выше; требуется pandas_ta_classic (офлайн-расчёт)
```

## IS / VALIDATION / OOS

```python
from historical_engine import SegmentSpec
bundle = engine.run_segments([
    SegmentSpec(label="IS", start_index=0, end_index=400),
    SegmentSpec(label="VALIDATION", start_index=400, end_index=600),
    SegmentSpec(label="OOS", start_index=600, end_index=800),
])
# каждый сегмент — независимый прогон (позиции не переносятся);
# движок НЕ оптимизирует параметры и не извлекает их из отчётов
```

## Границы изменений Stage E

Добавлены ТОЛЬКО новые файлы (16): `candidate/historical_engine/*.py`
(10 файлов) и тесты Stage E (`candidate/tests/test_stage_e_*.py` +
`candidate/tests/stage_e_tools.py`). Не изменён НИ ОДИН существующий
файл — проверено байт-в-байт (см. STAGE_E_NO_CHANGES_ABCD_PROOF.txt).
Файлы, не входящие в перечень Stage E, заменять не нужно.
