"""ROADMAP B1 — gold labels: save, load, replace, list, summarise, validate, and the API."""

from __future__ import annotations

import pytest

from src.labels import gold
from src.store.db import connect


@pytest.fixture
def conn():
    c = connect(":memory:")
    yield c
    c.close()


DT = {"type": "double top", "points": [{"time": 1000, "price": 110.0}, {"time": 2000, "price": 100.0},
                                         {"time": 3000, "price": 110.5}]}
ZONE = {"lower": 99.0, "upper": 101.0, "role": "support"}


def test_save_then_load_roundtrip(conn):
    row = gold.save(conn, "BTC/USDT", "1d", 3300, {"patterns": [DT], "zones": [ZONE], "note": " hmm "},
                    bar_time=1_789_000_000, now=10)
    got = gold.load(conn, "BTC/USDT", "1d", 3300)
    assert got == row
    assert got["bar_time"] == 1_789_000_000 and got["created_at"] == got["updated_at"] == 10
    assert got["labels"] == {"patterns": [DT], "zones": [ZONE], "nothing": False, "note": "hmm"}
    assert gold.load(conn, "BTC/USDT", "1d", 3301) is None


def test_saving_the_same_bar_replaces_it(conn):
    gold.save(conn, "BTC/USDT", "1d", 5, {"patterns": [DT]}, now=10)
    gold.save(conn, "BTC/USDT", "1d", 5, {"zones": [ZONE]}, now=20)
    rows = gold.list_all(conn)
    assert len(rows) == 1
    assert rows[0]["labels"]["patterns"] == [] and rows[0]["labels"]["zones"] == [ZONE]
    assert (rows[0]["created_at"], rows[0]["updated_at"]) == (10, 20)


def test_nothing_here_is_a_real_label(conn):
    gold.save(conn, "SOL/USDT", "1d", 7, {"nothing": True})
    assert gold.load(conn, "SOL/USDT", "1d", 7)["labels"]["nothing"] is True


@pytest.mark.parametrize("bad,msg", [
    ({"patterns": [{"type": "cup and handle", "points": DT["points"]}]}, "unknown type"),
    ({"patterns": [{"type": "double top", "points": DT["points"][:1]}]}, "at least 2"),
    ({"zones": [{"lower": 101.0, "upper": 99.0, "role": "support"}]}, "lower must be below"),
    ({"zones": [{"lower": 99.0, "upper": 101.0, "role": "middle"}]}, "role must be"),
    ({"nothing": True, "patterns": [DT]}, "can't be combined"),
    ({}, "empty label"),
])
def test_invalid_labels_are_rejected(conn, bad, msg):
    with pytest.raises(ValueError, match=msg):
        gold.save(conn, "BTC/USDT", "1d", 1, bad)
    assert gold.list_all(conn) == []


def test_summary_counts_by_pattern_type(conn):
    tri = {"type": "ascending triangle", "points": DT["points"]}
    gold.save(conn, "BTC/USDT", "1d", 1, {"patterns": [DT, tri], "zones": [ZONE]})
    gold.save(conn, "SOL/USDT", "1d", 2, {"patterns": [DT]})
    gold.save(conn, "EUR/USD", "1d", 3, {"nothing": True})
    s = gold.summary(conn)
    assert s["charts"] == 3 and s["patterns"] == 3 and s["zones"] == 1 and s["nothing"] == 1
    assert s["by_type"] == {"double top": 2, "ascending triangle": 1}
    assert list(s["by_type"])[0] == "double top"                  # most common first
    assert s["by_symbol_tf"] == {"BTC/USDT 1d": 1, "SOL/USDT 1d": 1, "EUR/USD 1d": 1}


def test_delete(conn):
    row = gold.save(conn, "BTC/USDT", "1d", 1, {"patterns": [DT]})
    gold.delete(conn, row["id"])
    assert gold.list_all(conn) == [] and gold.summary(conn)["charts"] == 0


def test_vocabulary_matches_the_detector():
    from src.patterns import chart_patterns as cp
    for name in ("DOUBLE_TOP", "HEAD_AND_SHOULDERS", "ASCENDING_TRIANGLE", "RECTANGLE", "ASCENDING_CHANNEL"):
        assert getattr(cp, name) in gold.DETECTOR_TYPES


def test_api_save_load_list_delete(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient

    import src.api.app as api
    monkeypatch.setattr(api, "_TRADES_DB", str(tmp_path / "g.db"))
    api._HITS.clear()
    client = TestClient(api.app)

    assert "double top" in client.get("/labels/types").json()["detector_types"]
    body = {"symbol": "BTC/USDT", "timeframe": "1d", "bar": 3300, "bar_time": 1_789_000_000,
            "labels": {"patterns": [DT], "zones": [ZONE]}}
    r = client.put("/labels", json=body)
    assert r.status_code == 200 and r.json()["summary"]["charts"] == 1
    one = client.get("/labels/one", params={"symbol": "BTC/USDT", "timeframe": "1d", "bar": 3300}).json()
    assert one["label"]["labels"]["patterns"] == [DT]
    assert client.put("/labels", json={**body, "labels": {}}).status_code == 400
    listing = client.get("/labels").json()
    assert len(listing["labels"]) == 1 and listing["summary"]["by_type"] == {"double top": 1}
    assert client.delete(f"/labels/{one['label']['id']}").json()["summary"]["charts"] == 0


def test_cors_preflight_allows_writes_from_the_allowed_origin():
    """The browser preflights PUT/POST/DELETE with a JSON body; GET-only CORS rejected them all
    (paper trading and label saving silently failed with 'Failed to fetch')."""
    from fastapi.testclient import TestClient

    import src.api.app as api
    client = TestClient(api.app)
    origin = api.cfg.allowed_origins[0]
    for method in ("POST", "PUT", "DELETE"):
        r = client.options("/labels", headers={"Origin": origin, "Access-Control-Request-Method": method,
                                               "Access-Control-Request-Headers": "content-type"})
        assert r.status_code == 200, method
    bad = client.options("/labels", headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "PUT"})
    assert bad.status_code == 400                      # other origins still refused


def test_analysis_reports_the_bar_it_was_computed_at(monkeypatch):
    """Labels are keyed to `bar_index` — the bar the chart actually shows — not the slider value.
    It must equal the as_of bar, be clamped to the warm-up floor, and be the last bar when live."""
    import numpy as np
    import pandas as pd
    from fastapi.testclient import TestClient

    import src.api.app as api
    import src.service.analyze as service
    n = 300
    idx = pd.date_range("2024-01-01", periods=n, freq="h", tz="UTC", name="timestamp")
    c = 100 + np.cumsum(np.sin(np.arange(n) / 5.0))
    df = pd.DataFrame({"open": c, "high": c + 1, "low": c - 1, "close": c, "volume": 1.0}, index=idx)
    monkeypatch.setattr(service, "get_candles", lambda *a, **k: df)
    api._CACHE.clear(); api._HITS.clear()
    client = TestClient(api.app)
    q = {"symbol": "BTC/USDT", "timeframe": "1h"}
    assert client.get("/analysis", params={**q, "as_of_bar": 200}).json()["bar_index"] == 200
    floor = api.cfg.indicators.slow_ma
    assert client.get("/analysis", params={**q, "as_of_bar": 3}).json()["bar_index"] == floor
    live = client.get("/analysis", params=q).json()
    assert live["bar_index"] == n - 1
    assert live["chart"]["candles"][-1]["time"] == int(idx[-1].timestamp())
