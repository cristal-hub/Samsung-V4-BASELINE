# strategy_api.py
# SAMSUNG V4 — NEW STRATEGY ENGINE. STAGE A.
# Единый контракт стратегии нового движка.
#
# НАЗНАЧЕНИЕ
#   Типизированный, документированный интерфейс, который будущие стратегии
#   нового движка (Этапы B/C и далее) реализуют явно. Контракт фиксирует:
#     * уникальный strategy_id и версию стратегии;
#     * описание параметров (ParamSpec) и их валидацию;
#     * получение конфигурации (StrategyConfig) и стабильного config_hash;
#     * контракт входного сигнала (EntrySignalInput -> Signal).
#
# ЧЕГО КОНТРАКТ СОЗНАТЕЛЬНО НЕ ДЕЛАЕТ (запрещено ТЗ Этапа A):
#     * изоляция изменяемого состояния по (strategy_id, FIGI) — Этап B;
#     * evaluate_exit и новый контракт выхода — Этап C;
#     * новый риск-менеджмент — Этап D;
#     * исторический симулятор — Этап E;
#     * новый Sandbox adapter — Этап F;
#     * никакой торговли, заявок и подключений к брокеру.
#
# БЕЗОПАСНОСТЬ:
#   * ActivationMode по умолчанию REGRESSION_ONLY: стратегия, не объявившая
#     явно TRADING_ALLOWED, не может быть активирована для торговли
#     (fail-closed по умолчанию).
#   * Никаких значений по умолчанию для торговых решений; отсутствие
#     обязательных параметров — ошибка, а не тихий fallback.
#
# STAGE A.1 (исправление замечания №1 независимого аудита):
#   @dataclass(frozen=True) защищает только атрибуты верхнего уровня.
#   Вложенные структуры params/metadata теперь хранятся в ГЛУБОКО
#   неизменяемых представлениях:
#     * ImmutableMapping — отображение без операций записи; хранит копию
#       содержимого в MappingProxyType, значения заморожены рекурсивно;
#     * ImmutableList  — последовательность на базе tuple (C-уровневая
#       неизменяемость), значения заморожены рекурсивно;
#     * множества -> frozenset;
#     * исходные словари КОПИРУЮТСЯ при создании: изменение источника
#       после создания конфигурации не меняет её содержимое;
#     * config_hash соответствует ФАКТИЧЕСКИ сохранённым параметрам
#       (StrategyConfig.recompute_config_hash()).
#   JSON-сериализация потребителей выполняется через StrategyConfig.as_dict()
#   (плоская глубокая модифицируемая копия) — round-trip сохраняет семантику
#   параметров и config_hash (тесты tests/test_stage_a1_config_immutability.py).
#
# STRATEGY LOGIC: UNCHANGED. RESEARCH ONLY. NO LIVE ORDERS. NO BROKER
# EXECUTION. NO SANDBOX EXECUTION.

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping as _MappingABC
from dataclasses import dataclass, field, fields as _dc_fields
from enum import Enum
from types import MappingProxyType
from typing import Any, Iterable, List, Mapping, Optional, Sequence, Tuple


# ---------------------------------------------------------------------------
# Исключения контракта
# ---------------------------------------------------------------------------

class StrategyContractError(Exception):
    """Базовая ошибка контракта стратегии (fail-closed)."""


class StrategyConfigError(StrategyContractError):
    """Конфигурация стратегии невалидна: запуск с ней запрещён."""


# ---------------------------------------------------------------------------
# Глубоко неизменяемые структуры (Stage A.1, замечание №1 аудита)
# ---------------------------------------------------------------------------

class ImmutableMapping(_MappingABC):
    """Глубоко неизменяемое отображение для params/metadata конфигурации.

    Гарантии:
      * операций записи НЕ существует: класс не реализует __setitem__/
        __delitem__/update/pop/clear/setdefault (Mapping ABC содержит
        только чтение), присвоение атрибутов запрещено (__setattr__);
      * внутреннее хранилище — MappingProxyType поверх СОБСТВЕННОЙ копии
        данных: даже запись через приватный атрибут _data отклоняется
        на уровне C (TypeError);
      * значения заморожены РЕКУРСИВНО (deep_freeze): вложенные dict ->
        ImmutableMapping, list/tuple -> ImmutableList, set -> frozenset;
      * при создании выполняется глубокая КОПИЯ: изменение исходных
        объектов после создания не влияет на содержимое;
      * ключи — только строки (fail-closed, как и в config_hash);
      * равенство семантическое: ImmutableMapping == dict с тем же
        содержимым (порядок ключей не важен);
      * хешируемость: hash(ImmutableMapping) согласован с равенством
        (необходимо для hash(StrategyConfig) frozen-дата класса).
    """

    __slots__ = ("_data",)

    def __init__(self, source: Any = None, **kwargs: Any) -> None:
        merged: dict = dict(source) if source is not None else {}
        merged.update(kwargs)
        frozen: dict = {}
        for key, value in merged.items():
            if not isinstance(key, str):
                raise StrategyConfigError(
                    f"ключи неизменяемого отображения должны быть "
                    f"строками: {key!r}")
            frozen[key] = deep_freeze(value)
        object.__setattr__(self, "_data", MappingProxyType(frozen))

    # --- чтение (только) ---------------------------------------------------

    def __getitem__(self, key: str) -> Any:
        return self._data[key]

    def __iter__(self):
        return iter(self._data)

    def __len__(self) -> int:
        return len(self._data)

    def __contains__(self, key: object) -> bool:
        return key in self._data

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def keys(self):
        return self._data.keys()

    def values(self):
        return self._data.values()

    def items(self):
        return self._data.items()

    # --- семантика равенства и хеша ----------------------------------------

    def __eq__(self, other: object) -> bool:
        if isinstance(other, _MappingABC):
            return dict(self._data) == dict(other)
        return NotImplemented

    def __hash__(self) -> int:
        # согласован с __eq__: равные отображения -> равные хеши
        return hash(frozenset(self._data.items()))

    def __repr__(self) -> str:
        return f"ImmutableMapping({dict(self._data)!r})"

    # --- копирование и сериализация ----------------------------------------

    def __reduce__(self):
        # восстановление через __init__ сохраняет глубокую заморозку
        # (работает для copy/deepcopy/pickle без обхода защиты записи)
        return (ImmutableMapping, (dict(self._data),))

    def to_mutable(self) -> dict:
        """Плоская глубокая МОДИФИЦИРУЕМАЯ копия (JSON-совместимая)."""
        return {key: unfreeze(value) for key, value in self._data.items()}

    # --- защита от записи -----------------------------------------------------

    def __setattr__(self, name: str, value: Any) -> None:
        raise TypeError(
            "ImmutableMapping неизменяем: операций записи не существует")

    def __delattr__(self, name: str) -> None:
        raise TypeError(
            "ImmutableMapping неизменяем: операций удаления не существует")


class ImmutableList(tuple):
    """Глубоко неизменяемая последовательность (на базе tuple).

    tuple гарантирует неизменяемость на C-уровне: у типа не существует
    операций записи вообще (в отличие от dict-подклассов). Значения
    заморожены рекурсивно (deep_freeze). Равенство семантическое:
    ImmutableList == list/tuple с тем же содержимым (это делает
    round-trip сериализации совместимым с исходными структурами).
    """

    __slots__ = ()

    def __new__(cls, iterable: Any = ()) -> "ImmutableList":
        return super().__new__(cls, (deep_freeze(item) for item in iterable))

    def __getitem__(self, index: Any) -> Any:
        result = super().__getitem__(index)
        if isinstance(index, slice):
            return ImmutableList(result)
        return result

    def __eq__(self, other: object) -> bool:
        if isinstance(other, (list, tuple)):
            return tuple(self) == tuple(other)
        return NotImplemented

    def __hash__(self) -> int:
        # согласован с __eq__ (tuple-хеш)
        return tuple.__hash__(self)

    def __repr__(self) -> str:
        return f"ImmutableList({list(self)!r})"

    def __reduce__(self):
        return (ImmutableList, (tuple(self),))

    def to_mutable(self) -> list:
        """Плоская глубокая МОДИФИЦИРУЕМАЯ копия (JSON-совместимая)."""
        return [unfreeze(item) for item in self]


def deep_freeze(value: Any) -> Any:
    """Рекурсивная глубокая заморозка значения (Stage A.1).

    Возвращает НЕЗАВИСИМУЮ неизменяемую копию:
      * ImmutableMapping/ImmutableList — возвращаются как есть (уже заморожены);
      * Mapping -> ImmutableMapping (глубокая копия);
      * set/frozenset -> frozenset из замороженных элементов;
      * list/tuple -> ImmutableList (глубокая копия);
      * скаляры (None/bool/int/float/str/Enum/...) — как есть (уже
        неизменяемы); никаких скрытых преобразований значений не выполняется.
    """
    if isinstance(value, (ImmutableMapping, ImmutableList)):
        return value
    if isinstance(value, Mapping):
        return ImmutableMapping(value)
    if isinstance(value, (set, frozenset)):
        return frozenset(deep_freeze(item) for item in value)
    if isinstance(value, (list, tuple)):
        return ImmutableList(value)
    return value


def unfreeze(value: Any) -> Any:
    """Глубокая МОДИФИЦИРУЕМАЯ копия замороженного значения.

    Обратна deep_freeze: ImmutableMapping -> dict, ImmutableList -> list,
    frozenset -> set. Используется для JSON-совместимой сериализации
    конфигурации (StrategyConfig.as_dict) — семантика значений
    сохраняется точно.
    """
    if isinstance(value, ImmutableMapping):
        return {key: unfreeze(item) for key, item in value.items()}
    if isinstance(value, ImmutableList):
        return [unfreeze(item) for item in value]
    if isinstance(value, frozenset):
        return {unfreeze(item) for item in value}
    return value


# ---------------------------------------------------------------------------
# Стабильный config_hash
# ---------------------------------------------------------------------------

CONFIG_HASH_ALGORITHM = "sha256"
CONFIG_HASH_VERSION = 1


def _normalize_for_json(value: Any) -> Any:
    """Рекурсивная нормализация значения к детерминированной JSON-форме.

    Правила (документированы в IMPLEMENTATION_REPORT.md, раздел config_hash):
      * Mapping -> dict со СТРОКОВЫМИ ключами; порядок ключей задаётся
        sort_keys при сериализации, поэтому исходный порядок не влияет;
      * tuple/set -> list (sorted для set — детерминизм);
      * Enum -> значение Enum;
      * bool/int/float/str/None -> как есть; float NaN/Infinity запрещены;
      * любые недетерминированные данные (время, случайные значения,
        пути файлов) в параметрах запрещены и отвергаются сериализацией.
    """
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise StrategyConfigError(
                "params содержат NaN/Infinity — в config_hash недопустимо")
        return value
    if isinstance(value, Enum):
        return _normalize_for_json(value.value)
    if isinstance(value, Mapping):
        result = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise StrategyConfigError(
                    f"ключи params должны быть строками: {key!r}")
            result[key] = _normalize_for_json(item)
        return result
    if isinstance(value, (list, tuple)):
        return [_normalize_for_json(item) for item in value]
    if isinstance(value, (set, frozenset)):
        return sorted(
            (_normalize_for_json(item) for item in value),
            key=lambda item: json.dumps(item, sort_keys=True,
                                        ensure_ascii=False, default=str),
        )
    raise StrategyConfigError(
        f"недетерминируемый тип в params: {type(value).__name__} — "
        "в config_hash допускаются только JSON-значения")


def canonical_config_payload(strategy_id: str,
                             strategy_version: str,
                             params: Mapping[str, Any]) -> str:
    """Канонический JSON-текст, из которого вычисляется config_hash.

    Состав данных хеша (точно и только это):
      * config_hash_version — версия формата хеша;
      * hash_algorithm      — имя алгоритма;
      * strategy_id         — идентификатор стратегии;
      * strategy_version    — версия стратегии;
      * params              — нормализованные параметры стратегии.

    НЕ участвуют: секреты/токены, содержимое runtime.env/.env, переменные
    окружения, пути файлов, время, случайные значения, порядок ключей JSON.
    """
    payload = {
        "config_hash_version": CONFIG_HASH_VERSION,
        "hash_algorithm": CONFIG_HASH_ALGORITHM,
        "strategy_id": str(strategy_id),
        "strategy_version": str(strategy_version),
        "params": _normalize_for_json(dict(params)),
    }
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def compute_config_hash(strategy_id: str,
                        strategy_version: str,
                        params: Mapping[str, Any]) -> str:
    """Стабильный config_hash конфигурации стратегии.

    Свойства (проверяются тестами Этапа A):
      * одинаковая конфигурация -> одинаковый hash (детерминизм);
      * изменение значимого параметра -> другой hash;
      * порядок ключей JSON не влияет на hash;
      * алгоритм и состав данных задокументированы; секреты не участвуют.
    """
    canonical = canonical_config_payload(strategy_id, strategy_version, params)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Описание и валидация параметров
# ---------------------------------------------------------------------------

class SignalDirection(str, Enum):
    """Направление входного сигнала (контракт Этапа A: только вход)."""
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


class ActivationMode(str, Enum):
    """Режим активации стратегии.

    REGRESSION_ONLY (по умолчанию)  — стратегия недоступна торговому режиму;
    TRADING_ALLOWED                 — стратегия ЯВНО объявлена активируемой.
    Fail-closed: умолчание запрещает торговлю.
    """
    TRADING_ALLOWED = "TRADING_ALLOWED"
    REGRESSION_ONLY = "REGRESSION_ONLY"


class ParamType(str, Enum):
    """Допустимые типы параметров стратегии."""
    INT = "int"        # только int (bool запрещён)
    FLOAT = "float"    # int | float (bool запрещён); NaN/Infinity запрещены
    STRING = "string"
    BOOL = "bool"


@dataclass(frozen=True)
class ParamSpec:
    """Описание одного параметра стратегии.

    minimum/maximum — структурные границы домена значения (например, RSI
    математически лежит в 0..100). Они НЕ являются новыми торговыми
    ограничениями: смысловые ограничения вводит только сама стратегия.
    """
    name: str
    param_type: ParamType
    description: str = ""
    required: bool = True
    default: Any = None
    minimum: Optional[float] = None
    maximum: Optional[float] = None
    exclusive_maximum: bool = False

    def normalize(self, value: Any) -> Any:
        """Нормализация значения к каноническому типу спецификации."""
        if self.param_type is ParamType.INT:
            if isinstance(value, bool) or not isinstance(value, int):
                raise StrategyConfigError(
                    f"{self.name}: ожидался int, получено "
                    f"{type(value).__name__}")
            return value
        if self.param_type is ParamType.FLOAT:
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise StrategyConfigError(
                    f"{self.name}: ожидалось число, получено "
                    f"{type(value).__name__}")
            result = float(value)
            if not math.isfinite(result):
                raise StrategyConfigError(
                    f"{self.name}: NaN/Infinity запрещены")
            return result
        if self.param_type is ParamType.STRING:
            if not isinstance(value, str):
                raise StrategyConfigError(
                    f"{self.name}: ожидалась строка, получено "
                    f"{type(value).__name__}")
            return value
        if self.param_type is ParamType.BOOL:
            if not isinstance(value, bool):
                raise StrategyConfigError(
                    f"{self.name}: ожидался bool, получено "
                    f"{type(value).__name__}")
            return value
        raise StrategyConfigError(
            f"{self.name}: неизвестный тип спецификации {self.param_type}")

    def check_range(self, value: Any, errors: List[str]) -> None:
        """Проверка структурных границ домена (не торговые правила)."""
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            return
        if not math.isfinite(value):
            return
        if self.minimum is not None and value < self.minimum:
            errors.append(
                f"{self.name}: значение {value} меньше минимума "
                f"{self.minimum}")
        if self.maximum is not None:
            limit = self.maximum
            if self.exclusive_maximum:
                if value >= limit:
                    errors.append(
                        f"{self.name}: значение {value} >= максимума "
                        f"{limit} (строгая граница)")
            elif value > limit:
                errors.append(
                    f"{self.name}: значение {value} больше максимума "
                    f"{limit}")


def validate_params_against_specs(specs: Sequence[ParamSpec],
                                  params: Mapping[str, Any],
                                  *,
                                  strict_unknown: bool = True) -> List[str]:
    """Общая валидация параметров по спецификациям (fail-closed).

    Проверяет: неизвестные ключи, отсутствие обязательных параметров,
    правильность типов (bool не считается int), NaN/Infinity, структурные
    границы домена. Возвращает список текстов ошибок (пустой = валидно).
    Никаких скрытых fallback-значений не подставляется.
    """
    errors: List[str] = []
    if not isinstance(params, Mapping):
        return [f"params должны быть отображением, получено "
                f"{type(params).__name__}"]
    spec_names = {spec.name for spec in specs}
    if strict_unknown:
        for name in params:
            if name not in spec_names:
                errors.append(f"неизвестный параметр: {name}")
    for spec in specs:
        if spec.name not in params:
            if spec.required:
                errors.append(f"отсутствует обязательный параметр: "
                              f"{spec.name}")
            continue
        value = params[spec.name]
        try:
            normalized = spec.normalize(value)
        except StrategyConfigError as exc:
            errors.append(str(exc))
            continue
        spec.check_range(normalized, errors)
    return errors


def normalize_params_by_specs(specs: Sequence[ParamSpec],
                              params: Mapping[str, Any]) -> dict:
    """Нормализация параметров к каноническим типам спецификаций.

    Вызывается ПОСЛЕ успешной validate_params_against_specs. Валидные
    необязательные параметры без значения получают default; отсутствия
    обязательных параметров сюда не попадают (вальидация их отвергла).
    Возвращает НОВЫЙ dict; вход не мутируется.
    """
    normalized: dict = {}
    for spec in specs:
        if spec.name in params:
            normalized[spec.name] = spec.normalize(params[spec.name])
        elif not spec.required:
            normalized[spec.name] = spec.normalize(spec.default) \
                if spec.default is not None else spec.default
    return normalized


# ---------------------------------------------------------------------------
# Конфигурация стратегии
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class StrategyConfig:
    """Неизменяемая конфигурация конкретной стратегии.

    strategy_id + config_hash однозначно идентифицируют, какая стратегия
    и какая версия конфигурации породила объект (атрибуция, attribution.py).

    Глубокая неизменяемость (Stage A.1, исправление замечания №1 аудита):
      * frozen=True защищает атрибуты верхнего уровня: strategy_id,
        strategy_version, config_hash, origin, params, metadata;
      * params и metadata — ImmutableMapping с глубокой защитой: вложенные
        отображения/списки/множества хранятся в неизменяемых структурах;
      * исходные словари копируются при создании: изменение источника
        после создания конфигурации НЕ меняет её содержимое;
      * config_hash соответствует ФАКТИЧЕСКИ сохранённым параметрам —
        проверяется методом recompute_config_hash().
    """
    strategy_id: str
    strategy_version: str
    params: Mapping[str, Any]
    config_hash: str
    origin: str = "engine"            # "engine" | "regression_harness"
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # 1. Валидация идентификационных полей (fail-closed, без умолчаний)
        for field_name in ("strategy_id", "strategy_version",
                           "config_hash", "origin"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value:
                raise StrategyConfigError(
                    f"StrategyConfig.{field_name} должен быть непустой "
                    "строкой")
        if not isinstance(self.params, Mapping):
            raise StrategyConfigError(
                "StrategyConfig.params должен быть отображением (Mapping), "
                f"получено {type(self.params).__name__}")
        if not isinstance(self.metadata, Mapping):
            raise StrategyConfigError(
                "StrategyConfig.metadata должен быть отображением "
                f"(Mapping), получено {type(self.metadata).__name__}")
        # 2. Глубокая заморозка + глубокая копия (замечание №1 аудита):
        #    источники НЕ сохраняются; изменение исходных словарей после
        #    создания конфигурации не влияет на её содержимое.
        object.__setattr__(self, "params", ImmutableMapping(self.params))
        object.__setattr__(self, "metadata",
                           ImmutableMapping(self.metadata))

    def attribution_dict(self) -> dict:
        """Пара атрибуции (strategy_id, config_hash) для новых объектов."""
        return {
            "strategy_id": self.strategy_id,
            "config_hash": self.config_hash,
        }

    def recompute_config_hash(self) -> str:
        """config_hash, вычисленный по ФАКТИЧЕСКИ сохранённым параметрам.

        Расхождение с полем config_hash означает, что объект создан с
        некорректной идентификацией (обнаруживается тестами Stage A.1);
        для конфигураций, построенных через Strategy.get_config /
        build_regression_config, значения совпадают всегда.
        """
        return compute_config_hash(self.strategy_id, self.strategy_version,
                                   self.params)

    def as_dict(self) -> dict:
        """Глубокая МОДИФИЦИРУЕМАЯ, JSON-СОВМЕСТИМАЯ копия конфигурации.

        Совместимость с JSON-сериализацией (Stage A.1): результат — обычные
        dict/list с теми же значениями; множества представляются
        ОТСОРТИРОВАННЫМИ списками — та же нормализация, что и в расчёте
        config_hash (_normalize_for_json), поэтому JSON round-trip
        (as_dict -> json.dumps -> json.loads -> новая StrategyConfig)
        сохраняет и семантику значений, и config_hash.
        Точная (нежелезно-JSON'ная) модифицируемая копия params/metadata —
        через config.params.to_mutable() / config.metadata.to_mutable().
        """
        return {
            "strategy_id": self.strategy_id,
            "strategy_version": self.strategy_version,
            "params": _normalize_for_json(self.params.to_mutable()),
            "config_hash": self.config_hash,
            "origin": self.origin,
            "metadata": _normalize_for_json(self.metadata.to_mutable()),
        }


# ---------------------------------------------------------------------------
# Входной сигнал (контракт входа; выход — Этап C, здесь НЕ реализуется)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class EntrySignalInput:
    """Входные данные для вычисления входного сигнала.

    candles — pandas.DataFrame со свечами (open/high/low/close/volume,
    DatetimeIndex). Готовность данных (достаточность истории) — это
    ОТДЕЛЬНОЕ понятие, не валидность конфигурации: недостаток свечей
    стратегия обрабатывает как HOLD/неготовность, а не как ошибку конфига.
    """
    figi: str
    ticker: str
    candles: Any                      # pandas.DataFrame (тип не навязывается)
    last_price: float
    drop_incomplete: bool = False
    extra: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Глубокая неизменяемость (та же природа замечания №1 аудита):
        # extra копируется и замораживается; None -> пустое отображение
        # (совместимо с прежним поведением, при котором None не читался).
        if self.extra is None:
            object.__setattr__(self, "extra", ImmutableMapping())
        else:
            if not isinstance(self.extra, Mapping):
                raise StrategyConfigError(
                    "EntrySignalInput.extra должен быть отображением "
                    f"(Mapping), получено {type(self.extra).__name__}")
            object.__setattr__(self, "extra", ImmutableMapping(self.extra))


@dataclass(frozen=True)
class Signal:
    """Результат вычисления сигнала стратегии.

    Атрибуция: strategy_id + config_hash присутствуют в самом сигнале —
    любой потребитель может установить источник решения.
    """
    strategy_id: str
    config_hash: str
    direction: SignalDirection
    reason: str
    figi: str = ""
    ticker: str = ""
    candle_time: Optional[str] = None
    decided_at: Optional[str] = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Глубокая неизменяемость (та же природа замечания №1 аудита):
        # metadata копируется и замораживается; None -> пустое отображение
        # (совместимо с прежним поведением, при котором None не читался).
        if self.metadata is None:
            object.__setattr__(self, "metadata", ImmutableMapping())
        else:
            if not isinstance(self.metadata, Mapping):
                raise StrategyConfigError(
                    "Signal.metadata должен быть отображением (Mapping), "
                    f"получено {type(self.metadata).__name__}")
            object.__setattr__(self, "metadata",
                               ImmutableMapping(self.metadata))


# ---------------------------------------------------------------------------
# Абстрактный контракт стратегии
# ---------------------------------------------------------------------------

class Strategy:
    """Абстрактный контракт стратегии нового движка.

    Реализации обязаны:
      * объявить уникальный strategy_id и strategy_version;
      * описать параметры (param_specs) и их валидацию (validate_params);
      * реализовать evaluate_entry (входной сигнал).
    Реализации НЕ обязаны и НЕ должны здесь: изоляция состояния
    (strategy_id, FIGI) — Этап B; выход/evaluate_exit — Этап C; риск —
    Этап D.

    activation_mode по умолчанию REGRESSION_ONLY: торговля возможна только
    при ЯВном TRADING_ALLOWED (fail-closed по умолчанию).
    """

    strategy_id: str = ""
    strategy_version: str = ""
    description: str = ""
    activation_mode: ActivationMode = ActivationMode.REGRESSION_ONLY

    # --- идентификация ----------------------------------------------------

    def param_specs(self) -> Tuple[ParamSpec, ...]:
        """Описание параметров стратегии (структура и домены)."""
        raise NotImplementedError

    # --- валидация и нормализация параметров ------------------------------

    def validate_params(self, params: Mapping[str, Any]) -> List[str]:
        """Список ошибок параметров (пустой список = валидно).

        Реализации могут добавлять смысловые проверки СВОЕЙ семантики
        (например, инвертированные RSI-пороги) поверх общей проверки.
        """
        return validate_params_against_specs(self.param_specs(), params)

    def normalize_params(self, params: Mapping[str, Any]) -> dict:
        """Нормализация параметров к каноническим типам (для config_hash)."""
        return normalize_params_by_specs(self.param_specs(), params)

    def default_params(self) -> Mapping[str, Any]:
        """Параметры по умолчанию, если стратегия их объявляет.

        Умолчания ДОЛЖНЫ быть явными значениями стратегии, а не скрытым
        fallback. Стратегии без допустимых умолчаний (в том числе
        regression-only) обязаны переопределить метод и отказаться от
        автоподстановки.
        """
        raise StrategyContractError(
            f"{self.strategy_id}: параметры по умолчанию не объявлены; "
            "скрытая автоподстановка запрещена (no silent defaults)")

    # --- конфигурация и config_hash ----------------------------------------

    def get_config(self,
                   params: Mapping[str, Any],
                   *,
                   origin: str = "engine",
                   metadata: Optional[Mapping[str, Any]] = None
                   ) -> StrategyConfig:
        """Валидирует параметры и возвращает StrategyConfig с config_hash.

        Ошибка валидации -> StrategyConfigError (fail-closed, без fallback).
        """
        errors = self.validate_params(params)
        if errors:
            raise StrategyConfigError(
                f"{self.strategy_id}: конфигурация невалидна: "
                + "; ".join(errors))
        normalized = self.normalize_params(params)
        config_hash = compute_config_hash(
            self.strategy_id, self.strategy_version, normalized)
        return StrategyConfig(
            strategy_id=self.strategy_id,
            strategy_version=self.strategy_version,
            params=normalized,
            config_hash=config_hash,
            origin=origin,
            metadata=dict(metadata or {}),
        )

    # --- входной сигнал -----------------------------------------------------

    def evaluate_entry(self,
                       signal_input: EntrySignalInput,
                       config: StrategyConfig) -> Signal:
        """Вычисляет входной сигнал по контракту EntrySignalInput -> Signal.

        Выход из позиции (evaluate_exit) — контракт Этапа C и здесь
        сознательно отсутствует.
        """
        raise NotImplementedError
