# IMPLEMENTATION REPORT — STAGE D — STRATEGY-SPECIFIC RISK SIZING

SAMSUNG V4 NEW STRATEGY ENGINE
Source package: Samsung_V4_STAGE_C_1 (Stage C.1, accepted)
Source commit: ee5080828dc71af5091d172568c7f6072c91196a
Mode: OFFLINE / READ ONLY DATA / RESEARCH ONLY / NO LIVE ORDERS /
NO REAL MONEY / NO SANDBOX EXECUTION
Status: IMPLEMENTED, НЕ принят (subject to independent review)

---

## 1. Что реализовано (ТЗ §13: what was implemented)

Независимый, детерминированный, строго-типизированный слой
стратегического риск-масштабирования позиций — новый изолированный
модуль `candidate/strategy_risk.py` (+ полный набор offline-тестов
`candidate/tests/test_stage_d_strategy_risk.py`).

Слой вычисляет безопасный ТЕОРЕТИЧЕСКИЙ объём позиции для конкретной
пары (стратегия, конфигурация, инструмент) по явной риск-политике,
привязанной к точной паре (strategy_id, config_hash). Один и тот же
инструмент при разных политиках получает разные объёмы (проверено
тестами §10.2). Слой полностью независим от брокерского исполнения:
не размещает, не изменяет и не отменяет заявки, не обращается к
broker SDK, Sandbox или LIVE (доказано: STAGE_D_NO_EXECUTION_CHANGES_PROOF.txt).

Компоненты модуля:

| Компонент | Назначение |
|---|---|
| `RiskPolicy` | Неизменяемая риск-политика: strategy_id, config_hash, risk_per_trade_fraction, max_position_notional_fraction; канонический SHA-256 policy_hash фактических параметров, фиксируемый при создании; verify_policy_hash() перехватывает tamper |
| `compute_risk_policy_hash()` | Стабильный канонический хеш (canonical JSON, sort_keys; без времени/случайности/ENV/секретов) |
| `TradeSide` | Сторона сделки: LONG (поддерживается), SHORT (явно НЕ поддерживается) |
| `SizingInput` | Неизменяемый типизированный вход: 11 обязательных полей; None = явное «отсутствует»; предоставленные значения валидируются при создании |
| `SizingOutcome` | Типизированные исходы: SIZED, ZERO_SIZE, INVALID_INPUT, MISSING_REQUIRED_DATA, ATTRIBUTION_MISMATCH, UNSUPPORTED_SIDE, INVALID_STOP_GEOMETRY, POLICY_INVALID |
| `SizingResult` | Неизменяемый результат: атрибуция, исход, reason_code, объём, лоты, деньги, аудиторская диагностика (точные десятичные строки) |
| `validate_sizing_result()` | Публичный независимый валидатор результата (точная Decimal-перепроверка по диагностике; перехватывает сломанные реализации) |
| `calculate_position_size()` | Чистая функция расчёта: 9 fail-closed ворот -> точный десятичный расчёт -> SIZED/ZERO_SIZE |

## 2. Точная формула и метод округления (ТЗ §13: exact formula and rounding method)

Все вычисления — в ТОЧНОЙ десятичной арифметике (`decimal`, контекст
prec=5000 внутри `localcontext`; сложения/умножения точны — округления
контекста не возникают). Плавающая точка в принятии решений не
используется. Десятичная модель входа: `Decimal(repr(value))` — repr
float в Python даёт кратчайшую строку, воспроизводящую тот же float;
int конвертируется точно.

```
risk_budget          = equity * risk_per_trade_fraction
price_risk_per_unit  = abs(entry_price - stop_price) * multiplier
total_risk_per_unit  = price_risk_per_unit + entry_cost_per_unit
                       + stop_exit_cost_per_unit
max_notional         = equity * max_position_notional_fraction

units_by_risk     = floor(risk_budget / total_risk_per_unit)
units_by_notional = floor(max_notional / (entry_price * multiplier))
units_by_bp       = floor(buying_power_limit /
                          (entry_price * multiplier + entry_cost_per_unit))

lots     = floor(min(units_by_risk, units_by_notional, units_by_bp)
                 / lot_size)
quantity = lots * lot_size
```

Метод округления: `DECIMAL_EXACT_FLOOR_TO_LOT` (фиксируется в
диагностике каждого результата).

* Округление ВНИЗ выполняется ТОЧНЫМ целочисленным делением отношений
  конечных десятичных дробей (`_floor_ratio`): a = A*10^ea, b = B*10^eb,
  floor(a/b) = (A*10^(ea-eb)) // B или A // (B*10^(eb-ea)). Никакого
  деления с контекстной точностью — результат точен для ЛЮБЫХ конечных
  входов (ТЗ §6: «no floating-point rounding that can accidentally
  exceed a risk or capital limit»).
* Объём никогда не округляется вверх ради минимального лота; объём
  меньше одного лота -> явный блокирующий исход ZERO_SIZE (сделка не
  форсируется).
* Покупательная способность расходуется консервативно: на единицу —
  notional + входная комиссия (объём не может превысить лимит).
* Defense-in-depth: итоговые проверки выполняются ТОЧНЫМИ сравнениями
  после расчёта (quantity*total_risk <= budget; quantity*notional <=
  max_notional; quantity*bp_cost <= buying_power); любое нарушение —
  блокирующий исход COMPUTATION_VERIFICATION_FAILED, никогда не
  положительный объём.
* Причина блокировки ZERO_SIZE — первый исчерпавший лимит в
  фиксированном порядке риск -> notional -> покупательная способность;
  все три величины и точные строки — в diagnostics.

Порядок ворот `calculate_position_size` (fail-closed, ТЗ §3–§8):

1. точные типы сотрудников (policy/config) — misuse -> исключение
   `SizingContractViolationError`;
2. перепроверка config_hash ИСХОДНЫМ алгоритмом Stage A.2.1
   (`AttributionContext.from_config`) — tamper конфигурации отклоняется
   до любой оценки;
3. целостность политики: пересчёт policy_hash против хеша,
   зафиксированного при создании -> POLICY_INVALID (перехват tamper);
4. точный тип входа -> INVALID_INPUT / INPUT_WRONG_TYPE;
5. отсутствие обязательных данных (явный None) -> MISSING_REQUIRED_DATA
   со списком отсутствующих полей;
6. направление: SHORT -> UNSUPPORTED_SIDE (long-only, ТЗ §5);
7. согласование атрибуции policy/config/input -> ATTRIBUTION_MISMATCH
   (STRATEGY_ID_MISMATCH / CONFIG_HASH_MISMATCH /
   INPUT_ATTRIBUTION_MISMATCH / FIGI_MISMATCH);
8. геометрия стопа: LONG — стоп СТРОГО ниже входа ->
   INVALID_STOP_GEOMETRY (STOP_NOT_BELOW_ENTRY; отдельно различаются
   EQUAL_TO_ENTRY и ABOVE_ENTRY в диагностике);
9. точный десятичный расчёт -> SIZED / ZERO_SIZE. Любое непредвиденное
   исключение вычисления конвертируется в блокирующий исход
   COMPUTATION_ERROR_FAIL_CLOSED — НИКОГДА в положительный объём.

## 3. Поддерживаемые направления (ТЗ §13: supported trade directions)

* **Только LONG** — текущий движок long-only по акциям; объем
  рассчитывается исключительно для длинных позиций (стоп СТРОГО ниже
  входа).
* **SHORT явно НЕ поддерживается**: TradeSide.SHORT возвращает
  блокирующий исход UNSUPPORTED_SIDE / SIDE_UNSUPPORTED_SHORT.
  «Стоп выше входа» для SHORT не обрабатывается (ТЗ §5).
* Неподдерживаемые направления НЕ интерпретируются молча как LONG.
* Соответствие существующим контрактам: SignalDirection.BUY (вход в
  длинную позицию) <-> TradeSide.LONG; SignalDirection.SELL —
  направление ВЫХОДА (Stage C), запросом масштабирования не является;
  SignalDirection.HOLD — сделки нет. Передача SignalDirection в поле
  side отклоняется ошибкой типа (SizingInputViolationError) — проверено
  тестом `test_signal_direction_not_silently_interpreted`.

## 4. Обязательные входные поля (ТЗ §13: required input fields)

`SizingInput` — все поля обязательны к явной передаче (без значений по
умолчанию; пропуск поля = TypeError). None = явное «данные отсутствуют»
(объект создаётся, расчёт блокируется MISSING_REQUIRED_DATA — значения
НЕ придумываются):

| Поле | Тип/диапазон | Смысл |
|---|---|---|
| `attribution` | точный `AttributionContext` или None | Проверенная атрибуция стратегии (Stage A.2.1) |
| `figi` | непустая строка (Stage B) или None | Инструмент |
| `side` | точный `TradeSide` или None | Сторона сделки |
| `available_equity` | float > 0 или None | Доступный капитал |
| `buying_power_limit` | float >= 0 или None | Доступные средства / явный лимит покупательной способности |
| `entry_price` | число > 0 или точный `PriceData` Stage C | Цена входа |
| `protective_stop_price` | число > 0 или точный `PriceData` Stage C | Защитный стоп |
| `lot_size` | int > 0 (bool/float запрещены) | Размер лота |
| `contract_multiplier` | float > 0 | Множитель инструмента |
| `entry_cost_per_unit` | float >= 0 или None | Оценка затрат входа на единицу |
| `stop_exit_cost_per_unit` | float >= 0 или None | Оценка затрат выхода по стопу на единицу |

Примечания: явно переданный ноль затрат — данные (нулевая комиссия),
а не «неизвестно»; неизвестность передаётся ТОЛЬКО None и блокирует
расчёт (ТЗ §6: «do not assume they are zero»). Ноль buying power —
валидные данные, приводящие к ZERO_SIZE (явное «средств нет»).

## 5. Все fail-closed случаи (ТЗ §13; полный список, покрыт тестами)

**Отклонение при создании объекта (исключение, объект не существует):**
нулевое/отрицательное equity; нулевые/отрицательные entry/stop цены;
нулевые/отрицательные lot_size; float-lot; bool-как-число для ЛЮБОГО
числового поля (входа и долей политики); NaN/Infinity для любого
числового поля; отрицательный buying power; отрицательные затраты;
нулевой/отрицательный multiplier; недопустимые символы strategy_id
(Stage B); некорректный формат config_hash (Stage A.2); доли вне (0; 1.0];
bool-доли; целые вне диапазона float (10**400); строки/SignalDirection/
подклассы в поле side.

**Типизированные блокирующие исходы `SizingResult` (quantity == 0,
lot_count == 0 — всегда, ТЗ §10.16):**
MISSING_REQUIRED_DATA (явный None любого из 11 полей — по одному и все
сразу); UNSUPPORTED_SIDE (SHORT); ATTRIBUTION_MISMATCH (strategy_id /
config_hash policy<->config; атрибуция входа; FIGI котировки PriceData);
INVALID_STOP_GEOMETRY (стоп не ниже входа, равенство или выше);
INVALID_INPUT (вход не точный тип SizingInput; COMPUTATION_ERROR_FAIL_CLOSED;
COMPUTATION_VERIFICATION_FAILED); POLICY_INVALID (policy_hash integrity —
tamper любого поля перехвачен пересчётом хеша); ZERO_SIZE
(RISK_BUDGET_BELOW_ONE_LOT / NOTIONAL_CAP_BELOW_ONE_LOT /
BUYING_POWER_BELOW_ONE_LOT / QUANTITY_BELOW_ONE_LOT).

**Отклонение на уровне сотрудников (исключение
SizingContractViolationError):** policy/config не точный тип;
config_hash конфигурации не проходит перепроверку Stage A.2.1.

**Границы округления:** budget ровно на 1 лот -> SIZED (10 единиц);
на копейку меньше -> ZERO_SIZE; точные кратные — без избытка.

**Экстремальные значения и переполнение:** equity 1e308 + цены 1e-300 —
точная целочисленная математика (объём 307-значный, валидатор проходит);
price_risk_per_unit вне float -> ZERO_SIZE с risk_per_unit=None и ТОЧНОЙ
строкой в diagnostics; субнормальные цены (5e-324) корректны; int вне
float-диапазона — контролируемая ошибка валидации. Ambient-контекст
Decimal НЕ влияет на результат (тест с prec=2/ROUND_UP).

## 6. Файлы добавлены/изменены (ТЗ §13; точный список)

**Добавлены (2):**
- `candidate/strategy_risk.py` — реализация Stage D (1881 строка);
- `candidate/tests/test_stage_d_strategy_risk.py` — тесты (162 теста).

**Изменены: 0. Удалены: 0.** Все 177 файлов candidate Stage C.1
совпадают byte-for-byte (STAGE_D_CHANGED_FILES.txt,
STAGE_D_IMMUTABILITY_PROOF.txt).

## 7. Тестовые счётчики (ТЗ §13: full and canonical test counts)

| Набор | До Stage D | После Stage D | Прирост |
|---|---|---|---|
| **Full** (весь candidate) | 1391 passed | **1553 passed** | +162 |
| **Canonical** (candidate/tests) | 871 passed | **1033 passed** | +162 |

* zero failed, zero skipped — в обоих наборах (проверено grep по логам);
* старые тесты: 0 потеряно, 0 ослаблено, 0 переписано
  (STAGE_D_NO_TEST_LOSS_CHECK.txt: все 1391 теста базы присутствуют в
  прогоне после);
* golden fixtures не перегенерировались
  (tests/fixtures/legacy_golden_signals.json — SHA-256 совпадает);
* новые тесты добавлены отдельным файлом, без правки существующих.

## 8. Доказательство неизменности прошлых этапов (ТЗ §13)

STAGE_D_IMMUTABILITY_PROOF.txt: **0 нарушений** — все 269 файлов базы
(pre-baseline manifest полного пакета Samsung_V4_STAGE_C_1) присутствуют
и совпадают byte-for-byte SHA-256. Ключевые файлы принятых этапов
проверены отдельно (SHA-256 совпадают с базой):

- Stage A.2.1 контракты: attribution.py, strategy_api.py, config.py;
- Stage B.1: strategy_state.py;
- Stage C/C.1: strategy_contracts.py;
- входные контракты Stage C (Signal/SignalDirection/EntrySignalInput) —
  только ПОТРЕБЛЯЮТСЯ модулем Stage D через публичные API;
- тесты Stage A/B/C: test_stage_a*.py, test_stage_b*.py,
  test_stage_c_*.py — не изменены;
- StrategyConfig, StrategyState, StateStore, StrategyStateManager,
  entry/exit контракты, exit merging — не изменены (ТЗ §3).

## 9. Доказательство отсутствия изменений broker/execution кода (ТЗ §13)

STAGE_D_NO_EXECUTION_CHANGES_PROOF.txt:

- execution.py, main.py, risk_manager.py, telegram_bot.py,
  tinkoff_client.py, screener.py, safe_start.py, order_ledger.py,
  build_safety.py, enable_sandbox_execution.py, config.py,
  engine_config.py, strategy.py — SHA-256 совпадают с Stage C.1;
- новые файлы Stage D проверены на КОД-уровневые broker/SDK-маркеры
  (импорты tinkoff/invest/grpc/telegram; вызовы place/post/cancel
  order, SandboxClient, send_message, Bot) — чисто; упоминания
  «Sandbox/LIVE» в шапке модуля — документация ЗАПРЕТОВ, не код;
- торговые флаги, Telegram, FORCE_TRADE, исторический симулятор,
  исторические данные, оптимизация, новые активные стратегии — не
  затронуты. Legacy Samsung V4 остаётся REGRESSION_ONLY.

## 10. Известные ограничения (ТЗ §13; подробно — KNOWN_LIMITATIONS_STAGE_D.md)

1. LONG-only: SHORT-масштабирование явно не поддерживается.
2. Слой — ЧИСТЫЙ расчёт: результат не является ордером/командой
   исполнения; трансформация в заявку — вне Stage D (запрещена §9).
3. Свежесть цен не проверяется в Stage D (проверка staleness —
   зона ответственности Stage C price gate); Stage D валидирует
   корректность значений, FIGI-согласованность и геометрию стопа.
4. Покупательная способность расходуется консервативно
   (notional + входная комиссия на единицу) — возможен чуть более
   строгий объём, чем «в лоб».
5. Float-зеркала денежных полей результата — отображение; точные
   значения всегда в diagnostics строками (Decimal). При экстремальных
   входах отдельное float-поле может быть None (непредставимо) — точное
   значение сохранено.
6. Явный ноль затрат трактуется как данные (нулевая комиссия),
   неизвестность — только None.
7. Слой не применяет портфельные лимиты/лимиты на количество позиций —
   только явные доли риск-политики и покупательную способность.

## 11. Статус

Stage D реализован и передаётся на независимую проверку. **Не заявляется
принятым.** Stage E не начинался.
