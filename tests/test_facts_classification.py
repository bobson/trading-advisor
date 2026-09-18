"""Classification lives in Layer 1, not Layer 2.

The bug this guards: Layer 2 (Claude) was classifying facts itself — the same Fear & Greed value
came back "neutral" in one run and "bullish" in another. The fix moves ALL classification into
the deterministic facts payload: every confluence signal carries a pre-computed vote AND category
(from the engine), and context items (sentiment, funding, distance-from-ATH) are marked explicitly
as non-directional so Layer 2 narrates them instead of voting them.

These offline tests can't make Claude's prose deterministic — they guard the thing that CAN be
guaranteed: the classification is complete and deterministic in Layer 1, leaving nothing for
Layer 2 to decide.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from src.advisor.facts import build_facts, facts_to_prompt
from src.config import load_config
from src.indicators.features import add_features
from src.structure.swings import find_swings

_VOTES = {"bullish", "bearish", "neutral"}
_CATEGORIES = {"trend", "momentum", "structure", "volume", "volatility"}
_FIXTURE = Path(__file__).parent / "fixtures" / "btc_1h_sample.csv"


@pytest.fixture(scope="module")
def cfg():
    return load_config()


@pytest.fixture(scope="module")
def facts(cfg):
    df = pd.read_csv(_FIXTURE, index_col="timestamp", parse_dates=["timestamp"])
    df.index = pd.to_datetime(df.index, utc=True)
    return build_facts(add_features(df, cfg), find_swings(df, cfg.structure.swing_sensitivity), cfg)


def test_every_signal_has_a_vote_and_a_category(facts):
    """The core guard: nothing is left for Layer 2 to classify — each signal is fully typed."""
    signals = facts["confluence"]["signals"]
    assert signals
    for s in signals:
        assert s["direction"] in _VOTES, s
        assert s["category"] in _CATEGORIES, s          # pre-computed category, from the engine


def test_categories_match_the_engine(cfg, facts):
    """The category is taken from the confluence engine's own map, not re-derived."""
    from src.signals.confluence import SIGNAL_CATEGORY

    for s in facts["confluence"]["signals"]:
        assert s["category"] == SIGNAL_CATEGORY.get(s["name"], "other")


def test_classification_is_deterministic(cfg):
    """Identical facts inputs produce an identical classification (Layer 1 is a pure function)."""
    df = pd.read_csv(_FIXTURE, index_col="timestamp", parse_dates=["timestamp"])
    df.index = pd.to_datetime(df.index, utc=True)
    a = build_facts(add_features(df, cfg), find_swings(df, cfg.structure.swing_sensitivity), cfg)
    b = build_facts(add_features(df, cfg), find_swings(df, cfg.structure.swing_sensitivity), cfg)
    assert a["confluence"]["signals"] == b["confluence"]["signals"]


def test_context_items_are_marked_non_directional(facts):
    """Sentiment / funding / ATH-distance are rendered as CONTEXT with an explicit non-directional
    marker — never as a bullish/bearish vote — and a mid-range Fear & Greed is flagged as carrying
    no directional information."""
    enriched = {
        **facts,
        "context": {
            "as_of": "2025-01-01",
            "fear_greed": {"value": 56, "label": "Greed", "as_of": "2025-01-01"},
            "fundamentals": {"coin": "bitcoin", "market_cap": 1.2e12, "volume_24h": 3e10,
                             "change_24h_pct": 1.2, "ath_change_pct": -8.5},
        },
        "derivatives": {"as_of": "2025-01-01", "funding": {"rate_pct": 0.006, "annualized_pct": 6.6, "state": "neutral"}},
    }
    text = facts_to_prompt(enriched)
    assert "CONTEXT ONLY" in text                                   # both context blocks marked
    assert "mid-range" in text and "no directional information" in text   # F&G 56 is uninformative
    assert "not a directional vote" in text                        # ATH distance / fundamentals
    assert "contrarian flag" in text                               # funding framed non-directionally


def test_fear_greed_extreme_reads_contrarian(facts):
    extreme = {**facts, "context": {"as_of": "x", "fear_greed": {"value": 9, "label": "Extreme Fear", "as_of": "x"}}}
    text = facts_to_prompt(extreme)
    assert "extreme fear" in text and "contrarian" in text


def test_signals_render_with_vote_and_category(facts):
    """The rendered prompt shows the pre-computed [VOTE · category] so the model narrates it."""
    text = facts_to_prompt(facts)
    assert "re-classify a signal" in text
    # e.g. "[NEUTRAL · trend] trend: ..." — vote and category both present on the line
    assert any("· trend]" in line and line.strip().startswith("[") for line in text.splitlines())
