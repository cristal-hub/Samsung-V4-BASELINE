# schema.py
# SAMSUNG V4 — NEW STRATEGY ENGINE. STAGE A.
# Описание и проверка структуры исторических параметров старой стратегии.
#
# ТЗ Этапа A (раздел 10), выполняемые этим модулем:
#   * наличие обязательных параметров; правильность типов; допустимые
#     диапазоны; отсутствие NaN и Infinity; отсутствие неизвестных ключей;
#     отсутствие скрытых fallback-значений — всё fail-closed;
#   * RSI: РАВНЫЕ верхний и нижний пороги ДОПУСТИМЫ — это соответствует
#     исходной семантике строгих сравнений "<" и ">" в strategy.py
#     (last_close < lower and rsi_val < RSI_OVERSOLD — BUY;
#      last_close > upper and rsi_val > RSI_OVERBOUGHT — SELL).
#     При равных порогах (исторический случай 50/50) обе ветки остаются
#     корректными и взаимоисключающими. ИНВЕРТИРОВАННЫЕ пороги
#     (OVERSOLD > OVERBOUGHT) — ошибка конфигурации;
#   * НЕ вводится ошибочное требование MIN_CANDLES_FOR_SIGNAL >=
#     TREND_FILTER_MA_PERIOD: готовность данных и валидность конфигурации —
#     разные понятия (проверяется тестом T-17);
#   * не вводятся НОВЫЕ торговые ограничения под видом валидации:
#     границы ниже — структурные домены величин (RSI/ADX в 0..100,
#     длины периодов >= 1), а не правила входа/выхода.
#
# STRATEGY LOGIC: UNCHANGED. Только проверка структуры параметров.

from __future__ import annotations

import math
from typing import Any, Dict, List, Mapping, Tuple

from strategy_api import (
    ParamSpec,
    ParamType,
    StrategyConfigError,
    normalize_params_by_specs,
    validate_params_against_specs,
)


def legacy_param_specs() -> Tuple[ParamSpec, ...]:
    """Структурные спецификации всех параметров старой стратегии.

    Состав в точности соответствует набору параметров, которыми baseline
    config.py управляет поведением strategy.py (входной сигнал), плюс
    VOLUME_CONFIRMATION_WINDOW. Параметры риск-менеджмента и исполнения
    сюда не входят (Этап D).
    """
    return (
        ParamSpec(
            name="MA_FAST_PERIOD", param_type=ParamType.INT,
            minimum=1,
            description="Период быстрой MA пересечения (исторически 9/5/2)."),
        ParamSpec(
            name="MA_SLOW_PERIOD", param_type=ParamType.INT,
            minimum=1,
            description="Период медленной MA пересечения (исторически 21/13/3)."),
        ParamSpec(
            name="TREND_FILTER_MA_PERIOD", param_type=ParamType.INT,
            minimum=1,
            description="Период MA фильтра тренда (исторически 100/50/5)."),
        ParamSpec(
            name="BB_PERIOD", param_type=ParamType.INT,
            minimum=1,
            description="Период полос Боллинджера (исторически 20)."),
        ParamSpec(
            name="BB_STD_DEV", param_type=ParamType.FLOAT,
            minimum=0.0, exclusive_maximum=True, maximum=None,
            description="Множитель СКО полос Боллинджера; >0 (исторически 2)."),
        ParamSpec(
            name="RSI_PERIOD", param_type=ParamType.INT,
            minimum=1,
            description="Период RSI (исторически 14)."),
        ParamSpec(
            name="RSI_OVERSOLD", param_type=ParamType.FLOAT,
            minimum=0.0, maximum=100.0,
            description="Нижний порог RSI для BUY; 0..100; равенство с "
                        "RSI_OVERBOUGHT допустимо (строгие сравнения)."),
        ParamSpec(
            name="RSI_OVERBOUGHT", param_type=ParamType.FLOAT,
            minimum=0.0, maximum=100.0,
            description="Верхний порог RSI для SELL; 0..100."),
        ParamSpec(
            name="MIN_CANDLES_FOR_SIGNAL", param_type=ParamType.INT,
            minimum=1,
            description="Минимум свечей для расчёта сигнала (готовность "
                        "ДАННЫХ, не ограничение конфигурации)."),
        ParamSpec(
            name="ADX_PERIOD", param_type=ParamType.INT,
            minimum=1,
            description="Период ADX (исторически 14)."),
        ParamSpec(
            name="ADX_TREND_THRESHOLD", param_type=ParamType.FLOAT,
            minimum=0.0, maximum=100.0,
            description="Порог ADX для режима TREND; домен 0..100."),
        ParamSpec(
            name="ADX_HYSTERESIS_CANDLES", param_type=ParamType.INT,
            minimum=1,
            description="Число новых свечей подтверждения смены режима ADX."),
        ParamSpec(
            name="VOLUME_SPIKE_FACTOR", param_type=ParamType.FLOAT,
            minimum=0.0,
            description="Множитель подтверждения объёма; >=0 "
                        "(0.0 отключает проверку, историческое значение)."),
        ParamSpec(
            name="VOLUME_CONFIRMATION_WINDOW", param_type=ParamType.INT,
            minimum=1,
            description="Окно усреднения объёма (исторически 20)."),
    )


SUPPORTED_PARAM_NAMES: Tuple[str, ...] = tuple(
    spec.name for spec in legacy_param_specs())


def validate_params(params: Mapping[str, Any]) -> List[str]:
    """Валидация параметров старой стратегии (fail-closed).

    Возвращает список ошибок (пустой список = валидно). Дополнительно к
    общей проверке структуры:
      * инвертированные RSI-пороги (OVERSOLD > OVERBOUGHT) — ошибка;
      * равные пороги — валидны (T-16; строгие сравнения "<" и ">");
      * соотношение MIN_CANDLES_FOR_SIGNAL и TREND_FILTER_MA_PERIOD
        СОЗНАТЕЛЬНО не проверяется (T-17): недостаток свечей — вопрос
        готовности данных, а не конфигурации.
    """
    errors = validate_params_against_specs(legacy_param_specs(), params)

    oversold = params.get("RSI_OVERSOLD")
    overbought = params.get("RSI_OVERBOUGHT")

    def _finite_number(value: Any) -> bool:
        return (
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            and math.isfinite(value)
        )

    if _finite_number(oversold) and _finite_number(overbought):
        if float(oversold) > float(overbought):
            errors.append(
                "RSI: инвертированные пороги недопустимы "
                f"(RSI_OVERSOLD={oversold} > RSI_OVERBOUGHT={overbought}); "
                "семантика строгих сравнений < и > делает такую "
                "конфигурацию бессмысленной")
        # Равные пороги ошибкой НЕ являются (T-16).
    return errors


def normalize_params(params: Mapping[str, Any]) -> Dict[str, Any]:
    """Нормализация параметров к каноническим типам (для config_hash).

    Вызывать ПОСЛЕ успешной validate_params. Ошибка нормализации
    оборачивается в StrategyConfigError (fail-closed).
    """
    try:
        return normalize_params_by_specs(legacy_param_specs(), params)
    except StrategyConfigError:
        raise
