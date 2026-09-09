"""Tests for recommendation #1 — out-of-sample period split (offline)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.backtest.suite import evaluate_periods, format_periods
from src.config import load_config


@pytest.fixture(scope="module")
def cfg():
    return load_config()


@pytest.fixture
def wave_df():
    n = 300
    idx = pd.date_range("2025-01-01", periods=n, freq="h", tz="UTC", name="timestamp")
    t = np.arange(n)
    close = 100 + 6 * np.sin(t / 6.0) + t * 0.05
    return pd.DataFrame(
        {"open": close, "high": close + 1, "low": close - 1, "close": close, "volume": 10.0},
        index=idx,
    )


def test_evaluate_periods_splits_full_and_halves(cfg, wave_df):
    periods = evaluate_periods(wave_df, cfg, horizon=12, step=1, require_categories=1)
    assert set(periods) == {"full", "1st half", "2nd half"}
    assert periods["full"] is not None and periods["full"].overall.n >= 1
    # each half backtests independently
    assert periods["1st half"] is not None and periods["2nd half"] is not None


def test_evaluate_periods_handles_too_short_window(cfg):
    tiny = pd.DataFrame(
        {"open": [1, 2, 3], "high": [1, 2, 3], "low": [1, 2, 3], "close": [1, 2, 3], "volume": [1, 1, 1]},
        index=pd.date_range("2025-01-01", periods=3, freq="h", tz="UTC", name="timestamp"),
    )
    periods = evaluate_periods(tiny, cfg, horizon=12)
    assert all(v is None for v in periods.values())  # no window has enough history


def test_format_periods_renders(cfg, wave_df):
    text = format_periods("BTC/USDT", evaluate_periods(wave_df, cfg, horizon=12, step=1, require_categories=1))
    assert "BTC/USDT" in text and "win-rate" in text
