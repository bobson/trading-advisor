"""Feature 6 — market regime tests.

Tuned/verified primarily on DAILY and WEEKLY bars (the multi-week trend-following use case), so
the synthetic fixtures here are daily/weekly, not 1h. The load-bearing test is the look-ahead
guard: mutating bars after i must never change the regime at bar i.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.config import load_config
from src.market.regime import (
    RANGING,
    TRENDING_DOWN,
    TRENDING_UP,
    _apply_hysteresis,
    classify_regime,
    compute_regime,
    get_regime,
    load_regime,
)
from src.indicators.features import add_features
from src.store.db import connect


@pytest.fixture(scope="module")
def cfg():
    return load_config()


def _daily(closes: np.ndarray, spread: float = 1.0) -> pd.DataFrame:
    n = len(closes)
    idx = pd.date_range("2020-01-01", periods=n, freq="D", tz="UTC", name="timestamp")
    return pd.DataFrame(
        {"open": closes, "high": closes + spread, "low": closes - spread,
         "close": closes, "volume": 1000.0}, index=idx,
    )


def _uptrend(n: int = 160) -> pd.DataFrame:
    return _daily(100.0 * (1.01 ** np.arange(n)), spread=0.5)   # steady compounding rise


def _flat(n: int = 160) -> pd.DataFrame:
    t = np.arange(n)
    return _daily(100.0 + 0.15 * np.sin(t / 4.0), spread=0.05)  # compressed, directionless


def _mixed_daily(n: int = 260) -> pd.DataFrame:
    """An uptrend, then a long sideways region with VARIABLE volatility — so non-trending
    (ranging/volatile/quiet) bars sit before any mid-frame cut. Those are the only bars whose
    label depends on the ATR percentile (trend bars ignore it), so they're precisely what makes
    the look-ahead guard bite the "no whole-series stats" requirement."""
    t = np.arange(n)
    trend = np.where(t < 110, 100.0 + t * 0.9, 100.0 + 110 * 0.9)
    amp = np.where(t < 110, 2.0, 4.0 + 3.0 * np.sin(t / 13.0))   # variable vol once sideways
    close = trend + amp * np.sin(t / 3.0)
    return _daily(close, spread=1.5)


# --- look-ahead guard (the centerpiece) ------------------------------------------------------

def test_regime_is_look_ahead_safe(cfg):
    df = _mixed_daily()
    k = 200
    full = compute_regime(df, cfg)

    assert full.iloc[k] is not None, "bar k unlabeled — the guard would be vacuous"
    # The ATR-percentile leak only affects NON-trending bars (trend bars ignore atr_rank), so the
    # pre-cut window must contain some, or a whole-series-percentile regression would slip past.
    pre = full.iloc[: k + 1].dropna()
    assert (~pre.isin([TRENDING_UP, TRENDING_DOWN])).any(), \
        "no non-trending bar before the cut — a whole-series ATR-percentile leak couldn't be caught"

    # The ×10 blows up ATR *after* the cut, so a leaky whole-series ATR percentile (or a centered
    # window) WOULD shift bar-k's volatility rank — this mutation is what makes the guard bite.
    mutated = df.copy()
    mutated.iloc[k + 1:] *= 10.0                 # finite garbage after the cut, never NaN
    after = compute_regime(mutated, cfg)

    pd.testing.assert_series_equal(full.iloc[: k + 1], after.iloc[: k + 1])


# --- coverage & sanity of the labels ---------------------------------------------------------

def test_every_bar_after_warmup_has_a_regime(cfg):
    r = compute_regime(_mixed_daily(), cfg)
    labeled = r.dropna()
    assert labeled.notna().all()
    assert labeled.index[-1] == r.index[-1]      # the latest bar is labeled
    assert set(labeled.unique()) <= set(("trending_up", "trending_down", "ranging", "volatile", "quiet"))


def test_uptrend_reads_trending_up_not_down(cfg):
    labels = compute_regime(_uptrend(), cfg).dropna()
    assert (labels == TRENDING_UP).sum() > 0
    assert (labels == TRENDING_UP).sum() > (labels == TRENDING_DOWN).sum()


def test_flat_market_is_never_trending(cfg):
    # A compressed, directionless series must never read as a trend (it lands in ranging/quiet).
    labels = set(compute_regime(_flat(), cfg).dropna().unique())
    assert TRENDING_UP not in labels and TRENDING_DOWN not in labels


def test_weekly_bars_are_labeled_and_stable(cfg):
    # A multi-year weekly uptrend: labels exist and don't flicker.
    idx = pd.date_range("2015-01-01", periods=200, freq="W", tz="UTC", name="timestamp")
    close = 100.0 * (1.02 ** np.arange(200)) + 8.0 * np.sin(np.arange(200) / 9.0)
    df = pd.DataFrame({"open": close, "high": close + 2, "low": close - 2,
                       "close": close, "volume": 1000.0}, index=idx)
    labels = classify_regime(add_features(df, cfg), cfg).dropna()
    assert len(labels) > 100
    switches = int((labels.values[1:] != labels.values[:-1]).sum())
    assert switches / len(labels) < 0.15         # stable, not bar-to-bar flicker


# --- hysteresis (anti-flicker), independent of the indicators --------------------------------

def test_hysteresis_suppresses_a_one_bar_blip():
    raw = pd.Series([TRENDING_UP] * 3 + [RANGING] + [TRENDING_UP] * 3)
    out = _apply_hysteresis(raw, persist=3)
    assert set(out.unique()) == {TRENDING_UP}    # the single RANGING bar never takes hold


def test_hysteresis_switches_only_after_persist_consecutive_bars():
    raw = pd.Series([TRENDING_UP, TRENDING_UP, RANGING, RANGING, RANGING, RANGING])
    out = _apply_hysteresis(raw, persist=3)
    assert out.iloc[3] == TRENDING_UP            # 2 consecutive RANGING: not yet
    assert out.iloc[4] == RANGING                # 3rd consecutive RANGING: switch
    # warm-up Nones pass through until the first real label
    raw2 = pd.Series([None, None, TRENDING_UP, TRENDING_UP])
    out2 = _apply_hysteresis(raw2, persist=3)
    assert pd.isna(out2.iloc[0]) and out2.iloc[2] == TRENDING_UP


# --- SQLite cache round-trip -----------------------------------------------------------------

def test_cache_round_trip(cfg):
    conn = connect(":memory:")
    df = _mixed_daily()
    regime = get_regime("BTC/USDT", "1d", df, cfg, conn=conn)
    loaded = load_regime(conn, "BTC/USDT", "1d")
    assert len(loaded) == len(regime)
    # compare only the labeled bars (NULL/None warm-up round-trips as None either way)
    a = regime.dropna()
    b = loaded.dropna()
    assert list(a.values) == list(b.values)
    assert list(a.index) == list(b.index)
    conn.close()
