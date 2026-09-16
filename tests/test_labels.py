"""Tests for ML Phase B — triple-barrier labels."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.config import load_config
from src.ml.labels import triple_barrier_labels


@pytest.fixture(scope="module")
def cfg():
    return load_config()


def _df(highs, lows, closes):
    n = len(closes)
    idx = pd.date_range("2025-01-01", periods=n, freq="h", tz="UTC", name="timestamp")
    return pd.DataFrame({"open": closes, "high": highs, "low": lows, "close": closes}, index=idx)


def test_up_barrier_hit_first():
    n = 12
    highs = [100.2] * n
    highs[3] = 102.0                      # a spike up at bar 3 (>= upper 101)
    df = _df(highs, [99.8] * n, [100.0] * n)
    atr = pd.Series([1.0] * n)            # barriers at +/- 1 -> 101 / 99
    labels = triple_barrier_labels(df, horizon=5, atr_mult=1.0, atr=atr)
    assert labels.iloc[0] == 1.0          # bar 0 sees the bar-3 spike within 5 -> up
    assert labels.iloc[3] == 0.0          # bar 3 sees only calm bars -> timeout


def test_down_barrier_hit_first():
    n = 12
    lows = [99.8] * n
    lows[2] = 98.0                        # a drop at bar 2 (<= lower 99)
    df = _df([100.2] * n, lows, [100.0] * n)
    atr = pd.Series([1.0] * n)
    labels = triple_barrier_labels(df, horizon=5, atr_mult=1.0, atr=atr)
    assert labels.iloc[0] == -1.0


def test_neither_is_timeout_and_tail_is_nan():
    n = 10
    df = _df([100.2] * n, [99.8] * n, [100.0] * n)   # never touches +/-1 barriers
    atr = pd.Series([1.0] * n)
    labels = triple_barrier_labels(df, horizon=4, atr_mult=1.0, atr=atr)
    assert labels.iloc[0] == 0.0
    assert labels.iloc[-4:].isna().all()             # last `horizon` bars can't be labeled


def test_labels_valid_on_real_shape(cfg):
    n = 120
    idx = pd.date_range("2025-01-01", periods=n, freq="h", tz="UTC", name="timestamp")
    close = 100 + np.sin(np.arange(n) / 6.0) * 4 + np.arange(n) * 0.05
    df = pd.DataFrame({"open": close, "high": close + 1, "low": close - 1, "close": close}, index=idx)
    labels = triple_barrier_labels(df, cfg, horizon=12)   # ATR from add_features
    assert set(labels.dropna().unique()) <= {-1.0, 0.0, 1.0}
    assert labels.iloc[-12:].isna().all()
