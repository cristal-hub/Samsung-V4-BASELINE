# STAGE E — ДОКАЗАТЕЛЬСТВО ОТСУТСТВИЯ LOOK-AHEAD BIAS И ДЕТЕРМИНИЗМА

## 1. Look-ahead bias: структурные гарантии

**G1. Данные к стратегии идут только через срез [0..i].**
Единственный канал — `HistoricalDataFeed.view_upto(i)` /
`entry_dataframe_upto(i)`; `CandleSeries.slice_upto` физически не может
отдать индекс >= i (raises DataFeedError). Метода, выдающего полную серию
в путь решений, у кормушки НЕТ. DataFrame — защитная копия.

**G2. Решение на закрытии i исполняется не ранее открытия i+1.**
Фазы EventEngine: исполнение (Ф1) → защита (Ф2) → решения (Ф3);
решения Ф3 всегда попадают в отложенную очередь и исполняются в Ф1
СЛЕДУЮЩЕЙ свечи. Вход по цене сигнальной свечи невозможен по построению.

**G3. Отсутствующие данные не подменяются.**
Пропуски обнаруживаются по явному интервалу (REPORT/STRICT);
интерполяции нет; NaN/Infinity/наивные метки отклоняются при сборке.

**G4. Цена price gate не из будущего.**
PriceData несёт метку времени закрытия свечи; Stage C `check_price`
(внутри ExitDecisionCoordinator) проверяет будущие метки
(`PRICE_FROM_FUTURE`) — в историческом прогоне все метки в прошлом или
равны моменту решения.

## 2. Тестовые доказательства (80 тестов Stage E)

| Гарантия | Тест |
|---|---|
| Стратегия видит ровно k+1 свечей на k-й свече, последняя метка == свече k | `test_strategy_never_sees_future_candles` |
| Вход по open СЛЕДУЮЩЕЙ свечи, не по close сигнальной (гэп +5%) | `test_signal_after_close_executes_next_open_not_signal_close` |
| Вход/выход никогда не совпадают со свечой решения | `test_no_execution_on_decision_candle_close` |
| view_upto не отдаёт будущее; отрицательный/завышенный индекс — ошибка | `test_view_upto_never_returns_future_candles` |
| Мутации DataFrame не влияют на данные движка | `test_entry_dataframe_upto_is_defensive_copy` |
| Пропуск обнаружен и задокументирован; STRICT запрещает | `test_gap_detection_report_policy`, `test_gap_policy_strict_rejects_series_with_gap` |
| SL/TP в одной свече → консервативный SL + флаг | `test_sl_and_tp_same_candle_conservative_sl_wins` |
| Гэп через стоп → выход по open (хуже стопа) | `test_stop_loss_gap_through_stop_executes_at_open` |

## 3. Детерминизм: структурные гарантии

* НЕТ `datetime.now`/`time.*`/`random`/`os.environ`/`uuid` в новых
  файлах (статический скан — STAGE_E_NO_BROKER_SDK_PROOF.txt);
* все метки времени — из данных свечей; часы Stage B.1/Stage C
  инъекцированы меткой текущей свечи;
* фиксированный порядок фаз; сортировки стабильные; JSON канонический
  (sort_keys, компактные разделители, allow_nan=False);
* run_id = SHA-256{data_sha256, engine_config_sha256,
  strategy_config_hash, segment, границы, версия движка};
  report_sha256 = SHA-256 канонического JSON отчёта (без полей хеша).

## 4. Тестовые доказательства детерминизма

| Свойство | Тест |
|---|---|
| Два прогона — идентичные отчёты и report_sha256 | `test_rerun_produces_identical_report_and_hash` |
| run_id чувствителен к данным, стабилен при повторе | `test_run_id_derives_from_data_config_and_segment` |
| engine_config_sha256 чувствителен к параметрам симуляции | `test_report_sha_covers_engine_config_change` |
| Хеш воспроизводится из канонического JSON | `test_report_json_is_canonical_and_hash_stable` |
| В отчёте нет NaN/Infinity | `test_report_contains_no_nan_or_infinity` |
| Legacy-стратегия (pandas_ta): два прогона — один хеш | `test_legacy_samsung_v4_regression_config_backtest_deterministic` |
| Прогон A не изменяется прогоном B (изоляция) | `test_strategy_isolation_no_state_bleed` |
| Сегмент OOS из бандла == тот же сегмент отдельно | `test_is_validation_oos_segments_run_independently` |

## 5. Честность модели исполнения (не «бумажная прибыль»)

* издержки обеих сторон фиксируются в каждой сделке (комиссия +
  проскальзывание), а также суммарно в costs;
* проскальзывание всегда неблагоприятное и ограничено диапазоном свечи;
* гэп через стоп исполняется по open (хуже стопа) — убыток не сглаживается;
* SL/TP-неоднозначность разрешается консервативно (SL) и помечается;
* Profit Factor без убыточных сделок — None с пометкой, не inf;
* нереализованные решения на границе не исполняются задним числом;
* buy&hold-бенчмарк включён для честного сравнения;
* размер позиции — только Stage D (тот же контракт, что и в реальной
  системе), блокировки входов документируются с reason_code.
