# strategy_risk.py — SAMSUNG V4 — NEW STRATEGY ENGINE. STAGE D.
#
# СТРАТЕГИЧЕСКОЕ РИСК-МАСШТАБИРОВАНИЕ ПОЗИЦИЙ (ТЗ Stage D §2–§8).
#
# НАЗНАЧЕНИЕ
#   Независимый, детерминированный, СТРАТЕГО-СПЕЦИФИЧНЫЙ слой расчёта
#   безопасного ТЕОРЕТИЧЕСКОГО объёма позиции для конкретной стратегии
#   и инструмента. Один и тот же инструмент при разных risk-политиках
#   получает РАЗНЫЕ расчётные объёмы. Слой ПОЛНОСТЬЮ независим от
#   брокерского исполнения: не размещает, не изменяет и не отменяет
#   заявки, не подключается к брокеру/Sandbox/LIVE (ТЗ §2, §9).
#
# АРХИТЕКТУРНЫЕ ПРИНЦИПЫ (ТЗ §3)
#   * используются ПРИНЯТЫЕ контракты Stage A.2.1: StrategyConfig и
#     AttributionContext (точные типы; контекст только проверенного
#     создания — AttributionContext.from_config);
#   * каждая risk-политика ЖЁСТКО привязана к точной паре
#     (strategy_id, config_hash); повторное использование политики для
#     другой стратегии/конфигурации отклоняется типизированным
#     результатом ATTRIBUTION_MISMATCH (ТЗ §4);
#   * все объекты — immutable, validated, типизированные (frozen
#     dataclass с валидацией в __post_init__); потребители принимают
#     объекты ТОЛЬКО точного типа (type(x) is X) — подкласс, ослабивший
#     __post_init__, не проходит границу потребителя;
#   * расчёт ДЕТЕРМИНИРОВАН: никакой информации о времени, случайности,
#     переменных окружения и секретов ни в расчёте, ни в хеше политики
#     (ТЗ §4);
#   * явный типизированный исход + машиночитаемый reason_code у каждого
#     результата (ТЗ §3, §7);
#   * FAIL-CLOSED (ТЗ §8): недостаточные, некорректные, несогласованные
#     и нефинитные входные данные блокируют расчёт; ноль, последняя
#     известная цена, доли риска «по умолчанию» и произвольные
#     fallback-значения НИКОГДА не подставляются.
#
# ОБЛАСТЬ ПОДДЕРЖИВАЕМЫХ НАПРАВЛЕНИЙ (ТЗ §5 — ЯВНО задокументировано)
#   Текущий движок поддерживает ТОЛЬКО ДОЛГИЕ (LONG) позиции по акциям.
#   SizingInput.side принимает точный тип TradeSide; поддерживается
#   только TradeSide.LONG. TradeSide.SHORT возвращает типизированный
#   блокирующий исход UNSUPPORTED_SIDE (SHORT-масштабирование ЯВНО НЕ
#   поддерживается; stop выше входа для SHORT не обрабатывается).
#   Неподдерживаемые направления НЕ интерпретируются молча как LONG.
#
#   Соответствие существующим контрактам направления (strategy_api):
#   SignalDirection.BUY (вход в длинную позицию)  <-> TradeSide.LONG;
#   SignalDirection.SELL — направление ВЫХОДА (Stage C), запросом на
#   масштабирование позиции НЕ является; SignalDirection.HOLD — сделка
#   отсутствует. SizingInput.side принимает ТОЛЬКО TradeSide; передача
#   SignalDirection отклоняется (ошибка типа) — молчаливой интерпретации
#   нет ни для одного из трёх значений SignalDirection.
#
# ФОРМУЛА (ТЗ §6) — явный денежный риск; все вычисления в ТОЧНОЙ
# десятичной арифметике (Decimal, точные умножения/сложения; округления
# вниз — точным целочисленным делением отношений конечных десятичных
# дробей; см. _floor_ratio). Плавающая точка в ПРИНЯТИИ РЕШЕНИЙ не
# используется вовсе (Decimal(repr(value)) — точная десятичная модель
# входа; сравнения и проверки — точные):
#
#   risk_budget          = equity * risk_per_trade_fraction
#   price_risk_per_unit  = abs(entry_price - stop_price) * multiplier
#   total_risk_per_unit  = price_risk_per_unit + entry_cost_per_unit
#                          + stop_exit_cost_per_unit
#   max_notional         = equity * max_position_notional_fraction
#
#   Ограничения объёма (в ЕДИНИЦАХ инструмента; каждое — СТРОГО вниз):
#     units_by_risk     = floor(risk_budget / total_risk_per_unit)
#     units_by_notional = floor(max_notional / (entry_price * multiplier))
#     units_by_bp       = floor(buying_power_limit /
#                               (entry_price * multiplier
#                                + entry_cost_per_unit))
#   Консервативно: расход покупательной способности на единицу включает
#   входную комиссию (объём НИКОГДА не превышает доступный лимит).
#
#   Итог: lots = floor(min(units_by_risk, units_by_notional,
#                          units_by_bp) / lot_size); quantity = lots*lot_size
#   Итоговый объём: ОКРУГЛЁН ВНИЗ до целого лота; НЕ превышает
#   риск-ограниченный объём; НЕ превышает максимальный notional; НЕ
#   превышает доступную покупательную способность; НИКОГДА не
#   округляется вверх ради минимального лота (ТЗ §6). Объём меньше
#   одного лота — явный блокирующий исход ZERO_SIZE (сделка не
#   форсируется). Итоговые проверки выполняются ТОЧНЫМИ сравнениями
#   (defense-in-depth): quantity*total_risk_per_unit <= risk_budget;
#   quantity*entry_price*multiplier <= max_notional;
#   quantity*(entry_price*multiplier + entry_cost_per_unit)
#       <= buying_power_limit.
#
# ГРАНИЦЫ STAGE D (ТЗ §9 — строго соблюдены)
#   * это ЧИСТЫЙ расчёт риск-масштабирования: никаких импортов broker
#     SDK, никаких брокерских соединений, Sandbox/LIVE, заявок,
#     изменений execution.py / main.py / risk_manager.py, торговых
#     флагов, Telegram, симулятора, исторических данных, оптимизации,
#     FORCE_TRADE и новой активной торговой стратегии;
#   * принятые контракты Stage A/B/C (StrategyConfig, AttributionContext,
#     Signal, PriceData, StrategyState/StateStore/StrategyStateManager,
#     entry/exit контракты, exit merging) НЕ изменяются — модуль только
#     ПОТРЕБЛЯЕТ их через существующие публичные API;
#   * legacy_samsung_v4 остаётся REGRESSION_ONLY.
#
# Режим: OFFLINE / READ ONLY DATA / RESEARCH ONLY / NO LIVE ORDERS /
# NO REAL MONEY / NO SANDBOX EXECUTION. Сетевых запросов нет.

from __future__ import annotations

import enum
import hashlib
import json
import math
import re
from dataclasses import dataclass
from decimal import Decimal, localcontext
from typing import Any, Mapping, Optional, Union

from attribution import AttributionContext
from strategy_api import (
    ImmutableMapping,
    StrategyConfig,
    unfreeze,
    validate_config_hash_format,
)
from strategy_contracts import PriceData
from strategy_state import validate_figi, validate_strategy_id

# ---------------------------------------------------------------------------
# Версии правил (входят в диагностику и в канонический хеш политики;
# время/случайность/окружение/секреты в хеш НЕ входят, ТЗ §4)
# ---------------------------------------------------------------------------

RISK_POLICY_SCHEMA_VERSION = "risk_policy_v1"
SIZING_RULES_VERSION = "sizing_rules_v1"

# Метод округления (фиксируется в диагностике каждого результата).
SIZING_ROUNDING_METHOD = "DECIMAL_EXACT_FLOOR_TO_LOT"

# Точность контекста Decimal: все входы — конечные десятичные дроби,
# полученные из float не длиннее repr (<= 17 значащих цифр, порядок
# <= 308). Произведения/суммы таких чисел имеют не более ~640 значащих
# цифр; 5000 гарантирует ТОЧНОСТЬ всех умножений и сложений (округление
# контекста не возникает), а деления как операции не используются —
# только точное целочисленное деление отношений (_floor_ratio).
_DECIMAL_PRECISION = 5000

# ---------------------------------------------------------------------------
# Ошибки Stage D (самостоятельная иерархия; ошибки Stage A/B/C не
# маскируются и не подменяются — пробрасываются как есть)
# ---------------------------------------------------------------------------


class StrategyRiskError(Exception):
    """Базовая ошибка Stage D (риск-масштабирование)."""


class RiskPolicyViolationError(StrategyRiskError):
    """Некорректные параметры risk-политики: объект НЕ создаётся."""


class SizingInputViolationError(StrategyRiskError):
    """Некорректное значение в SizingInput: объект НЕ создаётся.

    Политика «предоставленное значение обязано быть корректным»:
    переданное (не None) значение неверного типа/диапазона/нефинитное
    не может быть упаковано в типизированный неизменяемый вход.
    ОТСУТСТВУЮЩИЕ данные представляются ЯВНЫМ None (см. SizingInput) —
    они блокируют расчёт типизированным исходом MISSING_REQUIRED_DATA,
    а не ошибкой создания.
    """


class SizingResultViolationError(StrategyRiskError):
    """Некорректный/несогласованный SizingResult: объект НЕ создаётся."""


class SizingContractViolationError(StrategyRiskError):
    """Нарушение контракта вызывающего кода (неправильные типы
    СОТРУДНИКОВ расчёта: policy/config). Аналог
    CoordinatorViolationError Stage C: данные-носители (SizingInput)
    конвертируются в типизированный блокирующий исход, а неправильный
    тип сотрудника — ошибка использования API."""


# ---------------------------------------------------------------------------
# Коды причин (машиночитаемые; ТЗ §3)
# ---------------------------------------------------------------------------

REASON_SIZED_LONG = "SIZED_LONG"
REASON_QUANTITY_BELOW_ONE_LOT = "QUANTITY_BELOW_ONE_LOT"
REASON_RISK_BUDGET_BELOW_ONE_LOT = "RISK_BUDGET_BELOW_ONE_LOT"
REASON_NOTIONAL_CAP_BELOW_ONE_LOT = "NOTIONAL_CAP_BELOW_ONE_LOT"
REASON_BUYING_POWER_BELOW_ONE_LOT = "BUYING_POWER_BELOW_ONE_LOT"
REASON_INPUT_WRONG_TYPE = "INPUT_WRONG_TYPE"
REASON_MISSING_REQUIRED_FIELDS = "MISSING_REQUIRED_FIELDS"
REASON_POLICY_HASH_MISMATCH = "POLICY_HASH_MISMATCH"
REASON_STRATEGY_ID_MISMATCH = "STRATEGY_ID_MISMATCH"
REASON_CONFIG_HASH_MISMATCH = "CONFIG_HASH_MISMATCH"
REASON_INPUT_ATTRIBUTION_MISMATCH = "INPUT_ATTRIBUTION_MISMATCH"
REASON_FIGI_MISMATCH = "FIGI_MISMATCH"
REASON_SIDE_UNSUPPORTED_SHORT = "SIDE_UNSUPPORTED_SHORT"
REASON_STOP_NOT_BELOW_ENTRY = "STOP_NOT_BELOW_ENTRY"
REASON_COMPUTATION_ERROR_FAIL_CLOSED = "COMPUTATION_ERROR_FAIL_CLOSED"
REASON_COMPUTATION_VERIFICATION_FAILED = "COMPUTATION_VERIFICATION_FAILED"

# Обязательные ключи диагностики расчёта (аудируемость результата,
# ТЗ §7): точные десятичные представления всех промежуточных величин.
_SIZED_REQUIRED_DIAG_KEYS = (
    "sizing_rules_version",
    "inputs_decimal",
    "computed_decimal",
    "units_by_risk",
    "units_by_notional",
    "units_by_buying_power",
    "limiting_constraint",
    "rounding_method",
    "verification",
)
_ZERO_SIZE_REQUIRED_DIAG_KEYS = (
    "sizing_rules_version",
    "inputs_decimal",
    "computed_decimal",
    "units_by_risk",
    "units_by_notional",
    "units_by_buying_power",
    "rounding_method",
)

# ---------------------------------------------------------------------------
# Вспомогательные проверки (та же политика, что в Stage B/C)
# ---------------------------------------------------------------------------

_REASON_CODE_RE = re.compile(r"^[A-Z][A-Z0-9_]{0,127}$")


def _validate_reason_code(value: Any, error: type) -> str:
    """Код причины: непустая строка [A-Z][A-Z0-9_]* (до 128 символов)."""
    if not isinstance(value, str) or not _REASON_CODE_RE.match(value):
        raise error(
            "reason_code должен быть непустой строкой вида "
            f"[A-Z][A-Z0-9_]{{0,127}}; получено {value!r}")
    return value


def _validate_diag_value(value: Any, *, _path: str, error: type) -> Any:
    """Рекурсивная проверка диагностики на JSON-совместимость.

    Та же политика, что в Stage B/C: None, bool, int, конечный float,
    str, отображения со строковыми ключами, списки/кортежи; множества
    нормализуются в отсортированный список. NaN/Infinity и произвольные
    объекты отклоняются.
    """
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise error(
                f"{_path}: NaN/Infinity в диагностических данных "
                "недопустимы")
        return value
    if isinstance(value, str):
        return value
    if isinstance(value, Mapping):
        result: dict = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise error(
                    f"{_path}: ключи диагностических данных должны быть "
                    f"строками; получен {key!r} ({type(key).__name__})")
            result[key] = _validate_diag_value(
                item, _path=f"{_path}.{key}", error=error)
        return result
    if isinstance(value, (list, tuple)):
        return [_validate_diag_value(item, _path=f"{_path}[{i}]",
                                     error=error)
                for i, item in enumerate(value)]
    if isinstance(value, (set, frozenset)):
        items = [_validate_diag_value(item, _path=f"{_path}{{set}}",
                                      error=error) for item in value]
        items.sort(key=lambda item: repr(item))
        return items
    raise error(
        f"{_path}: диагностические данные должны быть JSON-совместимыми "
        f"(None/bool/int/float/str/Mapping/Sequence); получено "
        f"{type(value).__name__}")


def _normalize_diagnostics(value: Any, *,
                           error: type) -> ImmutableMapping:
    """Диагностика: None -> пустое отображение; иначе проверка+заморозка."""
    if value is None:
        return ImmutableMapping()
    if not isinstance(value, Mapping):
        raise error(
            "диагностические данные должны быть отображением (Mapping); "
            f"получено {type(value).__name__}")
    normalized = _validate_diag_value(unfreeze(value), _path="diagnostics",
                                      error=error)
    return ImmutableMapping(normalized)


def _validate_policy_hash_format(value: Any) -> str:
    """Формат risk_policy_hash совпадает с форматом config_hash (Stage A.2):
    SHA-256 hexdigest, ровно 64 hex-символа нижнего регистра."""
    return validate_config_hash_format(value)


def _is_valid_policy_hash_format(value: Any) -> bool:
    """Негативная форма проверки формата policy_hash (без исключения)."""
    try:
        _validate_policy_hash_format(value)
    except Exception:
        return False
    return isinstance(value, str) and bool(value)


def _validate_attribution_fields(strategy_id: Any, config_hash: Any,
                                 error: type) -> None:
    """Атрибуция результата: strategy_id/config_hash.

    config_hash — формат SHA-256 hexdigest (Stage A.2); strategy_id —
    непустая строка (точные правила Stage B применяются потребителем по
    мере надобности; результат обязан нести непустую строку в любом
    случае). risk_policy_hash проверяется ОТДЕЛЬНО: допускает пустую
    строку ТОЛЬКО для исхода POLICY_INVALID (целостность политики
    нарушена — честного хеша у результата быть не может).
    """
    if not isinstance(strategy_id, str) or not strategy_id:
        raise error(
            "strategy_id результата должен быть непустой строкой; "
            f"получено {type(strategy_id).__name__}")
    if not isinstance(config_hash, str) or not config_hash:
        raise error(
            "config_hash результата должен быть непустой строкой; "
            f"получено {type(config_hash).__name__}")
    try:
        validate_config_hash_format(config_hash)
    except Exception as exc:
        raise error(
            "config_hash результата не проходит проверку формата "
            f"Stage A.2: {exc}") from exc


# ---------------------------------------------------------------------------
# Числовая модель Stage D: точная десятичная арифметика (ТЗ §6)
# ---------------------------------------------------------------------------


def _to_decimal(value: Union[int, float]) -> Decimal:
    """Точная десятичная модель числового входа.

    int -> точный Decimal; float -> Decimal(repr(value)): repr float в
    Python — кратчайшая строка, дающая ТОТ ЖЕ float при обратном
    преобразовании, поэтому десятичная модель однозначно представляет
    переданное значение. NaN/Infinity/bool сюда не попадают (отклоняются
    при валидации входа); float-переполнение в Decimal невозможно для
    конечных float (значение <= ~1.8e308).
    """
    if isinstance(value, int):
        return Decimal(value)
    return Decimal(repr(value))


def _decimal_to_exact_str(value: Decimal) -> str:
    """Точное строковое представление конечного Decimal (для диагностики)."""
    return format(value, "f")


def _floor_ratio(a: Decimal, b: Decimal) -> int:
    """ТОЧНОЕ округление вниз отношения двух конечных десятичных дробей.

    a = A*10^ea, b = B*10^eb (A, B — целые из значащих цифр Decimal).
    floor(a/b) вычисляется ЦЕЛОЧИСЛЕННО:
        shift = ea - eb >= 0:  floor(A*10^shift / B)
        shift <  0:            floor(A / (B*10^-shift))
    Никакого деления с плавающей/контекстной точностью: результат точен
    для ЛЮБЫХ конечных входов (ТЗ §6: округление не должно случайно
    превысить риск/капитал). Требования: a >= 0, b > 0 (нарушение —
    внутренняя ошибка, конвертируется вызывающим кодом в fail-closed).
    """
    if b <= 0:
        raise ValueError("_floor_ratio: знаменатель обязан быть > 0")
    if a <= 0:
        return 0
    ta, tb = a.as_tuple(), b.as_tuple()
    digits_a = "".join(map(str, ta.digits)) or "0"
    digits_b = "".join(map(str, tb.digits)) or "0"
    int_a = int(digits_a)
    int_b = int(digits_b)
    shift = ta.exponent - tb.exponent
    if shift >= 0:
        return (int_a * (10 ** shift)) // int_b
    return int_a // (int_b * (10 ** (-shift)))


def _decimal_to_float_safe(value: Decimal) -> Optional[float]:
    """Decimal -> float без переполнения: вне диапазона float -> None.

    Потеря точности при переходе к float НЕ влияет на решения (все
    решения приняты в точной десятичной арифметике); точные значения
    всегда сохранены в diagnostics строками.
    """
    try:
        result = float(value)
    except (OverflowError, ValueError):
        return None
    if not math.isfinite(result):
        return None
    return result


# ---------------------------------------------------------------------------
# Направление сделки (ТЗ §5)
# ---------------------------------------------------------------------------


class TradeSide(enum.Enum):
    """Сторона сделки для риск-масштабирования (ТЗ §5).

    LONG  — длинная позиция (вход по SignalDirection.BUY); ЕДИНСТВЕННОЕ
            поддерживаемое направление текущего движка (акции, long-only).
    SHORT — короткая позиция; ЯВНО НЕ поддерживается Stage D: расчёт
            возвращает блокирующий исход UNSUPPORTED_SIDE. Stop выше
            входа для SHORT не обрабатывается (ТЗ §5).

    Не является SignalDirection: SignalDirection (BUY/SELL/HOLD) —
    направление СИГНАЛА (Stage A), а не запроса масштабирования;
    соответствие LONG <-> BUY задокументировано в шапке модуля. Молчаливая
    интерпретация SELL/HOLD как LONG (или SHORT) отсутствует.
    """
    LONG = "LONG"
    SHORT = "SHORT"


SUPPORTED_TRADE_SIDES = (TradeSide.LONG,)

# ---------------------------------------------------------------------------
# Risk policy (ТЗ §4)
# ---------------------------------------------------------------------------


def _canonical_fraction_repr(value: float) -> str:
    """Каноническое строковое представление доли для хеша.

    float -> repr (кратчайшее круговое представление, детерминированно
    для данного значения IEEE-754; не зависит от платформы/локали).
    """
    return repr(value)


def compute_risk_policy_hash(strategy_id: str,
                             config_hash: str,
                             risk_per_trade_fraction: float,
                             max_position_notional_fraction: float
                             ) -> str:
    """Стабильный канонический SHA-256 хеш ФАКТИЧЕСКИХ параметров политики.

    Состав (канонический JSON, sort_keys, компактные разделители):
      schema, strategy_id, config_hash и обе доли (repr float).
    НЕ входят: время, случайность, переменные окружения, секреты,
    машинно-зависимые форматы (ТЗ §4). Свойства (проверяются тестами):
      * одинаковые параметры -> одинаковый хеш (в любом порядке
        создания, в любом процессе);
      * изменение ЛЮБОГО параметра -> другой хеш;
      * формат — SHA-256 hexdigest (64 hex-символа), как config_hash.
    """
    payload = {
        "schema": RISK_POLICY_SCHEMA_VERSION,
        "strategy_id": strategy_id,
        "config_hash": config_hash,
        "risk_per_trade_fraction":
            _canonical_fraction_repr(risk_per_trade_fraction),
        "max_position_notional_fraction":
            _canonical_fraction_repr(max_position_notional_fraction),
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                           ensure_ascii=True, allow_nan=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _float_of_number(value: Union[int, float], *, field_name: str,
                     error: type) -> float:
    """float(int|float) с защитой от переполнения (ТЗ §8: extreme values).

    Целые Python произвольной точности: значение вне диапазона float —
    контролируемая ошибка валидации, а не OverflowError наружу.
    """
    try:
        result = float(value)
    except OverflowError as exc:
        raise error(
            f"{field_name}: значение {value!r} вне представимого "
            "диапазона float (экстремальные значения отклоняются, "
            "ТЗ §8)") from exc
    return result


def _validate_fraction(value: Any, *, field_name: str,
                       error: type) -> float:
    """Валидация доли риска/notional (ТЗ §4, fail-closed).

    Правила: конечное число (int|float); bool НЕ принимается как число;
    ноль и отрицательные значения недопустимы; значения выше 1.0
    недопустимы; умолчаний нет (обязательное поле без значения —
    TypeError на уровне сигнатуры / None -> ошибка валидации).
    Возвращает нормализованное float.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise error(
            f"{field_name} должен быть числом (int/float; bool НЕ "
            f"принимается как число); получено {type(value).__name__}")
    result = _float_of_number(value, field_name=field_name, error=error)
    if not math.isfinite(result):
        raise error(
            f"{field_name}: NaN/Infinity запрещены (ТЗ §4)")
    if result <= 0.0:
        raise error(
            f"{field_name} должен быть СТРОГО больше нуля; получено "
            f"{result!r} (нулевые и отрицательные доли недопустимы)")
    if result > 1.0:
        raise error(
            f"{field_name} не может превышать 1.0; получено {result!r}")
    return result


@dataclass(frozen=True)
class RiskPolicy:
    """Неизменяемая риск-политика конкретной стратегии (ТЗ §4).

    Жёсткая привязка: policy связана с ТОЧНОЙ парой
    (strategy_id, config_hash). Передача политики вместе с другой
    стратегией/конфигурацией отклоняется расчётом (ATTRIBUTION_MISMATCH,
    ТЗ §4) — молчаливого переиспользования не существует.

    Неизменяемость: frozen dataclass; setattr/delattr отклоняются;
    фактические параметры фиксируются при создании; policy_hash —
    канонический SHA-256 фактических параметров (compute_risk_policy_hash),
    вычисляется при создании и проверяется методом verify_policy_hash
    при каждом использовании (целостность, ТЗ §8).

    Поля без умолчаний (ТЗ §4: «missing required policy fields must
    block policy creation»; скрытых умолчаний для торговых решений нет):
      strategy_id                    — идентификатор стратегии (Stage B);
      config_hash                    — хеш конфигурации (Stage A.2);
      risk_per_trade_fraction        — доля капитала в риске на сделку,
                                       (0; 1.0];
      max_position_notional_fraction — максимальная доля капитала в
                                       notional одной позиции, (0; 1.0].
    """
    strategy_id: str
    config_hash: str
    risk_per_trade_fraction: float
    max_position_notional_fraction: float

    def __post_init__(self) -> None:
        # 1. Привязка к стратегии: правила Stage B (набор символов, длина).
        try:
            validate_strategy_id(self.strategy_id)
        except Exception as exc:
            raise RiskPolicyViolationError(
                "RiskPolicy.strategy_id не проходит проверку Stage B: "
                f"{exc}") from exc
        # 2. Привязка к конфигурации: формат config_hash (Stage A.2).
        #    Соответствие хеша ФАКТИЧЕСКИМ параметрам конфигурации
        #    проверяется StrategyConfig при её создании и перепроверяется
        #    расчётом через AttributionContext.from_config (у политики
        #    самих параметров конфигурации нет — только идентификатор).
        try:
            validate_config_hash_format(self.config_hash)
        except Exception as exc:
            raise RiskPolicyViolationError(
                "RiskPolicy.config_hash не проходит проверку формата "
                f"Stage A.2: {exc}") from exc
        # 3. Доли: явные, валидированные, без умолчаний (ТЗ §4).
        risk = _validate_fraction(
            self.risk_per_trade_fraction,
            field_name="risk_per_trade_fraction",
            error=RiskPolicyViolationError)
        cap = _validate_fraction(
            self.max_position_notional_fraction,
            field_name="max_position_notional_fraction",
            error=RiskPolicyViolationError)
        # 4. Нормализация к float и вычисление канонического хеша
        #    фактических параметров (frozen: только object.__setattr__).
        object.__setattr__(self, "risk_per_trade_fraction", risk)
        object.__setattr__(self, "max_position_notional_fraction", cap)
        # Хеш ФИКСИРУЕТСЯ при создании (вне полей dataclass, в __dict__):
        # изменение любого поля В ОБХОД API (object.__setattr__,
        # повреждённая десериализация) обнаруживается verify_policy_hash
        # как расхождение пересчитанного и сохранённого хешей (ТЗ §8).
        object.__setattr__(
            self, "_stored_policy_hash",
            compute_risk_policy_hash(self.strategy_id, self.config_hash,
                                     risk, cap))

    @property
    def policy_hash(self) -> str:
        """Канонический SHA-256, зафиксированный ПРИ СОЗДАНИИ политики.

        Это хеш фактических параметров НА МОМЕНТ СОЗДАНИЯ; совпадение с
        текущими полями отдельно проверяет verify_policy_hash (ТЗ §8).
        """
        return self._stored_policy_hash

    def verify_policy_hash(self) -> str:
        """Проверка целостности: пересчёт хеша по ФАКТИЧЕСКИМ полям.

        Возвращает пересчитанный хеш; расхождение с сохранённым при
        создании (объект изменён в обход API — object.__setattr__,
        повреждённая десериализация) -> RiskPolicyViolationError
        (ТЗ §8: policy hash integrity, fail-closed).
        """
        recomputed = compute_risk_policy_hash(
            self.strategy_id, self.config_hash,
            self.risk_per_trade_fraction,
            self.max_position_notional_fraction)
        if recomputed != self._stored_policy_hash:
            raise RiskPolicyViolationError(
                "целостность RiskPolicy нарушена: хеш фактических полей "
                f"{recomputed!r} не совпадает с хешем, зафиксированным "
                f"при создании {self._stored_policy_hash!r}; объект "
                "изменён в обход API — использование политики "
                "запрещено (ТЗ §8, fail-closed)")
        return recomputed

    def as_dict(self) -> dict:
        """JSON-совместимая копия параметров политики (для отчётов)."""
        return {
            "strategy_id": self.strategy_id,
            "config_hash": self.config_hash,
            "risk_per_trade_fraction": self.risk_per_trade_fraction,
            "max_position_notional_fraction":
                self.max_position_notional_fraction,
            "policy_hash": self.policy_hash,
            "schema": RISK_POLICY_SCHEMA_VERSION,
        }


# ---------------------------------------------------------------------------
# Вход sizing-контракта (ТЗ §5)
# ---------------------------------------------------------------------------

# Цена во входе: число или проверенный PriceData Stage C (точный тип).
# PriceData несёт собственную валидацию (конечная цена > 0) и FIGI —
# расчёт проверяет совпадение FIGI котировки с figi входа (ТЗ §8:
# «mismatched FIGI» -> ATTRIBUTION_MISMATCH/FIGI_MISMATCH).
PriceLike = Union[int, float, PriceData]


@dataclass(frozen=True)
class SizingInput:
    """Неизменяемый типизированный вход риск-масштабирования (ТЗ §5).

    Вход ЯВНО несёт ВСЕ данные, необходимые для расчёта. Значения полей
    обязательны к явной передаче: у полей НЕТ значений по умолчанию —
    пропуск поля в вызове конструктора = TypeError (объект не создаётся).

    ОТСУТСТВУЮЩИЕ данные: явный None. Такой объект создаётся, но расчёт
    возвращает блокирующий исход MISSING_REQUIRED_DATA со списком
    отсутствующих полей (данные НЕ придумываются, ТЗ §5/§6: ноль не
    подставляется, «неизвестно» не превращается в «ноль»).

    ПРЕДОСТАВЛЕННЫЕ значения валидируются при создании (fail-closed):
    неверный тип / NaN / Infinity / bool-как-число / нарушение диапазона
    -> SizingInputViolationError (некорректное значение не может быть
    упаковано в типизированный неизменяемый объект).

    Диапазоны предоставленных значений:
      available_equity            > 0     (нулевое/отрицательное —
                                           некорректный вход, ТЗ §8);
      buying_power_limit          >= 0    (ноль — явное «средств нет»,
                                           валидное значение, приводящее
                                           к ZERO_SIZE; отрицательное —
                                           некорректный вход);
      entry_price, stop_price     > 0     (число или PriceData);
      contract_multiplier         > 0;
      entry_cost_per_unit,
      stop_exit_cost_per_unit     >= 0    (ЯВНО переданные затраты;
                                           ноль означает явно переданную
                                           нулевую стоимость, а не
                                           «неизвестно» — неизвестность
                                           передаётся только None и
                                           блокирует расчёт, ТЗ §6);
      lot_size                    int > 0 (bool и float не принимаются).

    Числовые предоставленные значения нормализуются к float при создании
    (int -> float); исходные объекты PriceData сохраняются как есть
    (неизменяемые, Stage C).
    """
    attribution: Optional[AttributionContext]
    figi: Optional[str]
    side: Optional[TradeSide]
    available_equity: Optional[float]
    buying_power_limit: Optional[float]
    entry_price: Optional[PriceLike]
    protective_stop_price: Optional[PriceLike]
    lot_size: Optional[int]
    contract_multiplier: Optional[float]
    entry_cost_per_unit: Optional[float]
    stop_exit_cost_per_unit: Optional[float]

    def __post_init__(self) -> None:
        # 1. Атрибуция: только проверенный AttributionContext (точный
        #    тип; создание в обход охраняемого конструктора невозможно).
        if self.attribution is not None \
                and type(self.attribution) is not AttributionContext:
            raise SizingInputViolationError(
                "SizingInput.attribution принимает только точный тип "
                f"AttributionContext или None (отсутствие данных); "
                f"получено {type(self.attribution).__name__}")
        # 2. FIGI: None или проверка Stage B.
        if self.figi is not None:
            if not isinstance(self.figi, str) or not self.figi:
                raise SizingInputViolationError(
                    "SizingInput.figi должен быть непустой строкой или "
                    f"None; получено {type(self.figi).__name__}")
            try:
                validate_figi(self.figi)
            except Exception as exc:
                raise SizingInputViolationError(
                    f"SizingInput.figi не проходит проверку Stage B: "
                    f"{exc}") from exc
        # 3. Сторона: None или точный TradeSide. Строки/SignalDirection/
        #    подклассы не проходят (молчаливой интерпретации нет).
        if self.side is not None and type(self.side) is not TradeSide:
            raise SizingInputViolationError(
                "SizingInput.side принимает только точный тип TradeSide "
                f"или None; получено {type(self.side).__name__} "
                "(строки и SignalDirection не интерпретируются молча)")
        # 4. Числовые поля.
        object.__setattr__(
            self, "available_equity",
            self._validate_positive(self.available_equity,
                                    "available_equity"))
        object.__setattr__(
            self, "buying_power_limit",
            self._validate_non_negative(self.buying_power_limit,
                                        "buying_power_limit"))
        object.__setattr__(
            self, "entry_price",
            self._validate_price(self.entry_price, "entry_price"))
        object.__setattr__(
            self, "protective_stop_price",
            self._validate_price(self.protective_stop_price,
                                 "protective_stop_price"))
        object.__setattr__(
            self, "contract_multiplier",
            self._validate_positive(self.contract_multiplier,
                                    "contract_multiplier"))
        object.__setattr__(
            self, "entry_cost_per_unit",
            self._validate_non_negative(self.entry_cost_per_unit,
                                        "entry_cost_per_unit"))
        object.__setattr__(
            self, "stop_exit_cost_per_unit",
            self._validate_non_negative(self.stop_exit_cost_per_unit,
                                        "stop_exit_cost_per_unit"))
        # 5. Размер лота: только int > 0 (bool и float не принимаются;
        #    округление «наверх» до лота не выполняется).
        lot = self.lot_size
        if lot is not None:
            if isinstance(lot, bool) or not isinstance(lot, int):
                raise SizingInputViolationError(
                    "SizingInput.lot_size должен быть целым числом int "
                    f"> 0 (bool и float не принимаются); получено "
                    f"{type(lot).__name__}")
            if lot <= 0:
                raise SizingInputViolationError(
                    f"SizingInput.lot_size должен быть > 0; получено "
                    f"{lot!r}")
        # 6. Согласованность FIGI котировок ПЕРЕНОСИТСЯ на расчёт (ТЗ §8
        #    «mismatched FIGI» — типизированный исход FIGI_MISMATCH),
        #    т.к. figi входа сам может быть None («отсутствующие данные»).

    # --- валидаторы числовых полей -------------------------------------

    @staticmethod
    def _validate_number(value: Any, field_name: str) -> float:
        """Общая проверка числа: не bool, int|float, конечное."""
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise SizingInputViolationError(
                f"SizingInput.{field_name} должен быть числом (int/float; "
                f"bool НЕ принимается как число); получено "
                f"{type(value).__name__}")
        result = _float_of_number(
            value, field_name=f"SizingInput.{field_name}",
            error=SizingInputViolationError)
        if not math.isfinite(result):
            raise SizingInputViolationError(
                f"SizingInput.{field_name}: NaN/Infinity запрещены "
                "(нефинитные входы блокируют расчёт, ТЗ §8)")
        return result

    @classmethod
    def _validate_positive(cls, value: Any, field_name: str) -> \
            Optional[float]:
        """Строго положительное число или None («отсутствует»)."""
        if value is None:
            return None
        result = cls._validate_number(value, field_name)
        if result <= 0.0:
            raise SizingInputViolationError(
                f"SizingInput.{field_name} должен быть СТРОГО больше "
                f"нуля; получено {result!r} (нулевое/отрицательное "
                "значение — некорректный вход, ТЗ §8)")
        return result

    @classmethod
    def _validate_non_negative(cls, value: Any, field_name: str) -> \
            Optional[float]:
        """Неотрицательное число или None («отсутствует»)."""
        if value is None:
            return None
        result = cls._validate_number(value, field_name)
        if result < 0.0:
            raise SizingInputViolationError(
                f"SizingInput.{field_name} не может быть отрицательным; "
                f"получено {result!r}")
        return result

    @classmethod
    def _validate_price(cls, value: Any, field_name: str) -> \
            Optional[PriceLike]:
        """Цена: None, число > 0 или точный PriceData (Stage C)."""
        if value is None:
            return None
        if isinstance(value, PriceData):
            # Точный тип проверён isinstance? PriceData может иметь
            # подклассы — принимаем ТОЛЬКО точный тип.
            if type(value) is not PriceData:
                raise SizingInputViolationError(
                    f"SizingInput.{field_name} принимает только точный "
                    f"тип PriceData; получен подкласс "
                    f"{type(value).__name__}")
            return value
        return cls._validate_positive(value, field_name)

    # --- числовые значения цен (извлечение из числа/PriceData) ----------

    @property
    def entry_price_value(self) -> Optional[float]:
        """Числовое значение цены входа (None — отсутствует)."""
        if self.entry_price is None:
            return None
        if isinstance(self.entry_price, PriceData):
            return float(self.entry_price.price)
        return float(self.entry_price)

    @property
    def protective_stop_price_value(self) -> Optional[float]:
        """Числовое значение защитного стопа (None — отсутствует)."""
        if self.protective_stop_price is None:
            return None
        if isinstance(self.protective_stop_price, PriceData):
            return float(self.protective_stop_price.price)
        return float(self.protective_stop_price)


# Перечень полей данных SizingInput в фиксированном порядке (для списка
# отсутствующих полей в MISSING_REQUIRED_DATA; ТЗ §7).
SIZING_INPUT_DATA_FIELDS = (
    "attribution",
    "figi",
    "side",
    "available_equity",
    "buying_power_limit",
    "entry_price",
    "protective_stop_price",
    "lot_size",
    "contract_multiplier",
    "entry_cost_per_unit",
    "stop_exit_cost_per_unit",
)


# ---------------------------------------------------------------------------
# Исходы и результат масштабирования (ТЗ §7)
# ---------------------------------------------------------------------------


class SizingOutcome(enum.Enum):
    """Типизированный исход риск-масштабирования (ТЗ §7).

    SIZED                  — успешный расчёт (ЕДИНСТВЕННЫЙ исход с
                             положительным объёмом);
    ZERO_SIZE              — объём меньше одного лота: один лот
                             превышает допустимый риск/капитал/лимиты
                             (сделка не форсируется);
    INVALID_INPUT          — вход неверного типа/несогласован, ошибка
                             вычисления или нарушение целостности
                             политики (расчёт не выполняется или
                             результат непредставим);
    MISSING_REQUIRED_DATA  — отсутствуют обязательные данные (явный
                             None во входе);
    ATTRIBUTION_MISMATCH   — политика/конфигурация/вход не согласованы
                             по (strategy_id, config_hash, FIGI);
    UNSUPPORTED_SIDE       — направление явно не поддерживается
                             (SHORT; long-only движок, ТЗ §5);
    INVALID_STOP_GEOMETRY  — стоп не на стороне убытка (для LONG стоп
                             обязан быть СТРОГО ниже входа).

    Любой исход, кроме SIZED, БЛОКИРУЕТ сделку: блокирующий результат
    НИКОГДА не содержит положительного исполнительного объёма (ТЗ §7).
    """
    SIZED = "SIZED"
    ZERO_SIZE = "ZERO_SIZE"
    INVALID_INPUT = "INVALID_INPUT"
    MISSING_REQUIRED_DATA = "MISSING_REQUIRED_DATA"
    ATTRIBUTION_MISMATCH = "ATTRIBUTION_MISMATCH"
    UNSUPPORTED_SIDE = "UNSUPPORTED_SIDE"
    INVALID_STOP_GEOMETRY = "INVALID_STOP_GEOMETRY"
    POLICY_INVALID = "POLICY_INVALID"


_OUTCOME_VALUES = {outcome.value for outcome in SizingOutcome}

# Исходы, для которых расчёт ВЫПОЛНЕН (деньги в результате заполнены).
_COMPUTED_OUTCOMES = (SizingOutcome.SIZED, SizingOutcome.ZERO_SIZE)


@dataclass(frozen=True)
class SizingResult:
    """Неизменяемый типизированный результат риск-масштабирования (ТЗ §7).

    Содержит полную атрибуцию (strategy_id, config_hash,
    risk_policy_hash, FIGI), типизированный исход, машиночитаемый код
    причины, рассчитанный объём и деньги, а также диагностику,
    достаточную для аудита расчёта (точные десятичные представления
    всех входов и промежуточных величин — строками; ТЗ §7).

    Согласованность (fail-closed, проверяется при создании):
      * SIZED — единственный исход с положительным объёмом; объём целое
        число единиц, кратное lot_size, lot_count == quantity // lot_size
        >= 1; все денежные поля заполнены конечными float;
      * любой блокирующий исход — quantity == 0 и lot_count == 0
        (положительный исполнительный объём в блокирующем результате
        невозможен, ТЗ §7);
      * для не-расчётных исходов (данные не вычислялись) денежные поля
        None; для SIZED/ZERO_SIZE — конечные числа (или None в поле
        risk_per_unit ZERO_SIZE, если точное значение не представимо
        float — точное значение всегда в diagnostics);
      * FIGI обязателен (непустой, Stage B) для SIZED/ZERO_SIZE; для
        блокирующих исходов до распознавания входа допускается пустая
        строка (инструмент неизвестен), непустое значение проверяется;
      * result НЕ является заявкой/командой исполнения (ТЗ §7/§9):
        трансформация sizing-результата в ордер вне этого модуля
        запрещена архитектурой Stage D.
    """
    strategy_id: str
    config_hash: str
    risk_policy_hash: str
    figi: str
    outcome: SizingOutcome
    reason_code: str
    quantity: int
    lot_count: int
    lot_size: Optional[int]
    risk_budget: Optional[float]
    risk_per_unit: Optional[float]
    total_position_risk: Optional[float]
    position_notional: Optional[float]
    notional_cap: Optional[float]
    buying_power_cap: Optional[float]
    diagnostics: Optional[Mapping] = None

    def __post_init__(self) -> None:
        # 1. Типы и код причины.
        if type(self.outcome) is not SizingOutcome:
            raise SizingResultViolationError(
                "SizingResult.outcome должен быть точным типом "
                f"SizingOutcome; получено {type(self.outcome).__name__}")
        _validate_reason_code(self.reason_code, SizingResultViolationError)
        # 2. Атрибуция. strategy_id/config_hash — всегда от ПРОВЕРЕННОЙ
        #    конфигурации (непустые, формат Stage A.2). risk_policy_hash:
        #    непустой SHA-256 hexdigest; пустая строка допускается ТОЛЬКО
        #    для POLICY_INVALID (целостность политики нарушена — честного
        #    хеша у результата быть не может, ТЗ §8).
        _validate_attribution_fields(
            self.strategy_id, self.config_hash,
            SizingResultViolationError)
        if not isinstance(self.risk_policy_hash, str) or (
                not self.risk_policy_hash
                and self.outcome is not SizingOutcome.POLICY_INVALID):
            raise SizingResultViolationError(
                "risk_policy_hash результата должен быть непустой "
                "строкой (пустая — только для POLICY_INVALID); получено "
                f"{self.risk_policy_hash!r}")
        if self.risk_policy_hash:
            try:
                _validate_policy_hash_format(self.risk_policy_hash)
            except Exception as exc:
                raise SizingResultViolationError(
                    "risk_policy_hash результата не проходит проверку "
                    f"формата SHA-256 hexdigest: {exc}") from exc
        # 3. FIGI: строгая проверка для расчётных исходов; для
        #    блокирующих — пустая строка допустима (инструмент мог быть
        #    не распознан), непустое значение проверяется Stage B.
        if self.figi:
            try:
                validate_figi(self.figi)
            except Exception as exc:
                raise SizingResultViolationError(
                    f"SizingResult.figi не проходит проверку Stage B: "
                    f"{exc}") from exc
        elif self.outcome in _COMPUTED_OUTCOMES:
            raise SizingResultViolationError(
                "расчётный исход (SIZED/ZERO_SIZE) обязан нести непустой "
                "FIGI")
        # 4. Объём и лоты.
        if isinstance(self.quantity, bool) or not isinstance(self.quantity,
                                                             int):
            raise SizingResultViolationError(
                "SizingResult.quantity должен быть целым числом единиц "
                f"(int, bool запрещён); получено {type(self.quantity).__name__}")
        if isinstance(self.lot_count, bool) or not isinstance(self.lot_count,
                                                              int):
            raise SizingResultViolationError(
                "SizingResult.lot_count должен быть целым числом лотов "
                "(int, bool запрещён)")
        if self.outcome is SizingOutcome.SIZED:
            if self.quantity <= 0:
                raise SizingResultViolationError(
                    "SIZED обязан нести положительный объём; получено "
                    f"{self.quantity!r}")
            if self.lot_size is None \
                    or isinstance(self.lot_size, bool) \
                    or not isinstance(self.lot_size, int) \
                    or self.lot_size <= 0:
                raise SizingResultViolationError(
                    "SIZED обязан нести целый положительный lot_size")
            if self.quantity % self.lot_size != 0:
                raise SizingResultViolationError(
                    "объём SIZED обязан быть кратен lot_size: "
                    f"quantity={self.quantity}, lot_size={self.lot_size}")
            if self.lot_count != self.quantity // self.lot_size \
                    or self.lot_count <= 0:
                raise SizingResultViolationError(
                    "lot_count SIZED обязан равняться quantity // "
                    f"lot_size (> 0): quantity={self.quantity}, "
                    f"lot_count={self.lot_count}, "
                    f"lot_size={self.lot_size}")
        elif self.outcome in _COMPUTED_OUTCOMES:
            # ZERO_SIZE: объём меньше одного лота — ноль единиц и ноль
            # лотов (положительный объём в блокирующем исходе запрещён).
            if self.quantity != 0 or self.lot_count != 0:
                raise SizingResultViolationError(
                    "ZERO_SIZE обязан нести quantity == 0 и lot_count "
                    f"== 0; получено quantity={self.quantity!r}, "
                    f"lot_count={self.lot_count!r}")
            if self.lot_size is None \
                    or isinstance(self.lot_size, bool) \
                    or not isinstance(self.lot_size, int) \
                    or self.lot_size <= 0:
                raise SizingResultViolationError(
                    "ZERO_SIZE обязан нести целый положительный "
                    "lot_size (препятствие округления до лота)")
        else:
            # Блокирующие не-расчётные исходы: объём всегда нулевой.
            if self.quantity != 0 or self.lot_count != 0:
                raise SizingResultViolationError(
                    "блокирующий исход обязан нести quantity == 0 и "
                    f"lot_count == 0; получено quantity={self.quantity!r}, "
                    f"lot_count={self.lot_count!r}")
        # 5. Деньги: Optional[float], конечные, bool/типы отклоняются.
        for field_name in ("risk_budget", "risk_per_unit",
                           "total_position_risk", "position_notional",
                           "notional_cap", "buying_power_cap"):
            value = getattr(self, field_name)
            if value is None:
                if self.outcome is SizingOutcome.SIZED:
                    raise SizingResultViolationError(
                        f"SizingResult.{field_name} обязан быть заполнен "
                        "конечным числом для исхода SIZED")
                continue
            if isinstance(value, bool) or not isinstance(value,
                                                         (int, float)):
                raise SizingResultViolationError(
                    f"SizingResult.{field_name} должен быть числом или "
                    f"None; получено {type(value).__name__}")
            number = float(value)
            if not math.isfinite(number):
                raise SizingResultViolationError(
                    f"SizingResult.{field_name}: NaN/Infinity запрещены "
                    "(непредставимые значения переносятся в diagnostics "
                    "точной строкой)")
            object.__setattr__(self, field_name, number)
        # 6. Диагностика: JSON-совместимость + глубокая заморозка.
        object.__setattr__(
            self, "diagnostics",
            _normalize_diagnostics(self.diagnostics,
                                   error=SizingResultViolationError))
        # 7. Аудируемость расчётных исходов: обязательные ключи
        #    диагностики (точные строки промежуточных величин).
        if self.outcome in _COMPUTED_OUTCOMES:
            missing_keys = [key for key in _SIZED_REQUIRED_DIAG_KEYS
                            if key not in self.diagnostics]
            if self.outcome is SizingOutcome.ZERO_SIZE:
                missing_keys = [key for key in _ZERO_SIZE_REQUIRED_DIAG_KEYS
                                if key not in self.diagnostics]
            if missing_keys:
                raise SizingResultViolationError(
                    "диагностика расчётного исхода обязана содержать "
                    f"ключи аудита расчёта; отсутствуют: {missing_keys}")

    # --- фабрики явных исходов ------------------------------------------

    @classmethod
    def blocked(cls, *, strategy_id: str, config_hash: str,
                risk_policy_hash: str, figi: str,
                outcome: SizingOutcome, reason_code: str,
                diagnostics: Optional[Mapping] = None) -> \
            "SizingResult":
        """Блокирующий исход: нулевой объём, деньги не вычислялись."""
        return cls(strategy_id=strategy_id, config_hash=config_hash,
                   risk_policy_hash=risk_policy_hash, figi=figi,
                   outcome=outcome, reason_code=reason_code, quantity=0,
                   lot_count=0, lot_size=None, risk_budget=None,
                   risk_per_unit=None, total_position_risk=None,
                   position_notional=None, notional_cap=None,
                   buying_power_cap=None, diagnostics=diagnostics)

    @classmethod
    def zero_size(cls, *, strategy_id: str, config_hash: str,
                  risk_policy_hash: str, figi: str, reason_code: str,
                  lot_size: int, risk_budget: Optional[float],
                  risk_per_unit: Optional[float], notional_cap: float,
                  buying_power_cap: float,
                  diagnostics: Optional[Mapping] = None) -> "SizingResult":
        """Объём меньше одного лота: сделка не форсируется (ТЗ §6)."""
        return cls(strategy_id=strategy_id, config_hash=config_hash,
                   risk_policy_hash=risk_policy_hash, figi=figi,
                   outcome=SizingOutcome.ZERO_SIZE,
                   reason_code=reason_code, quantity=0, lot_count=0,
                   lot_size=lot_size, risk_budget=risk_budget,
                   risk_per_unit=risk_per_unit, total_position_risk=0.0,
                   position_notional=0.0, notional_cap=notional_cap,
                   buying_power_cap=buying_power_cap,
                   diagnostics=diagnostics)

    @classmethod
    def sized(cls, *, strategy_id: str, config_hash: str,
              risk_policy_hash: str, figi: str, reason_code: str,
              quantity: int, lot_count: int, lot_size: int,
              risk_budget: float, risk_per_unit: float,
              total_position_risk: float, position_notional: float,
              notional_cap: float, buying_power_cap: float,
              diagnostics: Optional[Mapping] = None) -> "SizingResult":
        """Успешный расчёт (единственный исход с положительным объёмом)."""
        return cls(strategy_id=strategy_id, config_hash=config_hash,
                   risk_policy_hash=risk_policy_hash, figi=figi,
                   outcome=SizingOutcome.SIZED, reason_code=reason_code,
                   quantity=quantity, lot_count=lot_count,
                   lot_size=lot_size, risk_budget=risk_budget,
                   risk_per_unit=risk_per_unit,
                   total_position_risk=total_position_risk,
                   position_notional=position_notional,
                   notional_cap=notional_cap,
                   buying_power_cap=buying_power_cap,
                   diagnostics=diagnostics)


# ---------------------------------------------------------------------------
# Публичный валидатор результата (независимая перепроверка; ТЗ §10 —
# негативные тесты демонстрируют перехват некорректных реализаций)
# ---------------------------------------------------------------------------


def validate_sizing_result(result: Any, *,
                           expected_policy: Any = None,
                           expected_config: Any = None,
                           expected_input: Any = None) -> None:
    """Независимая перепроверка SizingResult против контракта Stage D.

    Проверяет внутреннюю согласованность результата (включая ТОЧНЫЕ
    десятичные строки диагностики: объём не превышает ни один из
    лимитов, кратен лоту, деньги согласованы) и, при переданных
    ожидаемых объектах, соответствие атрибуции и входу.

    Бросает SizingResultViolationError при ЛЮБОМ нарушении. Предназначен
    для потребителей результата и негативных тестов: заведомо сломанная
    реализация (положительный объём в блокирующем исходе, превышение
    бюджета/notional/buying power, некратность лоту, подмена хешей)
    НЕ проходит валидатор.
    """
    if type(result) is not SizingResult:
        raise SizingResultViolationError(
            "validate_sizing_result принимает только точный тип "
            f"SizingResult; получено {type(result).__name__}")
    # 1. Атрибуция против ожидаемых объектов.
    if expected_policy is not None:
        if type(expected_policy) is not RiskPolicy:
            raise SizingResultViolationError(
                "expected_policy должен быть точным типом RiskPolicy")
        if result.strategy_id != expected_policy.strategy_id \
                or result.config_hash != expected_policy.config_hash:
            raise SizingResultViolationError(
                "атрибуция результата не совпадает с политикой")
        if result.risk_policy_hash != expected_policy.policy_hash:
            raise SizingResultViolationError(
                "risk_policy_hash результата не совпадает с хешем "
                "фактических параметров политики")
    if expected_config is not None:
        if type(expected_config) is not StrategyConfig:
            raise SizingResultViolationError(
                "expected_config должен быть точным типом StrategyConfig")
        if result.strategy_id != expected_config.strategy_id \
                or result.config_hash != expected_config.config_hash:
            raise SizingResultViolationError(
                "атрибуция результата не совпадает с конфигурацией")
    if expected_input is not None:
        if type(expected_input) is not SizingInput:
            raise SizingResultViolationError(
                "expected_input должен быть точным типом SizingInput")
        if expected_input.figi and result.figi != expected_input.figi:
            raise SizingResultViolationError(
                "FIGI результата не совпадает с FIGI входа")
    if result.outcome not in _COMPUTED_OUTCOMES:
        # Блокирующий исход: дополнительная проверка объёма уже сделана
        # при создании; для валидатора продублировать ЯВНО (ТЗ §10.16).
        if result.quantity != 0 or result.lot_count != 0:
            raise SizingResultViolationError(
                "блокирующий результат несёт положительный объём")
        return
    # 2. Расчётные исходы: точная перепроверка по строкам диагностики.
    diag = result.diagnostics
    inputs = diag.get("inputs_decimal")
    computed = diag.get("computed_decimal")
    if not isinstance(inputs, Mapping) or not isinstance(computed, Mapping):
        raise SizingResultViolationError(
            "диагностика расчётного результата обязана содержать "
            "inputs_decimal и computed_decimal")
    # Все ключи обязаны быть строками-числами: отсутствующий/нечисловой
    # ключ — нарушение контракта результата, а не произвольное
    # исключение наружу (fail-closed валидатор).
    try:
        _validate_sizing_result_exact(result, inputs=inputs,
                                      computed=computed)
    except SizingResultViolationError:
        raise
    except Exception as exc:  # decimal.InvalidOperation, TypeError и пр.
        raise SizingResultViolationError(
            "диагностика результата нечитаема/несогласована: "
            f"{type(exc).__name__}: {exc}") from exc


def _validate_sizing_result_exact(result: "SizingResult", *,
                                  inputs: Mapping, computed: Mapping) -> None:
    """Точная (Decimal) перепроверка расчётного результата по его
    диагностике. Вызывается из validate_sizing_result внутри
    protected-блока; декорации ошибок — SizingResultViolationError."""
    with localcontext() as ctx:
        ctx.prec = _DECIMAL_PRECISION
        equity = Decimal(str(inputs.get("equity")))
        risk_fraction = Decimal(str(inputs.get("risk_per_trade_fraction")))
        notional_fraction = Decimal(
            str(inputs.get("max_position_notional_fraction")))
        entry = Decimal(str(inputs.get("entry_price")))
        multiplier = Decimal(str(inputs.get("contract_multiplier")))
        entry_cost = Decimal(str(inputs.get("entry_cost_per_unit")))
        budget = Decimal(str(computed.get("risk_budget")))
        total_risk_per_unit = Decimal(
            str(computed.get("total_risk_per_unit")))
        per_unit_notional = Decimal(
            str(computed.get("per_unit_notional_cost")))
        per_unit_bp = Decimal(str(computed.get("per_unit_buying_power_cost")))
        max_notional = Decimal(str(computed.get("max_notional_cap")))
        buying_power = Decimal(str(inputs.get("buying_power_limit")))
        stop_price = Decimal(str(inputs.get("stop_price")))
        stop_exit_cost = Decimal(str(inputs.get("stop_exit_cost_per_unit")))
        lot_size = result.lot_size
        if lot_size is None or lot_size <= 0:
            raise SizingResultViolationError(
                "lot_size результата отсутствует или некорректен")
        # 2a. Деньги результата согласованы с точными величинами.
        quantity_d = Decimal(result.quantity)
        if result.risk_budget is None \
                or _decimal_to_float_safe(budget) != result.risk_budget:
            raise SizingResultViolationError(
                "risk_budget результата не совпадает с точным значением "
                "диагностики")
        # 2b. Объём кратен лоту и неотрицателен.
        if result.quantity < 0 or result.quantity % lot_size != 0:
            raise SizingResultViolationError(
                "объём результата не кратен lot_size")
        if result.outcome is SizingOutcome.SIZED:
            if result.quantity < lot_size:
                raise SizingResultViolationError(
                    "SIZED с объёмом меньше одного лота")
            if result.lot_count != result.quantity // lot_size:
                raise SizingResultViolationError(
                    "lot_count не соответствует quantity/lot_size")
        # 2c. ТОЧНЫЕ проверки лимитов (ТЗ §6): ни один не превышен.
        if quantity_d * total_risk_per_unit > budget:
            raise SizingResultViolationError(
                "объём превышает риск-бюджет (точная проверка)")
        if quantity_d * per_unit_notional > max_notional:
            raise SizingResultViolationError(
                "объём превышает максимальный notional (точная проверка)")
        if quantity_d * per_unit_bp > buying_power:
            raise SizingResultViolationError(
                "объём превышает покупательную способность (точная "
                "проверка)")
        # 2d. Согласованность вычисленных величин со входом.
        if budget != equity * risk_fraction:
            raise SizingResultViolationError(
                "risk_budget диагностики не равен equity * "
                "risk_per_trade_fraction")
        if max_notional != equity * notional_fraction:
            raise SizingResultViolationError(
                "max_notional_cap диагностики не равен equity * "
                "max_position_notional_fraction")
        price_risk = Decimal(str(computed.get("price_risk_per_unit")))
        if price_risk != abs(entry - stop_price) * multiplier:
            raise SizingResultViolationError(
                "price_risk_per_unit диагностики не согласован со входом")
        if total_risk_per_unit != price_risk + entry_cost + stop_exit_cost:
            raise SizingResultViolationError(
                "total_risk_per_unit диагностики не согласован со входом")
        if per_unit_notional != entry * multiplier:
            raise SizingResultViolationError(
                "per_unit_notional_cost диагностики не согласован со "
                "входом")
        if per_unit_bp != per_unit_notional + entry_cost:
            raise SizingResultViolationError(
                "per_unit_buying_power_cost диагностики не согласован со "
                "входом")
        # 2e. Итоговые деньги результата (float-зеркала точных величин).
        total_risk_exact = quantity_d * total_risk_per_unit
        notional_exact = quantity_d * per_unit_notional
        if result.total_position_risk is None or \
                _decimal_to_float_safe(total_risk_exact) \
                != result.total_position_risk:
            raise SizingResultViolationError(
                "total_position_risk результата не совпадает с точным "
                "значением quantity * total_risk_per_unit")
        if result.position_notional is None or \
                _decimal_to_float_safe(notional_exact) \
                != result.position_notional:
            raise SizingResultViolationError(
                "position_notional результата не совпадает с точным "
                "значением quantity * entry_price * multiplier")
        if result.notional_cap is None or \
                _decimal_to_float_safe(max_notional) != result.notional_cap:
            raise SizingResultViolationError(
                "notional_cap результата не совпадает с точным значением")
        if result.buying_power_cap is None or \
                _decimal_to_float_safe(buying_power) \
                != result.buying_power_cap:
            raise SizingResultViolationError(
                "buying_power_cap результата не совпадает с точным "
                "значением")


# ---------------------------------------------------------------------------
# Основной расчёт (ТЗ §3–§8): чистая функция, без состояния
# ---------------------------------------------------------------------------


def calculate_position_size(*,
                            policy: Any,
                            config: Any,
                            sizing_input: Any) -> SizingResult:
    """Детерминированный расчёт теоретического объёма позиции (ТЗ §2–§8).

    ЧИСТАЯ функция: без состояния, без времени, без случайности, без
    окружения; одинаковые аргументы -> структурно идентичный результат
    (ТЗ §10.17). НЕ размещает и не изменяет заявки (ТЗ §2/§9).

    Аргументы (все обязательные, keyword-only):
      policy       — RiskPolicy (точный тип): риск-политика стратегии;
      config       — StrategyConfig (точный тип): конфигурация стратегии;
      sizing_input — SizingInput (точный тип): данные расчёта.

    ПОРЯДОК ВОРОТ (fail-closed, ТЗ §3–§8):
      1. точные типы сотрудников (policy/config) — misuse -> исключение;
      2. перепроверка config_hash конфигурации ИСХОДНЫМ алгоритмом
         Stage A.2.1 (AttributionContext.from_config);
      3. целостность политики (пересчёт policy_hash);
      4. точный тип входа -> INVALID_INPUT/INPUT_WRONG_TYPE;
      5. отсутствие обязательных данных -> MISSING_REQUIRED_DATA;
      6. направление: SHORT -> UNSUPPORTED_SIDE (long-only, ТЗ §5);
      7. согласование атрибуции policy/config/input
         -> ATTRIBUTION_MISMATCH (стратегия/хеш/FIGI);
      8. геометрия стопа (LONG: стоп СТРОГО ниже входа)
         -> INVALID_STOP_GEOMETRY;
      9. точный десятичный расчёт (формулы ТЗ §6), округление СТРОГО
         вниз до целого лота, точные проверки лимитов -> SIZED/ZERO_SIZE.
    Любое непредвиденное исключение вычисления конвертируется в
    БЛОКИРУЮЩИЙ исход (никогда — в положительный объём, ТЗ §8).
    """
    # --- 1. Контракт вызывающего кода: точные типы сотрудников. -------
    if type(policy) is not RiskPolicy:
        raise SizingContractViolationError(
            "calculate_position_size требует точный тип RiskPolicy "
            f"(подклассы не проходят, ТЗ §3); получено "
            f"{type(policy).__name__}")
    if type(config) is not StrategyConfig:
        raise SizingContractViolationError(
            "calculate_position_size требует точный тип StrategyConfig "
            f"(Stage A.2.1; подклассы не проходят); получено "
            f"{type(config).__name__}")

    # --- 2. Перепроверка config_hash ИСХОДНЫМ алгоритмом Stage A.2.1 --
    try:
        AttributionContext.from_config(config)
    except Exception as exc:  # AttributionError (Stage A.2.1)
        raise SizingContractViolationError(
            "конфигурация не прошла проверку атрибуции Stage A.2.1 "
            f"(config_hash против фактических параметров): {exc}"
        ) from exc

    # --- 3. Целостность политики (ТЗ §8: policy hash integrity). ------
    # Пересчёт хеша по ФАКТИЧЕСКИМ полям против хеша, зафиксированного
    # при создании: изменение любого поля в обход API (tamper,
    # повреждённая десериализация) -> типизированный блокирующий исход
    # POLICY_INVALID (никогда не положительный объём, ТЗ §8).
    try:
        recomputed_hash = policy.verify_policy_hash()
        _validate_policy_hash_format(recomputed_hash)
    except Exception as exc:  # RiskPolicyViolationError и прочее
        stored = policy.policy_hash \
            if isinstance(getattr(policy, "policy_hash", None), str) else ""
        try:
            honest_hash = compute_risk_policy_hash(
                policy.strategy_id, policy.config_hash,
                policy.risk_per_trade_fraction,
                policy.max_position_notional_fraction)
        except Exception:
            honest_hash = ""  # честный хеш не вычислим: пусто (см. §7)
        return SizingResult.blocked(
            strategy_id=config.strategy_id,
            config_hash=config.config_hash,
            risk_policy_hash=honest_hash if honest_hash
            and _is_valid_policy_hash_format(honest_hash) else "",
            figi="",
            outcome=SizingOutcome.POLICY_INVALID,
            reason_code=REASON_POLICY_HASH_MISMATCH,
            diagnostics={
                "sizing_rules_version": SIZING_RULES_VERSION,
                "stored_policy_hash": stored[:128],
                "recomputed_policy_hash":
                    honest_hash if isinstance(honest_hash, str) else "",
                "exception_type": type(exc).__name__,
                "exception_message": str(exc)[:500],
                "detail": "целостность риск-политики нарушена: хеш "
                          "фактических полей не совпадает с хешем, "
                          "зафиксированным при создании; использование "
                          "политики запрещено (ТЗ §8, fail-closed)",
            })

    # --- 4. Точный тип входа: данные-носитель, не сотрудник. ----------
    if type(sizing_input) is not SizingInput:
        return SizingResult.blocked(
            strategy_id=config.strategy_id,
            config_hash=config.config_hash,
            risk_policy_hash=recomputed_hash,
            figi="",
            outcome=SizingOutcome.INVALID_INPUT,
            reason_code=REASON_INPUT_WRONG_TYPE,
            diagnostics={
                "sizing_rules_version": SIZING_RULES_VERSION,
                "received_type": type(sizing_input).__name__,
                "detail": "вход обязан быть точным типом SizingInput "
                          "(подклассы и duck-typing не проходят, ТЗ §3)",
            })

    input_attribution = sizing_input.attribution

    # --- 5. Отсутствующие обязательные данные (ТЗ §5/§7). -------------
    missing = [name for name in SIZING_INPUT_DATA_FIELDS
               if getattr(sizing_input, name) is None]
    if missing:
        return SizingResult.blocked(
            strategy_id=config.strategy_id,
            config_hash=config.config_hash,
            risk_policy_hash=recomputed_hash,
            figi=sizing_input.figi or "",
            outcome=SizingOutcome.MISSING_REQUIRED_DATA,
            reason_code=REASON_MISSING_REQUIRED_FIELDS,
            diagnostics={
                "sizing_rules_version": SIZING_RULES_VERSION,
                "missing_fields": missing,
                "detail": "обязательные данные отсутствуют (явный None); "
                          "значения НЕ придумываются: ноль, последняя "
                          "известная цена и умолчания не подставляются "
                          "(ТЗ §5/§6)",
            })

    # --- 6. Направление: long-only движок (ТЗ §5). ---------------------
    if sizing_input.side is TradeSide.SHORT:
        return SizingResult.blocked(
            strategy_id=config.strategy_id,
            config_hash=config.config_hash,
            risk_policy_hash=recomputed_hash,
            figi=sizing_input.figi or "",
            outcome=SizingOutcome.UNSUPPORTED_SIDE,
            reason_code=REASON_SIDE_UNSUPPORTED_SHORT,
            diagnostics={
                "sizing_rules_version": SIZING_RULES_VERSION,
                "requested_side": sizing_input.side.value,
                "supported_sides": [side.value
                                    for side in SUPPORTED_TRADE_SIDES],
                "detail": "SHORT-масштабирование явно не поддерживается "
                          "текущим движком (long-only, ТЗ §5); "
                          "неподдерживаемое направление НЕ "
                          "интерпретируется как LONG",
            })

    # --- 7. Согласование атрибуции (ТЗ §4/§8). -------------------------
    # 7a. Политика <-> конфигурация.
    if policy.strategy_id != config.strategy_id:
        return SizingResult.blocked(
            strategy_id=config.strategy_id,
            config_hash=config.config_hash,
            risk_policy_hash=recomputed_hash,
            figi=sizing_input.figi or "",
            outcome=SizingOutcome.ATTRIBUTION_MISMATCH,
            reason_code=REASON_STRATEGY_ID_MISMATCH,
            diagnostics={
                "sizing_rules_version": SIZING_RULES_VERSION,
                "policy_strategy_id": policy.strategy_id,
                "config_strategy_id": config.strategy_id,
                "detail": "риск-политика привязана к другой стратегии; "
                          "молчаливое переиспользование политики "
                          "запрещено (ТЗ §4)",
            })
    if policy.config_hash != config.config_hash:
        return SizingResult.blocked(
            strategy_id=config.strategy_id,
            config_hash=config.config_hash,
            risk_policy_hash=recomputed_hash,
            figi=sizing_input.figi or "",
            outcome=SizingOutcome.ATTRIBUTION_MISMATCH,
            reason_code=REASON_CONFIG_HASH_MISMATCH,
            diagnostics={
                "sizing_rules_version": SIZING_RULES_VERSION,
                "policy_config_hash": policy.config_hash,
                "config_config_hash": config.config_hash,
                "detail": "риск-политика привязана к другой версии "
                          "конфигурации (config_hash различаются); "
                          "переиспользование политики для иной "
                          "конфигурации запрещено (ТЗ §4)",
            })
    # 7b. Вход <-> конфигурация (контекст входа проверенного создания).
    if input_attribution.strategy_id != config.strategy_id \
            or input_attribution.config_hash != config.config_hash:
        return SizingResult.blocked(
            strategy_id=config.strategy_id,
            config_hash=config.config_hash,
            risk_policy_hash=recomputed_hash,
            figi=sizing_input.figi or "",
            outcome=SizingOutcome.ATTRIBUTION_MISMATCH,
            reason_code=REASON_INPUT_ATTRIBUTION_MISMATCH,
            diagnostics={
                "sizing_rules_version": SIZING_RULES_VERSION,
                "input_strategy_id": input_attribution.strategy_id,
                "input_config_hash": input_attribution.config_hash,
                "config_strategy_id": config.strategy_id,
                "config_config_hash": config.config_hash,
                "detail": "атрибуция входа не совпадает с конфигурацией "
                          "расчёта",
            })
    # 7c. FIGI котировок против FIGI входа (ТЗ §8: mismatched FIGI).
    price_objects = []
    if isinstance(sizing_input.entry_price, PriceData):
        price_objects.append(("entry_price", sizing_input.entry_price))
    if isinstance(sizing_input.protective_stop_price, PriceData):
        price_objects.append(("protective_stop_price",
                              sizing_input.protective_stop_price))
    for field_name, quote in price_objects:
        if quote.figi != sizing_input.figi:
            return SizingResult.blocked(
                strategy_id=config.strategy_id,
                config_hash=config.config_hash,
                risk_policy_hash=recomputed_hash,
                figi=sizing_input.figi or "",
                outcome=SizingOutcome.ATTRIBUTION_MISMATCH,
                reason_code=REASON_FIGI_MISMATCH,
                diagnostics={
                    "sizing_rules_version": SIZING_RULES_VERSION,
                    "field": field_name,
                    "input_figi": sizing_input.figi,
                    "quote_figi": quote.figi,
                    "detail": "котировка принадлежит другому инструменту "
                              "(mismatched FIGI, ТЗ §8)",
                })

    # --- 8. Геометрия стопа: LONG — стоп СТРОГО ниже входа (ТЗ §5). ----
    entry_value = sizing_input.entry_price_value
    stop_value = sizing_input.protective_stop_price_value
    if not stop_value < entry_value:
        return SizingResult.blocked(
            strategy_id=config.strategy_id,
            config_hash=config.config_hash,
            risk_policy_hash=recomputed_hash,
            figi=sizing_input.figi or "",
            outcome=SizingOutcome.INVALID_STOP_GEOMETRY,
            reason_code=REASON_STOP_NOT_BELOW_ENTRY,
            diagnostics={
                "sizing_rules_version": SIZING_RULES_VERSION,
                "trade_side": sizing_input.side.value,
                "entry_price": _decimal_to_exact_str(
                    _to_decimal(entry_value)),
                "stop_price": _decimal_to_exact_str(_to_decimal(stop_value)),
                "stop_relation": "EQUAL_TO_ENTRY"
                if stop_value == entry_value else "ABOVE_ENTRY",
                "detail": "для LONG защитный стоп обязан находиться "
                          "СТРОГО ниже цены входа (на стороне убытка); "
                          "стоп на входе или выше входа блокирует "
                          "масштабирование (ТЗ §5)",
            })

    # --- 9. Точный десятичный расчёт (ТЗ §6). --------------------------
    try:
        return _compute_sized_or_zero_size(
            policy=policy, config=config,
            recomputed_hash=recomputed_hash, sizing_input=sizing_input,
            entry_value=entry_value, stop_value=stop_value)
    except Exception as exc:  # noqa: BLE001 — fail-closed конвертация
        # Никакое исключение НЕ превращается в положительный объём
        # (ТЗ §8): явный блокирующий результат с диагностикой.
        return SizingResult.blocked(
            strategy_id=config.strategy_id,
            config_hash=config.config_hash,
            risk_policy_hash=recomputed_hash,
            figi=sizing_input.figi or "",
            outcome=SizingOutcome.INVALID_INPUT,
            reason_code=REASON_COMPUTATION_ERROR_FAIL_CLOSED,
            diagnostics={
                "sizing_rules_version": SIZING_RULES_VERSION,
                "exception_type": type(exc).__name__,
                "exception_message": str(exc)[:500],
                "detail": "непредвиденная ошибка вычисления конвертирована "
                          "в явный блокирующий исход; положительный объём "
                          "не возвращён (fail-closed, ТЗ §8)",
            })


def _compute_sized_or_zero_size(*, policy: RiskPolicy,
                                config: StrategyConfig,
                                recomputed_hash: str,
                                sizing_input: SizingInput,
                                entry_value: float,
                                stop_value: float) -> SizingResult:
    """Точный расчёт SIZED/ZERO_SIZE (вызывается calculate_position_size).

    Все операции — точные десятичные (сложение/умножение точны при
    prec=5000; округления вниз — целочисленные _floor_ratio). Итоговые
    проверки лимитов — точные сравнения (defense-in-depth): нарушение
    невозможно по построению и конвертируется в блокирующий исход.
    """
    figi = sizing_input.figi or ""
    lot_size = int(sizing_input.lot_size)
    strategy_id = config.strategy_id
    config_hash = config.config_hash
    policy_hash = recomputed_hash

    with localcontext() as ctx:
        ctx.prec = _DECIMAL_PRECISION
        equity_d = _to_decimal(float(sizing_input.available_equity))
        buying_power_d = _to_decimal(
            float(sizing_input.buying_power_limit))
        entry_d = _to_decimal(entry_value)
        stop_d = _to_decimal(stop_value)
        multiplier_d = _to_decimal(float(sizing_input.contract_multiplier))
        entry_cost_d = _to_decimal(float(sizing_input.entry_cost_per_unit))
        stop_exit_cost_d = _to_decimal(
            float(sizing_input.stop_exit_cost_per_unit))
        risk_fraction_d = _to_decimal(
            float(policy.risk_per_trade_fraction))
        notional_fraction_d = _to_decimal(
            float(policy.max_position_notional_fraction))

        # Формулы ТЗ §6 (точные операции).
        risk_budget_d = equity_d * risk_fraction_d
        max_notional_d = equity_d * notional_fraction_d
        price_risk_per_unit_d = abs(entry_d - stop_d) * multiplier_d
        total_risk_per_unit_d = (price_risk_per_unit_d + entry_cost_d
                                 + stop_exit_cost_d)
        per_unit_notional_d = entry_d * multiplier_d
        per_unit_bp_d = per_unit_notional_d + entry_cost_d

        # Защита от вырожденного знаменателя (price_risk_per_unit > 0
        # гарантирован геометрией стопа и multiplier > 0; проверка —
        # defense-in-depth): не деление, а точное отношение.
        if total_risk_per_unit_d <= 0 or per_unit_notional_d <= 0 \
                or per_unit_bp_d <= 0:
            return SizingResult.blocked(
                strategy_id=strategy_id, config_hash=config_hash,
                risk_policy_hash=policy_hash, figi=figi,
                outcome=SizingOutcome.INVALID_INPUT,
                reason_code=REASON_COMPUTATION_ERROR_FAIL_CLOSED,
                diagnostics={
                    "sizing_rules_version": SIZING_RULES_VERSION,
                    "detail": "вырожденный знаменатель (риск/стоимость "
                              "единицы <= 0): расчёт заблокирован "
                              "(fail-closed)",
                })

        units_by_risk = _floor_ratio(risk_budget_d, total_risk_per_unit_d)
        units_by_notional = _floor_ratio(max_notional_d,
                                         per_unit_notional_d)
        units_by_bp = _floor_ratio(buying_power_d, per_unit_bp_d)
        units_min = min(units_by_risk, units_by_notional, units_by_bp)
        lots = units_min // lot_size
        quantity = lots * lot_size

        inputs_decimal = {
            "equity": _decimal_to_exact_str(equity_d),
            "buying_power_limit": _decimal_to_exact_str(buying_power_d),
            "entry_price": _decimal_to_exact_str(entry_d),
            "stop_price": _decimal_to_exact_str(stop_d),
            "contract_multiplier": _decimal_to_exact_str(multiplier_d),
            "entry_cost_per_unit": _decimal_to_exact_str(entry_cost_d),
            "stop_exit_cost_per_unit":
                _decimal_to_exact_str(stop_exit_cost_d),
            "risk_per_trade_fraction":
                _decimal_to_exact_str(risk_fraction_d),
            "max_position_notional_fraction":
                _decimal_to_exact_str(notional_fraction_d),
        }
        computed_decimal = {
            "risk_budget": _decimal_to_exact_str(risk_budget_d),
            "max_notional_cap": _decimal_to_exact_str(max_notional_d),
            "price_risk_per_unit":
                _decimal_to_exact_str(price_risk_per_unit_d),
            "total_risk_per_unit":
                _decimal_to_exact_str(total_risk_per_unit_d),
            "per_unit_notional_cost":
                _decimal_to_exact_str(per_unit_notional_d),
            "per_unit_buying_power_cost":
                _decimal_to_exact_str(per_unit_bp_d),
        }

        # Точные итоговые проверки (ТЗ §6; defense-in-depth: нарушение
        # невозможно по построению _floor_ratio, но любое нарушение —
        # блокирующий исход, никогда не положительный объём).
        quantity_d = Decimal(quantity)
        risk_ok = quantity_d * total_risk_per_unit_d <= risk_budget_d
        notional_ok = quantity_d * per_unit_notional_d <= max_notional_d
        bp_ok = quantity_d * per_unit_bp_d <= buying_power_d
        verification = {
            "risk_ok": bool(risk_ok),
            "notional_ok": bool(notional_ok),
            "buying_power_ok": bool(bp_ok),
        }
        if not (risk_ok and notional_ok and bp_ok):
            return SizingResult.blocked(
                strategy_id=strategy_id, config_hash=config_hash,
                risk_policy_hash=policy_hash, figi=figi,
                outcome=SizingOutcome.INVALID_INPUT,
                reason_code=REASON_COMPUTATION_VERIFICATION_FAILED,
                diagnostics={
                    "sizing_rules_version": SIZING_RULES_VERSION,
                    "verification": verification,
                    "detail": "точная итоговая проверка лимитов не "
                              "пройдена: положительный объём не "
                              "возвращается (fail-closed)",
                })

        common_diag = {
            "sizing_rules_version": SIZING_RULES_VERSION,
            "lot_size": lot_size,
            "trade_side": sizing_input.side.value,
            "entry_price_source":
                "PriceData" if isinstance(sizing_input.entry_price,
                                          PriceData) else "number",
            "stop_price_source":
                "PriceData" if isinstance(sizing_input.protective_stop_price,
                                          PriceData) else "number",
            "inputs_decimal": inputs_decimal,
            "computed_decimal": computed_decimal,
            "units_by_risk": units_by_risk,
            "units_by_notional": units_by_notional,
            "units_by_buying_power": units_by_bp,
            "rounding_method": SIZING_ROUNDING_METHOD,
            "verification": verification,
            "risk_policy_schema": RISK_POLICY_SCHEMA_VERSION,
        }

        if lots < 1:
            # Объём меньше одного лота: явный блокирующий исход (ТЗ §6).
            # Причина — первый исчерпавший лимит в фиксированном порядке
            # риск -> notional -> покупательная способность; все три
            # величины в диагностике.
            if units_by_risk < lot_size:
                reason = REASON_RISK_BUDGET_BELOW_ONE_LOT
            elif units_by_notional < lot_size:
                reason = REASON_NOTIONAL_CAP_BELOW_ONE_LOT
            else:
                reason = REASON_BUYING_POWER_BELOW_ONE_LOT
            limiting = {
                "units_by_risk": units_by_risk,
                "units_by_notional": units_by_notional,
                "units_by_buying_power": units_by_bp,
                "lot_size": lot_size,
                "detail": "минимально допустимый объём меньше одного "
                          "лота; сделка не форсируется (ТЗ §6)",
            }
            diag = dict(common_diag)
            diag["zero_size_analysis"] = limiting
            risk_per_unit_float = _decimal_to_float_safe(
                total_risk_per_unit_d)
            return SizingResult.zero_size(
                strategy_id=strategy_id, config_hash=config_hash,
                risk_policy_hash=policy_hash, figi=figi,
                reason_code=reason, lot_size=lot_size,
                risk_budget=_decimal_to_float_safe(risk_budget_d),
                risk_per_unit=risk_per_unit_float,
                notional_cap=_decimal_to_float_safe(max_notional_d),
                buying_power_cap=_decimal_to_float_safe(buying_power_d),
                diagnostics=diag)

        # Успешный расчёт (ТЗ §6/§7).
        total_position_risk_d = quantity_d * total_risk_per_unit_d
        position_notional_d = quantity_d * per_unit_notional_d
        diag = dict(common_diag)
        diag["limiting_constraint"] = {
            "units_by_risk": units_by_risk,
            "units_by_notional": units_by_notional,
            "units_by_buying_power": units_by_bp,
        }
        if units_min == units_by_risk:
            diag["limiting_constraint"]["binding"] = "RISK"
        elif units_min == units_by_notional:
            diag["limiting_constraint"]["binding"] = "NOTIONAL"
        else:
            diag["limiting_constraint"]["binding"] = "BUYING_POWER"
        diag["exact_quantity"] = quantity
        diag["exact_lot_count"] = lots
        diag["exact_total_position_risk"] = \
            _decimal_to_exact_str(total_position_risk_d)
        diag["exact_position_notional"] = \
            _decimal_to_exact_str(position_notional_d)
        return SizingResult.sized(
            strategy_id=strategy_id, config_hash=config_hash,
            risk_policy_hash=policy_hash, figi=figi,
            reason_code=REASON_SIZED_LONG, quantity=quantity,
            lot_count=lots, lot_size=lot_size,
            risk_budget=_decimal_to_float_safe(risk_budget_d),
            risk_per_unit=_decimal_to_float_safe(total_risk_per_unit_d),
            total_position_risk=_decimal_to_float_safe(
                total_position_risk_d),
            position_notional=_decimal_to_float_safe(position_notional_d),
            notional_cap=_decimal_to_float_safe(max_notional_d),
            buying_power_cap=_decimal_to_float_safe(buying_power_d),
            diagnostics=diag)


__all__ = [
    "StrategyRiskError",
    "RiskPolicyViolationError",
    "SizingInputViolationError",
    "SizingResultViolationError",
    "SizingContractViolationError",
    "RISK_POLICY_SCHEMA_VERSION",
    "SIZING_RULES_VERSION",
    "SIZING_ROUNDING_METHOD",
    "REASON_SIZED_LONG",
    "REASON_QUANTITY_BELOW_ONE_LOT",
    "REASON_RISK_BUDGET_BELOW_ONE_LOT",
    "REASON_NOTIONAL_CAP_BELOW_ONE_LOT",
    "REASON_BUYING_POWER_BELOW_ONE_LOT",
    "REASON_INPUT_WRONG_TYPE",
    "REASON_MISSING_REQUIRED_FIELDS",
    "REASON_POLICY_HASH_MISMATCH",
    "REASON_STRATEGY_ID_MISMATCH",
    "REASON_CONFIG_HASH_MISMATCH",
    "REASON_INPUT_ATTRIBUTION_MISMATCH",
    "REASON_FIGI_MISMATCH",
    "REASON_SIDE_UNSUPPORTED_SHORT",
    "REASON_STOP_NOT_BELOW_ENTRY",
    "REASON_COMPUTATION_ERROR_FAIL_CLOSED",
    "REASON_COMPUTATION_VERIFICATION_FAILED",
    "TradeSide",
    "SUPPORTED_TRADE_SIDES",
    "SIZING_INPUT_DATA_FIELDS",
    "compute_risk_policy_hash",
    "RiskPolicy",
    "SizingInput",
    "SizingOutcome",
    "SizingResult",
    "validate_sizing_result",
    "calculate_position_size",
]
