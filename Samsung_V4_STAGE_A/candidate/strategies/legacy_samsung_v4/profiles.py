# profiles.py
# SAMSUNG V4 — NEW STRATEGY ENGINE. STAGE A.
# ИСТОРИЧЕСКИЕ профили старой стратегии Samsung V4.
#
# ТРЕБОВАНИЯ ТЗ (раздел 5), выполняемые этим файлом:
#   * значения SANDBOX_TEST / TECH_CHECK / CONSERVATIVE в точности совпадают
#     с исходным baseline (config.py, коммит 884cefd...); проверяется
#     автоматическим тестом G-5 (tests/test_stage_a_legacy_profiles.py);
#   * числовые параметры НЕ изменены и НЕ оптимизированы;
#   * ни один профиль НЕ выбирается активным по умолчанию;
#   * запуск нового движка НЕ требует выбора старого профиля;
#   * профили — исторические регрессионные данные, а не готовые стратегии
#     нового движка.
#
# FORCE_TRADE сознательно ОТСУТСТВУЕТ (ТЗ раздел 4): он не переносится в
# новую архитектуру ни как профиль, ни как режим, ни как тестовый
# переключатель; исторические упоминания в baseline config.py не
# расширяются и не используются тестами нового движка.

from __future__ import annotations

import json
import os
from functools import lru_cache
from typing import Any, Dict

PARAMS_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "params.json")

# Порядок кортежа — канонический порядок перечисления исторических профилей.
PROFILE_NAMES = ("SANDBOX_TEST", "TECH_CHECK", "CONSERVATIVE")

# Ключи, которые исторический профиль переопределяет относительно базовых
# значений config.py (в точности набор присваиваний профильных веток).
PROFILE_KEYS = (
    "ADX_TREND_THRESHOLD",
    "ADX_HYSTERESIS_CANDLES",
    "VOLUME_SPIKE_FACTOR",
    "MA_FAST_PERIOD",
    "MA_SLOW_PERIOD",
    "TREND_FILTER_MA_PERIOD",
    "RSI_OVERSOLD",
    "RSI_OVERBOUGHT",
    "MIN_CANDLES_FOR_SIGNAL",
)

# Значения СКОПИРОВАНЫ из baseline config.py дословно (идентичность — G-5).
PROFILES: Dict[str, Dict[str, Any]] = {
    "SANDBOX_TEST": {
        "ADX_TREND_THRESHOLD": 15,
        "ADX_HYSTERESIS_CANDLES": 1,
        "VOLUME_SPIKE_FACTOR": 0.0,
        "MA_FAST_PERIOD": 5,
        "MA_SLOW_PERIOD": 13,
        "TREND_FILTER_MA_PERIOD": 50,
        "RSI_OVERSOLD": 40,
        "RSI_OVERBOUGHT": 60,
        "MIN_CANDLES_FOR_SIGNAL": 60,
    },
    "TECH_CHECK": {
        "ADX_TREND_THRESHOLD": 20,
        "ADX_HYSTERESIS_CANDLES": 1,
        "VOLUME_SPIKE_FACTOR": 1.0,
        "MA_FAST_PERIOD": 9,
        "MA_SLOW_PERIOD": 21,
        "TREND_FILTER_MA_PERIOD": 100,
        "RSI_OVERSOLD": 30,
        "RSI_OVERBOUGHT": 70,
        "MIN_CANDLES_FOR_SIGNAL": 60,
    },
    "CONSERVATIVE": {
        "ADX_TREND_THRESHOLD": 25,
        "ADX_HYSTERESIS_CANDLES": 2,
        "VOLUME_SPIKE_FACTOR": 1.5,
        "MA_FAST_PERIOD": 9,
        "MA_SLOW_PERIOD": 21,
        "TREND_FILTER_MA_PERIOD": 100,
        "RSI_OVERSOLD": 30,
        "RSI_OVERBOUGHT": 70,
        "MIN_CANDLES_FOR_SIGNAL": 60,
    },
}


@lru_cache(maxsize=1)
def shared_params() -> Dict[str, Any]:
    """Базовые (непрофильные) исторические параметры из params.json.

    Возвращается копия; значения должны совпадать с базовыми присваиваниями
    baseline config.py (проверяет G-5). Кэш — чистое чтение статичного
    JSON-файла, недетерминизма нет.
    """
    with open(PARAMS_FILE, "r", encoding="utf-8") as handle:
        data = json.load(handle)
    shared = data.get("shared_params")
    if not isinstance(shared, dict) or not shared:
        raise ValueError(
            "params.json: отсутствует непустой объект shared_params")
    return dict(shared)


def build_regression_params(profile_name: str) -> Dict[str, Any]:
    """Эффективный набор исторических параметров для профиля.

    Семантика соответствует baseline config.py: базовые значения затем
    перекрываются профильными. Вызов ЯВНЫЙ: ни один профиль не подставляется
    автоматически и не выбирается по умолчанию. Возвращает копию.
    """
    if profile_name not in PROFILES:
        raise ValueError(
            f"неизвестный исторический профиль: {profile_name!r}; "
            f"известные: {PROFILE_NAMES}. "
            "FORCE_TRADE в новую архитектуру не переносится.")
    merged = dict(shared_params())
    merged.update(PROFILES[profile_name])
    return merged
