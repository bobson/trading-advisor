"""Tests for Phase 22 — crypto derivatives/positioning (funding + open interest).

Offline coverage uses a fake ccxt-like exchange (no network). A `@pytest.mark.network` test
hits the live binance perp (no key needed, like the OHLCV fetch).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.config import load_config
from src.derivatives.funding import read_funding
from src.derivatives.gather import _perp_symbol, gather_derivatives
from src.service.analyze import advise


@pytest.fixture(scope="module")
def cfg():
    return load_config()


class _FakeExchange:
    def __init__(self, funding=0.0008, oi_amount=100000.0, oi_value=8.0e9, raise_=False):
        self.funding = funding
        self.oi_amount = oi_amount
        self.oi_value = oi_value
        self.raise_ = raise_

    def fetch_funding_rate(self, perp):
        if self.raise_:
            raise RuntimeError("network down")
        return {"fundingRate": self.funding}

    def fetch_open_interest(self, perp):
        if self.raise_:
            raise RuntimeError("network down")
        return {"openInterestAmount": self.oi_amount, "openInterestValue": self.oi_value}


def test_perp_symbol_mapping():
    assert _perp_symbol("BTC/USDT") == "BTC/USDT:USDT"
    assert _perp_symbol("BTC/USDT:USDT") == "BTC/USDT:USDT"  # already a perp


def test_funding_classification(cfg):
    assert read_funding(_FakeExchange(funding=0.0008), "BTC/USDT:USDT", cfg).state == "crowded_longs"
    assert read_funding(_FakeExchange(funding=-0.0008), "BTC/USDT:USDT", cfg).state == "crowded_shorts"
    assert read_funding(_FakeExchange(funding=0.0001), "BTC/USDT:USDT", cfg).state == "neutral"


def test_gather_derivatives_crypto(cfg):
    d = gather_derivatives("BTC/USDT", cfg, exchange=_FakeExchange())
    assert d is not None
    assert d["perp"] == "BTC/USDT:USDT"
    assert d["funding"]["state"] == "crowded_longs"
    assert d["open_interest"]["amount"] == 100000.0


def test_gather_derivatives_forex_is_none(cfg):
    assert gather_derivatives("EUR/USD", cfg, exchange=_FakeExchange()) is None  # no perp for forex


def test_gather_derivatives_degrades_on_error(cfg):
    assert gather_derivatives("BTC/USDT", cfg, exchange=_FakeExchange(raise_=True)) is None


def test_advise_without_derivatives_is_derivative_free(cfg):
    n = 160
    idx = pd.date_range("2025-01-01", periods=n, freq="h", tz="UTC")
    close = 100 + np.sin(np.arange(n) / 6.0) * 5 + np.arange(n) * 0.05
    df = pd.DataFrame({"open": close, "high": close + 1, "low": close - 1, "close": close, "volume": 10.0}, index=idx)
    keyless = cfg.model_copy(update={"anthropic_api_key": None})
    result = advise("BTC/USDT", "1h", keyless, df=df)  # no derivatives arg
    assert result.facts.get("derivatives") is None      # pins "no network in advise"


def test_derivatives_render_in_facts_text(cfg):
    from src.advisor.facts import facts_to_prompt
    facts = {
        "market": {"symbol": "BTC/USDT", "exchange": "binance", "timeframe": "1h",
                   "last_close": 80000.0, "last_time": "2026-09-08 00:00:00"},
        "derivatives": {"as_of": "2026-09-08 12:00 UTC", "perp": "BTC/USDT:USDT",
                        "funding": {"rate_pct": 0.08, "annualized_pct": 87.6, "state": "crowded_longs"},
                        "open_interest": {"amount": 100000.0, "notional_usd": 8.0e9}},
        "trend": {"label": "sideways", "reasons": []},
        "momentum": {"rsi": None, "rsi_zone": "unknown", "macd": None, "macd_signal": None, "macd_state": "unknown"},
        "volume": None, "volatility": None, "divergence": None, "round_number": None,
        "market_adaptation": {"asset_class": "crypto", "volume_type": "real", "is_24_7": True,
                              "active_session": None, "weekend_gap": None, "significant_move_pct": None},
        "support_resistance": {"nearest_support": None, "nearest_resistance": None},
        "chart_patterns": [], "fibonacci": None,
        "confluence": {"bias": "neutral", "triggered": False, "confidence": 0.0,
                       "agreeing_categories": 0, "require_categories": 2, "categories": {},
                       "signals": [], "mtf_alignment": None, "mtf_trends": None},
    }
    text = facts_to_prompt(facts)
    assert "DERIVATIVES / POSITIONING" in text and "crowded_longs" in text


@pytest.mark.network
def test_derivatives_live_btc():
    d = gather_derivatives("BTC/USDT", load_config())
    assert d is not None and d["funding"] is not None
