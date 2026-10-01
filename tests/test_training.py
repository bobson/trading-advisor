"""ROADMAP D6 — blind training: setups come from the look-ahead-safe encyclopedia walk; the chart ends
at the breakout candle and nothing about the pattern leaks before the call; the call goes to the
journal as "blind" and is judged at once; answered setups aren't offered again."""

from __future__ import annotations

import random
from pathlib import Path

import pandas as pd
import pytest

from src.config import load_config
from src.research import training as T

FIXTURE = Path(__file__).parent / "fixtures" / "btc_1h_sample.csv"


@pytest.fixture(scope="module")
def cfg():
    return load_config()


@pytest.fixture(scope="module")
def candles():
    df = pd.read_csv(FIXTURE, index_col="timestamp", parse_dates=["timestamp"])
    df.index = pd.to_datetime(df.index, utc=True)
    return df


def test_setups_are_confirmed_judged_breakouts_keyed_by_time(cfg, candles):
    from src.service.analyze import _request_config
    got = T.collect_setups(candles, _request_config(cfg, "BTC/USDT", "1h"), "BTC/USDT", "1h", horizon=10)
    assert got, "the fixture has confirmed patterns"
    times = {int(t.timestamp()) for t in candles.index}
    for s in got:
        assert s["bar_time"] in times and s["outcome"] in ("target", "failed", "open")
        assert s["direction"] in ("bullish", "bearish") and s["regime"]


def _db(tmp_path, candles, n=3):
    from src.journal.store import connect as jconnect
    conn = jconnect(str(tmp_path / "t.db"))
    conn.executescript(T.SCHEMA)
    rows = [{"symbol": "BTC/USDT", "timeframe": "1h", "bar_time": int(candles.index[200 + 20 * k].timestamp()),
             "type": "double top", "direction": "bearish", "regime": "ranging", "outcome": "failed", "move_atr": -0.4,
             "breakout": 1.0, "invalidation": 2.0, "target": 0.5} for k in range(n)]
    T.save(conn, rows)
    return conn


def test_pick_filters_and_skips_answered_setups(tmp_path, candles):
    conn = _db(tmp_path, candles)
    assert T.options(conn)["types"] == {"double top": 3}
    assert T.pick(conn, type_="head and shoulders") is None
    s = T.pick(conn, rng=random.Random(1))
    conn.execute("""INSERT INTO journal_entries (created_at, source, symbol, timeframe, bar_time, price, direction,
        confidence, invalidation, horizon_value, horizon_unit, end_time, verdict_visible, explanation_visible,
        rule_version) VALUES (1,'blind',?,?,?,1,'up',60,0.5,24,'bars',2,0,0,1)""", (s["symbol"], s["timeframe"], s["bar_time"]))
    left = {T.pick(conn, rng=random.Random(k))["id"] for k in range(20)}
    assert s["id"] not in left and len(left) == 2


def test_api_next_hides_the_pattern_and_answer_judges_and_reveals(cfg, candles, monkeypatch, tmp_path):
    from fastapi.testclient import TestClient

    import src.api.app as api
    import src.data.registry as registry
    import src.service.analyze as service
    _db(tmp_path, candles, n=1).close()
    monkeypatch.setattr(api, "_TRADES_DB", str(tmp_path / "t.db"))
    monkeypatch.setattr(registry, "get_candles", lambda *a, **k: candles)
    monkeypatch.setattr(service, "get_candles", lambda *a, **k: candles)
    api._HITS.clear()
    client = TestClient(api.app)
    setup = client.get("/training/next").json()["setup"]
    assert setup["as_of_bar"] == 200 and setup["price"] == pytest.approx(float(candles["close"].iloc[200]))
    assert not {"type", "direction", "outcome", "regime"} & set(setup)                  # nothing leaks before the call
    body = {"setup_id": setup["id"], "direction": "up", "confidence": 70, "invalidation": setup["price"] * 0.99}
    rev = client.post("/training/answer", json=body).json()
    assert rev["entry"]["source"] == "blind" and rev["entry"]["outcome"] in ("correct", "incorrect", "invalidated")
    assert rev["setup"]["type"] == "double top" and rev["reveal_bar"] == 200 + cfg.morning_report.horizons["1h"]
    assert {"bias", "tier", "cautions", "patterns"} <= set(rev["engine"])
    # the engine's read is from the breakout candle, not later: the journal froze it at that bar
    assert rev["entry"]["bar_time"] == setup["bar_time"]
    assert client.post("/training/answer", json=body).status_code == 400                # one call per setup
    assert client.get("/training/next").json()["setup"] is None                         # pool exhausted
    journal = client.get("/journal").json()
    assert journal["stats"]["by_source"]["blind"]["n"] == 1                               # practice feeds calibration


def test_a_setup_the_cache_no_longer_covers_is_skipped(cfg, candles, monkeypatch, tmp_path):
    from fastapi.testclient import TestClient

    import src.api.app as api
    import src.data.registry as registry
    conn = _db(tmp_path, candles, n=1)
    conn.execute("UPDATE training_setups SET bar_time = 1")                               # a candle that isn't cached
    conn.commit(); conn.close()
    monkeypatch.setattr(api, "_TRADES_DB", str(tmp_path / "t.db"))
    monkeypatch.setattr(registry, "get_candles", lambda *a, **k: candles)
    api._HITS.clear()
    assert TestClient(api.app).get("/training/next").json()["setup"] is None
