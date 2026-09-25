"""ROADMAP B5 — raw pattern quality calibrated into low / medium / high bands against what the
encyclopedia measured, shown with counts (never the raw 0.62)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from src.config import load_config
from src.research.encyclopedia import Instance, aggregate, quality_band, quality_cuts
from src.research.scanner import pattern_quality, quality_meaning

FIXTURE = Path(__file__).parent / "fixtures" / "btc_1h_sample.csv"


def _inst(k, quality, *, outcome="failed", first_state="forming", ptype="double top", symbol="A"):
    x = Instance(ptype, symbol, "1d", (k, k + 1, k + 2), k + 2, first_state, "ranging", "bearish",
                 100.0, 110.0, 90.0, quality=quality)
    if outcome:
        x.confirmed_bar, x.outcome, x.move_atr = k + 5, outcome, 0.5
    return x


def _population():
    """60 double tops: low scores mostly failed, high scores mostly reached target."""
    out = []
    for k in range(60):
        q = k / 60
        out.append(_inst(k, q, outcome="target" if (q >= 0.5) == (k % 5 != 0) else "failed",
                         symbol="A" if k % 2 else "B"))
    return out


# --- cut points + bands -------------------------------------------------------------------------

def test_cuts_are_tertiles_of_the_forming_population_only():
    xs = [_inst(k, k / 10) for k in range(10)] + [_inst(100, 0.99, first_state="confirmed")]
    lo, hi = quality_cuts(xs)
    assert 0.25 < lo < 0.35 and 0.55 < hi < 0.65                    # 0.99 (first seen confirmed) ignored


def test_no_bands_when_too_few_or_every_score_is_identical():
    assert quality_cuts([_inst(0, 0.5), _inst(1, 0.7)]) is None
    assert quality_cuts([_inst(k, 1.0) for k in range(30)]) is None   # clamped detector: nothing to band


def test_ties_at_a_clamped_value_leave_medium_empty_without_error():
    cuts = [1.0, 1.0]
    assert [quality_band(q, cuts) for q in (0.4, 0.99, 1.0)] == ["low", "low", "high"]
    assert quality_band(None, cuts) is None and quality_band(0.5, None) is None


def test_scores_tied_at_the_floor_band_as_low_not_high():
    xs = [_inst(k, 0.0) for k in range(20)] + [_inst(100 + k, 0.3 + k / 100) for k in range(10)]
    cuts = quality_cuts(xs)
    assert quality_band(0.0, cuts) == "low" and quality_band(0.3, cuts) == "high"


def test_aggregate_writes_one_row_per_band_and_stores_the_cuts():
    rows = aggregate(_population())
    top = next(r for r in rows if r["symbol"] == "all" and r["regime"] == "all" and r["split"] == "all")
    assert top["quality_cuts"] and len(top["quality_cuts"]) == 2
    bands = {r["split"]: r for r in rows if r["symbol"] == "all" and r["regime"] == "all"
             and r["split"].startswith("quality=")}
    assert set(bands) == {"quality=low", "quality=medium", "quality=high"}
    assert sum(b["sample_size"] for b in bands.values()) == top["sample_size"]   # every instance in one band
    # per-market rows use the SAME pooled cut points
    per_market = next(r for r in rows if r["symbol"] == "A" and r["regime"] == "all" and r["split"] == "all")
    assert per_market["quality_cuts"] == top["quality_cuts"]


# --- lookup + meaning ------------------------------------------------------------------------------

def test_pattern_quality_returns_the_band_with_its_counts_and_meaning():
    rows = aggregate(_population())
    got = pattern_quality(rows, "double top", "1d", 0.95)
    assert got["band"] == "high" and got["raw"] == 0.95
    assert got["judged_n"] == 20 and got["target_hit_n"] + got["failed_n"] == 20
    assert got["meaning"].startswith("higher-scored ones failed less often")
    assert pattern_quality(rows, "double top", "1d", 0.01)["band"] == "low"


def test_meaning_says_so_when_a_higher_score_did_not_help_or_cases_are_few():
    flipped = [_inst(k, k / 60, outcome="failed" if k >= 40 else "target") for k in range(60)]
    assert "did NOT mean fewer failures" in quality_meaning(aggregate(flipped), "double top", "1d")
    few = [_inst(k, k / 9) for k in range(9)]
    assert quality_meaning(aggregate(few), "double top", "1d").startswith("too few cases")


def test_old_encyclopedia_rows_without_bands_give_none():
    rows = [{"pattern_type": "double top", "timeframe": "1d", "symbol": "all", "regime": "all", "split": "all",
             "sample_size": 50, "judged_n": 30}]
    assert pattern_quality(rows, "double top", "1d", 0.7) is None
    assert pattern_quality([], "double top", "1d", 0.7) is None


# --- facts, prompt, API ----------------------------------------------------------------------------

@pytest.fixture(scope="module")
def cfg():
    return load_config()


@pytest.fixture(scope="module")
def candles():
    df = pd.read_csv(FIXTURE, index_col="timestamp", parse_dates=["timestamp"])
    df.index = pd.to_datetime(df.index, utc=True)
    return df


def _rows_for(types, tf):
    out = []
    for t in types:
        out += aggregate([_inst(k, k / 60, ptype=t, outcome=o) for k, o in
                          ((k, "target" if k >= 30 else "failed") for k in range(60))])
    for r in out:
        r["timeframe"] = tf
    return out


def test_prompt_shows_the_band_never_the_raw_score(cfg, candles):
    from src.service.analyze import advise
    plain = advise("BTC/USDT", "1h", cfg, df=candles, explain_enabled=False)
    assert plain.facts["chart_patterns"], "fixture has patterns"
    assert "quality: not calibrated" in plain.facts_text               # no encyclopedia passed
    rows = _rows_for({p["type"] for p in plain.facts["chart_patterns"]}, "1h")
    got = advise("BTC/USDT", "1h", cfg, df=candles, explain_enabled=False, pattern_records=rows)
    for p in got.facts["chart_patterns"]:
        assert p["quality_band"]["band"] in ("low", "medium", "high")
        assert f"quality {p['quality']}" not in got.facts_text
    assert "bands split past" in got.facts_text and "in that band reached target" in got.facts_text


def test_api_chart_patterns_carry_the_band(cfg, candles, monkeypatch, tmp_path):
    from fastapi.testclient import TestClient

    import src.api.app as api
    import src.service.analyze as service
    from src.research.encyclopedia import save_rows
    from src.service.analyze import advise
    from src.store.db import connect

    types = {p["type"] for p in advise("BTC/USDT", "1h", cfg, df=candles, explain_enabled=False).facts["chart_patterns"]}
    db = str(tmp_path / "w.db")
    conn = connect(db)
    save_rows(conn, _rows_for(types, "1h"), built_at=1, params={}, replace_markets=[])
    conn.close()
    monkeypatch.setattr(api, "_TRADES_DB", db)
    monkeypatch.setattr(service, "get_candles", lambda *a, **k: candles)
    api._CACHE.clear(); api._HITS.clear()
    chart = TestClient(api.app).get("/analysis", params={"symbol": "BTC/USDT", "timeframe": "1h"}).json()["chart"]
    pats = chart["overlays"]["patterns"]
    assert pats and all(p["quality_band"]["band"] in ("low", "medium", "high") for p in pats)
