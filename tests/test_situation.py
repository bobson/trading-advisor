"""ROADMAP A3 — the situation tier is Layer 1's decision.

Each §2 "no clear setup" criterion is isolated in its own test (hand-built facts where ONLY that
criterion holds), plus: the confirmed shape (§4), precedence, determinism, forming patterns being
context only, and the explanation layer receiving — and being bound by — the tier.
"""

from __future__ import annotations

import copy
from pathlib import Path

import pandas as pd
import pytest

from src.advisor import explain as ex
from src.advisor import facts as facts_mod
from src.advisor.facts import build_facts, facts_to_prompt
from src.config import load_config
from src.indicators.features import add_features
from src.patterns.base import Pattern
from src.signals import situation as st
from src.structure.swings import find_swings

FIXTURE = Path(__file__).parent / "fixtures" / "btc_1h_sample.csv"


@pytest.fixture(scope="module")
def cfg():
    return load_config()


GOOD_PROFILE = {"price": "supports", "volume": "supports", "momentum": "neutral",
                "volatility": "neutral", "candlestick": "neutral", "higher_tf": "unavailable",
                "structure": "neutral"}


def _pattern(state="confirmed", direction="bullish", ptype="double bottom", **profile):
    return {"type": ptype, "direction": direction, "state": state,
            "confirmation": {**GOOD_PROFILE, **profile}}


def _facts(*, bias="neutral", triggered=False, categories=None, votes=None, patterns=None,
           rsi_zone="overbought", adx=30.0, trend="uptrend", round_near=False):
    """Minimal facts with every §2 criterion OFF by default-ish; tests flip exactly what they need."""
    votes = votes or {}
    return {
        "confluence": {
            "bias": bias, "triggered": triggered, "categories": categories or {},
            "signals": [{"name": n, "direction": d} for n, d in votes.items()],
        },
        "chart_patterns": patterns or [],
        "round_number": {"is_near": round_near},
        "momentum": {"rsi_zone": rsi_zone},
        "volatility": {"adx": adx},
        "trend": {"label": trend},
    }


def _tier(facts, cfg):
    return st.classify_situation(facts, cfg)


# --- each §2 criterion, isolated --------------------------------------------------------------

def test_criterion_no_pattern_no_confluence(cfg):
    f = _facts(round_near=True)                        # at a level; no pattern, not triggered
    s = _tier(f, cfg)
    assert s["tier"] == st.NO_SETUP and s["reasons"] == [st.R_NO_PATTERN_NO_CONFLUENCE]


def test_criterion_away_from_levels(cfg):
    # Categories aligned (trend + momentum) but price at no S/R, fib or round number, no pattern.
    f = _facts(bias="bullish", triggered=True,
               categories={"trend": "bullish", "momentum": "bullish", "structure": "neutral"},
               votes={"support_resistance": "neutral", "fibonacci": "neutral"})
    s = _tier(f, cfg)
    assert s["tier"] == st.NO_SETUP and s["reasons"] == [st.R_AWAY_FROM_LEVELS]


def test_criterion_conflicting_signals(cfg):
    f = _facts(categories={"trend": "bullish", "momentum": "bearish"},
               patterns=[_pattern()], round_near=True)          # a pattern silences the others
    s = _tier(f, cfg)
    assert s["tier"] == st.NO_SETUP and s["reasons"] == [st.R_CONFLICTING]


def test_criterion_neutral_indicators(cfg):
    f = _facts(categories={"trend": "neutral", "momentum": "neutral"}, patterns=[_pattern()],
               rsi_zone="neutral", adx=cfg.indicators.adx_trend_threshold - 5, trend="sideways",
               round_near=True)
    s = _tier(f, cfg)
    assert s["tier"] == st.NO_SETUP and s["reasons"] == [st.R_NEUTRAL_INDICATORS]


def test_neutral_indicators_not_when_price_is_at_sr(cfg):
    """'ADX low with NO range structure' — price at an S/R level is range structure."""
    f = _facts(categories={"structure": "bullish", "trend": "neutral"},
               votes={"support_resistance": "bullish"}, patterns=[_pattern()],
               rsi_zone="neutral", adx=10, trend="sideways")
    assert st.R_NEUTRAL_INDICATORS not in _tier(f, cfg)["reasons"]


def test_criterion_single_weak_signal(cfg):
    # One directional category (triggered only because require_categories could be 1), at a level.
    f = _facts(bias="bullish", triggered=True, categories={"trend": "bullish", "momentum": "neutral"},
               round_near=True)
    s = _tier(f, cfg)
    assert s["tier"] == st.NO_SETUP and s["reasons"] == [st.R_SINGLE_WEAK]


# --- confirmed: §4's shape -------------------------------------------------------------------

def _aligned(**kw):
    return _facts(bias="bullish", triggered=True,
                  categories={"trend": "bullish", "structure": "bullish"},
                  votes={"support_resistance": "bullish"}, **kw)


def test_confirmed_needs_the_full_shape(cfg):
    s = _tier(_aligned(patterns=[_pattern()]), cfg)
    assert s["tier"] == st.CONFIRMED and s["word_budget"] == 130


@pytest.mark.parametrize("pattern", [
    _pattern(direction="bearish"),                     # opposite the bias (SOL 1d's double bottom)
    _pattern(momentum="contradicts"),                  # momentum disagreeing
    _pattern(higher_tf="contradicts"),                 # higher timeframe opposing
    _pattern(volume="neutral", volatility="neutral"),  # no expansion
    _pattern(state="failed"),                          # failed is informative, not confirmed
])
def test_not_confirmed_when_any_element_is_missing(cfg, pattern):
    assert _tier(_aligned(patterns=[pattern]), cfg)["tier"] == st.NOTABLE


def test_confirmed_pattern_without_aligned_categories_is_not_confirmed(cfg):
    f = _facts(categories={"trend": "bullish", "structure": "neutral"}, patterns=[_pattern()],
               round_near=True, bias="bullish")
    assert _tier(f, cfg)["tier"] != st.CONFIRMED


def test_precedence_confirmed_beats_neutral_indicators(cfg):
    f = _aligned(patterns=[_pattern()], rsi_zone="neutral", adx=5, trend="sideways")
    assert _tier(f, cfg)["tier"] == st.CONFIRMED


# --- forming patterns are context only -------------------------------------------------------

def test_forming_only_chart_can_never_be_confirmed(cfg):
    perfect_but_forming = _pattern(state="forming", momentum="supports", volatility="supports")
    assert _tier(_aligned(patterns=[perfect_but_forming]), cfg)["tier"] != st.CONFIRMED


@pytest.mark.parametrize("base", [
    _facts(),                                                             # no_setup
    _aligned(),                                                           # aligned at a level
    _aligned(patterns=[_pattern()]),                                      # confirmed
])
def test_adding_forming_patterns_never_changes_the_tier(cfg, base):
    with_forming = copy.deepcopy(base)
    with_forming["chart_patterns"] += [_pattern(state="forming", ptype="ascending channel"),
                                       _pattern(state="forming", direction="bearish", ptype="rectangle")]
    assert _tier(with_forming, cfg) == _tier(base, cfg)


def test_forming_pattern_cannot_align_categories(cfg, monkeypatch):
    """Patterns are not confluence voters: injecting a forming pattern into build_facts leaves the
    confluence verdict (and `triggered`) byte-identical — the SOL 'forming channel' case."""
    df = pd.read_csv(FIXTURE, index_col="timestamp", parse_dates=["timestamp"])
    df.index = pd.to_datetime(df.index, utc=True)
    feat, swings = add_features(df, cfg), find_swings(df, cfg.structure.swing_sensitivity)
    base = build_facts(feat, swings, cfg)

    forming = Pattern(type="ascending channel", kind="continuation", direction="bullish",
                      state="forming", bars=[10, 20], breakout_level=1e9, invalidation_level=1.0)
    monkeypatch.setattr(facts_mod, "find_patterns", lambda *a, **k: [forming])
    injected = build_facts(feat, swings, cfg)
    assert injected["confluence"] == base["confluence"]
    assert injected["situation"]["tier"] != st.CONFIRMED


# --- determinism + wiring --------------------------------------------------------------------

def test_identical_facts_always_give_the_same_tier(cfg):
    f = _aligned(patterns=[_pattern()])
    results = [_tier(copy.deepcopy(f), cfg) for _ in range(5)]
    assert all(r == results[0] for r in results)
    assert _tier(f, cfg) == _tier(f, cfg)


def test_build_facts_carries_the_tier_and_prompt_leads_with_it(cfg):
    df = pd.read_csv(FIXTURE, index_col="timestamp", parse_dates=["timestamp"])
    df.index = pd.to_datetime(df.index, utc=True)
    feat, swings = add_features(df, cfg), find_swings(df, cfg.structure.swing_sensitivity)
    a, b = build_facts(feat, swings, cfg), build_facts(feat, swings, cfg)
    assert a["situation"] == b["situation"] and a["situation"]["tier"] in st.TIERS
    text = facts_to_prompt(a)
    assert text.startswith(f"SITUATION TIER: {a['situation']['tier']}")


# --- the explanation layer is bound by the tier ----------------------------------------------

class _Client:
    def __init__(self):
        self.captured = None
        client = self

        class _M:
            def create(self, **kw):
                client.captured = kw

                class _B:
                    type, text = "text", "ok"

                class _R:
                    content = [_B()]
                return _R()
        self.messages = _M()


def _mode(cfg, style):
    return cfg.model_copy(update={"advisor": cfg.advisor.model_copy(update={"explanation_style": style})})


@pytest.mark.parametrize("tier", [st.NO_SETUP, st.NOTABLE, st.CONFIRMED])
def test_brief_budget_comes_from_the_tier(cfg, tier):
    c = _Client()
    ex.explain("FACTS", _mode(cfg, "brief"), client=c, situation=st.situation(tier, []))
    note = c.captured["system"][1]["text"]
    assert f"SITUATION TIER: {tier}" in note and f"{st.WORD_BUDGET[tier]} words" in note
    assert c.captured["max_tokens"] == ex._tokens_for(st.WORD_BUDGET[tier]) + ex._OPPOSING_LINE_TOKENS
    # the note names ONE tier — no menu of budgets to choose from
    assert "mildly notable 70" not in note


def test_teaching_keeps_the_tier_but_lifts_the_word_cap(cfg):
    c = _Client()
    ex.explain("FACTS", _mode(cfg, "teaching"), client=c, situation=st.situation(st.NO_SETUP, []))
    note = c.captured["system"][1]["text"]
    assert "SITUATION TIER: no_setup" in note and c.captured["max_tokens"] == 2048


def test_synthesis_is_always_the_mtf_tier(cfg):
    c = _Client()
    ex.synthesize([("1h", "F", 1.0), ("4h", "G", 2.0)], _mode(cfg, "brief"), client=c)
    assert "SITUATION TIER: mtf_synthesis" in c.captured["system"][1]["text"]
    assert c.captured["max_tokens"] == ex._tokens_for(st.WORD_BUDGET[st.MTF_SYNTHESIS]) + ex._OPPOSING_LINE_TOKENS
