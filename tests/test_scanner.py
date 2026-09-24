"""Pattern scanner + the measured record beside every find."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from src.config import load_config
from src.research.scanner import SHOWN, pattern_record, scan, scan_market

FIXTURE = Path(__file__).parent / "fixtures" / "btc_1h_sample.csv"


@pytest.fixture(scope="module")
def cfg():
    return load_config()


@pytest.fixture(scope="module")
def candles():
    df = pd.read_csv(FIXTURE, index_col="timestamp", parse_dates=["timestamp"])
    df.index = pd.to_datetime(df.index, utc=True)
    return df


ROWS = [
    {"pattern_type": "double top", "timeframe": "1h", "symbol": "all", "regime": "all", "split": "all",
     "sample_size": 50, "judged_n": 30, "target_n": 30, "target_hit_n": 9, "follow_through_rate": 0.3,
     "failed_n": 18, "failure_rate": 0.6, "move_atr_median": 0.1},
    {"pattern_type": "double top", "timeframe": "1h", "symbol": "BTC/USDT", "regime": "all", "split": "all",
     "sample_size": 5, "judged_n": 3, "target_n": 3, "target_hit_n": 1, "follow_through_rate": None,
     "failed_n": 2, "failure_rate": None, "move_atr_median": None},
]


def test_record_is_the_all_markets_row_for_that_timeframe():
    r = pattern_record(ROWS, "double top", "1h")
    assert (r["target_hit_n"], r["target_n"], r["failed_n"], r["judged_n"]) == (9, 30, 18, 30)
    assert pattern_record(ROWS, "double top", "1d") is None
    assert pattern_record(ROWS, "falling wedge", "1h") is None


def test_scan_market_returns_only_current_patterns_with_records(cfg, candles):
    rows = scan_market(candles, "BTC/USDT", "1h", cfg, ROWS)
    assert rows, "fixture has current patterns"
    assert all(r["lifecycle"] in SHOWN for r in rows)
    for r in rows:
        assert r["record"] == (pattern_record(ROWS, r["type"], "1h"))
        if r["lifecycle"] == "forming":
            assert r["distance_atr"] is not None and r["distance_atr"] >= 0
        else:
            assert r["distance_atr"] == 0.0 and r["bars_since_breakout"] is not None


def test_scan_orders_fresh_then_forming_then_in_play_and_skips_bad_markets(cfg, candles):
    def candles_for(sym, tf):
        if sym == "BROKEN/USD":
            raise RuntimeError("no data")
        return candles
    out = scan([("BTC/USDT", "1h"), ("BROKEN/USD", "1h")], cfg, candles_for, ROWS)
    order = {"fresh": 0, "forming": 1, "in_play": 2}
    ranks = [order[r["lifecycle"]] for r in out["rows"]]
    assert ranks == sorted(ranks)
    assert out["skipped"] == [{"symbol": "BROKEN/USD", "timeframe": "1h", "reason": "no data"}]
    assert out["markets"] == 2


def test_api_scan_and_records_on_the_chart(cfg, candles, monkeypatch, tmp_path):
    from fastapi.testclient import TestClient

    import src.api.app as api
    import src.data.registry as registry
    import src.service.analyze as service
    from src.research.encyclopedia import save_rows
    from src.store.db import connect

    db = str(tmp_path / "w.db")
    conn = connect(db)
    save_rows(conn, [{**r, "examples": [], "insufficient_data": False, "seen_forming": 0, "decided_n": 0,
                      "pending_breakout_n": 0, "confirmed_n": 0, "invalidated_n": 0, "confirmation_rate": None,
                      "pending_outcome_n": 0, "move_n": 0, "move_atr_q1": None, "move_atr_q3": None,
                      "resolved_n": 0, "bars_to_resolution_median": None} for r in ROWS],
              built_at=1, params={}, replace_markets=[])
    conn.close()
    monkeypatch.setattr(api, "_TRADES_DB", db)
    monkeypatch.setattr(registry, "get_candles", lambda *a, **k: candles)
    monkeypatch.setattr(service, "get_candles", lambda *a, **k: candles)
    api._SCAN_CACHE.clear(); api._CACHE.clear(); api._HITS.clear()
    client = TestClient(api.app)

    out = client.get("/scan", params={"timeframes": "1h"}).json()
    assert out["rows"] and out["markets"] == len(registry.list_pairs())
    dt = [r for r in out["rows"] if r["type"] == "double top"]
    assert all(r["record"]["target_hit_n"] == 9 for r in dt)

    chart = client.get("/analysis", params={"symbol": "BTC/USDT", "timeframe": "1h"}).json()["chart"]
    for p in chart["overlays"]["patterns"]:
        assert "record" in p
        if p["type"] == "double top":
            assert p["record"]["failed_n"] == 18
