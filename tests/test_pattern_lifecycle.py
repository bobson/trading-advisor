"""Pattern life cycle after the breakout: fresh / in play / completed / expired / failed — so an old
signal is never presented as current. Uses a double top (peaks 110 at bars 2 and 6, neckline 100,
target 90) and hand-set closes/lows after the right peak."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.config import load_config
from src.indicators.features import COL_ATR
from src.patterns.chart_patterns import DOUBLE_TOP, find_patterns
from src.signals import situation as st
from src.structure.swings import SWING_HIGH, SWING_LOW


@pytest.fixture(scope="module")
def cfg():
    return load_config()


def _top(cfg, closes, lows=None, *, left_peak=2):
    """Double top with peaks at `left_peak` and 6; bars 7.. get `closes` (and optional `lows`)."""
    n = 7 + len(closes)
    idx = pd.date_range("2024-01-01", periods=n, freq="D", tz="UTC")
    c = np.full(n, 100.5)
    c[7:] = closes
    lo = c - 0.5
    if lows is not None:
        lo[7:] = lows
    df = pd.DataFrame({"open": c, "high": c + 0.5, "low": lo, "close": c, COL_ATR: 2.0}, index=idx)
    sw = pd.DataFrame([(left_peak, 110.0, SWING_HIGH), (4, 100.0, SWING_LOW), (6, 110.0, SWING_HIGH)],
                      columns=["bar", "price", "kind"])
    return next(p for p in find_patterns(df, sw, cfg) if p.type == DOUBLE_TOP)


def test_forming_until_it_breaks(cfg):
    p = _top(cfg, [104.0, 105.0])
    assert (p.state, p.lifecycle, p.state_bar) == ("forming", "forming", None)


def test_fresh_right_after_the_breakout(cfg):
    p = _top(cfg, [104.0, 99.0, 98.5])                       # broke below 100 on bar 8
    assert p.state == "confirmed" and p.lifecycle == "fresh"
    assert p.state_bar == 8 and p.bars_since_state_change == 1


def test_completed_once_the_target_is_reached(cfg):
    # target = 100 − (110 − 100) = 90; a later LOW of 89.5 reaches it, even though the close stays above
    p = _top(cfg, [99.0, 97.0, 95.0], lows=[98.5, 96.5, 89.5])
    assert p.target == 90.0
    assert p.lifecycle == "completed" and p.target_hit_bar == 9


def test_in_play_when_not_fresh_not_done_and_not_stale(cfg):
    # formation 2→6 = 4 bars; breakout 4 bars ago (> fresh 3, not > 1.0 × 4) → in play
    p = _top(cfg, [99.0, 98.0, 97.0, 96.0, 97.0])
    assert p.bars_since_state_change == 4 and p.lifecycle == "in_play"


def test_expired_when_it_outlives_its_own_formation(cfg):
    p = _top(cfg, [99.0, 98.0, 97.0, 96.0, 97.0, 96.5, 97.5])   # 6 bars since breakout > 4-bar formation
    assert p.lifecycle == "expired"
    longer = _top(cfg, [99.0, 98.0, 97.0, 96.0, 97.0, 96.5, 97.5], left_peak=0)  # 6-bar formation
    assert longer.lifecycle == "in_play"                       # same age, longer pattern → still in play


def test_failed_keeps_failed_with_its_bar(cfg):
    p = _top(cfg, [99.0, 105.0, 104.0])                        # broke, then reclaimed the neckline
    assert (p.state, p.lifecycle, p.state_bar) == ("failed", "failed", 8)


def test_history_patterns_never_make_the_tier_confirmed(cfg):
    base = {"confluence": {"bias": "bearish", "triggered": True,
                           "categories": {"trend": "bearish", "structure": "bearish"},
                           "signals": [{"name": "support_resistance", "direction": "bearish"}]},
            "round_number": {"is_near": False}, "momentum": {"rsi_zone": "neutral"},
            "volatility": {"adx": 30}, "trend": {"label": "downtrend"}}
    prof = {"price": "supports", "volume": "supports", "momentum": "neutral", "volatility": "neutral",
            "higher_tf": "unavailable"}
    pat = {"type": "double top", "direction": "bearish", "state": "confirmed", "confirmation": prof}
    for life, tier in (("fresh", st.CONFIRMED), ("in_play", st.CONFIRMED),
                       ("completed", st.NOTABLE), ("expired", st.NOTABLE)):
        facts = {**base, "chart_patterns": [{**pat, "lifecycle": life}]}
        assert st.classify_situation(facts, cfg)["tier"] == tier, life


def test_prompt_labels_history_as_history(cfg):
    from src.advisor.facts import _stage, _stage_text
    done = {"state": "confirmed", "lifecycle": "completed", "bars_since_state_change": 5,
            "state_bar": 10, "target_hit_bar": 13}
    assert _stage(done) == "COMPLETED · HISTORY"
    assert "reached its target 2 bars ago" in _stage_text(done) and "not a current setup" in _stage_text(done)
    fresh = {"state": "confirmed", "lifecycle": "fresh", "bars_since_state_change": 1}
    assert _stage(fresh) == "CONFIRMED · FRESH" and "broke out 1 bar ago" in _stage_text(fresh)


def test_chart_payload_carries_breakout_and_target_times():
    from src.service.analyze import advise
    from src.service.serialize import serialize_chart
    cfg = load_config()
    df = pd.read_csv("tests/fixtures/btc_1h_sample.csv", index_col="timestamp", parse_dates=["timestamp"])
    df.index = pd.to_datetime(df.index, utc=True)
    pats = serialize_chart(advise("BTC/USDT", "1h", cfg, df=df, explain_enabled=False))["overlays"]["patterns"]
    assert pats and all("lifecycle" in p and "state_time" in p and "target_hit_time" in p for p in pats)
    for p in pats:
        assert (p["state_time"] is None) == (p["lifecycle"] == "forming")
