"""Tests for recommendation #3 — funding study (offline; look-ahead safety is the key)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.config import load_config
from src.derivatives.funding_study import align_funding, study_funding


@pytest.fixture(scope="module")
def cfg():
    return load_config()


def test_align_funding_is_look_ahead_safe():
    # Funding settles at 00:00 and 08:00; each bar must see only the last settlement <= its time.
    candles_idx = pd.date_range("2025-01-01 00:00", periods=12, freq="h", tz="UTC")
    funding = pd.Series(
        [0.001, 0.002],
        index=pd.to_datetime(["2025-01-01 00:00", "2025-01-01 08:00"], utc=True),
    )
    aligned = align_funding(candles_idx, funding)
    assert aligned.iloc[0] == 0.001          # 00:00 bar -> 00:00 settlement
    assert aligned.iloc[7] == 0.001          # 07:00 bar -> still the 00:00 one (not the future 08:00)
    assert aligned.iloc[8] == 0.002          # 08:00 bar -> new settlement
    assert aligned.iloc[11] == 0.002


def test_align_funding_nan_before_first_settlement():
    candles_idx = pd.date_range("2025-01-01 00:00", periods=4, freq="h", tz="UTC")
    funding = pd.Series([0.001], index=pd.to_datetime(["2025-01-01 02:00"], utc=True))
    aligned = align_funding(candles_idx, funding)
    assert pd.isna(aligned.iloc[0]) and pd.isna(aligned.iloc[1])  # nothing known yet
    assert aligned.iloc[2] == 0.001


def test_study_funding_buckets(cfg):
    n = 60
    idx = pd.date_range("2025-01-01", periods=n, freq="h", tz="UTC")
    close = 100 + np.arange(n) * 0.1
    candles = pd.DataFrame({"close": close}, index=idx)
    # First third crowded-long, rest neutral.
    fb = pd.Series([0.001] * 20 + [0.0] * 40, index=idx)
    r = study_funding(candles, fb, cfg, horizon=12)
    assert r["high_funding"]["n"] > 0 and r["all"]["n"] > 0
    assert set(r) >= {"all", "high_funding", "low_funding", "horizon", "hi_threshold", "lo_threshold"}
