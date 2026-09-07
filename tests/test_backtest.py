"""Tests for Phase 14 — the forward-return backtest.

The centerpiece is the LOOK-AHEAD-BIAS guard: the signal at bar i must not change when bars
after i are altered. It runs through evaluate()'s own featured-full path (features computed
once on the whole frame), because that is the path whose correctness depends on indicator
causality — the self-contained slice path is look-ahead-free by construction and would pass
trivially.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.backtest.evaluate import BacktestReport, evaluate, signal_at
from src.config import load_config
from src.indicators.features import add_features


@pytest.fixture(scope="module")
def cfg():
    return load_config()


@pytest.fixture
def wave_df():
    """240 bars of a rising sine wave — ample warmup, swings, and setups."""
    n = 240
    idx = pd.date_range("2025-01-01", periods=n, freq="h", tz="UTC", name="timestamp")
    t = np.arange(n)
    close = 100 + 10 * np.sin(t / 6.0) + t * 0.05
    return pd.DataFrame(
        {"open": close, "high": close + 1.0, "low": close - 1.0, "close": close, "volume": 10.0},
        index=idx,
    )


def _verdict(res):
    return (res.bias, res.triggered, res.agreeing)


def test_look_ahead_guard_mirrors_evaluate_path(cfg, wave_df):
    """Mutating bars AFTER i must not change the signal at i — via evaluate()'s featured-full
    path. This is what would catch a non-causal indicator; a NaN mutation could not, so we use
    finite garbage."""
    i = int(len(wave_df) * 0.6)

    featured_a = add_features(wave_df, cfg)
    sig_a = signal_at(wave_df, i, cfg, featured=featured_a)

    df2 = wave_df.copy()
    df2.iloc[i + 1:] *= 10  # finite garbage in the future, NOT NaN
    featured_b = add_features(df2, cfg)
    sig_b = signal_at(df2, i, cfg, featured=featured_b)

    assert _verdict(sig_a) == _verdict(sig_b)


def test_slice_path_matches_featured_full(cfg, wave_df):
    """The self-contained slice path equals the featured-full path — justifies compute-once."""
    i = int(len(wave_df) * 0.6)
    featured = add_features(wave_df, cfg)
    assert _verdict(signal_at(wave_df, i, cfg, featured=featured)) == _verdict(
        signal_at(wave_df, i, cfg)
    )


def test_evaluate_reports_sample_sizes_and_is_consistent(cfg, wave_df):
    report = evaluate(wave_df, cfg, horizon=12, min_agreeing=1, step=1)
    assert isinstance(report, BacktestReport)
    assert report.overall.n >= 1  # min_agreeing=1 guarantees setups on a trending wave
    assert report.overall.n == report.by_bias["bullish"].n + report.by_bias["bearish"].n
    for s in (report.overall, *report.by_bias.values()):
        if s.n:
            assert 0.0 <= s.win_rate <= 1.0
    # Every outcome respects the horizon and never indexes past the frame (boundary check).
    for o in report.outcomes:
        assert o.horizon == 12
        assert o.bar + o.horizon < len(wave_df)
    assert "n=" in report.summary() and "CAVEAT" in report.summary()


def test_evaluate_raises_on_insufficient_history(cfg):
    tiny = pd.DataFrame(
        {"open": [1, 2, 3], "high": [1, 2, 3], "low": [1, 2, 3], "close": [1, 2, 3], "volume": [1, 1, 1]},
        index=pd.date_range("2025-01-01", periods=3, freq="h", tz="UTC", name="timestamp"),
    )
    with pytest.raises(ValueError, match="history"):
        evaluate(tiny, cfg)
