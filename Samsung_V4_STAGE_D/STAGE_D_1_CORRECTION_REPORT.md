# STAGE D.1 — CORRECTION REPORT
# SAMSUNG V4 NEW STRATEGY ENGINE — STAGE D.1 TARGETED CORRECTION

Режим: OFFLINE / READ ONLY DATA / RESEARCH ONLY / NO LIVE ORDERS /
NO REAL MONEY / NO SANDBOX EXECUTION. GitHub/commits/branches/PR — нет.
Status: ИСПРАВЛЕНО, НЕ принято (subject to independent review).

---

## 1. Объём аудита (ТЗ D.1 §3)

Повторная проверка реализации Stage D выполнена ПОЛНОСТЬЮ, до внесения
изменений:

1. Прочитан весь модуль `candidate/strategy_risk.py` (1881 строка
   исходной версии) и весь файл
   `candidate/tests/test_stage_d_strategy_risk.py` (1546 строк, 162
   теста) построчно.
2. Проверены фактические интерфейсы принятых этапов, потребляемые
   Stage D: `AttributionContext.from_config` (Stage A.2.1),
   `StrategyConfig`/`compute_config_hash`/`validate_config_hash_format`/
   `ImmutableMapping`/`unfreeze` (Stage A), `validate_figi`/
   `validate_strategy_id` (Stage B), `PriceData` (Stage C) — сигнатуры и
   инварианты совпадают с фактическим кодом Stage A/B/C.
3. Запущены ПОЛНЫЕ наборы тестов ДО изменений (см. §5).
4. Восстановлено окружение предыдущего прогона: в песочнице отсутствовал
   `pandas_ta_classic` (18 ошибок + 35 skip'ов чисто средовых причин,
   вне Stage D); после `pip install pandas-ta-classic` база
   воспроизвела точные счётчики Stage D: full **1553 passed**,
   canonical **1033 passed**, Stage D файл — **162 passed**.
5. Выполнен целевой математический аудит (см. §3): точные
   Fraction/Floor-эталоны для `_floor_ratio` (20 000 + 5 000
   fuzz-случаев), точные границы notional cap и buying power, hostile
   Decimal-контексты, экстремальные значения (subnormal × 1e308).

## 2. Найденные дефекты

### D-1 (дефект, ИСПРАВЛЕН): просачивание ambient-контекста Decimal

**Симптом.** `calculate_position_size` и `validate_sizing_result`
выполняли десятичную арифметику внутри `with localcontext() as ctx:
ctx.prec = 5000` — то есть переопределяли ТОЛЬКО точность. Все прочие
параметры контекста (Emax, Emin, rounding, traps) наследовались из
ambient-контекста процесса. При чужом (hostile) контексте, например
`decimal.setcontext()` с `Emax=2`, операция `equity * fraction`
(= 1000.0, adjusted exponent 3 > Emax=2) поднимала
`decimal.Overflow` — и (а) валидный вход блокировался как
`COMPUTATION_ERROR_FAIL_CLOSED` вместо `SIZED 190` (нарушение
детерминизма ТЗ Stage D §10.17 и собственного утверждения модуля
«ambient-контекст не влияет на результат»; собственный тест модуля
проверял только prec/rounding, поэтому дефект не ловил); (б) при
отключенном Overflow-trap операции могли получать `Infinity`; (в)
теоретически при чужом Emin результаты операций с малыми величинами
могли искажаться поднормальным округлением контекста. Money-safety не
нарушалась (любое искажение конвертировалось в блокирующий исход
gate 9 / точные проверки), НО детерминизм — контракт ТЗ §10.17 — был
нарушен, и валидатор мог ложно отклонить корректный результат.

**Исправление.** Введён ЯВНО зафиксированный модульный контекст
`_SIZING_DECIMAL_CONTEXT = Context(prec=5000, Emax=MAX_EMAX,
Emin=MIN_EMIN, rounding=ROUND_HALF_EVEN, traps=[InvalidOperation,
DivisionByZero, Overflow])` и оба места (`_compute_sized_or_zero_size`,
`_validate_sizing_result_exact`) переключены на
`with localcontext(_SIZING_DECIMAL_CONTEXT)`. `localcontext(ctx)`
работает с КОПИЕЙ контекста: ambient-контекст процесса не влияет ни на
один бит результата, модульный объект не мутируется. Границы
MAX_EMAX/MIN_EMIN (±999 999 999 999 999 999) на порядки шире любых
возможных входов (float ≤ ~1.8e308, произведения ~±656/-648 порядка) —
Overflow/Underflow контекста невозможны.

**Доказательства:** новые тесты `TestStageD1AmbientDecimalContextIsolation`
(8 тестов + 5 параметризованных комбинаций prec/rounding/Emax/Emin,
включая hostile-traps и отключенный Overflow-trap) — все проходят;
негативный прогон (см. §6) показывает, что 5 из них падают на
предкоррекционной реализации. Точный boundary-аудит после исправления:
все результаты идентичны эталонам, лимиты не превышаются.

### Проверено и НЕ является дефектом (исправлять нечего)

* `_floor_ratio`: точность подтверждена эталоном
  `floor(Fraction(a)/Fraction(b))` на 25 000 adversarial случаев
  (случайные конечные Decimal, экспоненты ±40, 1–40 значащих цифр;
  5 000 float-repr случаев) — 0 расхождений. Первичный «мисматч»
  fuzz-прогона был ошибкой эталона (деление в контексте prec=28 само
  округляло частное), а не реализации.
* Точные границы notional cap и buying power: ровно на границе объём
  принимается (SIZED, расход ЛИМИТА в точности равен капу: 200 единиц
  при cap 20000; 100 единиц при bp 10005), на копейку ниже — floor
  уменьшает объём (199/99); bp=0 переопределяет ровно-один-лот бюджет
  → ZERO_SIZE/BUYING_POWER_BELOW_ONE_LOT. Всё подтверждено тестами
  `TestStageD1ExactLimitBoundaries`.
* Формулы ТЗ §6, порядок ворот, fail-closed случаи §8, атрибуция/
  хеши/FIGI, immutable-объекты, блокирующие исходы без положительного
  объёма — соответствуют ТЗ; дефектов не обнаружено.
* `REASON_QUANTITY_BELOW_ONE_LOT` определён и экспортируется, но ни
  один путь расчёта его не возвращает (все ZERO_SIZE-случачи получают
  конкретную причину RISK_BUDGET/NOTIONAL_CAP/BUYING_POWER). Это
  зарезервированный элемент словаря причин, не дефект; оставлен без
  изменений (не ослаблять и не менять публичную поверхность без
  необходимости).
* Float-зеркала денежных полей результата могут отличаться от точных
  значений на 1 ulp при экстремальных порядках (точные значения всегда
  в diagnostics строками) — существующее известное ограничение №5
  Stage D, отображение не влияет на решения (все решения точные).
  Зафиксировано в known limitations, исправления не требует.

## 3. Математическая корректность (ТЗ D.1 §4–5): итог

* Формулы реализованы ТОЧНО как в ТЗ §6 (risk_budget, price_risk,
  total_risk_per_unit, min из трёх ограничений, floor до целого лота,
  никогда вверх); арифметика точная десятичная (сложения/умножения без
  округления контекста), деления — точное целочисленное деление
  отношений конечных десятичных дробей.
* Каждое из трёх ограничений проверяется точным сравнением после
  расчёта (defense-in-depth): превышение невозможно по построению
  `_floor_ratio`; подтверждено 25 000 fuzz-эталонов и граничными
  тестами.
* LONG-only: SHORT блокируется UNSUPPORTED_SIDE; стоп строго ниже
  входа (EQUAL/ABOVE блокируются); исключения никогда не превращаются
  в положительный объём.

## 4. Изменённые файлы (ТЗ D.1 §7–8)

| Путь | Статус | Причина | SHA-256 (Stage D) | SHA-256 (Stage D.1) |
|---|---|---|---|---|
| `candidate/strategy_risk.py` | MODIFIED | D-1: полностью явный Decimal-контекст | `2a29807e8818158216bffb01be609f8462ad0716e5ef5dc0d8aedff7782a7327` | `7f25b4ef4bf9f2f9b90507caf7b4ff53a20b95f987c337bbf3d95496bcd22d66` |
| `candidate/tests/test_stage_d_strategy_risk.py` | MODIFIED | +17 тестов D.1 (изоляция контекста, точные границы); старые 162 — без изменений (diff −0 строк) | `38c550f51eb34d88110dd24db5eeac7306a4df346549ec502dd3dcfafcfad073` | `0cade2967f68fc5bad648460adbec593dbe97a0fbc0771e7130fe2be0915ddf9` |

Изменение модуля минимально: −6/+46 строк (импорт, константа контекста,
два `with localcontext(...)`, docstrings). Ни один принятый контракт
Stage A/B/C не затронут. Изменение старых (не Stage D) файлов НЕ
потребовалось — конфликтов интерфейсов нет, отдельное разрешение не
запрашивается.

**Файлы для замены в репозитории: ровно два файла из таблицы выше.**
Все остальные файлы Stage D заменять НЕ нужно (байт-в-байт совпадают с
поставленным Stage D / принятым Stage C.1).

## 5. Тестовые счётчики (ТЗ D.1 §9)

| Набор | База Stage D (до D.1) | После D.1 | Прирост |
|---|---|---|---|
| **Full** (весь candidate) | 1553 passed | **1570 passed** | +17 |
| **Canonical** (candidate/tests) | 1033 passed | **1050 passed** | +17 |
| **Stage D файл** | 162 passed | **179 passed** | +17 |

* zero failed, zero skipped — во всех прогонах (до и после);
* по-тестовое сравнение verbose-логов: **LOST 0**, GAINED ровно 17
  новых тестов D.1; все 1553 теста базы присутствуют и проходят;
* средовое примечание: песочница была пересоздана, для воспроизведения
  базы потребовалась установка `pandas_ta_classic` (чисто средовая
  зависимость, не связана со Stage D; см. §1 п.4);
* golden fixtures не перегенерировались; старые тесты не ослаблялись и
  не удалялись (diff тестового файла: −0 строк).

## 6. Негативные тесты (ТЗ D.1 §3/§10)

`STAGE_D_1_NEGATIVE_TEST_EVIDENCE.txt`: предкоррекционный
`strategy_risk.py` восстановлен из поставленного Stage D ZIP в чистую
копию пакета, новые тесты D.1 запущены против него — **5 из 17 новых
тестов падают** (точно те, что проверяют изоляцию контекста: hostile
Emax, отключенный Overflow-trap, параметризованная комбинация
prec=5000/Emax=2, валидатор под hostile-контекстом, отсутствие мутации
зафиксированного контекста). Тесты ловят дефект. Граничные тесты
(notional/bp) проходят на обеих реализациях — они фиксируют КОРРЕКТНОЕ
поведение, а не дефект.

## 7. Подтверждения

* **Stage A/B/C не затронуты**: 177/177 файлов pristine Stage C.1
  байт-в-байт идентичны (STAGE_D_1_IMMUTABILITY_PROOF.txt); ключевые
  контракты (attribution.py, strategy_api.py, config.py,
  strategy_state.py, strategy_contracts.py) и тесты Stage A/B/C —
  SHA-256 совпадают.
* **Торговое исполнение не затронуто**: execution.py, main.py,
  risk_manager.py, telegram_bot.py и прочие торговые/
  инфраструктурные модули — SHA-256 совпадают с Stage C.1; Stage D не
  размещает/не изменяет/не отменяет заявки, не обращается к broker
  SDK/Sandbox/LIVE (проверка код-маркеров из Stage D сохраняется).
* **Не начат Stage E**; Stage D не заявляется принятым.

## 8. Состав поставки (partial ZIP `Samsung_V4_STAGE_D_1.zip`)

```
STAGE_D_1_CORRECTION_REPORT.md          — этот отчёт
STAGE_D_1_CHANGED_FILES.md              — точный список изменений и замен
STAGE_D_1_SHA256_MANIFEST.txt           — SHA-256 исходных/новых версий
STAGE_D_1_DIFF.patch                    — точный diff (Stage D -> D.1)
STAGE_D_1_TEST_RESULTS.txt              — полные логи до/после
STAGE_D_1_IMMUTABILITY_PROOF.txt        — байт-в-байт доказательство
STAGE_D_1_NEGATIVE_TEST_EVIDENCE.txt    — доказательство ловли дефекта
STAGE_D_1_KNOWN_LIMITATIONS.md          — известные ограничения
candidate/strategy_risk.py              — ПОЛНЫЙ исправленный файл
candidate/tests/test_stage_d_strategy_risk.py — ПОЛНЫЙ исправленный файл
```
