"""ROADMAP A5 — facts payload hardening: explicit absences, pre-computed distances, nearest level
above/below, pattern ages, reliability field, per-signal MTF votes, strongest opposing fact, and
the §3 render order."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.advisor.facts import build_facts, facts_to_prompt
from src.advisor.facts_detail import (
    distance,
    mtf_signal_alignment,
    nearest_structural_levels,
    strongest_opposing_fact,
    zone_edge_distance,
)
from src.config import load_config
from src.indicators.features import COL_ATR, add_features
from src.patterns.chart_patterns import DOUBLE_TOP, find_patterns
from src.structure.swings import SWING_HIGH, SWING_LOW, find_swings

FIXTURE = Path(__file__).parent / "fixtures" / "btc_1h_sample.csv"


@pytest.fixture(scope="module")
def cfg():
    return load_config()


@pytest.fixture(scope="module")
def real(cfg):
    df = pd.read_csv(FIXTURE, index_col="timestamp", parse_dates=["timestamp"])
    df.index = pd.to_datetime(df.index, utc=True)
    feat = add_features(df, cfg)
    facts = build_facts(feat, find_swings(df, cfg.structure.swing_sensitivity), cfg)
    return feat, facts, facts_to_prompt(facts)


# --- distances: computed in Layer 1, signed, ATR + % ------------------------------------------

def test_distance_math_and_sign():
    assert distance(110.0, 100.0, 5.0) == {"distance_atr": 2.0, "distance_pct": 10.0}
    assert distance(95.0, 100.0, 5.0) == {"distance_atr": -1.0, "distance_pct": -5.0}
    assert distance(None, 100.0, 5.0) is None
    assert distance(110.0, 100.0, None)["distance_atr"] is None        # no ATR -> explicit None


def test_zone_distance_is_to_the_nearer_edge_and_zero_inside():
    assert zone_edge_distance(99.0, 101.0, 100.0, 2.0) == {"distance_atr": 0.0, "distance_pct": 0.0}
    assert zone_edge_distance(104.0, 106.0, 100.0, 2.0)["distance_atr"] == 2.0   # to 104, not 106
    assert zone_edge_distance(90.0, 96.0, 100.0, 2.0)["distance_atr"] == -2.0    # to 96


def test_every_level_carries_distances(real):
    _, f, _ = real
    for key in ("nearest_support", "nearest_resistance"):
        z = f["support_resistance"][key]
        if z:
            assert "distance_atr" in z and "distance_pct" in z
    if f["fibonacci"]:
        assert set(f["fibonacci"]["key_level_distances"]) == set(f["fibonacci"]["key_levels"])
    assert "signed_distance_atr" in f["round_number"]
    for p in f["chart_patterns"]:
        assert set(p["distances"]) == {"breakout", "invalidation", "target"}
    for mav in f["moving_averages"].values():
        assert mav is None or {"value", "distance_atr", "distance_pct"} <= set(mav)
    for side in ("above", "below"):
        lv = f["nearest_levels"][side]
        assert lv is None or {"price", "source", "distance_atr", "distance_pct"} <= set(lv)


def test_distances_rendered_and_never_left_to_the_model(real):
    _, _, text = real
    assert "PRE-COMPUTED" in text and " ATR / " in text


# --- nearest structural level above / below ---------------------------------------------------

def test_nearest_levels_pick_the_closest_on_each_side():
    zones = pd.DataFrame({"lower": [95.0], "upper": [96.0]})
    out = nearest_structural_levels(100.0, 2.0, zones=zones, fib_levels={"0.5": 103.0},
                                    patterns=[{"type": "double top", "state": "forming",
                                               "breakout_level": 101.5, "invalidation_level": 108.0}])
    assert out["above"]["price"] == 101.5 and "breakout" in out["above"]["source"]
    assert out["below"]["price"] == 96.0 and "upper edge" in out["below"]["source"]
    assert out["above"]["distance_atr"] == 0.75 and out["below"]["distance_atr"] == -2.0


def test_nearest_levels_always_has_round_numbers_either_side():
    out = nearest_structural_levels(84_232.0, 400.0, zones=pd.DataFrame(), fib_levels=None, patterns=[])
    assert out["above"]["price"] == 85_000 and out["below"]["price"] == 84_000


# --- explicit absences ------------------------------------------------------------------------

def test_absences_are_explicit_in_facts_and_prompt(real):
    _, f, text = real
    assert isinstance(f["absences"], list)
    if f["divergence"] is None:
        assert "no RSI divergence detected" in f["absences"]
        assert "RSI divergence: none detected" in text
    if not any(p["state"] == "confirmed" for p in f["chart_patterns"]):
        assert "no confirmed chart pattern" in f["absences"]
    assert "NOT PRESENT (explicitly checked):" in text
    assert "market context (sentiment, fundamentals, calendar, news): not fetched" in text
    assert "derivatives positioning: not available" in text
    assert ("TRACK RECORD: not available" in text) == (f.get("base_rate") is None)


def test_absences_on_a_bare_frame(cfg):
    """No volume, no patterns, no divergence -> each is named, none silently dropped."""
    n = 80
    idx = pd.date_range("2024-01-01", periods=n, freq="h", tz="UTC", name="timestamp")
    close = 100 + np.sin(np.arange(n) / 3.0)
    df = pd.DataFrame({"open": close, "high": close + 0.5, "low": close - 0.5, "close": close}, index=idx)
    feat = add_features(df, cfg)
    f = build_facts(feat, find_swings(df, cfg.structure.swing_sensitivity), cfg)
    for expected in ("no volume data", "no RSI divergence detected", "no confirmed chart pattern"):
        assert expected in f["absences"]
    assert "no volume data available" in facts_to_prompt(f)


# --- bars since confirmation ------------------------------------------------------------------

def _double_top(cfg, closes_after):
    n = 7 + len(closes_after)
    idx = pd.date_range("2024-01-01", periods=n, freq="D", tz="UTC")
    c = np.full(n, 100.0)
    c[7:] = closes_after
    df = pd.DataFrame({"open": c, "high": c + 1, "low": c - 1, "close": c, COL_ATR: 2.0}, index=idx)
    sw = pd.DataFrame([(2, 110.0, SWING_HIGH), (4, 100.0, SWING_LOW), (6, 110.0, SWING_HIGH)],
                      columns=["bar", "price", "kind"])
    return next(p for p in find_patterns(df, sw, cfg) if p.type == DOUBLE_TOP)


def test_bars_since_confirmation(cfg):
    p = _double_top(cfg, [101.0, 95.0, 97.0, 96.0])         # broke below 100 on the 2nd close
    assert p.state == "confirmed" and p.bars_since_state_change == 2
    assert p.bars_since_completion == 4                      # last bar (10) − right peak (6)


def test_bars_since_failure_and_forming_is_none(cfg):
    failed = _double_top(cfg, [95.0, 97.0, 105.0, 104.0])   # reclaimed on the 3rd close
    assert failed.state == "failed" and failed.bars_since_state_change == 1
    forming = _double_top(cfg, [104.0, 105.0])
    assert forming.state == "forming" and forming.bars_since_state_change is None


# --- reliability field ------------------------------------------------------------------------

def test_reliability_is_a_field_marked_unmeasured(real):
    _, f, text = real
    rel = f["detector_reliability"]
    assert set(rel["detectors"]) == {s["name"] for s in f["confluence"]["signals"]}
    assert all(d == {"precision": None, "n": 0, "status": "unmeasured"} for d in rel["detectors"].values())
    assert "DETECTOR RELIABILITY: unmeasured" in text


# --- per-signal multi-timeframe alignment -----------------------------------------------------

def test_mtf_per_signal_on_real_data(real, cfg):
    _, f, text = real
    ms = f["mtf_signals"]
    assert ms["timeframes"][0] == cfg.market.timeframe
    assert "4h" in ms["timeframes"]                           # 350 1h bars -> 87 4h bars >= 50
    assert "1d" not in ms["timeframes"]                       # only ~14 daily bars -> dormant
    assert set(ms["signals"]["trend"]) == {"1h", "4h"}
    assert "trend: 1h " in text and " / 4h " in text


def test_mtf_per_signal_base_only_when_history_is_short(cfg):
    n = 60
    idx = pd.date_range("2024-01-01", periods=n, freq="h", tz="UTC")
    c = np.linspace(100, 110, n)
    feat = add_features(pd.DataFrame({"open": c, "high": c + 1, "low": c - 1, "close": c}, index=idx), cfg)
    out = mtf_signal_alignment(feat, {"trend": "bullish"}, cfg)
    assert out["timeframes"] == [cfg.market.timeframe]
    assert out["signals"] == {"trend": {cfg.market.timeframe: "bullish"}}


# --- strongest opposing fact ------------------------------------------------------------------

def _conf(bias, cats, signals):
    return {"bias": bias, "categories": cats, "signals": signals}


def test_strongest_opposing_fact_picks_the_heaviest_opposing_category(cfg):
    w = cfg.confluence.category_weights
    c = _conf("bullish", {"trend": "bullish", "momentum": "bearish", "volume": "bearish"},
              [{"name": "macd", "category": "momentum", "direction": "bearish", "reason": "MACD below"},
               {"name": "volume", "category": "volume", "direction": "bearish", "reason": "down volume"}])
    out = strongest_opposing_fact(c, cfg)
    heavier = max(("momentum", "volume"), key=lambda k: w.get(k, 1.0))
    assert out["category"] == heavier and set(out["opposing_categories"]) == {"momentum", "volume"}
    assert out["reason"] is not None


def test_no_opposing_fact_when_nothing_opposes_or_no_read(cfg):
    assert strongest_opposing_fact(_conf("bullish", {"trend": "bullish", "volume": "neutral"}, []), cfg) is None
    assert strongest_opposing_fact(_conf("neutral", {"trend": "bullish", "volume": "bearish"}, []), cfg) is None


def test_opposing_fact_is_rendered_or_its_absence_stated(real):
    _, f, text = real
    assert "STRONGEST OPPOSING FACT" in text
    if f["strongest_opposing_fact"] is None and f["confluence"]["bias"] in ("bullish", "bearish"):
        assert "no category votes against the read" in f["absences"]


# --- §3 priority order ------------------------------------------------------------------------

def test_prompt_follows_the_guides_priority_order(real):
    _, _, text = real
    heads = ["1. TREND & REGIME", "2. STRUCTURE", "3. PATTERNS", "4. MOMENTUM", "5. VOLATILITY",
             "6. VOLUME", "7. MARKET CONTEXT", "CONFLUENCE VERDICT"]
    positions = [text.index(h) for h in heads]
    assert positions == sorted(positions)


def test_weekly_votes_are_information_only(cfg):
    """A daily chart with ~60 weeks of history gets 1w per-signal votes (facts_from), while the
    veto (context_from = 4h/1d) is untouched — no higher-TF gate applies to a 1d base."""
    daily = cfg.model_copy(update={"market": cfg.market.model_copy(update={"timeframe": "1d"})})
    n = 420
    idx = pd.date_range("2023-01-02", periods=n, freq="D", tz="UTC", name="timestamp")
    c = 100 + np.cumsum(np.sin(np.arange(n) / 7.0))
    df = pd.DataFrame({"open": c, "high": c + 1, "low": c - 1, "close": c, "volume": 1000.0}, index=idx)
    feat = add_features(df, daily)
    f = build_facts(feat, find_swings(df, daily.structure.swing_sensitivity), daily)
    assert f["mtf_signals"]["timeframes"] == ["1d", "1w"]
    assert set(f["mtf_signals"]["signals"]["trend"]) == {"1d", "1w"}
    assert f["confluence"]["mtf_trends"] is None          # the gate never sees 1w
    assert "1w" not in daily.mtf.context_from and "1w" in daily.mtf.facts_from


def test_forex_prices_keep_their_precision(cfg):
    """A6 finding: facts used to round every price to 2 dp — EUR/USD zones read '1.15–1.15', ATR
    became 0.0 and pattern levels moved ~50 pips. Prices must keep the instrument's precision."""
    from src.market.precision import fmt_price, price_decimals, round_price
    assert (price_decimals(80_000), price_decimals(1.1464), price_decimals(0.52)) == (2, 5, 6)
    assert round_price(1.146894) == 1.14689 and fmt_price(63944.1) == "63944.10"

    n = 300
    idx = pd.date_range("2024-01-01", periods=n, freq="h", tz="UTC", name="timestamp")
    c = 1.10 + 0.004 * np.sin(np.arange(n) / 6.0) + np.linspace(0, 0.003, n)
    df = pd.DataFrame({"open": c, "high": c + 0.0006, "low": c - 0.0006, "close": c}, index=idx)
    f = build_facts(add_features(df, cfg), find_swings(df, cfg.structure.swing_sensitivity), cfg)
    assert f["volatility"]["atr"] and f["volatility"]["atr"] > 0          # not rounded to 0.0
    for key in ("nearest_support", "nearest_resistance"):
        z = f["support_resistance"][key]
        if z:
            assert z["lower"] != z["upper"] and z["distance_atr"] is not None
