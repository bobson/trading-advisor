"""Tests for Phase 19 — market adaptation (crypto vs forex context).

Forex data isn't wired until Phase 26, but `advise(..., df=...)` bypasses the provider, so a
coherent forex read is exercised here with an injected synthetic frame whose index crosses a
Friday->Sunday boundary (so the weekend-gap branch actually fires).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.config import load_config
from src.indicators.features import add_features
from src.market.adaptation import _forex_session, market_context
from src.service.analyze import advise


@pytest.fixture(scope="module")
def cfg():
    return load_config().model_copy(update={"anthropic_api_key": None})


def _raw(index, base=100.0):
    n = len(index)
    close = base + np.sin(np.arange(n) / 5.0) * (base * 0.02) + np.arange(n) * (base * 0.001)
    return pd.DataFrame(
        {"open": close, "high": close + base * 0.01, "low": close - base * 0.01,
         "close": close, "volume": 10.0},
        index=index,
    )


def _crypto_index(n=80):
    return pd.date_range("2025-01-01", periods=n, freq="h", tz="UTC", name="timestamp")


def _forex_index_weekend(n=80):
    """n-1 contiguous hourly bars ending Friday 20:00 UTC, then one bar Sunday 21:00 UTC."""
    head = pd.date_range(end=pd.Timestamp("2025-01-03 20:00", tz="UTC"), periods=n - 1, freq="h")
    sunday = pd.DatetimeIndex([pd.Timestamp("2025-01-05 21:00", tz="UTC")])  # Jan 5 2025 = Sunday
    idx = head.append(sunday)
    idx.name = "timestamp"
    return idx


def test_crypto_context(cfg):
    feat = add_features(_raw(_crypto_index()), cfg)
    mc = market_context("BTC/USDT", feat, cfg)
    assert mc.asset_class == "crypto"
    assert mc.volume_type == "real" and mc.is_24_7
    assert mc.active_session is None and mc.weekend_gap is None
    assert mc.significant_move_pct is not None and mc.significant_move_pct > 0


def test_forex_context_tick_volume_session_and_weekend_gap(cfg):
    feat = add_features(_raw(_forex_index_weekend(), base=1.10), cfg)
    mc = market_context("EUR/USD", feat, cfg)
    assert mc.asset_class == "forex"
    assert mc.volume_type == "tick" and not mc.is_24_7
    assert mc.weekend_gap is True                 # Fri->Sun jump detected
    assert mc.active_session == "Sydney / thin liquidity"  # last bar is 21:00 UTC


def test_forex_session_mapping():
    assert _forex_session(14) == "London/New York overlap"
    assert _forex_session(9) == "London"
    assert _forex_session(18) == "New York"
    assert _forex_session(3) == "Tokyo"
    assert _forex_session(22) == "Sydney / thin liquidity"


def test_forex_read_end_to_end_via_injected_df(cfg):
    forex_raw = _raw(_forex_index_weekend(), base=1.10)
    result = advise("EUR/USD", "1h", cfg, df=forex_raw)
    ma = result.facts["market_adaptation"]
    assert ma["asset_class"] == "forex" and ma["volume_type"] == "tick"
    assert result.facts["volume"]["type"] == "tick"      # volume fact tagged
    assert "TICK volume" in result.facts_text              # caveat surfaced to Layer 2
