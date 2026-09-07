"""Tests for Phase 7 — Layer 1 fact assembly (offline) and Layer 2 plumbing (mocked).

The live "done when" (explanation matches facts, never contradicts Layer 1) can only be
eyeballed with an API key. These tests cover what's verifiable offline: the facts dict is
assembled correctly, the displayed trend can't disagree with the confluence trend vote
(the consistency guarantee), and explain() wires the request and extracts text correctly.
"""

from __future__ import annotations

import pandas as pd
import pytest

from src.advisor.explain import explain
from src.advisor.facts import build_facts, facts_to_prompt
from src.config import load_config
from src.indicators.features import (
    COL_MACD,
    COL_MACD_SIGNAL,
    COL_RSI,
    COL_SMA_SLOW,
    PATTERN_COLUMNS,
)
from src.signals.confluence import BULLISH
from src.structure.swings import SWING_HIGH, SWING_LOW


@pytest.fixture(scope="module")
def cfg():
    return load_config()


@pytest.fixture
def uptrend_frame():
    """A 40-bar featured frame in a confirmed uptrend: rising SMA, oversold RSI, bullish MACD."""
    n = 40
    idx = pd.date_range("2025-01-01", periods=n, freq="h")
    close = pd.Series(range(90, 90 + n), dtype=float)  # gently rising
    close.iloc[-1] = 128.0
    df = pd.DataFrame(
        {
            "open": close.values,
            "high": (close + 1).values,
            "low": (close - 1).values,
            "close": close.values,
            COL_SMA_SLOW: pd.Series(range(80, 80 + n), dtype=float).values,  # rising -> slope>0
            COL_RSI: 25.0,        # oversold -> bullish
            COL_MACD: 1.0,        # > signal -> bullish
            COL_MACD_SIGNAL: 0.5,
        },
        index=idx,
    )
    for col in PATTERN_COLUMNS:
        df[col] = False
    return df


@pytest.fixture
def uptrend_swings():
    """Rising highs and rising lows -> uptrend structure; two lows near 100 form one S/R level."""
    records = [
        (2, 100.0, SWING_LOW),
        (5, 100.3, SWING_LOW),   # within 0.5% of 100.0 -> merges into one level (2 touches)
        (10, 110.0, SWING_HIGH),
        (15, 105.0, SWING_LOW),
        (20, 120.0, SWING_HIGH),
        (25, 115.0, SWING_LOW),
        (30, 130.0, SWING_HIGH),  # last swing is a high -> clean up-leg for Fibonacci
    ]
    return pd.DataFrame(records, columns=["bar", "price", "kind"])


# --- facts assembly ------------------------------------------------------------

def test_trend_and_momentum(cfg, uptrend_frame, uptrend_swings):
    facts = build_facts(uptrend_frame, uptrend_swings, cfg)
    assert facts["trend"]["label"] == "uptrend"
    assert facts["momentum"]["rsi"] == 25.0
    assert facts["momentum"]["rsi_zone"] == "oversold"
    assert facts["momentum"]["macd_state"] == "bullish"


def test_support_resistance_nearest(cfg, uptrend_frame, uptrend_swings):
    facts = build_facts(uptrend_frame, uptrend_swings, cfg)
    sr = facts["support_resistance"]
    # the two ~100 lows merged into a level below the 128 close
    assert sr["nearest_support"] is not None
    assert 100.0 <= sr["nearest_support"]["price"] <= 100.3
    assert sr["nearest_support"]["touches"] == 2
    # the single-touch highs (110/120/130) are filtered out -> no resistance level
    assert sr["nearest_resistance"] is None


def test_fibonacci_present(cfg, uptrend_frame, uptrend_swings):
    facts = build_facts(uptrend_frame, uptrend_swings, cfg)
    fib = facts["fibonacci"]
    assert fib is not None
    assert fib["direction"] == "up"
    assert set(fib["key_levels"].keys()) == {"0.382", "0.5", "0.618", "0.786"}


def test_confluence_flags_bullish(cfg, uptrend_frame, uptrend_swings):
    facts = build_facts(uptrend_frame, uptrend_swings, cfg)
    c = facts["confluence"]
    assert c["bias"] == BULLISH
    assert c["triggered"] is True
    assert c["agreeing"] == 3          # trend + rsi + macd (volume is neutral: no volume col here)
    assert len(c["signals"]) == 7      # + volume vote (Phase 15)


def test_displayed_trend_cannot_contradict_vote(cfg, uptrend_frame, uptrend_swings):
    """The consistency guarantee: same detector object feeds both display and the vote."""
    facts = build_facts(uptrend_frame, uptrend_swings, cfg)
    label = facts["trend"]["label"]
    trend_vote = next(s for s in facts["confluence"]["signals"] if s["name"] == "trend")
    # uptrend label <-> bullish vote; if they ever diverged, one of them was recomputed
    assert (label == "uptrend") == (trend_vote["direction"] == BULLISH)


def test_facts_to_prompt_renders(cfg, uptrend_frame, uptrend_swings):
    text = facts_to_prompt(build_facts(uptrend_frame, uptrend_swings, cfg))
    assert "TREND: uptrend" in text
    assert "CONFLUENCE VERDICT:" in text
    assert "BULLISH setup FLAGGED" in text


def test_volume_fact_absent_without_volume(cfg, uptrend_frame, uptrend_swings):
    """The fixture carries no volume column, so the volume fact is None and renders a note."""
    facts = build_facts(uptrend_frame, uptrend_swings, cfg)
    assert facts["volume"] is None
    text = facts_to_prompt(facts)
    assert "VOLUME:" in text and "no volume data" in text


def test_chart_patterns_field_present(cfg, uptrend_frame, uptrend_swings):
    facts = build_facts(uptrend_frame, uptrend_swings, cfg)
    assert isinstance(facts["chart_patterns"], list)  # additive Phase 9 field, may be empty
    text = facts_to_prompt(facts)
    assert "CHART PATTERNS (best-effort" in text  # labeled approximate for the model


# --- explain() plumbing (mocked client, no network) ----------------------------

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
        return _Resp([
            _Block("thinking", "internal reasoning that must be skipped"),
            _Block("text", "The setup is bullish. "),
            _Block("text", "Here is why."),
        ])


class _FakeClient:
    def __init__(self):
        self.captured = None
        self.messages = _FakeMessages(self)


def test_explain_extracts_only_text_blocks(cfg):
    client = _FakeClient()
    out = explain("FACTS HERE", cfg, client=client)
    assert out == "The setup is bullish. Here is why."  # thinking block skipped, stripped


def test_explain_uses_config_model_and_caches_system(cfg):
    client = _FakeClient()
    explain("FACTS HERE", cfg, client=client)
    assert client.captured["model"] == cfg.advisor.model
    system = client.captured["system"]
    assert system[0]["cache_control"] == {"type": "ephemeral"}
    # the facts land in the user turn
    assert "FACTS HERE" in client.captured["messages"][0]["content"]
