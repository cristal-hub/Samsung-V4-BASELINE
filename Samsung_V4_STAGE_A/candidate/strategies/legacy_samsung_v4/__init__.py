# strategies/legacy_samsung_v4/__init__.py
# SAMSUNG V4 — NEW STRATEGY ENGINE. STAGE A.
#
# Пакет изолированного REGRESSION-ONLY адаптера старой стратегии
# Samsung V4. Регистрация в реестре — ЯВНАЯ, при импорте пакета:
#   regression_only=True, activatable=False.
#
# Старая стратегия сохраняется как исторический эталон / источник golden
# tests / средство проверки обратной совместимости. Она НЕ является
# активной стратегией нового движка, НЕ выбирается автоматически и не
# доступна торговому режиму. FORCE_TRADE не переносится (ТЗ раздел 4).

from strategies import (
    StrategyRegistration,
    register_strategy,
)
from strategies.legacy_samsung_v4.strategy import (
    LegacyRegressionError,
    LegacySamsungV4Strategy,
)

__all__ = [
    "LegacySamsungV4Strategy",
    "LegacyRegressionError",
    "LEGACY_REGISTRATION",
]

LEGACY_REGISTRATION = StrategyRegistration(
    strategy=LegacySamsungV4Strategy(),
    activatable=False,
    regression_only=True,
    registered_at_stage="A",
)

register_strategy(LEGACY_REGISTRATION)
