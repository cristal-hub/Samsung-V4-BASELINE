# strategies/legacy_samsung_v4/strategy.py
# SAMSUNG V4 — NEW STRATEGY ENGINE. STAGE A.
#
# ИЗОЛИРОВАННЫЙ REGRESSION-ONLY АДАПТЕР СТАРОЙ СТРАТЕГИИ SAMSUNG V4.
#
# Роль (ТЗ Этапа A, разделы 3 и 7):
#   * старая стратегия НЕ кандидат нового движка; она сохраняется
#     исключительно как исторический эталон, источник golden tests и
#     средство проверки обратной совместимости;
#   * адаптер НЕ является активной стратегией нового торгового режима и
#     НЕ регистрируется как обычная доступная стратегия (реестр:
#     regression_only=True, activatable=False);
#   * никакой автоматической активации; выбор профиля — только явный
#     вызов build_regression_config(profile_name) из regression-harness.
#
# Изоляция:
#   * адаптер НЕ копирует торговую логику: он возвращает сигналы
#     оригинального модуля baseline strategy.py (StrategyManager), не
#     изменяя его файл;
#   * параметры на время регрессионного вызова временно устанавливаются
#     в модуль config (зависимость baseline-кода), затем восстанавливаются
#     строго в исходные значения (contextmanager, try/finally);
#   * production config.py НЕ изменяется; после вызова все значения
#     baseline (включая исторический PROFILE="FORCE_TRADE") нетронуты;
#   * тяжелые зависимости (pandas_ta_classic, модуль strategy baseline)
#     импортируются ЛЕНИВО — только при реальном регрессионном вызове,
#     чтобы загрузка реестра не требовала торговых зависимостей;
#   * FORCE_TRADE не переносится: profiles.py содержит только
#     SANDBOX_TEST / TECH_CHECK / CONSERVATIVE, и тесты нового движка
#     FORCE_TRADE не используют.
#
# STRATEGY LOGIC: UNCHANGED. RESEARCH ONLY. NO LIVE ORDERS. NO BROKER
# EXECUTION. NO SANDBOX EXECUTION.

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator, List, Mapping, Optional, Tuple

import strategy_api
from strategy_api import (
    ActivationMode,
    EntrySignalInput,
    ParamSpec,
    Signal,
    SignalDirection,
    Strategy,
    StrategyConfig,
    StrategyConfigError,
    StrategyContractError,
    compute_config_hash,
)

from strategies.legacy_samsung_v4 import profiles, schema


class LegacyRegressionError(StrategyContractError):
    """Нарушение регрессионной изоляции адаптера (fail-closed)."""


_STRATEGY_ID = "legacy_samsung_v4"
# Версия старой стратегии — из шапки baseline strategy.py (Tsclp_v2.0).
_STRATEGY_VERSION = "tsclp_v2.0"


@contextmanager
def _override_legacy_config(params: Mapping[str, Any]) -> Iterator[None]:
    """Временно устанавливает параметры в baseline-модуль config.

    Используется ТОЛЬКО regression-harness'ом. Гарантии:
      * до входа запоминаются исходные значения всех затрагиваемых
        атрибутов (включая ОТСУТСТВИЕ атрибута);
      * при любом исходе (успех/исключение) значения восстанавливаются
        строго к исходным (finally);
      * модуль config.py как файл не изменяется — меняются только
        атрибуты уже загруженного модуля на время вызова.
    """
    import config as legacy_config

    saved: List[Tuple[str, Any, bool]] = []
    try:
        for name, value in params.items():
            saved.append((name, getattr(legacy_config, name, None),
                          hasattr(legacy_config, name)))
            setattr(legacy_config, name, value)
        yield
    finally:
        for name, old_value, existed in reversed(saved):
            if existed:
                setattr(legacy_config, name, old_value)
            else:
                try:
                    delattr(legacy_config, name)
                except AttributeError:
                    pass


class LegacySamsungV4Strategy(Strategy):
    """Regression-only адаптер старой стратегии Samsung V4 (Tsclp_v2.0)."""

    strategy_id = _STRATEGY_ID
    strategy_version = _STRATEGY_VERSION
    description = (
        "Историческая стратегия Samsung V4 (Tsclp_v2.0) — изолированный "
        "регрессионный адаптер. НЕ является стратегией нового торгового "
        "режима; используется для golden tests (G-1), проверки идентичности "
        "исторических профилей (G-5) и обратной совместимости.")
    activation_mode = ActivationMode.REGRESSION_ONLY

    # --- контракт: описание и валидация параметров -------------------------

    def param_specs(self) -> Tuple[ParamSpec, ...]:
        return schema.legacy_param_specs()

    def validate_params(self, params: Mapping[str, Any]) -> List[str]:
        return schema.validate_params(params)

    def normalize_params(self, params: Mapping[str, Any]) -> dict:
        return schema.normalize_params(params)

    def default_params(self) -> Mapping[str, Any]:
        # Никакого неявного профиля и никакой автоподстановки: параметры
        # задаются ТОЛЬКО явным выбором исторического профиля.
        raise StrategyConfigError(
            "legacy_samsung_v4: параметры по умолчанию не объявлены; "
            "используйте build_regression_config(profile_name) с ЯВНЫМ "
            "историческим профилем (SANDBOX_TEST / TECH_CHECK / "
            "CONSERVATIVE); автоподстановка запрещена (no silent defaults)")

    # --- регрессионная конфигурация (единственный легальный путь) ----------

    def build_regression_config(self, profile_name: str) -> StrategyConfig:
        """Явно строит конфигурацию для regression-harness по профилю.

        Единственный способ получить usable StrategyConfig адаптера:
        origin='regression_harness'. evaluate_entry отклоняет любую
        другую конфигурацию (fail-closed). FORCE_TRADE среди профилей
        отсутствует — попытка запросить его даст ValueError.
        """
        params = profiles.build_regression_params(profile_name)
        errors = self.validate_params(params)
        if errors:
            raise StrategyConfigError(
                "исторические параметры профиля "
                f"{profile_name} невалидны: " + "; ".join(errors))
        normalized = self.normalize_params(params)
        config_hash = compute_config_hash(
            self.strategy_id, self.strategy_version, normalized)
        return StrategyConfig(
            strategy_id=self.strategy_id,
            strategy_version=self.strategy_version,
            params=normalized,
            config_hash=config_hash,
            origin="regression_harness",
            metadata={
                "profile": profile_name,
                "params_source": (
                    "strategies/legacy_samsung_v4/profiles.py + params.json"),
            },
        )

    def get_config(self, params, *, origin: str = "engine", metadata=None):
        """Контрактный get_config переопределён: только regression-origin.

        Адаптер не является стратегией торгового режима, поэтому конфигурация
        с origin='engine' запрещена (fail-closed).
        """
        if origin != "regression_harness":
            raise LegacyRegressionError(
                "legacy_samsung_v4 — regression-only стратегия: origin="
                f"{origin!r} запрещён; используйте build_regression_config("
                "profile_name)")
        return super().get_config(
            params, origin=origin, metadata=metadata)

    # --- входной сигнал (только regression-конфигурация) -------------------

    def evaluate_entry(self,
                       signal_input: EntrySignalInput,
                       config: StrategyConfig) -> Signal:
        """Мост к оригинальной логике baseline strategy.py.

        Изоляция: логика НЕ скопирована и НЕ переизобретена — вызывается
        оригинальный StrategyManager при временных параметрах профиля.
        """
        if config.origin != "regression_harness":
            raise LegacyRegressionError(
                "evaluate_entry запрещён для конфигурации с origin="
                f"{config.origin!r}: legacy-стратегия исполняется только "
                "в regression-harness (см. build_regression_config)")
        if config.strategy_id != self.strategy_id:
            raise LegacyRegressionError(
                "конфигурация принадлежит другой стратегии: "
                f"{config.strategy_id!r}")

        raw_signal, raw_reason = self._legacy_get_signal(
            config.params,
            signal_input.candles,
            signal_input.last_price,
            drop_incomplete=signal_input.drop_incomplete,
        )

        try:
            direction = SignalDirection(raw_signal)
        except ValueError as exc:
            raise LegacyRegressionError(
                f"baseline-модуль вернул неизвестный сигнал: "
                f"{raw_signal!r}") from exc

        candle_time: Optional[str] = None
        candles = signal_input.candles
        if candles is not None and getattr(candles, "index", None) is not None \
                and len(candles) > 0:
            candle_time = str(candles.index[-1])

        return Signal(
            strategy_id=self.strategy_id,
            config_hash=config.config_hash,
            direction=direction,
            reason=str(raw_reason),
            figi=signal_input.figi,
            ticker=signal_input.ticker,
            candle_time=candle_time,
            metadata={
                "profile": config.metadata.get("profile"),
                "origin": "regression_harness",
            },
        )

    # --- внутренний мост к baseline-модулю ----------------------------------

    def _legacy_get_signal(self,
                           params: Mapping[str, Any],
                           candles_df: Any,
                           last_price: float,
                           *,
                           drop_incomplete: bool = False
                           ) -> Tuple[str, str]:
        """Вызов ОРИГИНАЛЬНОЙ логики baseline strategy.py без её изменения.

        Импорты ленивые: baseline strategy.py тянет pandas_ta_classic;
        реестр и конфигурация движка должны работать без них.
        """
        import config as legacy_config  # baseline config.py (не изменяется)
        import strategy as legacy_strategy_module  # baseline strategy.py

        with _override_legacy_config(params):
            manager = legacy_strategy_module.StrategyManager()
            return manager.get_signal(
                candles_df,
                last_price,
                drop_incomplete=drop_incomplete,
            )

    # --- служебное ----------------------------------------------------------

    def baseline_config_profile_untouched(self) -> str:
        """Диагностика изоляции: текущее значение config.PROFILE.

        Тесты проверяют, что после регрессионных вызовов baseline-состояние
        (в том числе исторический PROFILE="FORCE_TRADE") не изменено.
        Метод ничего не меняет.
        """
        import config as legacy_config
        return str(getattr(legacy_config, "PROFILE", "?"))
