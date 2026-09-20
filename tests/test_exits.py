"""Feature 8 — the eight exit rules on hand-built price paths (pure, look-ahead-safe)."""

from __future__ import annotations

import pandas as pd
import pytest

from src.config import ExitsConfig, load_config
from src.indicators.features import COL_ATR, COL_SMA_SLOW
from src.market.regime import RANGING, TRENDING_UP
from src.backtest.exits import simulate_exit


@pytest.fixture(scope="module")
def cfg():
    return load_config()


def _ex(cfg, **over):
    return cfg.model_copy(update={"exits": ExitsConfig(**{**cfg.exits.model_dump(), **over})})


def _feat(close, *, high=None, low=None, atr=1.0, slow=None, regime=None):
    n = len(close)
    idx = pd.date_range("2024-01-01", periods=n, freq="D", tz="UTC")
    df = pd.DataFrame({
        "open": close,
        "high": high if high is not None else [c + 0.5 for c in close],
        "low": low if low is not None else [c - 0.5 for c in close],
        "close": close,
    }, index=idx)
    df[COL_ATR] = atr
    if slow is not None:
        df[COL_SMA_SLOW] = slow
    reg = pd.Series(regime, index=idx) if regime is not None else None
    return df, reg


def test_fixed_target(cfg):
    df, _ = _feat([100, 101, 102, 103], high=[100.5, 101.5, 102.5, 103.5])   # target = 100 + 3 = 103
    t = simulate_exit(df, 0, "bullish", cfg, "fixed_target")
    assert t.exit_bar == 3 and t.reason == "target" and t.exit_price == 103.0
    assert t.ret == pytest.approx(0.03)


def test_stop_only(cfg):
    df, _ = _feat([100, 100, 100, 100], low=[99.5, 99, 98.5, 97.5])          # stop = 100 - 2 = 98
    t = simulate_exit(df, 0, "bullish", cfg, "stop_only")
    assert t.exit_bar == 3 and t.reason == "stop" and t.exit_price == 98.0


def test_trailing_atr(cfg):
    df, _ = _feat([100, 102, 104, 100])                                       # peak close 104, trail 3 -> stop 101
    t = simulate_exit(df, 0, "bullish", cfg, "trailing_atr")
    assert t.exit_bar == 3 and t.reason == "trail" and t.exit_price == 100.0


def test_chandelier_stop_is_measured_before_this_bars_new_high(cfg):
    # bar 2 makes a huge new high (200) AND dips to 102: the stop is from the highest high THROUGH
    # bar 1 (=106 -> stop 103), so the bar's own high can't loosen the stop its low then hits.
    df, _ = _feat([100, 105, 101], high=[100, 106, 200], low=[99, 104, 102])
    t = simulate_exit(df, 0, "bullish", cfg, "chandelier")
    assert t.exit_bar == 2 and t.reason == "chandelier" and t.exit_price == 103.0


def test_regime_flip(cfg):
    df, reg = _feat([100, 101, 102, 103], regime=[TRENDING_UP, TRENDING_UP, TRENDING_UP, RANGING])
    t = simulate_exit(df, 0, "bullish", cfg, "regime_flip", regime=reg)
    assert t.exit_bar == 3 and t.reason == "regime"


def test_structure_rolling_low_proxy(cfg):
    c = _ex(cfg, structure_lookback=3)
    df, _ = _feat([100, 101, 102, 99], low=[99, 100, 101, 98])               # prior 2 lows min 100; close 99 < 100
    t = simulate_exit(df, 0, "bullish", c, "structure")
    assert t.exit_bar == 3 and t.reason == "structure"


def test_time_exit(cfg):
    c = _ex(cfg, time_bars=3)
    df, _ = _feat([100, 101, 102, 103, 104])
    t = simulate_exit(df, 0, "bullish", c, "time")
    assert t.exit_bar == 3 and t.reason == "time"


def test_ma_cross(cfg):
    df, _ = _feat([100, 106, 106, 104], slow=[105, 105, 105, 105])
    t = simulate_exit(df, 0, "bullish", cfg, "ma_cross")
    assert t.exit_bar == 3 and t.reason == "ma"


def test_short_stop_mirrors_long(cfg):
    df, _ = _feat([100, 100, 100, 100], high=[100.5, 101, 101.5, 102.5])     # short stop = 100 + 2 = 102
    t = simulate_exit(df, 0, "bearish", cfg, "stop_only")
    assert t.reason == "stop" and t.exit_price == 102.0 and t.ret == pytest.approx(-0.02)


def test_exit_is_look_ahead_safe(cfg):
    # a target exit at bar 3; mutating bars AFTER the exit must not change the trade.
    close = [100, 101, 102, 103] + [100] * 6
    high = [100.5, 101.5, 102.5, 103.5] + [100] * 6
    df, _ = _feat(close, high=high)
    before = simulate_exit(df, 0, "bullish", cfg, "fixed_target")
    assert before.exit_bar == 3                         # resolved before the mutation point
    df2 = df.copy()
    df2.iloc[4:] *= 10.0
    after = simulate_exit(df2, 0, "bullish", cfg, "fixed_target")
    assert (after.exit_bar, after.exit_price, after.reason) == (before.exit_bar, before.exit_price, before.reason)


# --- the grid / report / entry-vs-exit comparison -------------------------------------------

def _trending_df(n=260):
    import numpy as np
    idx = pd.date_range("2020-01-01", periods=n, freq="D", tz="UTC", name="timestamp")
    t = np.arange(n)
    close = 100 * (1.004 ** t) + 6 * np.sin(t / 9.0)      # drift up with pullbacks
    return pd.DataFrame({"open": close, "high": close + 2, "low": close - 2,
                         "close": close, "volume": 1000.0}, index=idx)


def test_exit_lab_report_structure_and_comparison(cfg):
    from src.backtest.exits import ENTRY_RULES, EXIT_RULES, run_exit_lab

    rep = run_exit_lab(_trending_df(), cfg, step=5)
    assert len(rep.grid) == len(ENTRY_RULES) * len(EXIT_RULES)
    assert set(rep.exits) == set(EXIT_RULES) and set(rep.entries) == set(ENTRY_RULES)
    assert rep.spread_across_exits >= 0 and rep.spread_across_entries >= 0
    assert rep.verdict in ("exit", "entry")
    assert any(s.n for s in rep.entries.values())          # some entry rule produced trades
    txt = rep.summary()
    assert "EXIT LAB" in txt and "ACROSS EXITS" in txt and "ACROSS ENTRIES" in txt
