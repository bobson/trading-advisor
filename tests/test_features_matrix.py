"""Tests for ML Phase A — the feature matrix, with the look-ahead guard as the centerpiece."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.config import load_config
from src.ml.features_matrix import FEATURE_COLUMNS, build_feature_matrix


@pytest.fixture(scope="module")
def cfg():
    return load_config()


@pytest.fixture
def df():
    n = 240
    idx = pd.date_range("2025-01-01", periods=n, freq="h", tz="UTC", name="timestamp")
    close = 100 + np.sin(np.arange(n) / 6.0) * 5 + np.arange(n) * 0.05
    return pd.DataFrame(
        {"open": close, "high": close + 1, "low": close - 1, "close": close, "volume": 10.0},
        index=idx,
    )


def test_shape_columns_and_warmup(cfg, df):
    m = build_feature_matrix(df, cfg)
    assert list(m.columns) == FEATURE_COLUMNS
    assert len(m) == len(df)                       # aligned to the candle index
    assert m.iloc[:20].isna().any(axis=1).all()    # warm-up rows carry NaN
    assert m.iloc[-1].notna().all()                # a mature row is fully populated
    assert np.isfinite(m.iloc[-1].to_numpy()).all()  # no inf leaking from /0


def test_feature_matrix_is_look_ahead_safe(cfg, df):
    """Mutating bars AFTER i must not change row i (the row a model would train/predict on)."""
    i = 180
    m1 = build_feature_matrix(df, cfg)
    df2 = df.copy()
    df2.iloc[i + 1:] *= 10  # finite garbage in the future
    m2 = build_feature_matrix(df2, cfg)
    pd.testing.assert_series_equal(m1.iloc[i], m2.iloc[i])
