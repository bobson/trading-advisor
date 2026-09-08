"""Tests for Phase 21 — the context layer (sentiment / calendar / news).

Offline coverage uses an injected `fetch` (canned JSON) — no network. Fear & Greed needs no
key, so it also gets a `@pytest.mark.network` live test. Calendar/news are exercised offline
only (their live Finnhub shape is UNVERIFIED until a key exists) plus graceful-empty paths.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.config import load_config
from src.context.calendar import fetch_economic_calendar
from src.context.gather import gather_context
from src.context.news import fetch_news
from src.context.sentiment import fetch_fear_greed
from src.service.analyze import advise


@pytest.fixture(scope="module")
def cfg():
    return load_config()


def _fake_fng(_url, params=None):
    return {"data": [{"value": "72", "value_classification": "Greed", "timestamp": "1757289600"}]}


def _raises(*_a, **_k):
    raise RuntimeError("network down")


# --- sentiment (keyless, verified) ---------------------------------------------

def test_fear_greed_parses_injected(cfg):
    fg = fetch_fear_greed(fetch=_fake_fng)
    assert fg is not None and fg.value == 72 and fg.label == "Greed"
    assert fg.as_of  # stamped so it can't read as present-tense


def test_fear_greed_degrades_on_error():
    assert fetch_fear_greed(fetch=_raises) is None


# --- calendar / news (key-gated) -----------------------------------------------

def test_calendar_and_news_empty_without_key(cfg):
    keyless = cfg.model_copy(update={"finnhub_api_key": None})
    assert fetch_economic_calendar(keyless, fetch=_fake_fng) == []
    assert fetch_news(keyless, fetch=_fake_fng) == []


def test_calendar_parses_high_impact_with_key(cfg):
    keyed = cfg.model_copy(update={"finnhub_api_key": "TESTKEY"})
    payload = {"economicCalendar": [
        {"time": "2026-09-09 12:30:00", "country": "US", "event": "CPI", "impact": "high"},
        {"time": "2026-09-09 09:00:00", "country": "US", "event": "Fed speak", "impact": "low"},
    ]}
    events = fetch_economic_calendar(keyed, fetch=lambda u, params=None: payload)
    assert len(events) == 1 and events[0].event == "CPI"  # low-impact filtered out


# --- gather_context aggregation ------------------------------------------------

def test_gather_context_crypto(cfg):
    ctx = gather_context("BTC/USDT", cfg, fetch=_fake_fng)
    assert ctx["fear_greed"]["value"] == 72
    assert "as_of" in ctx and isinstance(ctx["economic_calendar"], list)


def test_gather_context_forex_skips_fear_greed(cfg):
    ctx = gather_context("EUR/USD", cfg, fetch=_fake_fng)
    assert ctx["fear_greed"] is None  # Fear & Greed is a crypto index


def test_gather_context_never_raises_on_network_failure(cfg):
    ctx = gather_context("BTC/USDT", cfg, fetch=_raises)
    assert ctx["fear_greed"] is None and ctx["economic_calendar"] == [] and ctx["news"] == []


# --- the offline contract: advise never fetches context on its own -------------

def test_advise_without_context_stays_offline_and_context_free(cfg):
    n = 160
    idx = pd.date_range("2025-01-01", periods=n, freq="h", tz="UTC")
    close = 100 + np.sin(np.arange(n) / 6.0) * 5 + np.arange(n) * 0.05
    df = pd.DataFrame({"open": close, "high": close + 1, "low": close - 1, "close": close, "volume": 10.0}, index=idx)
    keyless = cfg.model_copy(update={"anthropic_api_key": None})
    result = advise("BTC/USDT", "1h", keyless, df=df)  # no context arg
    assert result.facts.get("context") is None          # pins "no network in advise"


def test_context_renders_in_facts_text(cfg):
    from src.advisor.facts import facts_to_prompt
    facts = {
        "market": {"symbol": "BTC/USDT", "exchange": "binance", "timeframe": "1h",
                   "last_close": 80000.0, "last_time": "2026-09-08 00:00:00"},
        "context": {"as_of": "2026-09-08 12:00 UTC",
                    "fear_greed": {"value": 72, "label": "Greed", "as_of": "2026-09-08"},
                    "economic_calendar": [], "news": []},
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
    assert "MARKET CONTEXT" in text and "Fear & Greed: 72" in text


@pytest.mark.network
def test_fear_greed_live():
    fg = fetch_fear_greed()
    assert fg is not None and 0 <= fg.value <= 100 and fg.label
