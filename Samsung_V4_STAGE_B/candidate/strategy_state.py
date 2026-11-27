# strategy_state.py — SAMSUNG V4 — NEW STRATEGY ENGINE. STAGE B.
#
# ИЗОЛИРОВАННОЕ СОСТОЯНИЕ СТРАТЕГИИ ПО КЛЮЧУ (strategy_id, FIGI).
#
# Назначение (ТЗ Stage B §2):
#   * состояние стратегии A не влияет на стратегию B;
#   * состояние инструмента X не влияет на инструмент Y;
#   * параллельная обработка не приводит к перекрёстному изменению состояния;
#   * изменение состояния одной пары (strategy_id, FIGI) не меняет другие;
#   * после перезапуска состояние восстанавливается из сохранённых данных;
#   * некорректное/несовместимое состояние НЕ приводит к незаметному
#     продолжению работы с неверными данными (fail-closed).
#
# Состав модуля (ТЗ Stage B §3):
#   * StrategyState         — типизированная неизменяемая модель состояния,
#                             привязанная к (strategy_id, FIGI, config_hash)
#                             и к версии схемы состояния;
#   * StateStore            — хранилище состояния: изоляция по ключу,
#                             детерминированная сериализация, атомарная
#                             запись, проверка схемы и ключей, обнаружение
#                             повреждённых записей, контролируемая ошибка
#                             при несовпадении config_hash (без автоматиче-
#                             ского переноса старого состояния);
#   * StrategyStateManager  — менеджер, выдающий стратегии ТОЛЬКО её
#                             собственное состояние; создаёт независимое
#                             состояние при отсутствии записи; не использует
#                             глобальный mutable context; корректен при
#                             параллельных обращениях;
#   * resolve_state_store_path — ЯВНОЕ разрешение пути persistent-хранилища
#                             из переданной конфигурации; скрытого пути по
#                             умолчанию НЕ существует (fail-closed).
#
# Интеграция с контрактом Stage A (ТЗ Stage B §3.4):
#   * StrategyConfig принимается ТОЛЬКО точного типа
#     (type(config) is StrategyConfig — решение Stage A.2.1 задокументировано
#     в attribution.py и сохраняется здесь);
#   * config_hash проверяется validate_config_hash_format (Stage A.2);
#   * AttributionContext принимается ТОЛЬКО проверенный (через
#     attribution._resolve_context — тот же вход проверки маркера
#     проверенного создания, что и для factory/stamp/CSV/JSONL; это
#     УСИЛЕНИЕ проверки, а не обход);
#   * ActivationMode и торговая логика здесь НЕ используются и не меняются;
#     legacy_samsung_v4 остаётся REGRESSION_ONLY.
#
# Ограничения Stage B (ТЗ §5) соблюдены: торговая логика, параметры,
# сигналы, риск-менеджмент, исполнение ордеров не затронуты; evaluate_exit
# (Stage C) не реализован; симулятор/Sandbox adapter не реализованы;
# подключения к брокеру и заявки отсутствуют; FORCE_TRADE не добавлен;
# старые файлы Samsung (state.json и др.) не читаются и не записываются.
#
# Режим: OFFLINE / READ ONLY DATA / RESEARCH ONLY / NO LIVE ORDERS.

from __future__ import annotations

import json
import os
import re
import tempfile
import threading
from dataclasses import dataclass, field, replace as _dataclass_replace
from datetime import datetime, timezone
from typing import Any, Callable, List, Mapping, Optional, Tuple

from strategy_api import (
    ImmutableMapping,
    StrategyConfig,
    unfreeze,
    validate_config_hash_format,
)

# ---------------------------------------------------------------------------
# Ошибки (fail-closed; ни одна ситуация не маскируется пустым состоянием)
# ---------------------------------------------------------------------------


class StrategyStateError(Exception):
    """Базовая ошибка подсистемы состояния стратегии (Stage B)."""


class StateValidationError(StrategyStateError):
    """Семантически невалидные данные состояния/ключей/config_hash."""


class StateSchemaError(StrategyStateError):
    """Неизвестная версия схемы состояния (требуется явное решение)."""


class StateCorruptionError(StrategyStateError):
    """Повреждённая запись состояния (структура/типы/JSON).

    Повреждённые данные НЕ подменяются пустым состоянием незаметно:
    ошибка пробрасывается вызывающему коду (fail-closed).
    """


class StateConfigMismatchError(StrategyStateError):
    """Несовпадение config_hash сохранённого состояния и ожидаемого.

    Старое состояние НЕ переносится автоматически на новую конфигурацию:
    требуется ЯВНОЕ решение владельца (reset_state либо отдельная
    совместимая обработка). Автоматический сброс запрещён.
    """


class StateAlreadyExistsError(StrategyStateError):
    """Создание состояния для уже существующей пары (strategy_id, FIGI)."""


class StateNotFoundError(StrategyStateError):
    """save_state для отсутствующей записи: создание — только create_state."""


class StateStoreConfigError(StrategyStateError):
    """Конфигурация хранилища отсутствует/невалидна.

    Отсутствие обязательной явной конфигурации persistent-хранилища
    НЕ приводит к скрытому переходу на другой путь (fail-closed).
    """


# ---------------------------------------------------------------------------
# Схема состояния и проверка ключей
# ---------------------------------------------------------------------------

# Версия схемы состояния. При несовместимых изменениях структуры payload
# версия увеличивается; старые записи читаются только при ЯВНОЙ реализации
# совместимости (автоматической миграции нет).
STATE_SCHEMA_VERSION = 1

# Ключ конфигурации, из которого resolve_state_store_path берёт путь
# persistent-хранилища. Единственный способ включить persistent-режим —
# ЯВНО задать этот ключ в переданной конфигурации (в engine.json он может
# быть добавлен владельцем на этапе интеграции Stage C; здесь engine.json
# сознательно не изменяется — Stage B не трогает конфигурацию Stage A).
STATE_STORE_CONFIG_KEY = "STATE_STORE_PATH"

# Допустимое содержимое strategy_id и FIGI. Оба значения попадают в имена
# файлов persistent-хранилища, поэтому набор символов ограничен безопасным
# подмножеством ASCII: буквы/цифры/точка/подчёркивание/дефис, первый
# символ — буква или цифра. Это исключает разделители пути ('/', '\\'),
# нулевой байт, '..', ведущие точки и любые управляющие символы.
_KEY_PART_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")

_MAX_STRATEGY_ID_LEN = 128
_MAX_FIGI_LEN = 64


def validate_strategy_id(strategy_id: Any) -> str:
    """Проверяет strategy_id как ключ состояния (fail-closed).

    Пустые значения, не-строки, разделители пути, управляющие символы,
    '..' и превышение длины отклоняются StateValidationError.
    """
    if not isinstance(strategy_id, str) or not strategy_id:
        raise StateValidationError(
            "strategy_id состояния должен быть непустой строкой; получено "
            f"{type(strategy_id).__name__}")
    if len(strategy_id) > _MAX_STRATEGY_ID_LEN:
        raise StateValidationError(
            "strategy_id состояния слишком длинный "
            f"({len(strategy_id)} > {_MAX_STRATEGY_ID_LEN})")
    if not _KEY_PART_RE.match(strategy_id):
        raise StateValidationError(
            "strategy_id состояния содержит недопустимые символы: "
            f"{strategy_id!r}; допустимы ASCII-буквы/цифры/точка/"
            "подчёркивание/дефис, первый символ — буква или цифра "
            "(защита от обхода изоляции через путь/имя файла)")
    return strategy_id


def validate_figi(figi: Any) -> str:
    """Проверяет FIGI как ключ состояния (fail-closed).

    Требования те же, что и к strategy_id: непустая строка безопасного
    набора символов; разделители пути и управляющие символы отклоняются.
    """
    if not isinstance(figi, str) or not figi:
        raise StateValidationError(
            "figi состояния должен быть непустой строкой; получено "
            f"{type(figi).__name__}")
    if len(figi) > _MAX_FIGI_LEN:
        raise StateValidationError(
            f"figi состояния слишком длинный ({len(figi)} > {_MAX_FIGI_LEN})")
    if not _KEY_PART_RE.match(figi):
        raise StateValidationError(
            "figi состояния содержит недопустимые символы: "
            f"{figi!r}; допустимы ASCII-буквы/цифры/точка/подчёркивание/"
            "дефис, первый символ — буква или цифра (защита от обхода "
            "изоляции через путь/имя файла)")
    return figi


def _validate_config_hash_of_state(config_hash: Any) -> str:
    """Проверка config_hash состояния форматом Stage A.2 (SHA-256, 64 hex)."""
    if not isinstance(config_hash, str) or not config_hash:
        raise StateValidationError(
            "config_hash состояния должен быть непустой строкой; получено "
            f"{type(config_hash).__name__}")
    try:
        return validate_config_hash_format(config_hash)
    except Exception as exc:  # StrategyContractError и подклассы
        raise StateValidationError(
            "config_hash состояния не соответствует формату SHA-256 "
            f"hexdigest: {exc}") from exc


# ---------------------------------------------------------------------------
# Детерминированная сериализация и проверка данных состояния
# ---------------------------------------------------------------------------


def _canonical_json(payload: Mapping[str, Any]) -> str:
    """Канонический JSON: отсортированные ключи, без пробелов, UTF-8.

    Одна и та же логическая запись всегда даёт побайтово одинаковую
    строку (детерминированная сериализация, ТЗ Stage B §4.6).
    """
    return json.dumps(payload, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False)


def _validate_state_value(value: Any, *, _path: str = "data") -> Any:
    """Рекурсивная проверка данных состояния на JSON-совместимость.

    Допустимы: None, bool, int, конечный float, str, отображения со
    строковыми ключами, списки/кортежи, множества (set/frozenset —
    нормализуются в ОТСОРТИРОВАННЫЙ список для детерминизма).
    NaN/Infinity отклоняются (та же политика, что и в config_hash
    Stage A.2); прочие объекты отклоняются StateValidationError.

    Возвращает нормализованное (чисто JSON-типовое) значение.
    """
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            raise StateValidationError(
                f"{_path}: NaN/Infinity в данных состояния недопустимы "
                "(та же политика fail-closed, что и для config_hash; "
                "такие значения не сериализуются детерминированно)")
        return value
    if isinstance(value, str):
        return value
    if isinstance(value, Mapping):
        result: dict = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise StateValidationError(
                    f"{_path}: ключи данных состояния должны быть "
                    f"строками; получен ключ {key!r} "
                    f"({type(key).__name__})")
            result[key] = _validate_state_value(
                item, _path=f"{_path}.{key}")
        return result
    if isinstance(value, (list, tuple)):
        return [
            _validate_state_value(item, _path=f"{_path}[{i}]")
            for i, item in enumerate(value)
        ]
    if isinstance(value, (set, frozenset)):
        # Множества не являются JSON-типом: нормализуем в отсортированный
        # список (детерминированный порядок), элементы — только JSON-скаляры.
        items = [
            _validate_state_value(item, _path=f"{_path}{{set}}")
            for item in value
        ]
        items.sort(key=lambda item: _canonical_json(
            {"v": item}))
        return items
    raise StateValidationError(
        f"{_path}: данные состояния должны быть JSON-совместимыми "
        f"(None/bool/int/float/str/Mapping/Sequence); получено "
        f"{type(value).__name__}; произвольные объекты и Enum отклоняются "
        "(состояние сериализуется детерминированно и восстанавливается "
        "после перезапуска)")


def _normalize_state_data(data: Any) -> dict:
    """Проверка и нормализация данных состояния ПОЛНОСТЬЮ до заморозки.

    Верхний уровень — обязательно отображение; значения — только
    JSON-совместимые (см. _validate_state_value). Проверка выполняется
    ДО построения ImmutableMapping, чтобы ВСЕ проблемы данных состояния
    давали единообразную StateValidationError (а не внутреннюю ошибку
    ImmutableMapping) и ни одно значение не отбрасывалось молча.
    """
    if not isinstance(data, Mapping):
        raise StateValidationError(
            "data состояния должен быть отображением (Mapping); "
            f"получено {type(data).__name__}")
    source = unfreeze(data) if isinstance(data, ImmutableMapping) else data
    normalized = _validate_state_value(source, _path="data")
    if not isinstance(normalized, dict):
        raise StateValidationError(
            "data состояния после нормализации должен быть отображением")
    return normalized


def _utc_now_iso() -> str:
    """Текущее время UTC в фиксированном формате ISO-8601."""
    return datetime.now(timezone.utc).isoformat(
        timespec="microseconds").replace("+00:00", "Z")


def _validate_timestamp(value: Any, field_name: str) -> str:
    """Проверка метки времени состояния (непустая строка ISO-8601 UTC)."""
    if not isinstance(value, str) or not value:
        raise StateValidationError(
            f"{field_name} состояния должен быть непустой строкой "
            f"ISO-8601; получено {type(value).__name__}")
    text = value
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise StateValidationError(
            f"{field_name} состояния не читается как ISO-8601: "
            f"{value!r}") from exc
    if parsed.tzinfo is None:
        raise StateValidationError(
            f"{field_name} состояния должен содержать часовой пояс (UTC): "
            f"{value!r}")
    return value


# ---------------------------------------------------------------------------
# Модель состояния стратегии
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class StrategyState:
    """Неизменяемое состояние одной пары (strategy_id, FIGI).

    Гарантии (ТЗ Stage B §3.1):
      * привязка к strategy_id, FIGI и config_hash — состояние
        однозначно связано с конфигурацией, для которой оно создано;
        несоответствие обнаруживается хранилищем/менеджером и не
        преодолевается автоматически (StateConfigMismatchError);
      * версия схемы состояния (schema_version) входит в payload и
        проверяется при десериализации (неизвестная версия —
        StateSchemaError, требуется явное решение);
      * типизированные данные: data — глубоко неизменяемое
        ImmutableMapping поверх проверенных JSON-совместимых значений;
        изменяемые объекты не сохраняются и наружу не выдаются;
      * контролируемая сериализация/десериализация: to_payload/to_json
        детерминированы; from_payload проверяет ВСЁ (структуру, типы,
        схему, ключи, формат config_hash, метки времени);
      * отсутствие общих изменяемых объектов между разными ключами:
        объекты состояния никогда не переиспользуются между ключами;
        data копируется глубоко при создании (изменение источника после
        создания не влияет на содержимое состояния).

    Неизменяемость: frozen dataclass + ImmutableMapping (та же природа
    защиты, что у StrategyConfig Stage A.1); setattr/delattr отклоняются.
    """

    strategy_id: str
    figi: str
    config_hash: str
    schema_version: int
    data: ImmutableMapping = field(default_factory=ImmutableMapping)
    created_at: str = ""
    updated_at: str = ""

    def __post_init__(self) -> None:
        # 1. Ключи: безопасный набор символов (изоляция, имена файлов).
        validate_strategy_id(self.strategy_id)
        validate_figi(self.figi)
        # 2. config_hash: формат Stage A.2.
        _validate_config_hash_of_state(self.config_hash)
        # 3. Версия схемы: новые объекты создаются ТОЛЬКО текущей версии.
        #    (Чтение записей других версий идёт через from_payload, где
        #    несовместимая версия даёт StateSchemaError ДО создания объекта.)
        if isinstance(self.schema_version, bool) or \
                not isinstance(self.schema_version, int):
            raise StateValidationError(
                "schema_version состояния должен быть целым числом; "
                f"получено {type(self.schema_version).__name__}")
        if self.schema_version != STATE_SCHEMA_VERSION:
            raise StateSchemaError(
                f"schema_version состояния {self.schema_version!r} не "
                f"совпадает с текущей схемой {STATE_SCHEMA_VERSION}; "
                "объект состояния текущей версии не создаётся (fail-closed)")
        # 4. Данные: верхний уровень — ОБЯЗАТЕЛЬНО отображение (типизированная
        #    структура состояния); JSON-совместимость + глубокая копия +
        #    глубокая заморозка. Невалидный верхний уровень отклоняется —
        #    ничего не отбрасывается молча.
        object.__setattr__(self, "data",
                           ImmutableMapping(_normalize_state_data(self.data)))
        # 5. Метки времени: непустые, ISO-8601, с часовым поясом.
        _validate_timestamp(self.created_at, "created_at")
        _validate_timestamp(self.updated_at, "updated_at")

    # --- фабрики ------------------------------------------------------------

    @classmethod
    def create(cls,
               strategy_id: Any,
               figi: Any,
               config_hash: Any,
               data: Optional[Mapping[str, Any]] = None,
               *,
               now: Optional[str] = None) -> "StrategyState":
        """Новое состояние для пары (strategy_id, figi) и конфигурации.

        data — стартовые данные (None -> пустое состояние); источник
        копируется глубоко. now — явно передаваемая метка времени
        (детерминизм в тестах); по умолчанию — текущее время UTC.
        """
        stamp = _validate_timestamp(now, "now") if now is not None \
            else _utc_now_iso()
        return cls(
            strategy_id=strategy_id,
            figi=figi,
            config_hash=config_hash,
            schema_version=STATE_SCHEMA_VERSION,
            data=ImmutableMapping(
                _normalize_state_data(data if data is not None else {})),
            created_at=stamp,
            updated_at=stamp,
        )

    def with_data(self,
                  new_data: Mapping[str, Any],
                  *,
                  now: Optional[str] = None) -> "StrategyState":
        """НОВОЕ состояние с заменёнными данными (прежнее не меняется).

        created_at сохраняется (история создания); updated_at — метка
        обновления (now или текущее время UTC). Возвращается независимый
        объект: изменение исходного состояния и источника new_data после
        вызова не влияет на результат.
        """
        stamp = _validate_timestamp(now, "now") if now is not None \
            else _utc_now_iso()
        return _dataclass_replace(
            self,
            data=ImmutableMapping(_normalize_state_data(new_data or {})),
            updated_at=stamp,
        )

    # --- сериализация ---------------------------------------------------------

    def to_payload(self) -> dict:
        """Модифицируемая JSON-совместимая копия состояния (для хранения).

        Порядок ключей фиксирован структурой словаря; побайтовая
        детерминированность обеспечивается to_json/_canonical_json.
        """
        return {
            "schema_version": self.schema_version,
            "strategy_id": self.strategy_id,
            "figi": self.figi,
            "config_hash": self.config_hash,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "data": _validate_state_value(unfreeze(self.data), _path="data"),
        }

    def to_json(self) -> str:
        """Детерминированная каноническая JSON-строка состояния."""
        return _canonical_json(self.to_payload())

    @classmethod
    def from_payload(cls, payload: Any) -> "StrategyState":
        """Контролируемая десериализация записи состояния.

        Ошибки классифицированы (fail-closed, без маскировки):
          * не-отображение / отсутствующие поля / неверные ТИПЫ полей —
            StateCorruptionError (запись повреждена; НЕ подменяется
            пустым состоянием);
          * неизвестная версия схемы — StateSchemaError (требуется явное
            решение о совместимости/сбросе);
          * семантически невалидные значения (набор символов ключей,
            формат config_hash, метки времени, данные) —
            StateValidationError.
        """
        if not isinstance(payload, Mapping):
            raise StateCorruptionError(
                "запись состояния должна быть JSON-объектом; получено "
                f"{type(payload).__name__}")
        required = ("schema_version", "strategy_id", "figi", "config_hash",
                    "created_at", "updated_at", "data")
        missing = [key for key in required if key not in payload]
        if missing:
            raise StateCorruptionError(
                "запись состояния повреждена: отсутствуют обязательные "
                f"поля {sorted(missing)}; пустым состоянием не "
                "подменяется (fail-closed)")

        schema_version = payload["schema_version"]
        if isinstance(schema_version, bool) or \
                not isinstance(schema_version, int):
            raise StateCorruptionError(
                "запись состояния повреждена: schema_version должен быть "
                f"целым числом; получено {type(schema_version).__name__}")
        if schema_version != STATE_SCHEMA_VERSION:
            raise StateSchemaError(
                f"неизвестная версия схемы состояния {schema_version!r} "
                f"(текущая: {STATE_SCHEMA_VERSION}); запись не читается и "
                "не заменяется пустым состоянием: требуется ЯВНОЕ решение "
                "о совместимости или сбросе (fail-closed)")

        strategy_id = payload["strategy_id"]
        if not isinstance(strategy_id, str):
            raise StateCorruptionError(
                "запись состояния повреждена: strategy_id должен быть "
                f"строкой; получено {type(strategy_id).__name__}")
        figi = payload["figi"]
        if not isinstance(figi, str):
            raise StateCorruptionError(
                "запись состояния повреждена: figi должен быть строкой; "
                f"получено {type(figi).__name__}")
        config_hash = payload["config_hash"]
        if not isinstance(config_hash, str):
            raise StateCorruptionError(
                "запись состояния повреждена: config_hash должен быть "
                f"строкой; получено {type(config_hash).__name__}")
        created_at = payload["created_at"]
        updated_at = payload["updated_at"]
        if not isinstance(created_at, str):
            raise StateCorruptionError(
                "запись состояния повреждена: created_at должен быть "
                f"строкой; получено {type(created_at).__name__}")
        if not isinstance(updated_at, str):
            raise StateCorruptionError(
                "запись состояния повреждена: updated_at должен быть "
                f"строкой; получено {type(updated_at).__name__}")
        data = payload["data"]
        if not isinstance(data, Mapping):
            raise StateCorruptionError(
                "запись состояния повреждена: data должен быть "
                f"JSON-объектом; получено {type(data).__name__}")

        return cls(
            strategy_id=strategy_id,
            figi=figi,
            config_hash=config_hash,
            schema_version=schema_version,
            data=ImmutableMapping(data),
            created_at=created_at,
            updated_at=updated_at,
        )

    def key(self) -> Tuple[str, str]:
        """Ключ изоляции состояния (strategy_id, figi)."""
        return (self.strategy_id, self.figi)


# ---------------------------------------------------------------------------
# Хранилище состояния
# ---------------------------------------------------------------------------


class StateStore:
    """Хранилище состояний по ключу (strategy_id, FIGI).

    Режимы (ТЗ Stage B §3.2):
      * persistent — ЯВНО переданный path (каталог): по одной JSON-записи
        на ключ, атомарная запись (tmp + os.replace + fsync), детермини-
        рованное содержимое (_canonical_json от payload состояния);
      * memory — path не передан (path=None): записи живут в памяти
        процесса. Скрытого пути по умолчанию НЕ существует: включить
        persistent-режим без явного пути невозможно; путь из конфигурации
        разрешается resolve_state_store_path (без fallback на другой путь).

    Гарантии:
      * изоляция по ключу: каждой паре соответствует отдельная запись
        (отдельный файл); запись одной пары не касается других;
      * наружу НЕ выдаются внутренние изменяемые ссылки: состояния
        неизменяемы (frozen + ImmutableMapping), источники копируются;
      * детерминированное сохранение: одинаковое содержимое -> одинаковые
        байты (sort_keys, без пробелов, allow_nan=False);
      * проверка версии схемы и соответствия strategy_id/FIGI/config_hash
        при каждом чтении; повреждённые записи обнаруживаются и дают
        StateCorruptionError/StateSchemaError — НЕ подменяются пустым
        состоянием;
      * несовпадение config_hash — StateConfigMismatchError: старое
        состояние НЕ переносится на новую конфигурацию автоматически,
        требуется ЯВНОЕ решение (reset_state);
      * корректность при параллельных обращениях: все операции под
        RLock хранилища; составные операции менеджера — под его RLock
        плюс контроль существования записи.
    """

    def __init__(self, *, path: Optional[str] = None) -> None:
        self._lock = threading.RLock()
        if path is None:
            # Memory-режим: явный и документированный; используется
            # тестами и процессами без persistent-истории. Скрытого
            # файлового пути нет.
            self._path: Optional[str] = None
            self._records: dict = {}
            return
        if not isinstance(path, str) or not path.strip():
            raise StateStoreConfigError(
                "path persistent-хранилища состояния должен быть непустой "
                f"строкой; получено {type(path).__name__}")
        self._path = path
        os.makedirs(self._path, exist_ok=True)

    # --- свойства -----------------------------------------------------------

    @property
    def mode(self) -> str:
        """Режим хранилища: 'persistent' или 'memory'."""
        return "persistent" if self._path is not None else "memory"

    @property
    def path(self) -> Optional[str]:
        """Явно переданный путь persistent-хранилища (memory -> None)."""
        return self._path

    # --- внутренние операции --------------------------------------------------

    @staticmethod
    def _filename(strategy_id: str, figi: str) -> str:
        """Имя файла записи: безопасный набор символов проверен ключами."""
        return f"{strategy_id}__{figi}.json"

    def _load(self, strategy_id: str, figi: str) -> Optional[StrategyState]:
        """Чтение одной записи с ПОЛНОЙ проверкой (fail-closed).

        Отсутствие записи — None (нормальная ситуация, обрабатывается
        вызывающим кодом); повреждённая запись — StateCorruptionError /
        StateSchemaError / StateValidationError (НЕ подменяется пустым
        состоянием).
        """
        if self._path is None:
            return self._records.get((strategy_id, figi))
        file_path = os.path.join(self._path,
                                 self._filename(strategy_id, figi))
        if not os.path.isfile(file_path):
            return None
        try:
            with open(file_path, "r", encoding="utf-8") as handle:
                raw = handle.read()
        except OSError as exc:
            raise StateCorruptionError(
                f"запись состояния {strategy_id!r}/{figi!r} не читается "
                f"({file_path}): {exc}") from exc
        try:
            payload = json.loads(raw)
        except (ValueError, TypeError) as exc:
            raise StateCorruptionError(
                f"запись состояния {strategy_id!r}/{figi!r} повреждена "
                f"(не читается как JSON: {exc}); пустым состоянием не "
                "подменяется (fail-closed)") from exc
        try:
            return StrategyState.from_payload(payload)
        except StrategyStateError as exc:
            raise type(exc)(
                f"запись состояния {strategy_id!r}/{figi!r} "
                f"({file_path}): {exc}") from exc

    def _persist(self, state: StrategyState) -> None:
        """Детерминированная атомарная запись одной записи состояния."""
        payload_text = state.to_json()
        if self._path is None:
            self._records[(state.strategy_id, state.figi)] = state
            return
        os.makedirs(self._path, exist_ok=True)
        final_path = os.path.join(
            self._path,
            self._filename(state.strategy_id, state.figi))
        fd, tmp_path = tempfile.mkstemp(
            dir=self._path, prefix=".tmp-state-", suffix=".json")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(payload_text)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_path, final_path)
        except Exception:
            try:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
            except OSError:
                pass
            raise
        try:
            dir_fd = os.open(self._path, os.O_RDONLY)
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
        except OSError:
            # fsync каталога может быть не поддержан файловой системой:
            # атомарность самой записи уже обеспечена os.replace.
            pass

    # --- публичный интерфейс (ТЗ Stage B §3.2) --------------------------------

    def get_state(self,
                  strategy_id: Any,
                  figi: Any,
                  *,
                  config_hash: Any = None) -> Optional[StrategyState]:
        """Состояние пары (strategy_id, figi) или None, если записи нет.

        config_hash (опционально) — ожидаемый hash подтверждённой
        конфигурации: при передаче несовпадающего значения —
        StateConfigMismatchError (контролируемая ошибка; старое состояние
        НЕ переносится на новую конфигурацию автоматически, требуется
        ЯВНОЕ решение о сбросе). Без config_hash возвращается состояние
        как есть (со своим config_hash в поле).
        """
        validate_strategy_id(strategy_id)
        validate_figi(figi)
        if config_hash is not None:
            _validate_config_hash_of_state(config_hash)
        with self._lock:
            state = self._load(strategy_id, figi)
        if state is None:
            return None
        if config_hash is not None and state.config_hash != config_hash:
            raise StateConfigMismatchError(
                f"config_hash сохранённого состояния ({state.config_hash!r}) "
                f"не совпадает с ожидаемым ({config_hash!r}) для пары "
                f"({strategy_id!r}, {figi!r}); старое состояние НЕ переносится "
                "на новую конфигурацию автоматически: требуется ЯВНОЕ "
                "решение — reset_state или отдельная совместимая обработка "
                "(fail-closed, Stage B)")
        return state

    def create_state(self,
                     strategy_id: Any,
                     figi: Any,
                     config_hash: Any,
                     data: Optional[Mapping[str, Any]] = None,
                     *,
                     now: Optional[str] = None) -> StrategyState:
        """Создание НЕЗАВИСИМОГО состояния для отсутствующей пары.

        Существующая запись -> StateAlreadyExistsError (без перезаписи,
        без скрытого сброса). Существование проверяется ПОД замком.
        """
        validate_strategy_id(strategy_id)
        validate_figi(figi)
        _validate_config_hash_of_state(config_hash)
        with self._lock:
            existing = self._load(strategy_id, figi)
            if existing is not None:
                raise StateAlreadyExistsError(
                    f"состояние пары ({strategy_id!r}, {figi!r}) уже "
                    f"существует (config_hash={existing.config_hash!r}); "
                    "перезапись и скрытый сброс запрещены: используйте "
                    "save_state для обновления или reset_state для ЯВНОГО "
                    "сброса (fail-closed)")
            state = StrategyState.create(
                strategy_id, figi, config_hash, data, now=now)
            self._persist(state)
            return state

    def save_state(self,
                   strategy_id: Any,
                   figi: Any,
                   state: Any) -> None:
        """Сохранение изменений состояния СУЩЕСТВУЮЩЕЙ пары.

        Проверяется: точный тип StrategyState, соответствие ключей
        записи и аргументов, совпадение config_hash с сохранённой
        записью (несовпадение — StateConfigMismatchError: сохранение не
        переносит состояние на другую конфигурацию скрыто; создание —
        только create_state: запись отсутствует -> StateNotFoundError).
        """
        validate_strategy_id(strategy_id)
        validate_figi(figi)
        if type(state) is not StrategyState:
            # Точный тип — то же решение, что и Stage A.2.1 для
            # StrategyConfig: подкласс не может ослабить проверку.
            raise StateValidationError(
                "save_state принимает ТОЛЬКО точный тип StrategyState; "
                f"получено {type(state).__name__}")
        if state.strategy_id != strategy_id or state.figi != figi:
            raise StateValidationError(
                "ключи состояния не совпадают с аргументами: "
                f"запись ({state.strategy_id!r}, {state.figi!r}) против "
                f"аргументов ({strategy_id!r}, {figi!r}); разнобой ключей "
                "недопустим (изоляция по (strategy_id, FIGI))")
        with self._lock:
            existing = self._load(strategy_id, figi)
            if existing is None:
                raise StateNotFoundError(
                    f"состояние пары ({strategy_id!r}, {figi!r}) не "
                    "существует: создание — только create_state "
                    "(save_state не создаёт записи скрыто)")
            if existing.config_hash != state.config_hash:
                raise StateConfigMismatchError(
                    f"save_state не переносит состояние на новую "
                    f"конфигурацию: сохранено {existing.config_hash!r}, "
                    f"записывается {state.config_hash!r}; требуется "
                    "ЯВНОЕ решение (reset_state) — fail-closed")
            self._persist(state)

    def reset_state(self, strategy_id: Any, figi: Any) -> bool:
        """ЯВНЫЙ сброс состояния ОДНОЙ пары (strategy_id, figi).

        Возвращает True, если запись существовала и удалена; False,
        если записи не было. Другие пары НЕ затрагиваются.
        """
        validate_strategy_id(strategy_id)
        validate_figi(figi)
        with self._lock:
            if self._path is None:
                return self._records.pop((strategy_id, figi), None) \
                    is not None
            file_path = os.path.join(self._path,
                                     self._filename(strategy_id, figi))
            if not os.path.isfile(file_path):
                return False
            os.remove(file_path)
            return True

    def list_states(self) -> List[StrategyState]:
        """Все записи хранилища, отсортированные по (strategy_id, figi).

        Каждая запись полностью проверяется при чтении; повреждённая
        запись даёт StateCorruptionError/StateSchemaError (не пропускается
        молча). Порядок детерминированный.
        """
        with self._lock:
            if self._path is None:
                keys = sorted(self._records.keys())
                return [self._records[key] for key in keys]
            states: List[StrategyState] = []
            for name in sorted(os.listdir(self._path)):
                if not name.endswith(".json") or name.startswith(".tmp-"):
                    continue
                file_path = os.path.join(self._path, name)
                if not os.path.isfile(file_path):
                    continue
                try:
                    with open(file_path, "r", encoding="utf-8") as handle:
                        payload = json.loads(handle.read())
                except (OSError, ValueError, TypeError) as exc:
                    raise StateCorruptionError(
                        f"запись состояния ({name}) повреждена и не "
                        f"читается ({file_path}): {exc}; пустым "
                        "состоянием не подменяется (fail-closed)") from exc
                state = StrategyState.from_payload(payload)
                # Защита от рассинхронизации имени файла и содержимого:
                # источник истины — содержимое; имя должно совпадать.
                expected_name = self._filename(state.strategy_id, state.figi)
                if expected_name != name:
                    raise StateCorruptionError(
                        f"запись состояния повреждена: имя файла {name!r} "
                        f"не соответствует содержимому "
                        f"({state.strategy_id!r}, {state.figi!r}); "
                        "запись не маскируется (fail-closed)")
                states.append(state)
            states.sort(key=lambda item: (item.strategy_id, item.figi))
            return states


def resolve_state_store_path(config: Mapping[str, Any]) -> str:
    """ЯВНОЕ разрешение пути persistent-хранилища из конфигурации.

    ТЗ Stage B §3.2/§4.16: путь постоянного хранилища делается явно
    конфигурируемым и обязательным для включения persistent-режима;
    скрытый путь не придумывается, состояние не записывается в старые
    файлы Samsung.

    Правила (fail-closed):
      * конфигурация должна быть отображением;
      * ключ STATE_STORE_PATH обязателен: его отсутствие —
        StateStoreConfigError (никакого пути по умолчанию, никакого
        fallback на env/каталог процесса/старые файлы Samsung);
      * значение — непустая строка.
    """
    if not isinstance(config, Mapping):
        raise StateStoreConfigError(
            "конфигурация хранилища состояния должна быть отображением; "
            f"получено {type(config).__name__}")
    if STATE_STORE_CONFIG_KEY not in config:
        raise StateStoreConfigError(
            f"путь persistent-хранилища состояния не задан: отсутствует "
            f"обязательный явный ключ {STATE_STORE_CONFIG_KEY!r}; скрытый "
            "путь по умолчанию НЕ используется (fail-closed): включение "
            "persistent-режима возможно ТОЛЬКО явной конфигурацией")
    value = config[STATE_STORE_CONFIG_KEY]
    if not isinstance(value, str) or not value.strip():
        raise StateStoreConfigError(
            f"{STATE_STORE_CONFIG_KEY} должен быть непустой строкой; "
            f"получено {type(value).__name__}")
    return value


# ---------------------------------------------------------------------------
# Менеджер состояния стратегии
# ---------------------------------------------------------------------------


class StrategyStateManager:
    """Выдаёт стратегии ТОЛЬКО её собственное состояние.

    ТЗ Stage B §3.3:
      * состояние по паре strategy_id + FIGI (изоляция по ключу);
      * независимое состояние создаётся при отсутствии записи;
      * изменения сохраняются; перекрёстное загрязнение исключено
        (каждая операция работает с одной записью под замком);
      * параллельные обращения корректны (замки менеджера и хранилища,
        контроль существования записи при создании);
      * глобальный mutable context НЕ используется (все зависимости
        внедрены явно);
      * одно состояние на все инструменты НЕ хранится.

    Интеграция со Stage A:
      * config (StrategyConfig) принимается ТОЛЬКО точного типа —
        type(config) is StrategyConfig (решение Stage A.2.1, документировано
        в attribution.py; подкласс не может ослабить привязку состояния
        к конфигурации);
      * AttributionContext принимается ТОЛЬКО проверенный — через
        attribution._resolve_context (тот же вход проверки маркера
        проверенного создания, что и для factory/stamp; неподтверждённый
        контекст отклоняется);
      * отсутствие подтверждённой конфигурации (ни config, ни config_hash)
        — StateValidationError: fail-closed, никаких фиктивных значений.
    """

    def __init__(self,
                 store: Any,
                 *,
                 clock: Optional[Callable[[], str]] = None) -> None:
        if type(store) is not StateStore:
            raise StateStoreConfigError(
                "StrategyStateManager требует точный тип StateStore; "
                f"получено {type(store).__name__}")
        self._store: StateStore = store
        self._clock = clock or _utc_now_iso
        self._lock = threading.RLock()

    # --- внутренние операции --------------------------------------------------

    def _resolve_config_hash(self,
                             strategy_id: str,
                             figi: str,
                             config: Any,
                             config_hash: Any) -> str:
        """Разрешение ожидаемого config_hash по Stage A контрактам.

        Принимается ровно один источник (или оба согласованных):
          * config — ТОЛЬКО точный тип StrategyConfig; его strategy_id
            обязан совпадать с ключом;
          * config_hash — строка формата Stage A.2.
        Ничего не передано -> StateValidationError (fail-closed).
        """
        if config is None and config_hash is None:
            raise StateValidationError(
                f"состояние ({strategy_id!r}, {figi!r}) не может быть "
                "получено/создано без подтверждённой конфигурации: не "
                "передан ни StrategyConfig, ни его config_hash; фиктивные "
                "значения и автоподстановка запрещены (fail-closed)")
        resolved: Optional[str] = None
        if config is not None:
            if type(config) is not StrategyConfig:
                raise StateValidationError(
                    "config состояния принимается ТОЛЬКО точного типа "
                    "StrategyConfig (наследование не поддерживается — "
                    "решение Stage A.2.1; подкласс не может ослабить "
                    f"привязку состояния к конфигурации); получено "
                    f"{type(config).__name__}")
            if config.strategy_id != strategy_id:
                raise StateValidationError(
                    f"config.strategy_id ({config.strategy_id!r}) не "
                    f"совпадает с ключом состояния ({strategy_id!r}); "
                    "состояние не может быть привязано к чужой "
                    "конфигурации (fail-closed)")
            resolved = config.config_hash
        if config_hash is not None:
            _validate_config_hash_of_state(config_hash)
            if resolved is not None and resolved != config_hash:
                raise StateValidationError(
                    "config_hash и config.config_hash противоречат друг "
                    f"другу: {config_hash!r} против {resolved!r}; "
                    "состояние не выдаётся (fail-closed)")
            resolved = config_hash
        return resolved  # type: ignore[return-value]

    def _get_or_create(self,
                       strategy_id: str,
                       figi: str,
                       expected_hash: str) -> StrategyState:
        """Получение состояния; отсутствие записи -> независимое создание.

        Составная операция под замком менеджера; StateAlreadyExistsError
        (гонка между get и create) обрабатывается повторным чтением.
        """
        with self._lock:
            state = self._store.get_state(strategy_id, figi,
                                          config_hash=expected_hash)
            if state is not None:
                return state
            try:
                return self._store.create_state(
                    strategy_id, figi, expected_hash,
                    now=self._clock())
            except StateAlreadyExistsError:
                # Гонка: запись создана параллельным потоком между
                # get_state и create_state. Повторное чтение под замком
                # хранилища; несовпадающий config_hash той записи дал бы
                # StateConfigMismatchError здесь же.
                state = self._store.get_state(strategy_id, figi,
                                              config_hash=expected_hash)
                if state is None:
                    raise StateCorruptionError(
                        f"состояние ({strategy_id!r}, {figi!r}): после "
                        "StateAlreadyExistsError запись не найдена; "
                        "хранилище неконсистентно (fail-closed)")
                return state

    # --- публичный интерфейс (ТЗ Stage B §3.3) --------------------------------

    def get_state(self,
                  strategy_id: Any,
                  figi: Any,
                  *,
                  config: Any = None,
                  config_hash: Any = None) -> StrategyState:
        """Собственное состояние пары (strategy_id, figi).

        Отсутствие записи -> создание независимого состояния, привязанного
        к переданной конфигурации. Несовпадение config_hash сохранённой
        записи с ожидаемым — StateConfigMismatchError (без автоматического
        переноса на новую конфигурацию).
        """
        validate_strategy_id(strategy_id)
        validate_figi(figi)
        expected_hash = self._resolve_config_hash(
            strategy_id, figi, config, config_hash)
        return self._get_or_create(strategy_id, figi, expected_hash)

    def update_state(self,
                     strategy_id: Any,
                     figi: Any,
                     *,
                     config: Any = None,
                     config_hash: Any = None,
                     data: Any = None,
                     updater: Optional[Callable[[StrategyState],
                                                Mapping[str, Any]]] = None,
                     now: Optional[str] = None) -> StrategyState:
        """Обновление данных состояния пары (get-or-create + save).

        Ровно один из аргументов data / updater:
          * data — новые данные целиком;
          * updater — функция (текущее состояние) -> новые данные;
            исключение из updater прерывает операцию БЕЗ записи
            (сохранённое состояние не меняется).
        Возвращает НОВОЕ неизменяемое состояние (записанное в хранилище).
        """
        validate_strategy_id(strategy_id)
        validate_figi(figi)
        if (data is None) == (updater is None):
            raise StateValidationError(
                "update_state требует РОВНО ОДИН источник новых данных: "
                "data или updater")
        expected_hash = self._resolve_config_hash(
            strategy_id, figi, config, config_hash)
        stamp = _validate_timestamp(now, "now") if now is not None else None
        with self._lock:
            current = self._get_or_create(strategy_id, figi, expected_hash)
            if updater is not None:
                new_data = updater(current)
            else:
                new_data = data
            if not isinstance(new_data, Mapping):
                raise StateValidationError(
                    "новые данные состояния должны быть отображением; "
                    f"получено {type(new_data).__name__}")
            new_state = current.with_data(new_data, now=stamp)
            self._store.save_state(strategy_id, figi, new_state)
            return new_state

    def reset_state(self, strategy_id: Any, figi: Any) -> bool:
        """ЯВНЫЙ сброс состояния одной пары (другие пары не затрагиваются)."""
        validate_strategy_id(strategy_id)
        validate_figi(figi)
        with self._lock:
            return self._store.reset_state(strategy_id, figi)

    def list_states(self) -> List[StrategyState]:
        """Все состояния хранилища (детерминированный порядок)."""
        with self._lock:
            return self._store.list_states()

    # --- интеграция с атрибуцией Stage A ---------------------------------------

    def get_state_for_context(self,
                              context: Any,
                              figi: Any) -> StrategyState:
        """Состояние по ПРОВЕРЕННОМУ AttributionContext (Stage A.2.1).

        Контекст проходит _resolve_context: принимается только контекст
        точного типа AttributionContext с маркером проверенного создания
        (тот же вход, что и для factory/stamp/CSV/JSONL). strategy_id и
        config_hash берутся ТОЛЬКО из проверенного контекста.
        """
        validate_figi(figi)
        from attribution import _resolve_context
        verified = _resolve_context(context)
        return self.get_state(
            verified.strategy_id, figi, config_hash=verified.config_hash)

    def update_state_for_context(self,
                                 context: Any,
                                 figi: Any,
                                 *,
                                 data: Any = None,
                                 updater: Optional[Callable[
                                     [StrategyState],
                                     Mapping[str, Any]]] = None,
                                 now: Optional[str] = None) -> StrategyState:
        """Обновление состояния по ПРОВЕРЕННОМУ AttributionContext."""
        validate_figi(figi)
        from attribution import _resolve_context
        verified = _resolve_context(context)
        return self.update_state(
            verified.strategy_id, figi,
            config_hash=verified.config_hash,
            data=data, updater=updater, now=now)
