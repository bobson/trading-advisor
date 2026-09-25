"""ROADMAP R1 — caution conditions: each fires when it should and not when it shouldn't, the set is
look-ahead-safe on real candles, and it reaches the facts text, the API and the live news path."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.config import load_config
from src.indicators.features import COL_ATR, COL_SMA_SLOW, COL_VOLUME, COL_VOLUME_MA
from src.risk import caution as C

FIXTURE = Path(__file__).parent / "fixtures" / "btc_1h_sample.csv"


@pytest.fixture(scope="module")
def cfg():
    return load_config()


def _feat(n=120, atr=None, vol=None, vol_ma=None, sma=100.0, start="2026-06-01", freq="1h"):
    idx = pd.date_range(start, periods=n, freq=freq, tz="UTC")
    f = pd.DataFrame(index=idx)
    f[COL_ATR] = atr if atr is not None else np.full(n, 2.0)
    f[COL_SMA_SLOW] = sma
    f[COL_VOLUME] = vol if vol is not None else np.full(n, 100.0)
    f[COL_VOLUME_MA] = vol_ma if vol_ma is not None else np.full(n, 100.0)
    return f


def _facts(close=100.0, atr=2.0, tier="notable", bias="bullish", sup=(94.0, 96.0), res=(108.0, 110.0),
           patterns=(), trend=None, asset="crypto", session=None, weekend_gap=None, tf="1h", context=None):
    base = tf
    ms = {"timeframes": [base] + list((trend or {}).keys()),
          "signals": {"trend": {base: "neutral", **(trend or {})}}}
    return {
        "market": {"symbol": "BTC/USDT" if asset == "crypto" else "EUR/USD", "timeframe": tf, "last_close": close},
        "volatility": {"atr": atr},
        "situation": {"tier": tier},
        "confluence": {"bias": bias},
        "support_resistance": {"nearest_support": sup and {"lower": sup[0], "upper": sup[1]},
                               "nearest_resistance": res and {"lower": res[0], "upper": res[1]}},
        "chart_patterns": list(patterns),
        "mtf_signals": ms,
        "market_adaptation": {"asset_class": asset, "active_session": session, "weekend_gap": weekend_gap},
        "context": context,
    }


def _get(entries, code):
    return next(e for e in entries if e["code"] == code)


def _run(facts, feat, cfg):
    return C.caution_conditions(facts, feat, cfg)


# --- each condition: fires / doesn't -----------------------------------------------------------------

def test_no_expansion_fires_only_when_neither_volume_nor_atr_expanded(cfg):
    pat = [{"type": "double bottom", "state": "confirmed", "lifecycle": "fresh", "bars_since_state_change": 2}]
    flat_atr = np.full(120, 2.0)
    quiet = _feat(atr=flat_atr, vol=np.full(120, 80.0))                       # 0.8× volume, ATR flat
    assert _get(_run(_facts(patterns=pat), quiet, cfg), "no_expansion")["active"] is True
    loud = _feat(atr=flat_atr, vol=np.full(120, 200.0))                       # 2× volume
    assert _get(_run(_facts(patterns=pat), loud, cfg), "no_expansion")["active"] is False
    rising = _feat(atr=np.linspace(1, 3, 120), vol=np.full(120, 80.0))       # ATR expanding
    assert _get(_run(_facts(patterns=pat), rising, cfg), "no_expansion")["active"] is False
    no_vol = _feat(atr=flat_atr, vol=np.zeros(120))                           # forex: no real volume
    assert _get(_run(_facts(patterns=pat), no_vol, cfg), "no_expansion")["active"] is True
    assert _get(_run(_facts(), quiet, cfg), "no_expansion")["active"] is False   # no fresh breakout


def test_stretched_is_measured_in_atr_from_the_slow_ma(cfg):
    assert _get(_run(_facts(close=107.0), _feat(), cfg), "stretched")["active"] is True     # 3.5 ATR
    assert _get(_run(_facts(close=93.0), _feat(), cfg), "stretched")["active"] is True      # below too
    assert _get(_run(_facts(close=104.0), _feat(), cfg), "stretched")["active"] is False    # 2 ATR


def test_volatility_extreme_high_low_and_normal(cfg):
    up = _get(_run(_facts(), _feat(atr=np.linspace(1, 3, 120)), cfg), "volatility_extreme")
    down = _get(_run(_facts(), _feat(atr=np.linspace(3, 1, 120)), cfg), "volatility_extreme")
    mid = _get(_run(_facts(), _feat(atr=np.r_[np.linspace(1, 3, 60), np.full(60, 2.0)]), cfg), "volatility_extreme")
    assert (up["active"], up["value"]["kind"]) == (True, "high")
    assert (down["active"], down["value"]["kind"]) == (True, "low")
    assert mid["active"] is False


def test_stop_in_noise_uses_the_reads_invalidation(cfg):
    near = _get(_run(_facts(sup=(98.4, 99.5)), _feat(), cfg), "stop_in_noise")         # 0.8 ATR
    far = _get(_run(_facts(sup=(94.0, 96.0)), _feat(), cfg), "stop_in_noise")          # 3 ATR
    assert near["active"] is True and far["active"] is False
    bear = _get(_run(_facts(bias="bearish", res=(100.5, 101.5)), _feat(), cfg), "stop_in_noise")
    assert bear["active"] is True                                                       # 0.75 ATR above
    none = _get(_run(_facts(tier="no_setup"), _feat(), cfg), "stop_in_noise")
    assert none["active"] is None and "not applicable" in none["detail"]


def test_no_room_compares_reward_after_costs_with_risk(cfg):
    tight = _get(_run(_facts(sup=(94.0, 96.0), res=(101.0, 103.0)), _feat(), cfg), "no_room")
    wide = _get(_run(_facts(sup=(98.0, 98.5), res=(108.0, 110.0)), _feat(), cfg), "no_room")
    assert tight["active"] is True and tight["value"]["cost_atr"] > 0
    assert wide["active"] is False
    assert _get(_run(_facts(tier="no_setup"), _feat(), cfg), "no_room")["active"] is None


def test_htf_against_reads_the_highest_directional_timeframe(cfg):
    against = _get(_run(_facts(trend={"4h": "bullish", "1d": "bearish"}), _feat(), cfg), "htf_against")
    assert against["active"] is True and against["value"]["timeframe"] == "1d"
    agree = _get(_run(_facts(trend={"4h": "bearish", "1d": "bullish"}), _feat(), cfg), "htf_against")
    assert agree["active"] is False
    flat = _get(_run(_facts(trend={"4h": "neutral"}), _feat(), cfg), "htf_against")
    assert flat["active"] is False
    assert _get(_run(_facts(trend=None), _feat(), cfg), "htf_against")["active"] is None


def test_event_risk_needs_the_calendar_and_is_never_guessed(cfg):
    now = pd.Timestamp.now(tz="UTC")
    ctx = {"economic_calendar": [{"time": str(now + timedelta(hours=2)), "country": "US", "event": "CPI", "impact": "high"}]}
    keyed = cfg.model_copy(update={"finnhub_api_key": "k"})
    assert _get(_run(_facts(context=ctx), _feat(), keyed), "event_risk")["active"] is True
    later = {"economic_calendar": [{"time": str(now + timedelta(hours=20)), "country": "US", "event": "CPI", "impact": "high"}]}
    assert _get(_run(_facts(context=later), _feat(), keyed), "event_risk")["active"] is False
    nokey = cfg.model_copy(update={"finnhub_api_key": None})
    assert _get(_run(_facts(context=ctx), _feat(), nokey), "event_risk")["active"] is None
    assert _get(_run(_facts(context=None), _feat(), keyed), "event_risk")["active"] is None


def test_thin_market_is_forex_only(cfg):
    fx = dict(asset="forex", tf="1h")
    assert _get(_run(_facts(**fx, weekend_gap=True), _feat(), cfg), "thin_market")["active"] is True
    assert _get(_run(_facts(**fx, session="Sydney / thin liquidity"), _feat(), cfg), "thin_market")["active"] is True
    assert _get(_run(_facts(**fx, session="London"), _feat(), cfg), "thin_market")["active"] is False
    daily = _feat(freq="1D")
    assert _get(_run(_facts(asset="forex", tf="1d", session="Sydney / thin liquidity"), daily, cfg),
                "thin_market")["active"] is False                                      # hour means nothing on 1d
    assert _get(_run(_facts(), _feat(), cfg), "thin_market")["active"] is None


def test_every_entry_is_unmeasured_and_the_order_is_fixed(cfg):
    out = _run(_facts(), _feat(), cfg)
    assert [e["code"] for e in out] == list(C.LABELS)
    assert {e["status"] for e in out} == {"unmeasured"}


# --- look-ahead safety on real candles ---------------------------------------------------------------

@pytest.fixture(scope="module")
def candles():
    df = pd.read_csv(FIXTURE, index_col="timestamp", parse_dates=["timestamp"])
    df.index = pd.to_datetime(df.index, utc=True)
    return df


def test_caution_is_look_ahead_safe(cfg, candles):
    """The walk's way: features on the FULL frame, then sliced to bar i. Mutating every bar after i
    (finite garbage, not NaN) must leave the conditions at i unchanged — checked at bars where
    conditions are actually ACTIVE, so the guard can't pass for the wrong reason."""
    from src.advisor.facts import build_facts
    from src.indicators.features import add_features
    from src.structure.swings import find_swings

    def caution_at(df, i):
        feat = add_features(df, cfg).iloc[: i + 1]
        return build_facts(feat, find_swings(df.iloc[: i + 1], cfg.structure.swing_sensitivity), cfg)["caution"]

    garbage = candles.copy()
    active_seen = set()
    for i in range(200, len(candles) - 5, 25):
        g = garbage.copy()
        g.iloc[i + 1:, :4] = g.iloc[i + 1:, :4] * 10
        a, b = caution_at(candles, i), caution_at(g, i)
        active_seen |= {e["code"] for e in a if e["active"]}
        assert a == b, f"caution at bar {i} changed when only future bars changed"
    assert len(active_seen) >= 3, f"guard exercised too few active conditions: {active_seen}"


# --- wiring: facts text, live news path, API ---------------------------------------------------------

def test_caution_reaches_the_facts_text_without_touching_the_verdict(cfg, candles):
    from src.service.analyze import advise
    r = advise("BTC/USDT", "1h", cfg, df=candles, explain_enabled=False)
    assert len(r.facts["caution"]) == 8
    assert "CAUTION CONDITIONS" in r.facts_text and "UNMEASURED" in r.facts_text
    assert r.facts_text.index("CAUTION CONDITIONS") < r.facts_text.index("CONFLUENCE VERDICT")


def test_live_context_rejudges_event_risk(cfg, candles):
    from src.service.analyze import advise
    now = pd.Timestamp.now(tz="UTC")
    ctx = {"economic_calendar": [{"time": str(now + timedelta(hours=1)), "country": "US", "event": "FOMC", "impact": "high"}]}
    keyed = cfg.model_copy(update={"finnhub_api_key": "k"})
    r = advise("BTC/USDT", "1h", keyed, df=candles, explain_enabled=False, context=ctx)
    ev = _get(r.facts["caution"], "event_risk")
    assert ev["active"] is True and "FOMC" in ev["detail"]


def test_api_payload_carries_caution(candles, monkeypatch):
    from fastapi.testclient import TestClient

    import src.api.app as api
    import src.service.analyze as service
    monkeypatch.setattr(service, "get_candles", lambda *a, **k: candles)
    api._CACHE.clear(); api._HITS.clear()
    body = TestClient(api.app).get("/analysis", params={"symbol": "BTC/USDT", "timeframe": "1h"}).json()
    assert [e["code"] for e in body["caution"]] == list(C.LABELS)
