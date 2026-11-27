# tests/stage_a_golden_tools.py
# SAMSUNG V4 — NEW STRATEGY ENGINE. STAGE A.
# Вспомогательный модуль ТЕСТОВ ЭТАПА A (не production-код, не test_*):
#   * детерминированные свечные fixture для golden-теста G-1;
#   * канонизация fixture и контроль целостности (sha256);
#   * генератор tests/fixtures/legacy_golden_signals.json (запускается
#     вручную: python -m tests.stage_a_golden_tools из каталога candidate).
#
# ТЗ: тесты только offline; реальные сетевые обращения, брокерские
# подключения, Sandbox-заявки и LIVE-заявки запрещены. Модуль ни к чему
# не подключается и ничего не торгует.

from __future__ import annotations

import hashlib
import json
import os
import sys

import numpy as np
import pandas as pd

import strategy_api as sa
from strategies.legacy_samsung_v4 import profiles
from strategies.legacy_samsung_v4.strategy import LegacySamsungV4Strategy

GOLDEN_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "fixtures", "legacy_golden_signals.json")


# ---------------------------------------------------------------------------
# Детерминированные fixture (без случайных чисел: чистая математика форм)
# ---------------------------------------------------------------------------

def _base_frame(close, volume):
    n = len(close)
    wick = np.abs(np.sin(np.arange(n) * 0.7)) * 0.5
    high = close + wick + 0.15
    low = close - wick - 0.15
    open_ = (high + low) / 2.0
    idx = pd.date_range("2024-01-02 10:00", periods=n, freq="5min")
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close,
         "volume": volume}, index=idx)


def fixture_a_long_rise_reversal():
    """Долгий подъём + плато + резкий разворот вниз на последней свече.

    SANDBOX_TEST -> SELL (пересечение MA(5/13) вниз + фильтр MA50 +
    подтверждение объёма); TECH_CHECK/CONSERVATIVE -> HOLD
    ("фильтр MA100 не пройден") — ветка отклонения по тренд-фильтру.
    """
    p1 = np.full(40, 180.0) + np.sin(np.arange(40) * 0.3) * 0.8
    p2 = 180.0 + np.linspace(0, 70, 70) + np.sin(np.arange(70) * 0.5) * 0.6
    p3 = np.full(12, 250.0)
    close = np.concatenate([p1, p2, p3[:-1], [222.0]])
    volume = np.concatenate([np.full(40, 2000.0), np.full(70, 2200.0),
                             np.full(11, 2000.0), [6000.0]])
    return _base_frame(close, volume)


def fixture_b_rise_dip_reversal():
    """Подъём -> плато -> малый откат -> импульс вверх на последней свече.

    SANDBOX_TEST -> BUY (свежее пересечение MA(5/13) вверх); TECH_CHECK/
    CONSERVATIVE -> HOLD ("Нет пересечения MA").
    """
    p1 = np.full(40, 180.0) + np.sin(np.arange(40) * 0.3) * 0.8
    p2 = 180.0 + np.linspace(0, 60, 60) + np.sin(np.arange(60) * 0.5) * 0.6
    p3 = np.full(8, 240.0)
    p4 = 240.0 - np.array([1.0, 2.0, 3.0])
    close = np.concatenate([p1, p2, p3, p4, [247.0]])
    volume = np.concatenate([np.full(40, 2000.0), np.full(60, 2200.0),
                             np.full(8, 2000.0), np.full(3, 2000.0),
                             [6500.0]])
    return _base_frame(close, volume)


def fixture_c_range_oversold():
    """Боковик + прокол нижней полосы BB (CONSERVATIVE -> RANGE/BB-ветка)."""
    n = 130
    t = np.arange(n)
    part = (200.0 + 2.5 * np.sign(np.sin(t * 0.35)) * np.abs(np.sin(t * 0.9))
            + 1.0 * np.sin(t * 2.1))
    drop = 200.0 - 2.5 - np.linspace(0, 10, 10)
    close = np.concatenate([part, drop])
    volume = np.concatenate([np.full(n, 2000.0), np.full(10, 2400.0)])
    volume[-1] = 7000.0
    return _base_frame(close, volume)


def fixture_d_short_history():
    """Короткая история: готовность данных — НЕ ошибка конфигурации.

    Ожидается HOLD 'Недостаточно данных' для всех профилей (T-17).
    """
    n = 30
    close = 200.0 + np.cumsum(np.sin(np.arange(n) * 0.4))
    volume = np.full(n, 2000.0)
    df = _base_frame(close, volume)
    df["is_complete"] = True
    return df


def fixture_e_incomplete_last():
    """is_complete=False на последней свече; вызов с drop_incomplete=True.

    Последняя свеча удаляется подготовкой данных, сигнал считается по
    предыдущей свече (ветка _prepare_dataframe baseline-логики).
    """
    df = fixture_c_range_oversold().copy()
    df["is_complete"] = True
    df.iloc[-1, df.columns.get_loc("is_complete")] = False
    return df


FIXTURE_BUILDERS = {
    "A_long_rise_reversal": (fixture_a_long_rise_reversal, False),
    "B_rise_dip_reversal": (fixture_b_rise_dip_reversal, False),
    "C_range_oversold": (fixture_c_range_oversold, False),
    "D_short_history": (fixture_d_short_history, False),
    "E_incomplete_last": (fixture_e_incomplete_last, True),
}


# ---------------------------------------------------------------------------
# Канонизация и целостность fixture
# ---------------------------------------------------------------------------

def canonical_frame(df):
    """Детерминированное JSON-представление fixture (для sha256)."""
    cols = [c for c in ("open", "high", "low", "close", "volume",
                        "is_complete") if c in df.columns]
    data = {
        "columns": cols,
        "index": [str(ts) for ts in df.index],
        "rows": [
            [None if pd.isna(v)
             else (bool(v) if isinstance(v, (bool, np.bool_)) else float(v))
             for v in df[c]]
            for c in cols
        ],
    }
    return data


def fixture_sha256(name: str) -> str:
    builder, _ = FIXTURE_BUILDERS[name]
    df = builder()
    payload = json.dumps(canonical_frame(df), sort_keys=True,
                         separators=(",", ":"),
                         ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


# ---------------------------------------------------------------------------
# Пересчёт golden-файла (ручной запуск)
# ---------------------------------------------------------------------------

def regenerate_golden_file() -> str:
    """Пересчитывает expectations из ОРИГИНАЛЬНОЙ baseline-логики."""
    strategy = LegacySamsungV4Strategy()
    golden = {
        "_comment": (
            "G-1 golden signals: ожидаемые (signal, reason) ОРИГИНАЛЬНОЙ "
            "логики baseline strategy.py на детерминированных fixture, "
            "снятые через regression-адаптер Stage A. Тест пересчитывает "
            "и сравнивает. Не редактировать вручную."),
        "generator": "regression adapter -> baseline strategy.py",
        "fixture_sha256": {},
        "expectations": {},
    }
    for name, (_, drop_incomplete) in FIXTURE_BUILDERS.items():
        df = builder_df(name)
        last_price = float(df["close"].iloc[-1])
        golden["fixture_sha256"][name] = fixture_sha256(name)
        for profile in profiles.PROFILE_NAMES:
            config = strategy.build_regression_config(profile)
            signal = strategy.evaluate_entry(
                sa.EntrySignalInput(figi="FIX", ticker=name,
                                    candles=df.copy(),
                                    last_price=last_price,
                                    drop_incomplete=drop_incomplete),
                config)
            golden["expectations"][f"{name}::{profile}"] = {
                "signal": signal.direction.value,
                "reason": signal.reason,
            }
    with open(GOLDEN_PATH, "w", encoding="utf-8") as handle:
        json.dump(golden, handle, ensure_ascii=False, indent=2,
                  sort_keys=True)
        handle.write("\n")
    return GOLDEN_PATH


def builder_df(name: str):
    builder, _ = FIXTURE_BUILDERS[name]
    return builder()


if __name__ == "__main__":
    print("regenerated:", regenerate_golden_file())
    sys.exit(0)
