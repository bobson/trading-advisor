"""Tests for Phase 12 — the service core (`advise`) and its JSON-serializable result.

These run offline. The deterministic pipeline is exercised on synthetic candles; the
Layer 2 explanation is covered two ways: the keyless fallback (`explanation is None`) and,
with an injected fake client, that a real explanation flows into the payload — without ever
needing ANTHROPIC_API_KEY.
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from src.config import load_config
from src.service.analyze import AnalysisResult, advise


@pytest.fixture(scope="module")
def cfg():
    """Real config, but forced keyless so the deterministic path is what we assert by default."""
    return load_config().model_copy(update={"anthropic_api_key": None})


@pytest.fixture
def wave_df():
    """160 bars of a rising sine wave — guarantees swings, S/R, trendlines, and a fib leg."""
    n = 160
    idx = pd.date_range("2025-01-01", periods=n, freq="h")
    t = np.arange(n)
    close = 100 + 10 * np.sin(t / 6.0) + t * 0.05
    return pd.DataFrame(
        {"open": close, "high": close + 1.0, "low": close - 1.0, "close": close},
        index=idx,
    )


# --- fake Anthropic client (mirrors tests/test_vision.py) ----------------------

class _Block:
    def __init__(self, type_, text=""):
        self.type = type_
        self.text = text


class _Resp:
    def __init__(self, content):
        self.content = content


class _FakeMessages:
    def __init__(self, parent):
        self.parent = parent

    def create(self, **kwargs):
        self.parent.captured = kwargs
        return _Resp([_Block("text", "This market is in an uptrend.")])


class _FakeClient:
    def __init__(self):
        self.captured = None
        self.messages = _FakeMessages(self)


# --- tests ---------------------------------------------------------------------

def test_advise_payload_is_json_serializable(cfg, wave_df):
    """The 'done when': advise returns a dict that json.dumps cleanly, carrying the facts."""
    result = advise("BTC/USDT", "1h", cfg, df=wave_df)
    assert isinstance(result, AnalysisResult)

    payload = result.to_payload()
    json.dumps(payload)  # must not raise — the whole point of the JSON seam

    # The fib path is the one prone to numpy leakage; wave_df guarantees a leg, so assert it
    # is actually present (not silently None) and thus was exercised by json.dumps above.
    assert payload["fibonacci"] is not None
    for key in ("market", "trend", "momentum", "support_resistance", "confluence"):
        assert key in payload
    assert payload["explanation"] is None  # keyless fixture -> facts-only fallback


def test_advise_market_is_per_request_not_from_config(cfg, wave_df):
    """symbol/timeframe are arguments; the config's market is only a default and is untouched."""
    result = advise("ETH/USDT", "4h", cfg, df=wave_df)
    market = result.to_payload()["market"]
    assert market["symbol"] == "ETH/USDT"
    assert market["timeframe"] == "4h"

    # The original config must not be mutated by the per-request override.
    assert cfg.market.symbol == "BTC/USDT"
    assert cfg.market.timeframe == "1h"


def test_advise_explanation_flows_into_payload(cfg, wave_df):
    """With an injected client (no key needed), Claude's text lands in the payload."""
    client = _FakeClient()
    result = advise("BTC/USDT", "1h", cfg, df=wave_df, client=client)

    assert result.explanation == "This market is in an uptrend."
    assert result.to_payload()["explanation"] == "This market is in an uptrend."
    # The config's model choice is honoured on the way through to the client.
    assert client.captured["model"] == cfg.advisor.model


def test_advise_carries_geometry_matching_the_facts(cfg, wave_df):
    """Compute-once: the fib object on the result is the same leg the facts report."""
    result = advise("BTC/USDT", "1h", cfg, df=wave_df)
    assert result.fib is not None
    facts_fib = result.to_payload()["fibonacci"]
    assert facts_fib["impulse_low"] == round(result.fib.low_price, 2)
    assert facts_fib["impulse_high"] == round(result.fib.high_price, 2)
