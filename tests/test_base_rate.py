"""Tests for recommendation #2 — the honest track record (base rates)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.backtest.base_rate import base_rate_entry, compute_base_rate
from src.config import load_config
from src.service.analyze import advise


@pytest.fixture(scope="module")
def cfg():
    return load_config()


@pytest.fixture
def wave_df():
    n = 240
    idx = pd.date_range("2025-01-01", periods=n, freq="h", tz="UTC", name="timestamp")
    t = np.arange(n)
    close = 100 + 5 * np.sin(t / 6.0) + t * 0.05
    return pd.DataFrame(
        {"open": close, "high": close + 1, "low": close - 1, "close": close, "volume": 10.0},
        index=idx,
    )


def test_compute_base_rate_shape(cfg, wave_df):
    br = compute_base_rate(wave_df, cfg, horizon=12, step=2, require_categories=1)
    assert br["horizon"] == 12
    for key in ("overall", "bullish", "bearish"):
        assert "n" in br[key] and "win_rate" in br[key]


def test_base_rate_entry_picks_bias():
    rates = {"horizon": 24, "bullish": {"n": 100, "win_rate": 0.55}, "bearish": {"n": 80, "win_rate": 0.45},
             "overall": {"n": 180, "win_rate": 0.50}}
    e = base_rate_entry(rates, "bullish")
    assert e == {"bias": "bullish", "win_rate": 0.55, "n": 100, "horizon": 24}
    # neutral bias falls back to overall
    assert base_rate_entry(rates, "neutral")["win_rate"] == 0.50
    # missing/empty -> None
    assert base_rate_entry(None, "bullish") is None
    assert base_rate_entry({"bullish": {"n": 0, "win_rate": None}}, "bullish") is None


def test_advise_attaches_base_rate(cfg, wave_df):
    keyless = cfg.model_copy(update={"anthropic_api_key": None})
    rates = {"horizon": 24, "bullish": {"n": 234, "win_rate": 0.53}, "bearish": {"n": 195, "win_rate": 0.47},
             "overall": {"n": 429, "win_rate": 0.51}}
    result = advise("BTC/USDT", "1h", keyless, df=wave_df, base_rate=rates)
    br = result.facts.get("base_rate")
    assert br is not None and br["n"] in (234, 195, 429)
    assert "TRACK RECORD" in result.facts_text


def test_advise_without_base_rate_has_none(cfg, wave_df):
    result = advise("BTC/USDT", "1h", cfg.model_copy(update={"anthropic_api_key": None}), df=wave_df)
    assert result.facts.get("base_rate") is None
