"""ROADMAP R3 — the honest test of the caution conditions: the pre-registered decision rule finds a
planted effect and does NOT find one in random flags; statuses by kind; the one walk with a purged
70/30 split; storage and injection into facts / facts text / API."""

from __future__ import annotations

import random
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.config import load_config
from src.risk import caution_stats as S
from src.risk.caution import LABELS, is_caution

FIXTURE = Path(__file__).parent / "fixtures" / "btc_1h_sample.csv"


def _case(symbol, part, flagged, loss, code="no_expansion", asset="crypto", tf="1h"):
    return {"symbol": symbol, "timeframe": tf, "asset": asset, "i": 0, "part": part, "direction": "bullish",
            "flags": {code: flagged}, "bracket": "loss" if loss else "win", "rule_v1": "expired",
            "mae_atr": 1.0, "range_atr": 2.0}


def _population(effect_markets=("A", "B", "C"), n=200, p_flag_loss=0.70, p_loss=0.45, tune_sign=1, seed=1):
    """Flagged cases lose p_flag_loss in `effect_markets`; everything else loses p_loss."""
    rnd = random.Random(seed)
    out = []
    for m in ("A", "B", "C"):
        for part in ("tune", "test"):
            for k in range(n):
                flagged = k % 2 == 0
                p = p_flag_loss if (flagged and m in effect_markets) else p_loss
                if part == "tune" and flagged and m in effect_markets and tune_sign < 0:
                    p = p_loss - 0.2
                out.append(_case(m, part, flagged, rnd.random() < p))
    return out


# --- the decision rule --------------------------------------------------------------------------------

def test_a_planted_condition_is_found():
    s = S.judge_directional(_population(), "no_expansion")
    assert s["status"] == "helps" and s["test"]["diff"] >= S.MIN_EFFECT
    assert s["markets_agreeing"] == "3 of 3"


def test_random_flags_are_not_a_finding():
    """Flags with no link to the outcome, big samples: the rule must not call it 'helps'."""
    for seed in range(5):
        s = S.judge_directional(_population(effect_markets=(), n=1500, seed=seed), "no_expansion")
        assert s["status"] == "no_effect", (seed, s["test"]["diff"])


def test_an_effect_that_flips_sign_in_the_older_part_is_not_a_finding():
    assert S.judge_directional(_population(tune_sign=-1), "no_expansion")["status"] == "no_effect"


def test_an_effect_in_one_market_only_is_not_a_finding():
    s = S.judge_directional(_population(effect_markets=("A",), p_flag_loss=0.95, n=2000), "no_expansion")
    assert s["status"] == "no_effect"


def test_too_few_cases_are_insufficient_never_a_rate():
    s = S.judge_directional(_population(n=10), "no_expansion")
    assert s["status"] == "insufficient" and s["test"]["diff"] is None


def test_every_condition_gets_its_pre_registered_kind():
    stats = S.aggregate(_population())
    assert set(stats) == set(LABELS)
    assert stats["stop_in_noise"]["status"] == stats["no_room"]["status"] == "by_construction"
    assert stats["volatility_extreme"]["status"] == "sizing"
    assert stats["event_risk"]["status"] == "forward_only"
    assert stats["thin_market"]["status"] == "insufficient"          # judged on forex cases only (none here)


def test_the_bracket_is_first_touch_both_ways():
    h, lo = np.array([101.5, 99.0]), np.array([100.2, 98.5])
    assert S._bracket("bullish", 100.0, 1.0, h, lo) == "win"
    assert S._bracket("bearish", 100.0, 1.0, h, lo) == "loss"
    assert S._bracket("bullish", 100.0, 1.0, np.array([101.2]), np.array([98.8])) == "ambiguous"
    assert S._bracket("bullish", 100.0, 1.0, np.array([100.5]), np.array([99.5])) == "none"


# --- the one walk, split and purge ------------------------------------------------------------------------

@pytest.fixture(scope="module")
def cfg():
    return load_config()


@pytest.fixture(scope="module")
def candles():
    df = pd.read_csv(FIXTURE, index_col="timestamp", parse_dates=["timestamp"])
    df.index = pd.to_datetime(df.index, utc=True)
    return df


def test_collect_uses_the_one_walk_with_a_purged_70_30_split(cfg, candles, monkeypatch):
    from src.service.analyze import _request_config
    calls = []
    real = S._ev.walk
    monkeypatch.setattr(S._ev, "walk", lambda *a, **k: (calls.append(1), real(*a, **k))[1])
    req = _request_config(cfg, "BTC/USDT", "1h")
    cases = S.collect(candles, req, "BTC/USDT", "1h", step=3)
    assert calls == [1] and cases
    horizon = cfg.morning_report.horizons["1h"]
    test_start = min(c["i"] for c in cases if c["part"] == "test")
    assert all(c["i"] + horizon < test_start for c in cases if c["part"] == "tune")      # no leak across
    assert all(c["direction"] in ("bullish", "bearish") and set(c["flags"]) == set(LABELS) for c in cases)
    assert {c["bracket"] for c in cases} <= {"win", "loss", "ambiguous", "none"}


# --- storage, injection, display ---------------------------------------------------------------------------

def test_save_load_and_apply_to_facts(cfg, candles, tmp_path):
    from src.service.analyze import advise
    from src.store.db import connect
    conn = connect(str(tmp_path / "c.db"))
    S.save(conn, S.aggregate(_population()), built_at=1, params={})
    stats = S.load(conn)
    assert stats["no_expansion"]["status"] == "helps" and stats["stop_in_noise"]["status"] == "by_construction"
    r = advise("BTC/USDT", "1h", cfg, df=candles, explain_enabled=False, caution_stats=stats)
    by = {c["code"]: c for c in r.facts["caution"]}
    assert by["no_expansion"]["status"] == "helps" and "held-back history" in by["no_expansion"]["record"]
    assert by["no_room"]["status"] == "by_construction" and "arithmetic warning" in by["no_room"]["record"]
    assert "arithmetic warning about this read's own levels" in r.facts_text       # the no_room tag
    plain = advise("BTC/USDT", "1h", cfg, df=candles, explain_enabled=False)
    assert {c["status"] for c in plain.facts["caution"]} == {"unmeasured"}        # build_facts untouched


def test_only_backed_conditions_are_cautions_the_rest_is_information():
    assert is_caution({"active": True, "status": "helps"})
    assert is_caution({"active": True, "status": "by_construction"})
    assert is_caution({"active": True, "status": "unmeasured"})
    assert not is_caution({"active": True, "status": "no_effect"})
    assert not is_caution({"active": True, "status": "insufficient"})
    assert not is_caution({"active": False, "status": "helps"})


def test_api_analysis_carries_measured_statuses(candles, monkeypatch, tmp_path):
    from fastapi.testclient import TestClient

    import src.api.app as api
    import src.service.analyze as service
    from src.store.db import connect
    db = str(tmp_path / "w.db")
    conn = connect(db)
    S.save(conn, S.aggregate(_population()), built_at=1, params={})
    conn.close()
    monkeypatch.setattr(api, "_TRADES_DB", db)
    monkeypatch.setattr(service, "get_candles", lambda *a, **k: candles)
    api._CACHE.clear(); api._HITS.clear()
    body = TestClient(api.app).get("/analysis", params={"symbol": "BTC/USDT", "timeframe": "1h"}).json()
    assert {c["code"]: c["status"] for c in body["caution"]}["event_risk"] == "forward_only"
