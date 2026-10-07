"""Training on entry types: the entry detectors on the walk (look-ahead-safe), the mirror judge, the pool's
second family, and the per-type scorecard."""

from __future__ import annotations

import random
from pathlib import Path

import pandas as pd
import pytest

from src.config import load_config
from src.research import entries as E
from src.research import training as T

FIXTURE = Path(__file__).parent / "fixtures" / "btc_1h_sample.csv"


@pytest.fixture(scope="module")
def cfg():
    from src.service.analyze import _request_config
    return _request_config(load_config(), "BTC/USDT", "1h")


@pytest.fixture(scope="module")
def candles():
    df = pd.read_csv(FIXTURE, index_col="timestamp", parse_dates=["timestamp"])
    df.index = pd.to_datetime(df.index, utc=True)
    return df


@pytest.fixture(scope="module")
def found(cfg, candles):
    return E.collect_entries(candles, cfg, "BTC/USDT", "1h", horizon=10)


def test_entries_are_typed_judged_both_ways_and_keyed_by_time(found, candles):
    assert found, "the fixture has entry moments"
    times = {int(t.timestamp()) for t in candles.index}
    for s in found:
        assert s["type"] in E.ENTRY_TYPES and s["family"] == "entry"
        assert s["direction"] in ("bullish", "bearish") and s["bar_time"] in times
        assert s["outcome"] in ("target", "failed", "open") and s["outcome_opp"] in ("target", "failed", "open")
        assert (s["target"] > s["invalidation"]) == (s["direction"] == "bullish")
    assert len({s["type"] for s in found}) >= 3


def test_the_same_entry_is_not_taken_again_within_the_cooldown(found):
    pos = {}
    for s in found:
        if s["type"] == "RSI divergence":
            continue
        key = (s["type"], s["direction"])
        if key in pos:
            assert s["bar_time"] - pos[key] > E.COOLDOWN * 3600
        pos[key] = s["bar_time"]


def test_detection_never_sees_the_future(cfg, candles, found):
    """Garbage after bar `cut` changes no entry whose whole judging window ends before it."""
    cut = 300
    bad = candles.copy()
    bad.iloc[cut:, :4] = bad.iloc[cut:, :4] * 10
    again = E.collect_entries(bad, cfg, "BTC/USDT", "1h", horizon=10)
    limit = int(candles.index[cut - 10 - 1].timestamp())
    keep = lambda xs: [x for x in xs if x["bar_time"] < limit]  # noqa: E731
    assert keep(found) and keep(again) == keep(found)


def test_the_mirror_is_the_same_distances_the_other_way():
    sup, res = {"lower": 94.0, "upper": 95.0}, {"lower": 110.0, "upper": 111.0}
    # bullish: next 110, invalidation 94 → mirror bearish: next 90, invalidation 106
    up_first = [(111, 99)]
    down_first = [(101, 89)]
    assert E._judge("bullish", 100.0, 2.0, sup, res, up_first)[:2] == ("target", "failed")
    assert E._judge("bullish", 100.0, 2.0, sup, res, down_first)[:2] == ("failed", "target")
    assert E._judge("bullish", 100.0, 2.0, sup, res, [(101, 99)])[:2] == ("open", "open")


def _pool(tmp_path, candles, rows):
    from src.journal.store import connect as jconnect
    conn = jconnect(str(tmp_path / "t.db"))
    T.ensure_schema(conn)
    T.save(conn, rows)
    return conn


def _row(candles, k, typ="support bounce", family="entry", outcome="target", opp="failed"):
    return {"symbol": "BTC/USDT", "timeframe": "1h", "bar_time": int(candles.index[200 + k].timestamp()), "type": typ,
            "direction": "bullish", "regime": "ranging", "outcome": outcome, "outcome_opp": opp, "family": family,
            "move_atr": 0.5, "breakout": 1.0, "invalidation": 0.5, "target": 2.0}


def test_an_old_table_gets_the_new_columns_and_patterns_stay_patterns(tmp_path, candles):
    from src.journal.store import connect as jconnect
    conn = jconnect(str(tmp_path / "old.db"))
    conn.executescript(T.SCHEMA.replace("UNIQUE", "UNIQUE"))
    T.save(conn, [{k: v for k, v in _row(candles, 0, typ="double top").items() if k not in ("family", "outcome_opp")}])
    T.ensure_schema(conn)
    assert T.options(conn)["families"] == {"double top": "pattern"}


def test_pick_by_family_and_the_scorecard(tmp_path, candles):
    rows = [_row(candles, k) for k in range(3)] + [_row(candles, 10, typ="double top", family="pattern", opp=None)]
    conn = _pool(tmp_path, candles, rows)
    assert T.pick(conn, family="entry", rng=random.Random(0))["family"] == "entry"
    assert T.pick(conn, family="pattern")["type"] == "double top"
    s = rows[0]
    conn.execute("""INSERT INTO journal_entries (created_at, source, symbol, timeframe, bar_time, price, direction,
        confidence, invalidation, horizon_value, horizon_unit, end_time, verdict_visible, explanation_visible,
        rule_version, outcome) VALUES (1,'blind',?,?,?,1,'up',80,0.5,24,'bars',2,0,0,1,'correct')""",
                 (s["symbol"], s["timeframe"], s["bar_time"]))
    conn.commit()
    card = {r["type"]: r for r in T.scorecard(conn)["rows"]}
    sb = card["support bounce"]
    assert sb["family"] == "entry" and sb["pool"]["n"] == 3 and sb["pool"]["target"] == 3
    assert sb["pool"]["opposite_target"] == 0 and sb["pool"]["target_rate"] is None          # < 20: counts only
    assert sb["you"]["n"] == 1 and sb["you"]["correct"] == 1 and sb["you"]["brier"] == pytest.approx(0.04)
    assert card["double top"]["pool"]["opposite_target"] is None and card["double top"]["you"] is None
    assert list(card)[0] == "support bounce"                                                   # entries first


def test_api_entry_family_next_answer_and_scorecard(candles, monkeypatch, tmp_path):
    from fastapi.testclient import TestClient

    import src.api.app as api
    import src.data.registry as registry
    import src.service.analyze as service
    _pool(tmp_path, candles, [_row(candles, 0), _row(candles, 30, typ="double top", family="pattern", opp=None)]).close()
    monkeypatch.setattr(api, "_TRADES_DB", str(tmp_path / "t.db"))
    monkeypatch.setattr(registry, "get_candles", lambda *a, **k: candles)
    monkeypatch.setattr(service, "get_candles", lambda *a, **k: candles)
    api._HITS.clear()
    client = TestClient(api.app)
    setup = client.get("/training/next", params={"family": "entry"}).json()["setup"]
    assert setup["as_of_bar"] == 200 and not {"type", "direction", "outcome"} & set(setup)
    rev = client.post("/training/answer", json={"setup_id": setup["id"], "direction": "up", "confidence": 60,
                                                "invalidation": setup["price"] * 0.99}).json()
    assert rev["setup"]["type"] == "support bounce" and rev["record"] is None and rev["pool"]["n"] == 1
    card = client.get("/training/scorecard").json()
    assert {r["type"] for r in card["rows"]} == {"support bounce", "double top"}
    assert next(r for r in card["rows"] if r["type"] == "support bounce")["you"]["n"] == 1
