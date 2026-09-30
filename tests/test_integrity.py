"""ROADMAP C1 (slim) — the integrity guard. For every check: a deliberately corrupted explanation is
caught AND a correct look-alike passes (false alarms are the real risk). Real explanations (saved
live Claude output, brief + teaching, BTC/SOL/EUR) pass. The retry and the facts-only fallback work."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pandas as pd
import pytest

from src.advisor.integrity import check_explanation, facts_only_summary
from src.config import load_config

FIX = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="module")
def cfg():
    return load_config()


@pytest.fixture(scope="module")
def facts(cfg):
    from src.service.analyze import advise
    df = pd.read_csv(FIX / "btc_1h_sample.csv", index_col="timestamp", parse_dates=["timestamp"])
    df.index = pd.to_datetime(df.index, utc=True)
    return advise("BTC/USDT", "1h", cfg, df=df, explain_enabled=False).facts


def _hard(text, facts, **kw):
    return [v["check"] for v in check_explanation(text, facts, **kw).hard]


def _soft(text, facts, **kw):
    return [v["check"] for v in check_explanation(text, facts, **kw).soft]


# --- real explanations pass ---------------------------------------------------------------------------

def test_saved_real_explanations_pass_without_a_hard_failure():
    for ex in json.loads((FIX / "real_explanations.json").read_text()):
        r = check_explanation(ex["explanation"], ex["facts"], style=ex["style"])
        assert r.ok, (ex["symbol"], ex["style"], r.hard)


# --- hard checks: caught, and their look-alikes pass -------------------------------------------------------

def test_invented_price_is_caught_and_rounded_or_unit_numbers_pass(facts):
    last = facts["market"]["last_close"]
    assert _hard(f"Resistance sits at {last * 1.07:,.2f}.", facts) == ["invented_price"]
    assert _hard(f"Price is at {last:,.2f}; round that to {round(last, -2):,.0f}.", facts) == []
    assert _hard("Volume is 1.1× its average and the stop is 0.9 ATR away.", facts) == []


def test_contradicting_what_the_facts_list_as_absent(facts):
    f = copy.deepcopy(facts)
    f["absences"] = list(f["absences"]) + ["no RSI divergence detected"]
    assert "contradicts_absence" in _hard("A bearish divergence is building on RSI.", f)
    assert "contradicts_absence" not in _hard("There is no divergence on RSI.", f)


def test_a_forming_pattern_described_as_confirmed(facts):
    f = copy.deepcopy(facts)
    f["chart_patterns"] = [{**f["chart_patterns"][0], "type": "double top", "state": "forming", "lifecycle": "forming"}]
    assert "state_upgrade" in _hard("The double top has confirmed and price broke out lower.", f)
    assert "state_upgrade" not in _hard("A close below the neckline would confirm the double top.", f)
    assert "state_upgrade" not in _hard("The double top is not confirmed yet.", f)


def test_a_directional_claim_against_the_read(facts):
    f = copy.deepcopy(facts)
    f["confluence"] = {**f["confluence"], "bias": "bearish"}
    f["situation"] = {**f["situation"], "tier": "notable"}
    assert _hard("Momentum favours the bulls here.", f) == ["opposite_direction"]
    assert _hard("Bearish read at resistance.\nOpposing: trend votes bullish.", f) == []    # bare words pass
    assert _hard("This suggests downside toward support.", f) == []                         # same direction


# --- soft checks --------------------------------------------------------------------------------------------

def test_directional_phrase_without_a_directional_read_is_soft(facts):
    f = copy.deepcopy(facts)
    f["situation"] = {**f["situation"], "tier": "no_setup"}
    f["confluence"] = {**f["confluence"], "bias": "neutral"}
    assert "directional_phrase" in _soft("Structure suggests upside from here.", f)
    assert _hard("Structure suggests upside from here.", f) == []                          # soft, never a rewrite


def test_missing_opposing_line_and_word_budget(facts):
    f = copy.deepcopy(facts)
    f["strongest_opposing_fact"] = {"category": "trend", "direction": "bullish", "detector": "trend",
                                    "reason": "higher highs", "opposing_categories": ["trend"]}
    f["situation"] = {**f["situation"], "word_budget": 30}
    assert "missing_opposing" in _soft("Short read.", f)
    assert "missing_opposing" not in _soft("Short read.\nOpposing: trend votes bullish.", f)
    long = "word " * 60 + "\nOpposing: trend votes bullish."
    assert "over_budget" in _soft(long, f, style="brief")
    assert "over_budget" not in _soft(long, f, style="teaching")                           # teaching is exempt
    assert "over_budget" not in _soft("word " * 30 + "\nOpposing: " + "x " * 40, f, style="brief")  # Opposing not counted


def test_unknown_pattern_and_history_described_as_current(facts):
    f = copy.deepcopy(facts)
    f["chart_patterns"] = [{**f["chart_patterns"][0], "type": "falling wedge", "state": "confirmed", "lifecycle": "completed"}]
    assert "unknown_pattern" in _soft("A cup and handle is visible.", f)
    assert "unknown_pattern" not in _soft("There is no head and shoulders here.", f)
    assert "history_as_current" in _soft("The falling wedge is the current setup.", f)
    assert "history_as_current" not in _soft("The falling wedge completed earlier and is history.", f)


# --- the retry and the fallback -------------------------------------------------------------------------------

class _Client:
    """Returns the scripted texts in order and records every request."""
    def __init__(self, texts):
        self.texts, self.calls = list(texts), []
        outer = self

        class _M:
            @staticmethod
            def create(**kw):
                outer.calls.append(kw)
                t = outer.texts.pop(0)
                return type("R", (), {"content": [type("B", (), {"type": "text", "text": t})()]})()
        self.messages = _M


def _advise(cfg, client):
    from src.service.analyze import advise
    df = pd.read_csv(FIX / "btc_1h_sample.csv", index_col="timestamp", parse_dates=["timestamp"])
    df.index = pd.to_datetime(df.index, utc=True)
    return advise("BTC/USDT", "1h", cfg, df=df, client=client)


def test_a_clean_explanation_is_not_retried(cfg, facts):
    c = _Client([f"Price at {facts['market']['last_close']}."])
    r = _advise(cfg, c)
    assert len(c.calls) == 1 and r.verification["ok"] and not r.verification["retried"]


def test_a_bad_explanation_is_rewritten_once_with_the_violations(cfg, facts):
    bad = f"Resistance sits at {facts['market']['last_close'] * 1.07:,.2f}."
    c = _Client([bad, f"Price at {facts['market']['last_close']}."])
    r = _advise(cfg, c)
    assert len(c.calls) == 2 and r.verification["retried"] and r.verification["ok"] and not r.verification["fallback"]
    retry_msgs = c.calls[1]["messages"]
    assert retry_msgs[1] == {"role": "assistant", "content": bad}
    assert "invented_price" in retry_msgs[2]["content"]
    assert r.verification["first_attempt_hard"][0]["check"] == "invented_price"


def test_two_bad_explanations_fall_back_to_the_facts_only_summary(cfg, facts):
    bad = f"Resistance sits at {facts['market']['last_close'] * 1.07:,.2f}."
    c = _Client([bad, bad])
    r = _advise(cfg, c)
    v = r.verification
    assert v["fallback"] and v["notice"] and not v["ok"]
    assert r.explanation == facts_only_summary(r.facts)
    assert check_explanation(r.explanation, r.facts).ok                  # the fallback passes its own check


def test_facts_only_summary_is_layer_one_only(facts):
    s = facts_only_summary(facts)
    assert s.splitlines()[0].endswith(".") and ("categories agree" in s or "no directional read" in s)
