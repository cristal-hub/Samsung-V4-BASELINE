# STAGE D — ARCHITECTURE REPORT

SAMSUNG V4 NEW STRATEGY ENGINE — STRATEGY-SPECIFIC RISK SIZING

---

## 1. Место в архитектуре

```
Stage A.2.1 (принят)     StrategyConfig, AttributionContext, Signal,
                         SignalDirection, EntrySignalInput
                                   |  (потребление через публичные API)
Stage B.1   (принят)     StrategyState, StateStore, StrategyStateManager
                                   |
Stage C.1   (принят)     entry/exit контракты, PriceData, check_price,
                         ExitDecisionCoordinator, exit merging
                                   |
Stage D     (ЭТОТ ЭТАП)  strategy_risk.py — РИСК-МАСШТАБИРОВАНИЕ
                         RiskPolicy / SizingInput / SizingResult /
                         calculate_position_size / validate_sizing_result
                                   |
                         (вне Stage D: слой исполнения — НЕ реализуется,
                          НЕ модифицируется; заявок нет)
```

Stage D — ЧИСТЫЙ расчётный слой. Никакого состояния, никакого I/O,
никаких брокерских вызовов. Вход -> детерминированный типизированный
выход. Одинаковые аргументы -> структурно идентичный результат
(проверено тестом при искажённом ambient-контексте Decimal).

## 2. Связь с принятыми контрактами (ТЗ §3)

| Принятый контракт | Как используется Stage D | Изменения |
|---|---|---|
| `StrategyConfig` | точный тип; перепроверка config_hash через `AttributionContext.from_config` (исходный алгоритм Stage A.2.1) | нет |
| `AttributionContext` | точный тип в SizingInput; только проверенное создание | нет |
| `PriceData` (Stage C) | опциональная форма цен входа/стопа: несёт собственную валидацию (>0, конечность) и FIGI — согласованность FIGI с входом проверяется расчётом (FIGI_MISMATCH) | нет |
| `SignalDirection` (Stage A) | НЕ принимается в поле side (молчаливой интерпретации BUY/SELL/HOLD нет); соответствие LONG<->BUY задокументировано | нет |
| `validate_strategy_id` / `validate_figi` (Stage B) | правила валидации идентификаторов переиспользуются | нет |
| `ImmutableMapping` / `unfreeze` (Stage A) | глубокая заморозка diagnostics | нет |
| StateStore / StrategyStateManager | НЕ используются: Stage D не имеет состояния и не создаёт вторую систему хранения | нет |

Конфликтов с существующими публичными интерфейсами не обнаружено
(ТЗ §3: «document the conflict instead of modifying an accepted
contract» — конфликтов нет, принятые контракты не менялись).

## 3. Дизайн-решения

### 3.1 Два класса ошибок: сотрудники vs данные-носители

По образцу Stage C (координатор vs check_price):
* **Сотрудники** (policy, config) — аргументы вызывающего кода.
  Неправильный ТИП сотрудника = misuse API ->
  `SizingContractViolationError` (исключение).
* **Данные-носитель** (sizing_input) — переносят рыночные данные.
  Мусор вместо входа (не точный тип, duck-typing, подкласс) ->
  типизированный блокирующий результат INVALID_INPUT/INPUT_WRONG_TYPE.
  Атрибутивные несогласованности между сотрудниками и входом — тоже
  данные -> ATTRIBUTION_MISMATCH.

### 3.2 Риск-политика: хеш фиксируется при создании

`RiskPolicy.policy_hash` вычисляется при создании и СОХРАНЯЕТСЯ (вне
полей dataclass, в `__dict__`). `verify_policy_hash()` пересчитывает
хеш по фактическим полям и сравнивает: изменение ЛЮБОГО поля в обход
API (object.__setattr__ обходит frozen, но не хеш) -> RiskPolicyViolationError
-> расчёт возвращает POLICY_INVALID. Политика:
* поля без умолчаний (отсутствие поля = TypeError, ТЗ §4);
* доли в домене (0; 1.0], конечные, bool запрещены;
* канонический payload: JSON sort_keys + repr(float) — детерминирован,
  не зависит от платформы/времени/ENV/секретов; версия схемы
  risk_policy_v1 входит в payload.

### 3.3 Точная десятичная арифметика

Требование ТЗ §6 («Use Decimal or another numerically safe approach»)
выполнено консервативно:
* Контекст prec=5000 внутри `localcontext`: все умножения/сложения
  входов (repr-float не длиннее 17 значащих цифр, порядок <= 308)
  точны — округление контекста не возникает даже для произведений
  экстремальных входов (<= ~620 цифр).
* Округление вниз — БЕЗ операции деления: `_floor_ratio(a, b)` через
  целочисленное деление значащих цифр и степеней 10. Точно для любых
  конечных десятичных a>=0, b>0 (деление на ноль невозможно
  по построению: total_risk > 0 при строгой геометрии стопа; явная
  защита от вырожденного знаменателя осталась как defense-in-depth).
* Итоговые проверки — точные сравнения Decimal (никаких «допусков»).
* Ambient-контекст Decimal изолирован (тест: prec=2 + ROUND_UP не
  меняют результат).

### 3.4 Отсутствующие данные vs нулевые данные

ТЗ §5/§6: «Do not invent values for missing data», «do not assume they
are zero». Модель:
* None = явное «отсутствует» -> расчёт НЕ выполняется ->
  MISSING_REQUIRED_DATA со списком полей (фиксированный порядок);
* предоставленные значения обязаны быть корректными (диапазон/тип/
  конечность) — иначе объект входа не создаётся;
* явно переданный ноль затрат — данные (нулевая комиссия); ноль
  buying power — валидное состояние «средств нет» -> ZERO_SIZE;
  ноль equity/цен/лотов/мультипликатора — некорректные значения
  (отклонение при создании), т.к. делают расчёт бессмысленным и
  перечислены в ТЗ §8 как fail-closed.

### 3.5 Диагностика достаточна для аудита (ТЗ §7)

Каждый расчётный результат несёт:
* `inputs_decimal` / `computed_decimal` — ТОЧНЫЕ десятичные строки
  всех входов и промежуточных величин (масштаб арифметики сохранён:
  100000.0 * 0.01 = "1000.000");
* units_by_risk / units_by_notional / units_by_buying_power + binding;
* verification {risk_ok, notional_ok, buying_power_ok};
* rounding_method, sizing_rules_version, risk_policy_schema;
* для SIZED дополнительно exact_quantity/exact_lot_count/
  exact_total_position_risk/exact_position_notional; источник цен
  (number/PriceData); для ZERO_SIZE — zero_size_analysis.

Float-поля результата — зеркала для удобства потребителей; при
экстремальных входах непредставимое float-значение -> None (точное —
в diagnostics). Никогда не NaN/Infinity (валидация результата).

### 3.6 Публичный валидатор как инструмент негативных тестов

`validate_sizing_result(result, expected_policy=..., expected_config=...,
expected_input=...)` перепроверяет результат ТОЧНОЙ Decimal-математикой
по его же диагностике: объём кратен лоту, не превышает риск-бюджет /
notional / buying power; деньги согласованы со входом (budget =
equity*fraction; risk_per_unit = |entry-stop|*mult + costs; ...); хеши и
атрибуция соответствуют ожидаемым объектам. ТЗ §10 («negative tests
demonstrate the tests catch invalid implementations»): 15 негативных
тестов — обход конструкции (object.__new__), подделка денег/диагностики,
сломанная реализация-«сизер» — все перехватываются.

## 4. Поверхность API модуля

```python
calculate_position_size(*, policy: RiskPolicy, config: StrategyConfig,
                        sizing_input: SizingInput) -> SizingResult
validate_sizing_result(result, *, expected_policy=None,
                       expected_config=None, expected_input=None) -> None
compute_risk_policy_hash(strategy_id, config_hash, risk, cap) -> str
RiskPolicy(...); .policy_hash; .verify_policy_hash(); .as_dict()
SizingInput(...); .entry_price_value; .protective_stop_price_value
SizingResult.sized(...) / .zero_size(...) / .blocked(...)
TradeSide.LONG / TradeSide.SHORT; SUPPORTED_TRADE_SIDES == (LONG,)
SizingOutcome: SIZED / ZERO_SIZE / INVALID_INPUT / MISSING_REQUIRED_DATA /
               ATTRIBUTION_MISMATCH / UNSUPPORTED_SIDE /
               INVALID_STOP_GEOMETRY / POLICY_INVALID
```

Иерархия ошибок (самостоятельная; ошибки Stage A/B/C не маскируются):
`StrategyRiskError` -> RiskPolicyViolationError,
SizingInputViolationError, SizingResultViolationError,
SizingContractViolationError.

## 5. Границы (ТЗ §9 — все соблюдены)

* Нет импортов broker SDK; нет соединений; нет Sandbox/LIVE; нет заявок
  (доказано код-уровневой проверкой STAGE_D_NO_EXECUTION_CHANGES_PROOF.txt).
* execution.py / main.py / risk_manager.py / флаги / Telegram — не тронуты.
* Принятые контракты Stage A/B/C — не изменены.
* Никакого исторического симулятора, загрузок данных, оптимизации,
  FORCE_TRADE, новых активных стратегий. Legacy Samsung V4 —
  REGRESSION_ONLY.
