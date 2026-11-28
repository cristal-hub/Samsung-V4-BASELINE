# strategy_contracts.py — SAMSUNG V4 — NEW STRATEGY ENGINE. STAGE C.
#
# ТИПИЗИРОВАННЫЕ КОНТРАКТЫ ВХОДА/ВЫХОДА И ДЕТЕРМИНИРОВАННОЕ
# ОБЪЕДИНЕНИЕ ВЫХОДОВ (ТЗ Stage C §2–§3).
#
# Назначение:
#   * Entry contract — типизированный результат проверки входа
#     (§3.1): однозначно различает разрешённый вход, отсутствие
#     сигнала, запрет входа, недостаточность/некорректность исходных
#     данных (и отдельные явные состояния для некорректного результата
#     стратегии и ошибки оценки — ни одно из них НЕ допускает вход);
#   * Exit contract — типизированный результат оценки выхода (§3.2):
#     стратегический выход, защитный выход, отсутствие выхода,
#     невозможность безопасной оценки; стратегический и защитный
#     источники решений остаются РАЗНЫМИ;
#   * Exit merging — детерминированное объединение стратегического и
#     защитного выходов (§3.3): защитный выход нельзя потерять,
#     стратегический не может отменить/подавить защитный, правила
#     приоритета явные и документированные (таблица истинности ниже);
#   * Missing price — fail-closed (§3.4): отсутствующая/некорректная/
#     устаревшая цена НЕ подменяется нулём или последней известной
#     ценой, фиктивный выход не создаётся, состояние не изменяется
#     «как будто выход состоялся» — возвращается отдельный типизиро-
#     ванный результат невозможности безопасной оценки;
#   * State integration (§3.5): интеграция с StrategyStateManager
#     Stage B.1 — изоляция по (strategy_id, FIGI), проверка config_hash,
#     обновление ТОЛЬКО через существующий атомарный API, ошибки
#     состояния не маскируются.
#
# STAGE C.1 (исправление дефекта порядка операций): price gate
#   выполняется СТРОГО ДО любого доступа к состоянию. manager.get_state
#   Stage B.1 создаёт запись при отсутствии, поэтому при блокирующей
#   цене (отсутствующая/некорректная/устаревшая) состояние НЕ
#   запрашивается вовсе: новая запись состояния не создаётся,
#   существующая не изменяется, оценщики не вызываются — fail-closed
#   до границы оценки, без побочных эффектов на хранилище.
#
# ГРАНИЦЫ STAGE C (ТЗ §4 — строго соблюдены):
#   * это контрактный слой и интеграция состояния, а НЕ торговое
#     исполнение: модуль НЕ размещает и НЕ отменяет заявки, НЕ
#     подключается к брокеру/Sandbox/LIVE, НЕ реализует симулятор,
#     исторические данные, risk sizing, EmergencyExitController,
#     гибрид LIMIT→reconcile→MARKET, Force Trade и новую торговую
#     стратегию;
#   * смысл принятых контрактов Stage A.2.1 (StrategyConfig,
#     AttributionContext, Signal, EntrySignalInput) и Stage B.1
#     (StrategyState/StateStore/StrategyStateManager) НЕ меняется —
#     модуль только ПОТРЕБЛЯЕТ их через существующие публичные API;
#   * legacy_samsung_v4 остаётся REGRESSION_ONLY; старые runtime-файлы
#     Samsung не читаются и не пишутся.
#
# Защита от обхода проверок через подклассы (ТЗ §5):
#   * все контрактные объекты — frozen dataclass с валидацией в
#     __post_init__;
#   * ВСЕ потребители контрактов (merge, координатор, валидаторы)
#     принимают объекты ТОЛЬКО точного типа (type(x) is X) — подкласс,
#     ослабивший __post_init__, не проходит границу потребителя;
#   * атрибуция (strategy_id, config_hash, figi) перепроверяется на
#     согласованность на каждой границе; координатор дополнительно
#     перепроверяет config_hash ИСХОДНЫМ алгоритмом Stage A.2.1
#     (AttributionContext.from_config), а не доверяет полям объекта.
#
# Режим: OFFLINE / READ ONLY DATA / RESEARCH ONLY / NO LIVE ORDERS /
# NO REAL MONEY. Сетевых запросов к брокеру, Sandbox или LIVE нет.

from __future__ import annotations

import enum
import math
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Mapping, Optional

from strategy_api import (
    EntrySignalInput,
    ImmutableMapping,
    Signal,
    SignalDirection,
    Strategy,
    StrategyConfig,
    unfreeze,
    validate_config_hash_format,
)
from strategy_state import (
    StrategyStateManager,
    validate_figi,
    validate_strategy_id,
)
from attribution import AttributionContext

# ---------------------------------------------------------------------------
# Ошибки Stage C (fail-closed; самостоятельная иерархия — ошибки Stage A/B
# не маскируются и не подменяются, а пробрасываются как есть)
# ---------------------------------------------------------------------------


class ContractViolationError(Exception):
    """Базовая ошибка нарушения контракта Stage C."""


class EntryContractViolationError(ContractViolationError):
    """Некорректный объект/результат контракта входа."""


class ExitContractViolationError(ContractViolationError):
    """Некорректный объект/результат контракта выхода."""


class ExitMergeViolationError(ContractViolationError):
    """Нарушение правил объединения выходов (в т.ч. несогласованная
    атрибуция объединяемых результатов)."""


class PriceDataViolationError(ContractViolationError):
    """Некорректные данные цены при создании PriceData."""


class CoordinatorViolationError(ContractViolationError):
    """Нарушение контракта использования координатора/раннера
    (неправильные типы аргументов вызывающего кода)."""


# ---------------------------------------------------------------------------
# Перечисления контрактов
# ---------------------------------------------------------------------------


class EntryOutcome(enum.Enum):
    """Состояние результата проверки входа (ТЗ Stage C §3.1).

    ENTRY_ALLOWED          — разрешённый вход (единственное состояние,
                             допускающее вход);
    NO_SIGNAL              — отсутствие сигнала;
    ENTRY_FORBIDDEN        — явный запрет входа;
    DATA_INSUFFICIENT      — недостаточность или некорректность исходных
                             данных (вход НЕ разрешается);
    INVALID_STRATEGY_RESULT— некорректный результат стратегии (тип,
                             атрибуция, направление): вход НЕ разрешается;
    EVALUATION_ERROR       — ошибка при вычислении (исключение стратегии):
                             вход НЕ разрешается.

    Ни одно состояние, кроме ENTRY_ALLOWED, не может быть истолковано
    как разрешение входа (fail-closed, ТЗ §3.1: не допускать неявного
    разрешения входа при ошибке, отсутствии данных или некорректном
    результате стратегии).
    """
    ENTRY_ALLOWED = "ENTRY_ALLOWED"
    NO_SIGNAL = "NO_SIGNAL"
    ENTRY_FORBIDDEN = "ENTRY_FORBIDDEN"
    DATA_INSUFFICIENT = "DATA_INSUFFICIENT"
    INVALID_STRATEGY_RESULT = "INVALID_STRATEGY_RESULT"
    EVALUATION_ERROR = "EVALUATION_ERROR"


class ExitOutcome(enum.Enum):
    """Состояние результата оценки выхода (ТЗ Stage C §3.2).

    STRATEGIC_EXIT      — стратегический выход (источник: STRATEGIC);
    PROTECTIVE_EXIT     — защитный выход (источник: PROTECTIVE);
    NO_EXIT             — отсутствие выхода (оценивший слой решил
                          не выходить);
    EVALUATION_BLOCKED  — невозможность безопасной оценки выхода
                          (цена отсутствует/некорректна/устарела или
                          слой оценки не смог выдать решение);
                          выход НЕ считается состоявшимся.
    """
    STRATEGIC_EXIT = "STRATEGIC_EXIT"
    PROTECTIVE_EXIT = "PROTECTIVE_EXIT"
    NO_EXIT = "NO_EXIT"
    EVALUATION_BLOCKED = "EVALUATION_BLOCKED"


class ExitDecisionSource(enum.Enum):
    """Источник решения выхода (ТЗ Stage C §3.2).

    Стратегический и защитный источники остаются РАЗНЫМИ источниками
    решений. PRICE_GATE — решение «оценка невозможна» вынесла сама
    контрактная проверка цены (fail-closed gate), ДО вызова оценщиков.
    """
    STRATEGIC = "STRATEGIC"
    PROTECTIVE = "PROTECTIVE"
    PRICE_GATE = "PRICE_GATE"


class ExitMergeOutcome(enum.Enum):
    """Итог детерминированного объединения выходов (ТЗ Stage C §3.3).

    PROTECTIVE_EXIT                     — защитный выход (высший
                                          приоритет; никогда не
                                          подавляется);
    STRATEGIC_EXIT                      — стратегический выход при
                                          защитном NO_EXIT;
    NO_EXIT                             — оба слоя: выхода нет;
    INCOMPLETE_PROTECTIVE_EVALUATION    — защитный слой не смог дать
                                          безопасную оценку: ИТОГОВОЕ
                                          РЕШЕНИЕ НЕ ВЫНОСИТСЯ
                                          (fail-closed; информация
                                          стратегического слоя
                                          сохраняется в diagnostics);
    INCOMPLETE_STRATEGIC_EVALUATION     — стратегический слой не смог
                                          дать безопасную оценку при
                                          защитном NO_EXIT: итоговое
                                          решение не выносится;
    INCOMPLETE_PRICE_EVALUATION         — проверка цены не пройдена ДО
                                          вызова оценщиков (цена
                                          отсутствует/некорректна/
                                          устарела при
                                          price_required=True либо
                                          передана некорректная):
                                          оценщики не вызывались,
                                          итоговое решение не выносится.
    """
    PROTECTIVE_EXIT = "PROTECTIVE_EXIT"
    STRATEGIC_EXIT = "STRATEGIC_EXIT"
    NO_EXIT = "NO_EXIT"
    INCOMPLETE_PROTECTIVE_EVALUATION = "INCOMPLETE_PROTECTIVE_EVALUATION"
    INCOMPLETE_STRATEGIC_EVALUATION = "INCOMPLETE_STRATEGIC_EVALUATION"
    INCOMPLETE_PRICE_EVALUATION = "INCOMPLETE_PRICE_EVALUATION"


class PriceCheckOutcome(enum.Enum):
    """Результат проверки цены (ТЗ Stage C §3.4, fail-closed).

    PRICE_OK       — цена пригодна для безопасной оценки выхода;
    PRICE_MISSING  — цена не передана (когда она требуется);
    PRICE_INVALID  — цена некорректна (тип, NaN/Infinity, <= 0, чужой
                     FIGI, метка времени в будущем);
    PRICE_STALE    — цена устарела относительно явно заданного
                     максимального возраста.
    """
    PRICE_OK = "PRICE_OK"
    PRICE_MISSING = "PRICE_MISSING"
    PRICE_INVALID = "PRICE_INVALID"
    PRICE_STALE = "PRICE_STALE"


# ---------------------------------------------------------------------------
# Общие правила валидации Stage C
# ---------------------------------------------------------------------------

EXIT_MERGE_RULES_VERSION = "exit_merge_rules_v1"

_REASON_CODE_RE = re.compile(r"^[A-Z][A-Z0-9_]{0,127}$")


def _validate_reason_code(value: Any, error: type) -> str:
    """Код причины: непустая строка [A-Z][A-Z0-9_]* (до 128 символов).

    Машиночитаемый код причины обязателен для каждого результата
    контракта (ТЗ §3.1–§3.2: «код причины»); диагностика может нести
    дополнительные человекочитаемые подробности.
    """
    if not isinstance(value, str) or not _REASON_CODE_RE.match(value):
        raise error(
            "reason_code должен быть непустой строкой вида "
            f"[A-Z][A-Z0-9_]{{0,127}}; получено {value!r}")
    return value


def _validate_json_value(value: Any, *, _path: str,
                         error: type) -> Any:
    """Рекурсивная проверка диагностических данных на JSON-совместимость.

    Та же политика, что и в данных состояния Stage B: None, bool, int,
    конечный float, str, отображения со строковыми ключами, списки/
    кортежи; множества нормализуются в отсортированный список.
    NaN/Infinity и произвольные объекты отклоняются.
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
            result[key] = _validate_json_value(
                item, _path=f"{_path}.{key}", error=error)
        return result
    if isinstance(value, (list, tuple)):
        return [_validate_json_value(item, _path=f"{_path}[{i}]",
                                     error=error)
                for i, item in enumerate(value)]
    if isinstance(value, (set, frozenset)):
        items = [_validate_json_value(item, _path=f"{_path}{{set}}",
                                      error=error) for item in value]
        items.sort(key=lambda item: repr(item))
        return items
    raise error(
        f"{_path}: диагностические данные должны быть JSON-совместимыми "
        f"(None/bool/int/float/str/Mapping/Sequence); получено "
        f"{type(value).__name__}")


def _normalize_diagnostics(value: Any, *, error: type) -> ImmutableMapping:
    """Диагностика: None -> пустое отображение; иначе проверка+заморозка."""
    if value is None:
        return ImmutableMapping()
    if not isinstance(value, Mapping):
        raise error(
            "диагностические данные должны быть отображением (Mapping); "
            f"получено {type(value).__name__}")
    normalized = _validate_json_value(unfreeze(value), _path="diagnostics",
                                      error=error)
    return ImmutableMapping(normalized)


def _validate_iso_timestamp(value: Any, field_name: str,
                            error: type) -> datetime:
    """Метка времени: непустая строка ISO-8601 С часовым поясом.

    Та же политика, что и в Stage B для created_at/updated_at: без
    часового пояса значение отклоняется (нельзя детерминированно
    сравнивать наивные и осведомлённые метки).
    """
    if not isinstance(value, str) or not value:
        raise error(
            f"{field_name} должен быть непустой строкой ISO-8601 "
            f"с часовым поясом; получено {type(value).__name__}")
    text = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise error(
            f"{field_name} не читается как ISO-8601: {value!r}") from exc
    if parsed.tzinfo is None:
        raise error(
            f"{field_name} должен содержать часовой пояс: {value!r}")
    return parsed


def _validate_attribution(strategy_id: Any, figi: Any, config_hash: Any,
                          error: type) -> None:
    """Проверка тройки атрибуции контракта (strategy_id, FIGI, config_hash).

    strategy_id и FIGI — по правилам Stage B (набор символов, длина);
    config_hash — по формату Stage A.2 (SHA-256 hexdigest). Ошибки
    Stage A/B заворачиваются в ошибку Stage C соответствующего
    контракта (самостоятельная поверхность ошибок Stage C).
    """
    if not isinstance(strategy_id, str) or not strategy_id:
        raise error(
            "strategy_id контракта должен быть непустой строкой; "
            f"получено {type(strategy_id).__name__}")
    try:
        validate_strategy_id(strategy_id)
    except Exception as exc:  # StateValidationError и подклассы
        raise error(
            f"strategy_id контракта не проходит проверку Stage B: "
            f"{exc}") from exc
    if not isinstance(figi, str) or not figi:
        raise error(
            "figi контракта должен быть непустой строкой; "
            f"получено {type(figi).__name__}")
    try:
        validate_figi(figi)
    except Exception as exc:
        raise error(
            f"figi контракта не проходит проверку Stage B: {exc}") from exc
    if not isinstance(config_hash, str) or not config_hash:
        raise error(
            "config_hash контракта должен быть непустой строкой; "
            f"получено {type(config_hash).__name__}")
    try:
        validate_config_hash_format(config_hash)
    except Exception as exc:  # StrategyConfigError (Stage A.2)
        raise error(
            f"config_hash контракта не проходит проверку формата "
            f"Stage A.2: {exc}") from exc


def _utc_now_iso() -> str:
    """Текущее время UTC в фиксированном формате ISO-8601."""
    return datetime.now(timezone.utc).isoformat(
        timespec="microseconds").replace("+00:00", "Z")


def _validate_utc_datetime(value: Any, field_name: str,
                           error: type) -> datetime:
    """Аргумент `now`: осведомлённый datetime (наивный отклоняется)."""
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise error(
            f"{field_name} должен быть datetime с часовым поясом "
            f"(tz-aware); получено {type(value).__name__}")
    return value


# ---------------------------------------------------------------------------
# Цена: PriceData и fail-closed проверка (ТЗ Stage C §3.4)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PriceData:
    """Типизированная цена с меткой времени и источником.

    Инварианты (fail-closed):
      * figi — валидный идентификатор инструмента (правила Stage B);
      * price — конечное число СТРОГО больше нуля; NaN/Infinity/0/отрица-
        тельные значения отклоняются ПРИ СОЗДАНИИ: нулевая цена не может
        попасть в контракт ни при каких обстоятельствах (ТЗ §3.4);
      * timestamp — ISO-8601 с часовым поясом;
      * source — непустая строка (откуда пришла цена).

    Никакой автоподстановки: недостающая цена представляется
    ОТСУТСТВИЕМ объекта (None), а не фиктивным значением.
    """
    figi: str
    price: float
    timestamp: str
    source: str

    def __post_init__(self) -> None:
        if not isinstance(self.figi, str) or not self.figi:
            raise PriceDataViolationError(
                "PriceData.figi должен быть непустой строкой; "
                f"получено {type(self.figi).__name__}")
        try:
            validate_figi(self.figi)
        except Exception as exc:
            raise PriceDataViolationError(
                f"PriceData.figi не проходит проверку Stage B: {exc}"
            ) from exc
        if isinstance(self.price, bool) or \
                not isinstance(self.price, (int, float)):
            raise PriceDataViolationError(
                "PriceData.price должен быть числом (int/float, bool "
                f"запрещён); получено {type(self.price).__name__}")
        price = float(self.price)
        if not math.isfinite(price):
            raise PriceDataViolationError(
                "PriceData.price: NaN/Infinity запрещены (некорректная "
                "цена не может быть сохранена в контракте)")
        if price <= 0.0:
            raise PriceDataViolationError(
                f"PriceData.price должен быть СТРОГО больше нуля; "
                f"получено {price!r} (нулевая/отрицательная цена "
                "запрещена, ТЗ Stage C §3.4)")
        object.__setattr__(self, "price", price)
        _validate_iso_timestamp(self.timestamp, "PriceData.timestamp",
                                PriceDataViolationError)
        if not isinstance(self.source, str) or not self.source.strip():
            raise PriceDataViolationError(
                "PriceData.source должен быть непустой строкой "
                "(откуда пришла цена)")


@dataclass(frozen=True)
class PriceCheckResult:
    """Типизированный результат проверки цены (ТЗ Stage C §3.4).

    PRICE_OK несёт проверенный PriceData; остальные состояния несут
    диагностическую причину и НЕ содержат цены (никаких подстановок).
    """
    outcome: PriceCheckOutcome
    reason_code: str
    diagnostics: ImmutableMapping = field(default_factory=ImmutableMapping)
    price: Optional[PriceData] = None

    def __post_init__(self) -> None:
        if type(self.outcome) is not PriceCheckOutcome:
            raise PriceDataViolationError(
                "PriceCheckResult.outcome должен быть точным типом "
                f"PriceCheckOutcome; получено {type(self.outcome).__name__}")
        _validate_reason_code(self.reason_code, PriceDataViolationError)
        object.__setattr__(
            self, "diagnostics",
            _normalize_diagnostics(self.diagnostics,
                                   error=PriceDataViolationError))
        if self.price is not None and type(self.price) is not PriceData:
            raise PriceDataViolationError(
                "PriceCheckResult.price принимает только точный тип "
                f"PriceData или None; получено {type(self.price).__name__}")
        if (self.outcome is PriceCheckOutcome.PRICE_OK) != \
                (self.price is not None):
            raise PriceDataViolationError(
                "PriceCheckResult: PRICE_OK обязан нести проверенный "
                "PriceData; остальные состояния — None (никаких "
                "подстановочных цен)")


def check_price(price: Any,
                *,
                expected_figi: Any,
                now: Optional[datetime] = None,
                max_age_seconds: Optional[float] = None
                ) -> PriceCheckResult:
    """Fail-closed проверка цены для оценки выхода (ТЗ Stage C §3.4).

    Правила (все отклонения — типизированный результат, НИКАКИХ
    подстановок и исключений):
      * price is None                         -> PRICE_MISSING;
      * не точный тип PriceData               -> PRICE_INVALID
                                                 (PRICE_WRONG_TYPE);
      * price.figi != expected_figi           -> PRICE_INVALID
                                                 (PRICE_FOREIGN_FIGI):
                                                 чужая цена не может
                                                 использоваться;
      * метка времени в будущем               -> PRICE_INVALID
                                                 (PRICE_FROM_FUTURE):
                                                 рассинхрон часов не
                                                 проходит молча;
      * max_age_seconds задан и возраст цены
        превышает его                         -> PRICE_STALE (PRICE_STALE);
      * иначе                                  -> PRICE_OK с ценой.

    max_age_seconds — ЯВНЫЙ параметр контракта (обязательный ключевой
    аргумент вызывающей стороны): None означает «проверку устаревания
    отключили явным решением оператора» и фиксируется в diagnostics;
    скрытого порога по умолчанию НЕ существует. Последняя известная
    цена нигде НЕ подставляется — такого механизма в контракте нет.

    now — осведомлённый datetime (по умолчанию текущее время UTC).
    """
    validate_figi(expected_figi)
    now_dt = _validate_utc_datetime(now, "now", PriceDataViolationError) \
        if now is not None else datetime.now(timezone.utc)

    if price is None:
        return PriceCheckResult(
            outcome=PriceCheckOutcome.PRICE_MISSING,
            reason_code="PRICE_MISSING",
            diagnostics={
                "expected_figi": expected_figi,
                "detail": "цена не передана; подстановка нуля или "
                          "последней известной цены запрещена "
                          "(ТЗ Stage C §3.4)",
            })

    if type(price) is not PriceData:
        return PriceCheckResult(
            outcome=PriceCheckOutcome.PRICE_INVALID,
            reason_code="PRICE_WRONG_TYPE",
            diagnostics={
                "expected_figi": expected_figi,
                "received_type": type(price).__name__,
                "detail": "цена должна быть точным типом PriceData "
                          "(подклассы и duck-typing отклоняются)",
            })

    if price.figi != expected_figi:
        return PriceCheckResult(
            outcome=PriceCheckOutcome.PRICE_INVALID,
            reason_code="PRICE_FOREIGN_FIGI",
            diagnostics={
                "expected_figi": expected_figi,
                "received_figi": price.figi,
                "detail": "цена принадлежит другому инструменту",
            })

    try:
        price_dt = _validate_iso_timestamp(
            price.timestamp, "price.timestamp", PriceDataViolationError)
    except PriceDataViolationError as exc:
        return PriceCheckResult(
            outcome=PriceCheckOutcome.PRICE_INVALID,
            reason_code="PRICE_BAD_TIMESTAMP",
            diagnostics={
                "expected_figi": expected_figi,
                "detail": str(exc),
            })

    age_seconds = (now_dt - price_dt).total_seconds()
    if age_seconds < 0.0:
        return PriceCheckResult(
            outcome=PriceCheckOutcome.PRICE_INVALID,
            reason_code="PRICE_FROM_FUTURE",
            diagnostics={
                "expected_figi": expected_figi,
                "price_timestamp": price.timestamp,
                "age_seconds": age_seconds,
                "detail": "метка времени цены в будущем относительно "
                          "текущего времени",
            })

    diagnostics = {
        "expected_figi": expected_figi,
        "price_timestamp": price.timestamp,
        "price_source": price.source,
        "age_seconds": age_seconds,
        "max_age_seconds": max_age_seconds,
    }

    if max_age_seconds is not None:
        if isinstance(max_age_seconds, bool) or \
                not isinstance(max_age_seconds, (int, float)) or \
                not math.isfinite(float(max_age_seconds)) or \
                max_age_seconds < 0:
            raise PriceDataViolationError(
                "max_age_seconds должен быть конечным неотрицательным "
                f"числом или None; получено {max_age_seconds!r}")
        if age_seconds > float(max_age_seconds):
            diagnostics["detail"] = (
                "цена устарела: возраст превышает явно заданный "
                "максимальный; подстановка последней известной цены "
                "запрещена (ТЗ Stage C §3.4)")
            return PriceCheckResult(
                outcome=PriceCheckOutcome.PRICE_STALE,
                reason_code="PRICE_STALE",
                diagnostics=diagnostics)

    diagnostics["detail"] = "цена прошла fail-closed проверку"
    return PriceCheckResult(
        outcome=PriceCheckOutcome.PRICE_OK,
        reason_code="PRICE_OK",
        diagnostics=diagnostics,
        price=price,
    )


# ---------------------------------------------------------------------------
# КОНТРАКТ ВХОДА (ТЗ Stage C §3.1)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EntryEvaluation:
    """Типизированный результат проверки входа (ТЗ Stage C §3.1).

    Однозначно различает: разрешённый вход (ENTRY_ALLOWED), отсутствие
    сигнала (NO_SIGNAL), запрет входа (ENTRY_FORBIDDEN), недостаточность/
    некорректность исходных данных (DATA_INSUFFICIENT), некорректный
    результат стратегии (INVALID_STRATEGY_RESULT) и ошибку оценки
    (EVALUATION_ERROR).

    Однозначная атрибуция каждого результата: strategy_id, config_hash,
    FIGI, тип результата, код причины, диагностические данные.

    Неизменяемость: frozen dataclass; diagnostics — ImmutableMapping.
    Потребители принимают объекты ТОЛЬКО точного типа
    (validate_entry_evaluation), поэтому подкласс с ослабленной
    валидацией не проходит границу потребителя.
    """
    strategy_id: str
    config_hash: str
    figi: str
    outcome: EntryOutcome
    reason_code: str
    diagnostics: ImmutableMapping = field(default_factory=ImmutableMapping)

    def __post_init__(self) -> None:
        _validate_attribution(self.strategy_id, self.figi, self.config_hash,
                              EntryContractViolationError)
        if type(self.outcome) is not EntryOutcome:
            raise EntryContractViolationError(
                "EntryEvaluation.outcome должен быть точным типом "
                f"EntryOutcome; получено {type(self.outcome).__name__}")
        _validate_reason_code(self.reason_code, EntryContractViolationError)
        object.__setattr__(
            self, "diagnostics",
            _normalize_diagnostics(self.diagnostics,
                                   error=EntryContractViolationError))

    # --- фабрики явных состояний --------------------------------------------

    @classmethod
    def allowed(cls, strategy_id: str, config_hash: str, figi: str,
                reason_code: str,
                diagnostics: Optional[Mapping] = None) -> "EntryEvaluation":
        """Единственное состояние, допускающее вход."""
        return cls(strategy_id=strategy_id, config_hash=config_hash,
                   figi=figi, outcome=EntryOutcome.ENTRY_ALLOWED,
                   reason_code=reason_code, diagnostics=diagnostics)

    @classmethod
    def no_signal(cls, strategy_id: str, config_hash: str, figi: str,
                  reason_code: str,
                  diagnostics: Optional[Mapping] = None) -> "EntryEvaluation":
        """Отсутствие сигнала (вход НЕ разрешается)."""
        return cls(strategy_id=strategy_id, config_hash=config_hash,
                   figi=figi, outcome=EntryOutcome.NO_SIGNAL,
                   reason_code=reason_code, diagnostics=diagnostics)

    @classmethod
    def forbidden(cls, strategy_id: str, config_hash: str, figi: str,
                  reason_code: str,
                  diagnostics: Optional[Mapping] = None) -> "EntryEvaluation":
        """Явный запрет входа."""
        return cls(strategy_id=strategy_id, config_hash=config_hash,
                   figi=figi, outcome=EntryOutcome.ENTRY_FORBIDDEN,
                   reason_code=reason_code, diagnostics=diagnostics)

    @classmethod
    def data_insufficient(
            cls, strategy_id: str, config_hash: str, figi: str,
            reason_code: str,
            diagnostics: Optional[Mapping] = None) -> "EntryEvaluation":
        """Недостаточность/некорректность исходных данных."""
        return cls(strategy_id=strategy_id, config_hash=config_hash,
                   figi=figi, outcome=EntryOutcome.DATA_INSUFFICIENT,
                   reason_code=reason_code, diagnostics=diagnostics)

    @classmethod
    def invalid_strategy_result(
            cls, strategy_id: str, config_hash: str, figi: str,
            reason_code: str,
            diagnostics: Optional[Mapping] = None) -> "EntryEvaluation":
        """Некорректный результат стратегии (вход НЕ разрешается)."""
        return cls(strategy_id=strategy_id, config_hash=config_hash,
                   figi=figi, outcome=EntryOutcome.INVALID_STRATEGY_RESULT,
                   reason_code=reason_code, diagnostics=diagnostics)

    @classmethod
    def evaluation_error(
            cls, strategy_id: str, config_hash: str, figi: str,
            reason_code: str,
            diagnostics: Optional[Mapping] = None) -> "EntryEvaluation":
        """Ошибка при вычислении (вход НЕ разрешается)."""
        return cls(strategy_id=strategy_id, config_hash=config_hash,
                   figi=figi, outcome=EntryOutcome.EVALUATION_ERROR,
                   reason_code=reason_code, diagnostics=diagnostics)


def validate_entry_evaluation(value: Any, *,
                              expected_strategy_id: Any = None,
                              expected_config_hash: Any = None,
                              expected_figi: Any = None) -> EntryEvaluation:
    """Граница потребителя результата входа (fail-closed).

    Принимает ТОЛЬКО точный тип EntryEvaluation (type(value) is ...):
    подкласс, duck-typed объект или None отклоняются. При переданных
    ожидаемых значениях атрибуции — перепроверка совпадения; расхождение
    strategy_id/config_hash/figi (подмена атрибуции) отклоняется.
    """
    if type(value) is not EntryEvaluation:
        raise EntryContractViolationError(
            "результат входа должен быть точным типом EntryEvaluation; "
            f"получено {type(value).__name__} (подклассы и duck-typing "
            "не допускаются: подкласс не может ослабить валидацию)")
    if expected_strategy_id is not None and \
            value.strategy_id != expected_strategy_id:
        raise EntryContractViolationError(
            "атрибуция результата входа не совпадает с ожидаемой: "
            f"strategy_id {value.strategy_id!r} вместо "
            f"{expected_strategy_id!r} (подмена атрибуции отклоняется)")
    if expected_config_hash is not None and \
            value.config_hash != expected_config_hash:
        raise EntryContractViolationError(
            "атрибуция результата входа не совпадает с ожидаемой: "
            f"config_hash {value.config_hash!r} вместо "
            f"{expected_config_hash!r} (подмена атрибуции отклоняется)")
    if expected_figi is not None and value.figi != expected_figi:
        raise EntryContractViolationError(
            "атрибуция результата входа не совпадает с ожидаемой: "
            f"figi {value.figi!r} вместо {expected_figi!r}")
    return value


class EntryEvaluationRunner:
    """Запуск проверки входа с конвертацией ВСЕХ проблем в типизированные
    результаты (ТЗ Stage C §3.1).

    Гарантии:
      * при ЛЮБОЙ проблеме (недостающие данные, исключение стратегии,
        некорректный результат) возвращается явное НЕ-разрешающее
        состояние — неявное разрешение входа при ошибке невозможно;
      * ошибки misuse вызывающего кода (неверные типы config/strategy/
        входного объекта) — контролируемое исключение
        CoordinatorViolationError (это ошибка программирования, а не
        торговая ситуация);
      * смысл контракта Stage A (Strategy.evaluate_entry -> Signal)
        не меняется: стратегия вызывается как в Stage A, Stage C
        добавляет типизированную границу результата.
    """

    def evaluate(self,
                 *,
                 strategy: Any,
                 config: Any,
                 entry_input: Any) -> EntryEvaluation:
        # 1. Контракт вызывающего кода: точные типы (misuse — исключение).
        if type(config) is not StrategyConfig:
            raise CoordinatorViolationError(
                "EntryEvaluationRunner.evaluate требует точный тип "
                f"StrategyConfig; получено {type(config).__name__}")
        if type(entry_input) is not EntrySignalInput:
            raise CoordinatorViolationError(
                "EntryEvaluationRunner.evaluate требует точный тип "
                f"EntrySignalInput; получено "
                f"{type(entry_input).__name__}")
        if not isinstance(strategy, Strategy):
            raise CoordinatorViolationError(
                "EntryEvaluationRunner.evaluate требует стратегию "
                f"контракта Stage A (isinstance Strategy); получено "
                f"{type(strategy).__name__}")
        strategy_id = config.strategy_id
        config_hash = config.config_hash

        # 2. Fail-closed проверка исходных данных -> DATA_INSUFFICIENT.
        #    Некорректный figi — ошибка ВЫЗЫВАЮЩЕГО кода (маршрутизация
        #    запроса, а не рыночные данные): fail-fast исключение,
        #    контракт с недействительным figi не создаётся.
        try:
            validate_figi(entry_input.figi)
        except Exception as exc:
            raise CoordinatorViolationError(
                f"figi входных данных не проходит проверку Stage B: "
                f"{exc}") from exc
        figi = entry_input.figi

        if entry_input.candles is None:
            return EntryEvaluation.data_insufficient(
                strategy_id, config_hash, figi, "CANDLES_MISSING",
                {"detail": "свечи не переданы; вход не оценивается"})

        last_price = entry_input.last_price
        if isinstance(last_price, bool) or \
                not isinstance(last_price, (int, float)) or \
                not math.isfinite(float(last_price)) or \
                float(last_price) <= 0.0:
            return EntryEvaluation.data_insufficient(
                strategy_id, config_hash, figi, "PRICE_INVALID",
                {"detail": "last_price отсутствует/некорректен "
                           "(NaN/Infinity/<=0 не допускаются); нулевая "
                           "цена не подставляется"})

        # 3. Вызов стратегии Stage A: исключение -> EVALUATION_ERROR.
        try:
            signal = strategy.evaluate_entry(entry_input, config)
        except Exception as exc:  # noqa: BLE001 — конвертация в контракт
            return EntryEvaluation.evaluation_error(
                strategy_id, config_hash, figi, "EVALUATOR_RAISED",
                {"exception_type": type(exc).__name__,
                 "exception_message": str(exc)[:500],
                 "detail": "исключение стратегии конвертировано в "
                           "явное НЕ-разрешающее состояние"})

        # 4. Некорректный результат стратегии -> INVALID_STRATEGY_RESULT.
        if type(signal) is not Signal:
            return EntryEvaluation.invalid_strategy_result(
                strategy_id, config_hash, figi, "RESULT_WRONG_TYPE",
                {"received_type": type(signal).__name__,
                 "detail": "стратегия обязана вернуть точный тип "
                           "Signal (Stage A)"})
        if signal.strategy_id != strategy_id or \
                signal.config_hash != config_hash:
            return EntryEvaluation.invalid_strategy_result(
                strategy_id, config_hash, figi, "ATTRIBUTION_MISMATCH",
                {"signal_strategy_id": str(signal.strategy_id),
                 "signal_config_hash": str(signal.config_hash),
                 "detail": "атрибуция сигнала не совпадает с конфигурацией: "
                           "подмена strategy_id/config_hash отклоняется"})
        if isinstance(signal.figi, str) and signal.figi and \
                signal.figi != figi:
            return EntryEvaluation.invalid_strategy_result(
                strategy_id, config_hash, figi, "FIGI_MISMATCH",
                {"signal_figi": signal.figi,
                 "detail": "сигнал принадлежит другому инструменту"})

        # 5. Отображение направления Stage A на состояние контракта входа.
        direction = signal.direction
        signal_reason = signal.reason if isinstance(signal.reason, str) \
            else str(signal.reason)
        diagnostics = {
            "signal_reason": signal_reason[:500],
            "direction": direction.value if isinstance(direction,
                                                       SignalDirection)
            else str(direction),
            "ticker": signal.ticker if isinstance(signal.ticker, str) else "",
        }
        if type(direction) is not SignalDirection:
            return EntryEvaluation.invalid_strategy_result(
                strategy_id, config_hash, figi, "DIRECTION_UNKNOWN",
                {"detail": "направление сигнала не является элементом "
                           "SignalDirection"})
        if direction is SignalDirection.BUY:
            return EntryEvaluation.allowed(
                strategy_id, config_hash, figi, "ENTRY_SIGNAL_BUY",
                diagnostics)
        if direction is SignalDirection.HOLD:
            return EntryEvaluation.no_signal(
                strategy_id, config_hash, figi, "NO_SIGNAL_HOLD",
                diagnostics)
        if direction is SignalDirection.SELL:
            return EntryEvaluation.forbidden(
                strategy_id, config_hash, figi, "ENTRY_FORBIDDEN_SELL",
                diagnostics)
        return EntryEvaluation.invalid_strategy_result(
            strategy_id, config_hash, figi, "DIRECTION_UNKNOWN",
            {"detail": "направление сигнала не входит в контракт входа"})


# ---------------------------------------------------------------------------
# КОНТРАКТ ВЫХОДА (ТЗ Stage C §3.2)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ExitEvaluation:
    """Типизированный результат оценки выхода (ТЗ Stage C §3.2).

    Поддерживает: стратегический выход, защитный выход, отсутствие
    выхода, невозможность безопасной оценки. Стратегический выход и
    защитный выход остаются РАЗНЫМИ источниками решений (поле
    decision_source).

    Обязательная атрибуция каждого результата: strategy_id, config_hash,
    FIGI, источник решения, причина (reason_code), тип выхода (exit_type
    — только для реальных выходов), диагностические данные и метка
    решения для последующей обработки.

    Согласованность полей (fail-closed, проверяется при создании):
      * STRATEGIC_EXIT      <-> decision_source == STRATEGIC;
      * PROTECTIVE_EXIT     <-> decision_source == PROTECTIVE;
      * NO_EXIT             <-> decision_source in {STRATEGIC, PROTECTIVE}
                               (какой слой решил не выходить — известно);
      * EVALUATION_BLOCKED  <-> decision_source in {PRICE_GATE, STRATEGIC,
                               PROTECTIVE} (что помешало безопасной
                               оценке — цена/слой — известно);
      * exit_type обязателен ТОЛЬКО для реальных выходов и обязан
        отсутствовать у NO_EXIT / EVALUATION_BLOCKED (несуществующий
        тип выхода не создаётся).
    """
    strategy_id: str
    config_hash: str
    figi: str
    outcome: ExitOutcome
    decision_source: ExitDecisionSource
    reason_code: str
    exit_type: Optional[str] = None
    decided_at: Optional[str] = None
    diagnostics: ImmutableMapping = field(default_factory=ImmutableMapping)

    def __post_init__(self) -> None:
        _validate_attribution(self.strategy_id, self.figi, self.config_hash,
                              ExitContractViolationError)
        if type(self.outcome) is not ExitOutcome:
            raise ExitContractViolationError(
                "ExitEvaluation.outcome должен быть точным типом "
                f"ExitOutcome; получено {type(self.outcome).__name__}")
        if type(self.decision_source) is not ExitDecisionSource:
            raise ExitContractViolationError(
                "ExitEvaluation.decision_source должен быть точным типом "
                "ExitDecisionSource; получено "
                f"{type(self.decision_source).__name__}")
        _validate_reason_code(self.reason_code, ExitContractViolationError)

        if self.outcome is ExitOutcome.STRATEGIC_EXIT:
            if self.decision_source is not ExitDecisionSource.STRATEGIC:
                raise ExitContractViolationError(
                    "STRATEGIC_EXIT обязан исходить от источника "
                    f"STRATEGIC; получено {self.decision_source.value}")
            if self.exit_type is None:
                raise ExitContractViolationError(
                    "реальный выход обязан нести exit_type (тип выхода); "
                    "None не допускается")
        elif self.outcome is ExitOutcome.PROTECTIVE_EXIT:
            if self.decision_source is not ExitDecisionSource.PROTECTIVE:
                raise ExitContractViolationError(
                    "PROTECTIVE_EXIT обязан исходить от источника "
                    f"PROTECTIVE; получено {self.decision_source.value}")
            if self.exit_type is None:
                raise ExitContractViolationError(
                    "реальный выход обязан нести exit_type (тип выхода); "
                    "None не допускается")
        elif self.outcome is ExitOutcome.NO_EXIT:
            if self.decision_source is ExitDecisionSource.PRICE_GATE:
                raise ExitContractViolationError(
                    "NO_EXIT обязан исходить от слоя оценки "
                    "(STRATEGIC или PROTECTIVE), а не от PRICE_GATE")
            if self.exit_type is not None:
                raise ExitContractViolationError(
                    "NO_EXIT не может нести exit_type: несуществующий "
                    "выход не типизируется")
        else:  # EVALUATION_BLOCKED
            if self.exit_type is not None:
                raise ExitContractViolationError(
                    "EVALUATION_BLOCKED не может нести exit_type: "
                    "безопасная оценка не состоялась, выхода нет")

        if self.exit_type is not None:
            _validate_reason_code(self.exit_type, ExitContractViolationError)

        if self.decided_at is not None:
            _validate_iso_timestamp(self.decided_at, "decided_at",
                                    ExitContractViolationError)
        object.__setattr__(
            self, "diagnostics",
            _normalize_diagnostics(self.diagnostics,
                                   error=ExitContractViolationError))

    # --- фабрики явных состояний --------------------------------------------

    @classmethod
    def strategic_exit(cls, strategy_id: str, config_hash: str, figi: str,
                       exit_type: str, reason_code: str,
                       decided_at: Optional[str] = None,
                       diagnostics: Optional[Mapping] = None
                       ) -> "ExitEvaluation":
        """Стратегический выход (источник: STRATEGIC)."""
        return cls(strategy_id=strategy_id, config_hash=config_hash,
                   figi=figi, outcome=ExitOutcome.STRATEGIC_EXIT,
                   decision_source=ExitDecisionSource.STRATEGIC,
                   reason_code=reason_code, exit_type=exit_type,
                   decided_at=decided_at, diagnostics=diagnostics)

    @classmethod
    def protective_exit(cls, strategy_id: str, config_hash: str, figi: str,
                        exit_type: str, reason_code: str,
                        decided_at: Optional[str] = None,
                        diagnostics: Optional[Mapping] = None
                        ) -> "ExitEvaluation":
        """Защитный выход (источник: PROTECTIVE)."""
        return cls(strategy_id=strategy_id, config_hash=config_hash,
                   figi=figi, outcome=ExitOutcome.PROTECTIVE_EXIT,
                   decision_source=ExitDecisionSource.PROTECTIVE,
                   reason_code=reason_code, exit_type=exit_type,
                   decided_at=decided_at, diagnostics=diagnostics)

    @classmethod
    def no_exit(cls, strategy_id: str, config_hash: str, figi: str,
                decision_source: ExitDecisionSource, reason_code: str,
                decided_at: Optional[str] = None,
                diagnostics: Optional[Mapping] = None) -> "ExitEvaluation":
        """Отсутствие выхода: слой оценил и решил не выходить."""
        return cls(strategy_id=strategy_id, config_hash=config_hash,
                   figi=figi, outcome=ExitOutcome.NO_EXIT,
                   decision_source=decision_source, reason_code=reason_code,
                   exit_type=None, decided_at=decided_at,
                   diagnostics=diagnostics)

    @classmethod
    def evaluation_blocked(cls, strategy_id: str, config_hash: str,
                           figi: str,
                           decision_source: ExitDecisionSource,
                           reason_code: str,
                           decided_at: Optional[str] = None,
                           diagnostics: Optional[Mapping] = None
                           ) -> "ExitEvaluation":
        """Невозможность безопасной оценки выхода (fail-closed).

        Выход НЕ считается состоявшимся; состояние НЕ изменяется «как
        будто выход состоялся» (ТЗ Stage C §3.4).
        """
        return cls(strategy_id=strategy_id, config_hash=config_hash,
                   figi=figi, outcome=ExitOutcome.EVALUATION_BLOCKED,
                   decision_source=decision_source, reason_code=reason_code,
                   exit_type=None, decided_at=decided_at,
                   diagnostics=diagnostics)


def validate_exit_evaluation(value: Any, *,
                             expected_strategy_id: Any = None,
                             expected_config_hash: Any = None,
                             expected_figi: Any = None) -> ExitEvaluation:
    """Граница потребителя результата выхода (fail-closed).

    Принимает ТОЛЬКО точный тип ExitEvaluation; при переданных
    ожидаемых значениях атрибуции — перепроверка совпадения (подмена
    strategy_id/config_hash/figi отклоняется).
    """
    if type(value) is not ExitEvaluation:
        raise ExitContractViolationError(
            "результат выхода должен быть точным типом ExitEvaluation; "
            f"получено {type(value).__name__} (подклассы и duck-typing "
            "не допускаются)")
    if expected_strategy_id is not None and \
            value.strategy_id != expected_strategy_id:
        raise ExitContractViolationError(
            "атрибуция результата выхода не совпадает с ожидаемой: "
            f"strategy_id {value.strategy_id!r} вместо "
            f"{expected_strategy_id!r}")
    if expected_config_hash is not None and \
            value.config_hash != expected_config_hash:
        raise ExitContractViolationError(
            "атрибуция результата выхода не совпадает с ожидаемой: "
            f"config_hash {value.config_hash!r} вместо "
            f"{expected_config_hash!r}")
    if expected_figi is not None and value.figi != expected_figi:
        raise ExitContractViolationError(
            "атрибуция результата выхода не совпадает с ожидаемой: "
            f"figi {value.figi!r} вместо {expected_figi!r}")
    return value


@dataclass(frozen=True)
class ExitEvaluationRequest:
    """Типизированный запрос оценки выхода к слою стратегии.

    Содержит ТОЛЬКО проверенные значения: атрибуция проверена, данные
    состояния — ImmutableMapping JSON-совместимых значений (из
    StrategyState Stage B.1), цена — уже прошедшая fail-closed проверку
    PriceData (или None). Некорректные значения не могут попасть в
    запрос: __post_init__ отклоняет их при создании.
    """
    strategy_id: str
    config_hash: str
    figi: str
    state_data: ImmutableMapping = field(default_factory=ImmutableMapping)
    price: Optional[PriceData] = None

    def __post_init__(self) -> None:
        _validate_attribution(self.strategy_id, self.figi, self.config_hash,
                              ExitContractViolationError)
        if not isinstance(self.state_data, Mapping):
            raise ExitContractViolationError(
                "ExitEvaluationRequest.state_data должен быть "
                f"отображением; получено {type(self.state_data).__name__}")
        normalized = _validate_json_value(
            unfreeze(self.state_data), _path="state_data",
            error=ExitContractViolationError)
        object.__setattr__(self, "state_data", ImmutableMapping(normalized))
        if self.price is not None and type(self.price) is not PriceData:
            raise ExitContractViolationError(
                "ExitEvaluationRequest.price принимает только точный тип "
                f"PriceData или None; получено {type(self.price).__name__}")


# ---------------------------------------------------------------------------
# ДЕТЕРМИНИРОВАННОЕ ОБЪЕДИНЕНИЕ ВЫХОДОВ (ТЗ Stage C §3.3)
# ---------------------------------------------------------------------------

# Явные правила приоритета (таблица истинности; protective-major):
#
#   защитный \ стратегический | STRATEGIC_EXIT | NO_EXIT | EVALUATION_BLOCKED
#   --------------------------+----------------+---------+-------------------
#   PROTECTIVE_EXIT           | PROTECTIVE_EXIT| PROTECTIVE_EXIT | PROTECTIVE_EXIT
#   NO_EXIT                   | STRATEGIC_EXIT | NO_EXIT | INCOMPLETE_STRATEGIC_EVALUATION
#   EVALUATION_BLOCKED        | INCOMPLETE_PROTECTIVE_EVALUATION (все случаи)
#
# Свойства (ТЗ §3.3):
#   * защитный выход нельзя потерять: PROTECTIVE_EXIT побеждает во ВСЕХ
#     случаях;
#   * стратегический выход не может отменить или подавить защитный:
#     при двух выходах побеждает ЗАЩИТНЫЙ, стратегическая информация
#     сохраняется в diagnostics (note=PROTECTIVE_PRIORITY_OVER_STRATEGIC_EXIT);
#   * отсутствие стратегического выхода не отменяет защитный;
#   * конфликтующие результаты обрабатываются по таблице выше
#     (заранее определённые правила, никакой скрытой приоритетности);
#   * итог сохраняет источник и причину решения;
#   * одинаковые входы всегда дают одинаковый итог: merge — ЧИСТАЯ
#     функция (без времени, без случайности, без обращения к состоянию).


@dataclass(frozen=True)
class ExitMergeResult:
    """Детерминированный итог объединения стратегического и защитного
    выходов (ТЗ Stage C §3.3).

    Сохраняет источник и причину решения: для реальных выходов —
    decision_source/reason_code/exit_type победившего решения; для
    NO_EXIT — причина согласия слоёв; для INCOMPLETE_* — причина
    незавершённости оценки. Полные сведения обоих входов — в
    diagnostics (ничего не теряется молча).

    Инварианты:
      * reason_code — ВСЕГДА непустой код (итог без причины запрещён);
      * decision_source задан ТОЛЬКО у реальных итоговых выходов;
      * exit_type задан ТОЛЬКО у реальных итоговых выходов;
      * equality по содержимому: одинаковые входы -> равные результаты
        (детерминированность проверяется тестами).
    """
    strategy_id: str
    config_hash: str
    figi: str
    final_outcome: ExitMergeOutcome
    reason_code: str
    decision_source: Optional[ExitDecisionSource] = None
    exit_type: Optional[str] = None
    diagnostics: ImmutableMapping = field(default_factory=ImmutableMapping)

    def __post_init__(self) -> None:
        _validate_attribution(self.strategy_id, self.figi, self.config_hash,
                              ExitMergeViolationError)
        if type(self.final_outcome) is not ExitMergeOutcome:
            raise ExitMergeViolationError(
                "ExitMergeResult.final_outcome должен быть точным типом "
                "ExitMergeOutcome; получено "
                f"{type(self.final_outcome).__name__}")
        _validate_reason_code(self.reason_code, ExitMergeViolationError)

        if self.final_outcome is ExitMergeOutcome.PROTECTIVE_EXIT:
            if self.decision_source is not ExitDecisionSource.PROTECTIVE:
                raise ExitMergeViolationError(
                    "итог PROTECTIVE_EXIT обязан нести источник "
                    f"PROTECTIVE; получено {self.decision_source}")
            if self.exit_type is None:
                raise ExitMergeViolationError(
                    "итог PROTECTIVE_EXIT обязан нести exit_type")
        elif self.final_outcome is ExitMergeOutcome.STRATEGIC_EXIT:
            if self.decision_source is not ExitDecisionSource.STRATEGIC:
                raise ExitMergeViolationError(
                    "итог STRATEGIC_EXIT обязан нести источник "
                    f"STRATEGIC; получено {self.decision_source}")
            if self.exit_type is None:
                raise ExitMergeViolationError(
                    "итог STRATEGIC_EXIT обязан нести exit_type")
        else:
            if self.decision_source is not None:
                raise ExitMergeViolationError(
                    f"итог {self.final_outcome.value} не является "
                    "исполнимым решением и не может нести "
                    f"decision_source; получено {self.decision_source}")
            if self.exit_type is not None:
                raise ExitMergeViolationError(
                    f"итог {self.final_outcome.value} не является "
                    "исполнимым решением и не может нести exit_type")

        object.__setattr__(
            self, "diagnostics",
            _normalize_diagnostics(self.diagnostics,
                                   error=ExitMergeViolationError))


def _merge_input_summary(result: ExitEvaluation) -> dict:
    """JSON-сводка входа объединения (ничего не теряется молча)."""
    return {
        "outcome": result.outcome.value,
        "decision_source": result.decision_source.value,
        "reason_code": result.reason_code,
        "exit_type": result.exit_type,
    }


def merge_exit_evaluations(strategic: Any,
                           protective: Any) -> ExitMergeResult:
    """Детерминированное объединение стратегического и защитного выходов.

    ЧИСТАЯ функция: одинаковые входные результаты всегда дают одинаковый
    итог (без времени, случайности, обращения к состоянию — ТЗ §3.3).

    Оба входа обязаны быть точного типа ExitEvaluation и согласованными
    по атрибуции (strategy_id, config_hash, figi попарно равны) —
    объединение результатов разных стратегий/конфигураций/инструментов
    запрещено. ВСЕ нарушения входа объединения дают единый тип ошибки
    ExitMergeViolationError (единая поверхность ошибок merge).

    Правила приоритета — таблица истинности EXIT_MERGE_RULES_VERSION
    (см. выше): защитный выход побеждает всегда; стратегический выход
    проходит только при защитном NO_EXIT; незавершённая оценка любого
    слоя подавляет ИСПОЛНИМЫЙ итог (fail-closed: итоговое решение не
    выносится), при этом информация обоих входов сохраняется в
    diagnostics.
    """
    try:
        validate_exit_evaluation(strategic)
        validate_exit_evaluation(protective)
    except ExitContractViolationError as exc:
        raise ExitMergeViolationError(
            "объединение запрещено: некорректный вход объединения "
            f"(ожидается точный тип ExitEvaluation): {exc}") from exc

    if (strategic.strategy_id, strategic.config_hash, strategic.figi) != \
            (protective.strategy_id, protective.config_hash,
             protective.figi):
        raise ExitMergeViolationError(
            "объединение запрещено: атрибуция стратегического и "
            "защитного результатов не совпадает — "
            f"strategic=({strategic.strategy_id!r}, "
            f"{strategic.config_hash[:8]}..., {strategic.figi!r}), "
            f"protective=({protective.strategy_id!r}, "
            f"{protective.config_hash[:8]}..., {protective.figi!r}); "
            "результаты разных стратегий/конфигураций/инструментов не "
            "объединяются")

    base_diagnostics = {
        "merge_rules_version": EXIT_MERGE_RULES_VERSION,
        "strategic": _merge_input_summary(strategic),
        "protective": _merge_input_summary(protective),
    }

    if protective.outcome is ExitOutcome.PROTECTIVE_EXIT:
        diagnostics = dict(base_diagnostics)
        if strategic.outcome is ExitOutcome.STRATEGIC_EXIT:
            diagnostics["note"] = "PROTECTIVE_PRIORITY_OVER_STRATEGIC_EXIT"
        elif strategic.outcome is ExitOutcome.EVALUATION_BLOCKED:
            diagnostics["note"] = \
                "PROTECTIVE_EXIT_WITH_STRATEGIC_EVALUATION_BLOCKED"
        return ExitMergeResult(
            strategy_id=strategic.strategy_id,
            config_hash=strategic.config_hash,
            figi=strategic.figi,
            final_outcome=ExitMergeOutcome.PROTECTIVE_EXIT,
            reason_code=protective.reason_code,
            decision_source=ExitDecisionSource.PROTECTIVE,
            exit_type=protective.exit_type,
            diagnostics=diagnostics)

    if protective.outcome is ExitOutcome.NO_EXIT:
        if strategic.outcome is ExitOutcome.STRATEGIC_EXIT:
            return ExitMergeResult(
                strategy_id=strategic.strategy_id,
                config_hash=strategic.config_hash,
                figi=strategic.figi,
                final_outcome=ExitMergeOutcome.STRATEGIC_EXIT,
                reason_code=strategic.reason_code,
                decision_source=ExitDecisionSource.STRATEGIC,
                exit_type=strategic.exit_type,
                diagnostics=base_diagnostics)
        if strategic.outcome is ExitOutcome.NO_EXIT:
            return ExitMergeResult(
                strategy_id=strategic.strategy_id,
                config_hash=strategic.config_hash,
                figi=strategic.figi,
                final_outcome=ExitMergeOutcome.NO_EXIT,
                reason_code="NO_EXIT_CONFIRMED",
                diagnostics=base_diagnostics)
        # Стратегический слой не смог дать безопасную оценку при
        # защитном NO_EXIT: итоговое решение не выносится (fail-closed).
        return ExitMergeResult(
            strategy_id=strategic.strategy_id,
            config_hash=strategic.config_hash,
            figi=strategic.figi,
            final_outcome=ExitMergeOutcome.INCOMPLETE_STRATEGIC_EVALUATION,
            reason_code=strategic.reason_code,
            diagnostics=base_diagnostics)

    # Защитный слой не смог дать безопасную оценку: исполнимый итог
    # не выносится при ЛЮБОМ стратегическом результате (fail-closed);
    # информация стратегического слоя сохраняется в diagnostics.
    return ExitMergeResult(
        strategy_id=strategic.strategy_id,
        config_hash=strategic.config_hash,
        figi=strategic.figi,
        final_outcome=ExitMergeOutcome.INCOMPLETE_PROTECTIVE_EVALUATION,
        reason_code=protective.reason_code,
        diagnostics=base_diagnostics)


# ---------------------------------------------------------------------------
# КООРДИНАТОР ВЫХОДОВ: интеграция со Stage B.1 (ТЗ Stage C §3.4–§3.5)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ExitDecisionReport:
    """Полный типизированный отчёт одного цикла оценки выхода.

    Содержит результат проверки цены, результаты обоих слоёв (None —
    если слой НЕ вызывался: при блокировке до вызова оценщиков), итог
    объединения и признак записи в состояние. Отчёт — контрактный
    объект, а не команда исполнения: он НЕ создаёт заявок и НЕ меняет
    исполнение (граница Stage C).
    """
    strategy_id: str
    config_hash: str
    figi: str
    price_check: PriceCheckResult
    merged: ExitMergeResult
    strategic_result: Optional[ExitEvaluation] = None
    protective_result: Optional[ExitEvaluation] = None
    state_updated: bool = False
    decided_at: str = ""

    def __post_init__(self) -> None:
        _validate_attribution(self.strategy_id, self.figi, self.config_hash,
                              ExitContractViolationError)
        if type(self.price_check) is not PriceCheckResult:
            raise ExitContractViolationError(
                "ExitDecisionReport.price_check должен быть точным типом "
                f"PriceCheckResult; получено {type(self.price_check).__name__}")
        if type(self.merged) is not ExitMergeResult:
            raise ExitContractViolationError(
                "ExitDecisionReport.merged должен быть точным типом "
                f"ExitMergeResult; получено {type(self.merged).__name__}")
        for name, value in (("strategic_result", self.strategic_result),
                            ("protective_result", self.protective_result)):
            if value is not None and type(value) is not ExitEvaluation:
                raise ExitContractViolationError(
                    f"ExitDecisionReport.{name} должен быть точным типом "
                    f"ExitEvaluation или None; получено "
                    f"{type(value).__name__}")
        if not isinstance(self.state_updated, bool):
            raise ExitContractViolationError(
                "ExitDecisionReport.state_updated должен быть bool")
        if self.decided_at:
            _validate_iso_timestamp(self.decided_at, "decided_at",
                                    ExitContractViolationError)
        else:
            raise ExitContractViolationError(
                "ExitDecisionReport.decided_at обязателен")

        evaluators_called = self.strategic_result is not None and \
            self.protective_result is not None
        if evaluators_called:
            # Атрибуция отчёта обязана совпадать с результатами слоёв.
            for name, value in (("strategic_result", self.strategic_result),
                                ("protective_result",
                                 self.protective_result)):
                if (value.strategy_id, value.config_hash, value.figi) != \
                        (self.strategy_id, self.config_hash, self.figi):
                    raise ExitContractViolationError(
                        f"атрибуция {name} не совпадает с атрибуцией "
                        "отчёта: подмена strategy_id/config_hash/figi "
                        "отклоняется")
            if self.merged.final_outcome is \
                    ExitMergeOutcome.INCOMPLETE_PRICE_EVALUATION:
                raise ExitContractViolationError(
                    "INCOMPLETE_PRICE_EVALUATION не может быть итогом при "
                    "вызванных оценщиках")
        else:
            if self.strategic_result is not None or \
                    self.protective_result is not None:
                raise ExitContractViolationError(
                    "оба слоя обязаны быть либо вызваны (оба результата "
                    "заданы), либо не вызваны (оба None): частичный вызов "
                    "запрещён")
            if self.merged.final_outcome is not \
                    ExitMergeOutcome.INCOMPLETE_PRICE_EVALUATION:
                raise ExitContractViolationError(
                    "если оценщики не вызывались, итог обязан быть "
                    "INCOMPLETE_PRICE_EVALUATION; получено "
                    f"{self.merged.final_outcome.value}")


class ExitDecisionCoordinator:
    """Координатор выхода: цена -> оценщики -> объединение -> состояние.

    Интеграция со Stage B.1 (ТЗ Stage C §3.5):
      * состояние изолировано по (strategy_id, FIGI): все операции идут
        через StrategyStateManager (точный тип), который выдаёт ТОЛЬКО
        состояние запрошенной пары;
      * config_hash проверяется: конфиг принимается ТОЛЬКО точного типа
        StrategyConfig; AttributionContext.from_config ПЕРЕПРОВЕРЯЕТ
        config_hash ИСХОДНЫМ алгоритмом Stage A.2.1 по фактическим
        параметрам (подмена хеша отклоняется ДО любой оценки);
        несовпадение config_hash сохранённого состояния —
        StateConfigMismatchError из Stage B.1 (без автопереноса);
      * глобальное изменяемое состояние НЕ используется; вторая система
        хранения НЕ создаётся (только StateStore через менеджер);
      * обновления состояния выполняются ТОЛЬКО через существующий
        атомарный API manager.update_state (атомарный read-modify-write
        Stage B.1); ошибки состояния пробрасываются как есть (не
        маскируются пустыми значениями).

    Fail-closed цена (ТЗ §3.4 + порядок Stage C.1):
      * price_required=True и цена отсутствует/некорректна/устарела —
        оценщики НЕ вызываются, состояние НЕ изменяется, возвращается
        отчёт с итогом INCOMPLETE_PRICE_EVALUATION и диагностикой;
      * нулевая цена не подставляется; последняя известная цена не
        используется (механизма подстановки НЕ существует);
      * если цена НЕ требуется (price_required=False), но ПЕРЕДАНА
        некорректная/устаревшая цена — она не дойдёт до оценщиков:
        fail-closed блокировка (мусорные данные не проходят молча);
      * ПОРЯДОК STAGE C.1: проверка цены выполняется СТРОГО ДО
        manager.get_state — get_state Stage B.1 создаёт запись при
        отсутствии, поэтому при блокирующей цене состояние НЕ
        запрашивается вовсе: новая запись не создаётся, существующая
        не изменяется (хранилище не получает побочных эффектов до
        прохождения price gate).

    Запись в состояние:
      * при ИСПОЛНИМОМ итоге (PROTECTIVE_EXIT / STRATEGIC_EXIT / NO_EXIT)
        в данные состояния пары через атомарный updater записывается
        ключ "last_exit_evaluation" (типизированная сводка решения);
      * при INCOMPLETE_* состояние НЕ изменяется вовсе (нельзя менять
        состояние так, будто выход состоялся, — ТЗ §3.4);
      * это запись КОНТРАКТНОГО решения, а не исполнение: заявок нет.
    """

    STATE_EXIT_EVALUATION_KEY = "last_exit_evaluation"

    def __init__(self,
                 *,
                 manager: Any,
                 strategic_evaluator: Any,
                 protective_evaluator: Any,
                 clock: Optional[Callable[[], str]] = None) -> None:
        if type(manager) is not StrategyStateManager:
            raise CoordinatorViolationError(
                "ExitDecisionCoordinator требует точный тип "
                f"StrategyStateManager (Stage B.1); получено "
                f"{type(manager).__name__}")
        for name, evaluator in (("strategic_evaluator", strategic_evaluator),
                                ("protective_evaluator",
                                 protective_evaluator)):
            method = getattr(evaluator, "evaluate_exit", None)
            if not callable(method):
                raise CoordinatorViolationError(
                    f"{name} обязан предоставлять вызываемый метод "
                    "evaluate_exit(request) -> ExitEvaluation; получено "
                    f"{type(evaluator).__name__}")
        self._manager = manager
        self._strategic_evaluator = strategic_evaluator
        self._protective_evaluator = protective_evaluator
        self._clock = clock or _utc_now_iso

    # --- внутренние операции --------------------------------------------------

    def _call_evaluator(self,
                        evaluator: Any,
                        source: ExitDecisionSource,
                        request: ExitEvaluationRequest,
                        decided_at: str) -> ExitEvaluation:
        """Вызов одного оценщика с конвертацией ВСЕХ проблем в типизиро-
        ванный fail-closed результат ЕГО источника.

        Граница безопасности — ПРОВЕРКА РЕЗУЛЬТАТА, а не тип оценщика:
        подкласс не может провести некорректный результат дальше.
        Исключение оценщика или некорректный/чужой результат
        конвертируются в EVALUATION_BLOCKED этого источника (выход не
        создаётся, ничего не исполняется).
        """
        strategy_id = request.strategy_id
        config_hash = request.config_hash
        figi = request.figi
        try:
            result = evaluator.evaluate_exit(request)
        except Exception as exc:  # noqa: BLE001 — конвертация в контракт
            return ExitEvaluation.evaluation_blocked(
                strategy_id, config_hash, figi, source,
                "EVALUATOR_RAISED",
                decided_at=decided_at,
                diagnostics={
                    "exception_type": type(exc).__name__,
                    "exception_message": str(exc)[:500],
                    "layer": source.value,
                    "detail": "исключение оценщика конвертировано в "
                              "явную невозможность безопасной оценки",
                })
        try:
            validate_exit_evaluation(
                result,
                expected_strategy_id=strategy_id,
                expected_config_hash=config_hash,
                expected_figi=figi,
            )
        except ExitContractViolationError as exc:
            return ExitEvaluation.evaluation_blocked(
                strategy_id, config_hash, figi, source,
                "INVALID_EVALUATOR_RESULT",
                decided_at=decided_at,
                diagnostics={
                    "received_type": type(result).__name__,
                    "detail": str(exc)[:500],
                    "layer": source.value,
                })
        return result

    def _record_exit_evaluation(self,
                                strategy_id: str,
                                config_hash: str,
                                figi: str,
                                merged: ExitMergeResult,
                                decided_at: str) -> None:
        """Запись КОНТРАКТНОГО решения в состояние через АТОМАРНЫЙ API
        Stage B.1 (manager.update_state, read-modify-write под замком
        хранилища).

        Ошибки состояния НЕ маскируются: пробрасываются как есть.
        Запись содержит сводку решения и полную атрибуцию; она НЕ
        является исполнением и не создаёт заявок.
        """
        record = {
            "outcome": merged.final_outcome.value,
            "decision_source": merged.decision_source.value
            if merged.decision_source is not None else None,
            "reason_code": merged.reason_code,
            "exit_type": merged.exit_type,
            "merge_rules_version": EXIT_MERGE_RULES_VERSION,
            "strategy_id": strategy_id,
            "config_hash": config_hash,
            "figi": figi,
            "decided_at": decided_at,
        }

        def _updater(current) -> Mapping[str, Any]:
            data = unfreeze(current.data)
            data[self.STATE_EXIT_EVALUATION_KEY] = record
            return data

        self._manager.update_state(
            strategy_id, figi,
            config_hash=config_hash,
            updater=_updater,
            now=decided_at,
        )

    # --- основной цикл ----------------------------------------------------------

    def evaluate_and_record(self,
                            *,
                            config: Any,
                            figi: Any,
                            price_required: bool,
                            price_max_age_seconds: Optional[float],
                            price: Any = None,
                            now: Optional[datetime] = None
                            ) -> ExitDecisionReport:
        """Один цикл: config/FIGI -> price gate -> состояние -> оценщики
        -> merge -> запись состояния.

        ПОРЯДОК ОПЕРАЦИЙ (Stage C.1): проверка цены выполняется СТРОГО
        ДО manager.get_state. Так как get_state Stage B.1 создаёт запись
        при отсутствии, блокирующая цена (отсутствующая/некорректная/
        устаревшая) возвращает INCOMPLETE_PRICE_EVALUATION БЕЗ доступа
        к хранилищу: новая запись состояния не создаётся, существующая
        не изменяется, оценщики не вызываются.

        price_required и price_max_age_seconds — ЯВНЫЕ обязательные
        параметры (скрытых умолчаний для торговых решений нет, ТЗ §5):
        None для price_max_age_seconds означает отключённую проверку
        устаревания явным решением оператора.
        """
        # 1. Контракт вызывающего кода (misuse — исключение).
        if type(config) is not StrategyConfig:
            raise CoordinatorViolationError(
                "ExitDecisionCoordinator требует точный тип StrategyConfig"
                f"; получено {type(config).__name__}")
        if not isinstance(price_required, bool):
            raise CoordinatorViolationError(
                "price_required должен быть bool (явное решение; скрытых "
                "умолчаний для торговых решений нет)")
        if price_max_age_seconds is not None:
            if isinstance(price_max_age_seconds, bool) or \
                    not isinstance(price_max_age_seconds, (int, float)) or \
                    not math.isfinite(float(price_max_age_seconds)) or \
                    price_max_age_seconds < 0:
                raise CoordinatorViolationError(
                    "price_max_age_seconds должен быть конечным "
                    f"неотрицательным числом или None; получено "
                    f"{price_max_age_seconds!r}")
        try:
            validate_figi(figi)
        except Exception as exc:
            raise CoordinatorViolationError(
                f"figi не проходит проверку Stage B: {exc}") from exc

        # 2. Проверенная атрибуция: config_hash перепроверяется ИСХОДНЫМ
        #    алгоритмом Stage A.2.1 (AttributionContext.from_config) —
        #    подмена config_hash отклоняется ДО любой оценки.
        try:
            AttributionContext.from_config(config)
        except Exception as exc:  # AttributionError (Stage A.2.1)
            raise CoordinatorViolationError(
                "конфигурация не прошла проверку атрибуции Stage A.2.1 "
                f"(config_hash против фактических параметров): {exc}"
            ) from exc
        strategy_id = config.strategy_id
        config_hash = config.config_hash

        now_dt = _validate_utc_datetime(now, "now",
                                        CoordinatorViolationError) \
            if now is not None else datetime.now(timezone.utc)
        decided_at = self._clock()

        # 3. Price gate ДО ЛЮБОГО доступа к состоянию (Stage C.1):
        #    manager.get_state Stage B.1 создаёт запись при отсутствии,
        #    поэтому при блокирующей цене состояние НЕ запрашивается
        #    вовсе — хранилище не получает побочных эффектов.
        price_check = check_price(
            price, expected_figi=figi, now=now_dt,
            max_age_seconds=price_max_age_seconds)

        blocked_before_evaluators = (
            (price_required and
             price_check.outcome is not PriceCheckOutcome.PRICE_OK)
            or (not price_required and price_check.outcome is
                PriceCheckOutcome.PRICE_INVALID)
            or (not price_required and price_check.outcome is
                PriceCheckOutcome.PRICE_STALE))

        if blocked_before_evaluators:
            # ТЗ §3.4 + Stage C.1: отдельный типизированный результат
            # невозможности безопасной оценки. Оценщики НЕ вызываются,
            # manager.get_state НЕ вызывается (запись состояния не
            # создаётся, существующая не изменяется), фиктивный выход
            # не создаётся.
            price_diagnostics = dict(price_check.diagnostics.to_mutable())
            price_diagnostics["evaluators_called"] = False
            price_diagnostics["price_required"] = price_required
            price_diagnostics["detail"] = \
                (price_diagnostics.get("detail") or "") + \
                "; выход не оценивался: безопасная оценка цены " \
                "невозможна, состояние не изменяется"
            merged = ExitMergeResult(
                strategy_id=strategy_id,
                config_hash=config_hash,
                figi=figi,
                final_outcome=ExitMergeOutcome.INCOMPLETE_PRICE_EVALUATION,
                reason_code=price_check.reason_code,
                diagnostics=price_diagnostics)
            return ExitDecisionReport(
                strategy_id=strategy_id,
                config_hash=config_hash,
                figi=figi,
                price_check=price_check,
                merged=merged,
                strategic_result=None,
                protective_result=None,
                state_updated=False,
                decided_at=decided_at,
            )

        # 4. Чтение состояния пары через менеджер Stage B.1 (изоляция по
        #    ключу; несовпадение config_hash — StateConfigMismatchError):
        #    ТОЛЬКО после прохождения price gate (Stage C.1).
        state = self._manager.get_state(
            strategy_id, figi, config_hash=config_hash)

        # 5. Запрос оценщикам: только проверенные значения; данные
        #    состояния пары — как есть (ImmutableMapping).
        request = ExitEvaluationRequest(
            strategy_id=strategy_id,
            config_hash=config_hash,
            figi=figi,
            state_data=state.data,
            price=price_check.price,
        )
        strategic_result = self._call_evaluator(
            self._strategic_evaluator, ExitDecisionSource.STRATEGIC,
            request, decided_at)
        protective_result = self._call_evaluator(
            self._protective_evaluator, ExitDecisionSource.PROTECTIVE,
            request, decided_at)

        # 6. Детерминированное объединение (защитный приоритет).
        merged = merge_exit_evaluations(strategic_result, protective_result)

        # 7. Запись в состояние ТОЛЬКО при исполнимом итоге; при
        #    INCOMPLETE_* состояние не изменяется вовсе.
        state_updated = False
        if merged.final_outcome in (
                ExitMergeOutcome.PROTECTIVE_EXIT,
                ExitMergeOutcome.STRATEGIC_EXIT,
                ExitMergeOutcome.NO_EXIT,
        ):
            self._record_exit_evaluation(
                strategy_id, config_hash, figi, merged, decided_at)
            state_updated = True

        return ExitDecisionReport(
            strategy_id=strategy_id,
            config_hash=config_hash,
            figi=figi,
            price_check=price_check,
            merged=merged,
            strategic_result=strategic_result,
            protective_result=protective_result,
            state_updated=state_updated,
            decided_at=decided_at,
        )
