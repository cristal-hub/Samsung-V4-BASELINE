# STAGE E — CHANGED FILES

Stage E НЕ изменяет ни одного существующего файла.
Все изменения — ТОЛЬКО НОВЫЕ файлы (16). Статус каждого — ADDED; MODIFIED/DELETED отсутствуют.

База сравнения: Stage D.1 (полное дерево candidate).
Для каждого нового файла: точный путь, назначение, SHA-256 новой версии. Исходной версии не существует (файлы созданы заново).

| # | Путь | Статус | Назначение | SHA-256 (новый) |
|---|---|---|---|---|
| 1 | `candidate/historical_engine/__init__.py` | ADDED | публичный реэкспорт пакета historical_engine | `725b0c038499b13556000f7bf3a3577f6d81d7edc8b769dbccf49d1c5ebebb8c` |
| 2 | `candidate/historical_engine/models.py` | ADDED | Candle/CandleSeries/EngineConfig/SegmentSpec, канонические хеши | `55ad69ca0602eb07699bcb7a09d1b0e4cb2a1360eb12bb679c7e6fe52eb637d0` |
| 3 | `candidate/historical_engine/data_feed.py` | ADDED | HistoricalDataFeed: хронология, пропуски, отсутствие будущего | `bdeed50665affe67023b920d7f73632af8ecb5e590349bd2df2957d968870784` |
| 4 | `candidate/historical_engine/ledger.py` | ADDED | PortfolioLedger: кэш, позиции, PnL, комиссии, история, инварианты | `b12ccf73414db8e960e93abb2a341ea8ce8773c8c1b8e28fba5cadb1c4ec0fc3` |
| 5 | `candidate/historical_engine/risk_integration.py` | ADDED | RiskIntegration: размер позиции строго через Stage D | `467899281f4d111e615edd79ea0e8b364794d91477b4a3d444962bbd181e7d91` |
| 6 | `candidate/historical_engine/execution.py` | ADDED | HistoricalExecutionSimulator: next-open, slippage, SL/TP, гэпы | `ec2cf9f47bc574fe40be420092d64e6a5c2e002d348978c2c99d54276767769a` |
| 7 | `candidate/historical_engine/strategy_runner.py` | ADDED | StrategyRunner: контракты Stage A/C, оценщики выхода | `79ad78b75f5e962c9c07d9d5d88758d85d138fd7068ffafaeda4c3a5fe9cf3a6` |
| 8 | `candidate/historical_engine/event_engine.py` | ADDED | EventEngine: детерминированные фазы на каждой свече | `5392eba3701ee6993cee91d9d3dd22146a7b23c446b6af084a3c1104c7c89a54` |
| 9 | `candidate/historical_engine/report.py` | ADDED | BacktestReport: статистика, издержки, причины, SHA-256 | `18b80b0dc97f1c20eb1381bb9fe8259722ac6699f3ad60cd3cb34c256c86caed` |
| 10 | `candidate/historical_engine/engine.py` | ADDED | BacktestEngine: фасад, независимые IS/VALIDATION/OOS прогоны | `a3dbeb5c493fd228aea7c4148dc0e65a42c9acc2526b40aa7e698188e261713e` |
| 11 | `candidate/tests/stage_e_tools.py` | ADDED | вспомогательные детерминированные стратегии/данные тестов | `51d0946d16380e1908e8adca7200d69b934ae986e1f4d0dfca58da1b2dd0015e` |
| 12 | `candidate/tests/test_stage_e_data_feed.py` | ADDED | 24 теста: хронология, некорректные данные, пропуски, future-proof | `dbd4155a2d06a2ba32775625f56237d0675b65a5b4b16632dd96e4ddf863472a` |
| 13 | `candidate/tests/test_stage_e_engine_decisions.py` | ADDED | 15 тестов: look-ahead, next-open, детерминизм, Stage D, изоляция, IS/VALIDATION/OOS, неразрешённые решения | `dc906b3e4fdfac5efe8da00324b7b2c0e979a3b51863c353553afa7c7164fd73` |
| 14 | `candidate/tests/test_stage_e_execution_ledger.py` | ADDED | 25 тестов: slippage, комиссии, SL/TP/конфликт/гэп, границы лотов и лимитов, недостаточный капитал/BP, инварианты ledger, LONG/SHORT | `898071e2dd04bc5a8e95d6926d97f54daa6335f57769ba10ebfd4dbf15600295` |
| 15 | `candidate/tests/test_stage_e_integration.py` | ADDED | 6 тестов: Stage B/C интеграция, защитный слой, legacy-прогон | `c1a6cddaad3d8ed07012c7f3580a2658b6dc221dbcac37be4cad9604029964b3` |
| 16 | `candidate/tests/test_stage_e_report.py` | ADDED | 10 тестов: PF/WinRate/avg, просадка, канонический JSON, SHA-256 | `306ad6b63e89becb94b6c5af64d03bfd710c6e0ca64fb29e770ecfcede3d3956` |

## Проверка остальных файлов

* все прочие файлы дерева candidate совпадают байт-в-байт с принятым Stage D.1 (SHA-256, 0 исключений) — см. STAGE_E_NO_CHANGES_ABCD_PROOF.txt;
* принятые контракты Stage A/B/C/D не тронуты;
* торговое исполнение и инфраструктура legacy не тронуты;
* golden fixtures не перегенерировались.

## Замена файлов в репозитории

Из этой поставки заменять существующие файлы НЕ нужно (замены нет). Достаточно РАЗМЕСТИТЬ 16 новых файлов с сохранением относительных путей — остальное дерево уже совпадает с Stage D.1.
