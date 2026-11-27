# strategies/__init__.py
# SAMSUNG V4 — NEW STRATEGY ENGINE. STAGE A.
# Пространство стратегий нового движка и явный реестр.
#
# ПРИНЦИПЫ (обязательные, ТЗ Этапа A):
#   * РЕГИСТРАЦИЯ ТОЛЬКО ЯВНАЯ: стратегия попадает в реестр только
#     явным вызовом register_strategy из собственного пакета; никакого
#     автосканирования модулей и автоматической регистрации нет.
#   * АВТОВЫБОР СТРАТЕГИИ ЗАПРЕЩЁН: реестр никогда не выбирает активную
#     стратегию; выбор делает только владелец проекта через
#     engine.json / переменную окружения ACTIVE_STRATEGY (engine_config.py).
#   * fail-closed: стратегия по умолчанию регистрируется как
#     regression_only (неактивируемая); для торговли нужен явный
#     TRADING_ALLOWED + activatable=True.
#   * Старая стратегия Samsung V4 НЕ является стратегией нового торгового
#     режима: она зарегистрирована отдельно с regression_only=True и
#     activatable=False (см. legacy_samsung_v4).
#
# На Этапе A активируемых стратегий НЕТ: activatable_strategy_ids()
# возвращает пустой кортеж — торговый режим невозможен по построению.

from dataclasses import dataclass
from typing import Dict, Optional, Tuple

import strategy_api


class StrategyRegistryError(Exception):
    """Ошибка реестра стратегий (fail-closed)."""


@dataclass(frozen=True)
class StrategyRegistration:
    """Явная запись реестра.

    activatable    — стратегия доступна для ВЫБОРА в торговый режим
                     (требует activation_mode == TRADING_ALLOWED);
    regression_only— стратегия предназначена только для регрессионных
                     проверок (требует activation_mode == REGRESSION_ONLY);
    registered_at_stage — этап, на котором выполнена регистрация.
    """
    strategy: strategy_api.Strategy
    activatable: bool
    regression_only: bool
    registered_at_stage: str


_registry: Dict[str, StrategyRegistration] = {}


def register_strategy(registration: StrategyRegistration,
                      *,
                      replace: bool = False) -> None:
    """Явная регистрация стратегии. Дубликаты запрещены (fail-closed)."""
    if not isinstance(registration, StrategyRegistration):
        raise StrategyRegistryError("ожидается StrategyRegistration")
    strategy = registration.strategy
    if not strategy.strategy_id:
        raise StrategyRegistryError("strategy_id пуст — регистрация отклонена")
    if registration.activatable and registration.regression_only:
        raise StrategyRegistryError(
            f"{strategy.strategy_id}: activatable и regression_only "
            "взаимоисключающи")
    if registration.activatable and \
            strategy.activation_mode is not strategy_api.ActivationMode.TRADING_ALLOWED:
        raise StrategyRegistryError(
            f"{strategy.strategy_id}: activatable=True требует явного "
            "activation_mode=TRADING_ALLOWED")
    if registration.regression_only and \
            strategy.activation_mode is not strategy_api.ActivationMode.REGRESSION_ONLY:
        raise StrategyRegistryError(
            f"{strategy.strategy_id}: regression_only=True требует "
            "activation_mode=REGRESSION_ONLY")
    if strategy.strategy_id in _registry and not replace:
        raise StrategyRegistryError(
            f"{strategy.strategy_id}: стратегия уже зарегистрирована")
    _registry[strategy.strategy_id] = registration


def is_known(strategy_id: str) -> bool:
    return strategy_id in _registry


def is_activatable(strategy_id: str) -> bool:
    registration = _registry.get(strategy_id)
    if registration is None:
        return False
    return registration.activatable and not registration.regression_only


def known_strategy_ids() -> Tuple[str, ...]:
    return tuple(sorted(_registry))


def activatable_strategy_ids() -> Tuple[str, ...]:
    """Стратегии, доступные для выбора в торговый режим.

    На Этапе A ВСЕГДА пуст (новых торговых стратегий ещё нет; старая
    стратегия зарегистрирована как regression-only).
    """
    return tuple(sorted(
        strategy_id for strategy_id, registration in _registry.items()
        if registration.activatable and not registration.regression_only
    ))


def get_registration(strategy_id: str) -> Optional[StrategyRegistration]:
    return _registry.get(strategy_id)


def get_strategy(strategy_id: str) -> strategy_api.Strategy:
    registration = _registry.get(strategy_id)
    if registration is None:
        raise StrategyRegistryError(
            f"неизвестная стратегия: {strategy_id}; "
            f"известные: {known_strategy_ids()}")
    return registration.strategy


# --- Явная регистрация пакетов стратегий (без автосканирования) -----------
# На Этапе A зарегистрирован ТОЛЬКО изолированный regression-адаптер старой
# стратегии. Никакой другой регистрации нет; FORCE_TRADE не переносится.
from . import legacy_samsung_v4  # noqa: E402,F401  (явная регистрация)
