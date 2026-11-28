# engine_config.py
# SAMSUNG V4 — NEW STRATEGY ENGINE. STAGE A.
# Загрузка, объединение, проверка и нормализация конфигурации нового движка.
#
# ИСТОЧНИКИ И ПРИОРИТЕТ ACTIVE_STRATEGY (документировано, ТЗ раздел 6):
#   1. Основной источник — engine.json, расположенный рядом с runtime.env
#      (.env), т.е. в корневом каталоге движка рядом с config.py/main.py.
#   2. Переменная окружения ACTIVE_STRATEGY может ПЕРЕОПРЕДЕЛЯТЬ значение
#      JSON: если она задана непустым значением — используется она.
#   3. Если переменная окружения не задана (или пуста) — используется
#      значение JSON.
#   4. Если значение отсутствует в ОБОИХ источниках — состояние
#      UNCONFIGURED: запуск торгового режима ЗАПРЕЩЁН; допустимы только
#      offline-тесты и проверка архитектуры.
#   5. Неизвестное ACTIVE_STRATEGY — ошибка конфигурации (fail-closed).
#   6. Никакого автоматического выбора стратегии; никаких скрытых
#      fallback-значений; пустые значения НЕ заменяются умолчаниями.
#
# ПОВЕДЕНИЕ НА КРАЙНИЕ СЛУЧАИ (документировано, fail-closed):
#   * engine.json отсутствует      -> предупреждение; источник — только env;
#                                     при пустом env -> UNCONFIGURED;
#   * engine.json битый (не JSON)  -> CONFIG_ERROR (env НЕ «спасает»);
#   * engine.json не объект        -> CONFIG_ERROR;
#   * ACTIVE_STRATEGY в JSON: null или пустая строка -> значение не задано;
#   * ACTIVE_STRATEGY не строка (число/список/объект/bool) -> CONFIG_ERROR;
#   * env ACTIVE_STRATEGY не строка -> CONFIG_ERROR;
#   * env ACTIVE_STRATEGY из одних пробелов -> считается НЕ заданной
#     (переход к JSON; документировано явно);
#   * неизвестные ключи engine.json -> предупреждения (поведение не влияют);
#   * ключи-комментарии с префиксом "_" игнорируются.
#
# РЕЕСТР СТРАТЕГИЙ (strategies/__init__.py):
#   * известная, но regression-only стратегия (legacy_samsung_v4) НЕ может
#     быть выбрана в торговый режим -> CONFIG_ERROR;
#   * на Этапе A activatable_strategy_ids() пуст: ЛЮБОЕ непустое значение
#     ACTIVE_STRATEGY даёт CONFIG_ERROR — торговля невозможна по построению.
#
# config_hash: стратегия вычисляет его по контракту strategy_api
# (sha256 по каноническому JSON; секреты и runtime.env не участвуют).
#
# АТРИБУЦИЯ (Stage A.1): EngineConfig несёт неизменяемый AttributionContext
# (strategy_id, config_hash) для валидной CONFIGURED-конфигурации; контекст
# выводится ЯВНО из StrategyConfig (AttributionContext.from_config) и
# передаётся явно в фабрику атрибутированных объектов (AttributionFactory).
# Глобального контекста атрибуции не существует; компоненты движка
# получают контекст только через явные зависимости.
#
# STRATEGY LOGIC: UNCHANGED. RESEARCH ONLY. NO LIVE ORDERS.

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Mapping, Optional, Tuple

import strategy_api
import strategies as strategies_registry
from attribution import AttributionContext


ENGINE_JSON_FILENAME = "engine.json"
ENV_ACTIVE_STRATEGY = "ACTIVE_STRATEGY"

_JSON_COMMENT_PREFIX = "_"
_JSON_KNOWN_KEYS = frozenset({
    "ACTIVE_STRATEGY",
    "ENGINE_SCHEMA_VERSION",
})


class EngineConfigError(Exception):
    """Конфигурация движка невалидна: торговый режим запрещён (fail-closed)."""


class ConfigSource(str, Enum):
    ENVIRONMENT = "environment"
    ENGINE_JSON = "engine_json"
    NONE = "none"


class EngineStatus(str, Enum):
    UNCONFIGURED = "UNCONFIGURED"   # стратегия не выбрана; offline разрешён
    CONFIGURED = "CONFIGURED"       # явный выбор валидной активируемой стратегии
    CONFIG_ERROR = "CONFIG_ERROR"   # fail-closed: конфигурация невалидна


@dataclass(frozen=True)
class EngineConfig:
    """Итог нормализации конфигурации движка (неизменяемый отчёт)."""
    status: EngineStatus
    active_strategy: Optional[str]
    active_strategy_source: ConfigSource
    engine_json_path: str
    engine_json_present: bool
    errors: Tuple[str, ...] = ()
    warnings: Tuple[str, ...] = ()
    attribution: Optional[AttributionContext] = None

    @property
    def trading_allowed(self) -> bool:
        """Торговый режим разрешён ТОЛЬКО в состоянии CONFIGURED."""
        return self.status is EngineStatus.CONFIGURED


def default_engine_json_path() -> str:
    """engine.json рядом с runtime.env (.env) — корневой каталог движка.

    config.py читает runtime.env из рабочего каталога движка; engine.json
    располагается в том же каталоге (рядом с config.py/main.py).
    """
    return os.path.join(
        os.path.dirname(os.path.abspath(__file__)), ENGINE_JSON_FILENAME)


def load_engine_config(*,
                       engine_json_path: Optional[str] = None,
                       environ: Optional[Mapping[str, str]] = None
                       ) -> EngineConfig:
    """Загружает и проверяет конфигурацию движка (fail-closed).

    Функция НИКОГДА не выбирает стратегию сама и не подставляет
    умолчания. Результат — статус + явные ошибки/предупреждения.
    Исключения наружу не выбрасываются: все ошибки отражены в статусе
    CONFIG_ERROR и списке errors.
    """
    env: Dict[str, str] = dict(os.environ if environ is None else environ)
    path = engine_json_path or default_engine_json_path()

    errors: list = []
    warnings: list = []

    # --- 1. engine.json ------------------------------------------------------
    json_present = os.path.isfile(path)
    json_active_raw: Any = None
    json_has_value = False

    if json_present:
        try:
            with open(path, "r", encoding="utf-8") as handle:
                raw_text = handle.read()
            data = json.loads(raw_text)
        except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
            return _config_error(
                path=path,
                json_present=True,
                errors=(
                    f"engine.json не читается как JSON ({path}): {exc}; "
                    "fail-closed: переменная окружения не «спасает» битый "
                    "конфигурационный файл",),
            )
        if not isinstance(data, dict):
            return _config_error(
                path=path,
                json_present=True,
                errors=(f"engine.json должен быть JSON-объектом, получено "
                        f"{type(data).__name__}",),
            )
        for key in data:
            if key.startswith(_JSON_COMMENT_PREFIX):
                continue
            if key not in _JSON_KNOWN_KEYS:
                warnings.append(
                    f"engine.json: неизвестный ключ {key!r} игнорируется "
                    "(поведение движка от него не зависит)")
        if "ACTIVE_STRATEGY" in data:
            json_active_raw = data["ACTIVE_STRATEGY"]
    else:
        warnings.append(
            f"engine.json не найден ({path}); источник — только переменная "
            "окружения ACTIVE_STRATEGY")

    # --- 2. environment --------------------------------------------------------
    env_raw = env.get(ENV_ACTIVE_STRATEGY)
    env_value: Optional[str] = None
    if env_raw is not None:
        if not isinstance(env_raw, str):
            return _config_error(
                path=path, json_present=json_present,
                errors=(
                    f"{ENV_ACTIVE_STRATEGY} в окружении должен быть строкой, "
                    f"получено {type(env_raw).__name__}",),
            )
        stripped = env_raw.strip()
        if stripped == "":
            warnings.append(
                f"{ENV_ACTIVE_STRATEGY} задана, но пуста — считается "
                "не заданной (приоритет переходит к engine.json)")
        else:
            env_value = stripped

    # --- 3. нормализация JSON-значения -----------------------------------------
    if json_present and "ACTIVE_STRATEGY" in data:
        if json_active_raw is None:
            pass  # явное null = значение не задано (документировано)
        elif isinstance(json_active_raw, str):
            stripped_json = json_active_raw.strip()
            if stripped_json == "":
                warnings.append(
                    "engine.json: ACTIVE_STRATEGY пустая строка — "
                    "считается не заданной")
            else:
                json_active_raw = stripped_json
                json_has_value = True
        else:
            return _config_error(
                path=path, json_present=json_present,
                errors=(
                    "engine.json: ACTIVE_STRATEGY должен быть строкой или "
                    f"null, получено {type(json_active_raw).__name__}",),
            )

    # --- 4. объединение источников (env > json) ---------------------------------
    if env_value is not None:
        effective = env_value
        source = ConfigSource.ENVIRONMENT
    elif json_has_value:
        effective = json_active_raw
        source = ConfigSource.ENGINE_JSON
    else:
        effective = None
        source = ConfigSource.NONE

    if effective is None:
        warnings.append(
            "ACTIVE_STRATEGY не задана ни в окружении, ни в engine.json — "
            "состояние UNCONFIGURED: торговый режим запрещён, разрешены "
            "только offline-тесты и проверка архитектуры")
        return EngineConfig(
            status=EngineStatus.UNCONFIGURED,
            active_strategy=None,
            active_strategy_source=ConfigSource.NONE,
            engine_json_path=path,
            engine_json_present=json_present,
            errors=(),
            warnings=tuple(warnings),
            attribution=None,
        )

    # --- 5. проверка выбранного значения против реестра --------------------------
    known = strategies_registry.known_strategy_ids()
    activatable = strategies_registry.activatable_strategy_ids()

    if effective not in known:
        errors.append(
            f"ACTIVE_STRATEGY={effective!r} — неизвестная стратегия "
            f"(источник: {source.value}); известные: {list(known)}; "
            "автоматический выбор запрещён")
        return _config_error(path=path, json_present=json_present,
                             errors=errors, warnings=warnings)

    registration = strategies_registry.get_registration(effective)
    if not strategies_registry.is_activatable(effective):
        reason = "regression-only (исторический эталон, не для торговли)" \
            if registration.regression_only else "не активируема"
        errors.append(
            f"ACTIVE_STRATEGY={effective!r} известна, но {reason}; "
            f"активируемые стратегии: {list(activatable)}; выбор торгового "
            "режима отклонён (fail-closed)")
        return _config_error(path=path, json_present=json_present,
                             errors=errors, warnings=warnings)

    # --- 6. CONFIGURED: валидная активируемая стратегия (Этап B+ сценарий) -------
    strategy = strategies_registry.get_strategy(effective)
    try:
        default_params = dict(strategy.default_params())
        config = strategy.get_config(default_params, origin="engine")
    except (strategy_api.StrategyContractError, ValueError) as exc:
        errors.append(
            f"стратегия {effective!r} отклонила собственные параметры по "
            f"умолчанию: {exc}")
        return _config_error(path=path, json_present=json_present,
                             errors=errors, warnings=warnings)

    return EngineConfig(
        status=EngineStatus.CONFIGURED,
        active_strategy=effective,
        active_strategy_source=source,
        engine_json_path=path,
        engine_json_present=json_present,
        errors=(),
        warnings=tuple(warnings),
        # Stage A.1: единый явный механизм — контекст выводится из
        # StrategyConfig методом AttributionContext.from_config.
        attribution=AttributionContext.from_config(config),
    )


def _config_error(*, path: str,
                  json_present: bool,
                  errors: Tuple[str, ...],
                  warnings: Tuple[str, ...] = ()) -> EngineConfig:
    return EngineConfig(
        status=EngineStatus.CONFIG_ERROR,
        active_strategy=None,
        active_strategy_source=ConfigSource.NONE,
        engine_json_path=path,
        engine_json_present=json_present,
        errors=tuple(errors),
        warnings=tuple(warnings),
        attribution=None,
    )


def require_trading_ready(engine_config: EngineConfig) -> AttributionContext:
    """Шлюз торгового режима: валиден только статус CONFIGURED.

    Этап A возвращает ошибку ВСЕГДА (активируемых стратегий нет).
    Этап B+ вызывает этот шлюз перед любым торговым запуском; для
    UNCONFIGURED / CONFIG_ERROR торговля запрещена (fail-closed).
    """
    if not engine_config.trading_allowed or \
            engine_config.attribution is None:
        detail = "; ".join(engine_config.errors) if engine_config.errors \
            else "ACTIVE_STRATEGY не задана"
        raise EngineConfigError(
            f"торговый режим запрещён (status={engine_config.status.value}): "
            f"{detail}")
    return engine_config.attribution
