"""Tests for ML Phase C — the walk-forward instrument.

The two load-bearing tests: the instrument must (1) FIND a real signal when one exists, and
(2) report ~0.5 AUC on pure noise — i.e. it neither misses a true edge nor hallucinates one
(which would mean look-ahead leakage). Those are what make a "no edge" verdict trustworthy.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.config import load_config
from src.ml.walkforward import evaluate_walkforward, walk_forward_eval


@pytest.fixture(scope="module")
def cfg():
    return load_config()


def test_instrument_finds_a_real_signal():
    rng = np.random.default_rng(0)
    n = 800
    y = rng.integers(0, 2, n)
    predictive = y + rng.normal(0, 0.5, n)          # a feature that genuinely predicts y
    X = pd.DataFrame({"signal": predictive, "noise": rng.normal(size=n)})
    r = evaluate_walkforward(X, pd.Series(y), n_folds=5)
    assert r["auc"] > 0.8                             # should clearly beat 0.5


def test_instrument_reports_no_edge_on_pure_noise():
    rng = np.random.default_rng(1)
    n = 800
    y = rng.integers(0, 2, n)
    X = pd.DataFrame(rng.normal(size=(n, 4)), columns=list("abcd"))
    r = evaluate_walkforward(X, pd.Series(y), n_folds=5)
    assert 0.4 <= r["auc"] <= 0.6                     # noise -> coin flip out-of-sample


def test_walk_forward_eval_shape(cfg):
    rng = np.random.default_rng(0)
    n = 600
    idx = pd.date_range("2025-01-01", periods=n, freq="h", tz="UTC", name="timestamp")
    close = 100 + np.cumsum(rng.normal(0, 1.0, n))   # volatile random walk -> barriers get hit
    df = pd.DataFrame({"open": close, "high": close + 0.5, "low": close - 0.5,
                       "close": close, "volume": rng.uniform(1, 100, n)}, index=idx)
    r = walk_forward_eval(df, cfg, horizon=12, n_folds=4)
    assert r["n_oos"] > 0 and "baseline_acc" in r and "calibration" in r
