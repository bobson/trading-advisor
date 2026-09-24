"""ROADMAP B4 — measured records beside directional reads: verdict records (build, roll-up, lookup,
<20 rule), injection into facts/prompt, the API payload, and the guide rule."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from src.config import load_config
from src.research import verdict_records as vr
from src.research.verdict_records import MIN_N, aggregate, record_for, record_text

FIXTURE = Path(__file__).parent / "fixtures" / "btc_1h_sample.csv"


@pytest.fixture(scope="module")
def cfg():
    return load_config()


@pytest.fixture(scope="module")
def candles():
    df = pd.read_csv(FIXTURE, index_col="timestamp", parse_dates=["timestamp"])
    df.index = pd.to_datetime(df.index, utc=True)
    return df


def _cases(n, resolved, *, bias="bullish", agreeing=2, aligned=True):
    return [(bias, agreeing, aligned, k < resolved) for k in range(n)]


def test_aggregate_counts_per_type_and_rolls_up_all_markets():
    rows = aggregate({("BTC/USDT", "1d"): _cases(30, 12), ("ETH/USDT", "1d"): _cases(10, 7)})
    get = lambda s: next(r for r in rows if r["symbol"] == s)  # noqa: E731
    assert (get("BTC/USDT")["n"], get("BTC/USDT")["resolved"]) == (30, 12)
    assert (get("all")["n"], get("all")["resolved"]) == (40, 19)


def test_record_prefers_the_markets_own_row_when_it_has_enough_cases():
    rows = aggregate({("BTC/USDT", "1d"): _cases(30, 12), ("ETH/USDT", "1d"): _cases(10, 7)})
    for r in rows:
        r["horizon"] = 24
    own = record_for(rows, "BTC/USDT", "1d", "bullish", 2, True)
    assert own["scope"] == "BTC/USDT" and (own["resolved"], own["n"], own["rate"]) == (12, 30, 0.4)
    thin = record_for(rows, "ETH/USDT", "1d", "bullish", 2, True)          # 10 own cases -> pooled
    assert thin["scope"] == "all markets" and thin["n"] == 40


def test_insufficient_data_never_becomes_a_percentage():
    rows = aggregate({("BTC/USDT", "1d"): _cases(7, 5)})
    for r in rows:
        r["horizon"] = 24
    rec = record_for(rows, "BTC/USDT", "1d", "bullish", 2, True)
    assert rec["insufficient"] and rec["rate"] is None and rec["n"] < MIN_N
    text = record_text(rec)
    assert "insufficient data (7 cases)" in text and "%" not in text


def test_neutral_reads_and_unknown_types_have_no_record():
    rows = aggregate({("BTC/USDT", "1d"): _cases(30, 12)})
    assert record_for(rows, "BTC/USDT", "1d", "neutral", 0, False) is None
    assert record_for(rows, "BTC/USDT", "1d", "bearish", 2, True) is None
    assert record_for([], "BTC/USDT", "1d", "bullish", 2, True) is None


def test_record_text_reads_like_the_spec():
    rows = aggregate({("BTC/USDT", "1d"): _cases(430, 212)})
    for r in rows:
        r["horizon"] = 24
    t = record_text(record_for(rows, "BTC/USDT", "1d", "bullish", 2, True))
    assert t.startswith("categories aligned bullish, 2 categories agreeing — 212 of 430 resolved that way (49%)")


def test_collect_uses_the_one_walk_and_the_forward_close(cfg, candles, monkeypatch):
    calls = []
    real = vr._ev.walk
    monkeypatch.setattr(vr._ev, "walk", lambda *a, **k: (calls.append(1), real(*a, **k))[1])
    cases = vr.collect(candles, cfg, horizon=10, step=25)
    assert calls == [1] and cases
    assert all(b in ("bullish", "bearish") and isinstance(al, bool) and isinstance(res, bool)
               for b, _, al, res in cases)


def test_sqlite_round_trip(tmp_path):
    from src.store.db import connect
    conn = connect(str(tmp_path / "v.db"))
    vr.save(conn, aggregate({("BTC/USDT", "1d"): _cases(30, 12)}), horizon=24, built_at=5,
            markets=[("BTC/USDT", "1d")])
    rows = vr.load(conn)
    assert {r["symbol"] for r in rows} == {"BTC/USDT", "all"} and rows[0]["horizon"] == 24


def test_records_are_injected_into_facts_and_the_prompt(cfg, candles):
    from src.service.analyze import advise
    plain = advise("BTC/USDT", "1h", cfg, df=candles, explain_enabled=False)
    c = plain.facts["confluence"]
    assert "verdict_record" not in plain.facts                               # not in build_facts
    cases = _cases(40, 18, bias=c["bias"], agreeing=c["agreeing_categories"], aligned=c["triggered"])
    rows = aggregate({("BTC/USDT", "1h"): cases})
    for r in rows:
        r["horizon"] = 24
    pat_rows = [{"pattern_type": p["type"], "timeframe": "1h", "symbol": "all", "regime": "all", "split": "all",
                 "sample_size": 50, "judged_n": 30, "target_n": 30, "target_hit_n": 11, "follow_through_rate": 0.367,
                 "failed_n": 15, "failure_rate": 0.5, "move_atr_median": 0.2} for p in plain.facts["chart_patterns"]]
    got = advise("BTC/USDT", "1h", cfg, df=candles, explain_enabled=False,
                 verdict_records=rows, pattern_records=pat_rows)
    if c["bias"] in ("bullish", "bearish"):
        assert got.facts["verdict_record"]["resolved"] == 18
        assert "VERDICT RECORD" in got.facts_text and "18 of 40 resolved that way" in got.facts_text
    for p in got.facts["chart_patterns"]:
        assert p["record"]["target_hit_n"] == 11
    assert "history of this pattern type after a breakout: reached target 11 of 30 (37%)" in got.facts_text


def test_guide_requires_directional_reads_to_cite_their_record():
    from src.advisor.explain import ANALYST_GUIDE
    assert "Every directional read references its record" in ANALYST_GUIDE
    assert "VERDICT RECORD" in ANALYST_GUIDE and "insufficient data" in ANALYST_GUIDE


def test_api_analysis_carries_the_verdict_record(candles, monkeypatch, tmp_path):
    from fastapi.testclient import TestClient

    import src.api.app as api
    import src.service.analyze as service
    from src.store.db import connect
    db = str(tmp_path / "w.db")
    conn = connect(db)
    vr.save(conn, aggregate({("BTC/USDT", "1h"): _cases(40, 18, bias="bearish", agreeing=1, aligned=False)
                             + _cases(40, 22, bias="bullish", agreeing=1, aligned=False)
                             + _cases(40, 19, bias="bearish", agreeing=2, aligned=True)
                             + _cases(40, 21, bias="bullish", agreeing=2, aligned=True)}),
            horizon=24, built_at=1, markets=[("BTC/USDT", "1h")])
    conn.close()
    monkeypatch.setattr(api, "_TRADES_DB", db)
    monkeypatch.setattr(service, "get_candles", lambda *a, **k: candles)
    api._CACHE.clear(); api._HITS.clear()
    body = TestClient(api.app).get("/analysis", params={"symbol": "BTC/USDT", "timeframe": "1h"}).json()
    assert "verdict_record" in body
    c = body["confluence"]
    if c["bias"] in ("bullish", "bearish") and c["agreeing_categories"] in (1, 2):
        assert body["verdict_record"]["n"] == 40
