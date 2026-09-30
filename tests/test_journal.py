"""ROADMAP D1 — the prediction journal: logging rules (sides, range, no hedging, live bar, delete
window), the fixed resolution rule for every case incl. the exact-equal close, no resolution before
the data covers the window (incl. a forex weekend), idempotency, and the calibration maths."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.config import load_config
from src.journal import calibration as C
from src.journal.resolve import judge, resolve_due
from src.journal.store import JournalError, connect, delete, end_time_for, list_entries, log_call

FIXTURE = Path(__file__).parent / "fixtures" / "btc_1h_sample.csv"


@pytest.fixture(scope="module")
def cfg():
    return load_config()


@pytest.fixture(scope="module")
def candles():
    df = pd.read_csv(FIXTURE, index_col="timestamp", parse_dates=["timestamp"])
    df.index = pd.to_datetime(df.index, utc=True)
    return df


def _log(conn, df, cfg, **kw):
    args = dict(symbol="BTC/USDT", timeframe="1h", direction="up", confidence=65, invalidation=float(df["close"].iloc[-1]) * 0.98,
                horizon_value=12, horizon_unit="bars", verdict_visible=False, explanation_visible=False, now=1_000_000)
    args.update(kw)
    return log_call(conn, df=df, cfg=cfg, **args)


# --- logging rules -----------------------------------------------------------------------------------

def test_a_call_is_logged_at_the_last_closed_bar_with_the_engine_frozen(cfg, candles):
    conn = connect(":memory:")
    e = _log(conn, candles.iloc[:300], cfg)
    assert e["bar_time"] == int(candles.index[299].timestamp()) and e["price"] == float(candles["close"].iloc[299])
    assert e["end_time"] == e["bar_time"] + 3600 + 12 * 3600 and e["outcome"] is None
    assert {"bias", "tier", "patterns", "regime", "facts_hash", "engine_commit"} <= set(e["engine"])


@pytest.mark.parametrize("kw, msg", [
    ({"direction": "up", "invalidation": 10**9}, "50% away"),
    ({"direction": "up", "invalidation": 0.0}, "50% away"),
    ({"direction": "up", "invalidation": 70_000.0}, "below"),        # the fixture's price is ~64,000
    ({"direction": "down", "invalidation": 58_000.0}, "above"),
    ({"confidence": 40}, "50–100"),
    ({"confidence": 101}, "50–100"),
    ({"direction": "neutral"}, "up or down"),
    ({"horizon_value": 0}, "at least 1"),
])
def test_bad_calls_are_refused(cfg, candles, kw, msg):
    with pytest.raises(JournalError, match=msg):
        _log(connect(":memory:"), candles.iloc[:300], cfg, **kw)


def test_no_hedging_one_live_call_per_market_and_bar(cfg, candles):
    conn = connect(":memory:")
    df = candles.iloc[:300]
    _log(conn, df, cfg)
    with pytest.raises(JournalError, match="already logged"):
        _log(conn, df, cfg, direction="down", invalidation=float(df["close"].iloc[-1]) * 1.02)
    with pytest.raises(JournalError, match="already logged"):              # not from another page either
        _log(conn, df, cfg, source="morning", direction="down", invalidation=float(df["close"].iloc[-1]) * 1.02)


def test_delete_only_within_five_minutes_and_never_after_resolution(cfg, candles):
    conn = connect(":memory:")
    e = _log(conn, candles.iloc[:300], cfg)
    with pytest.raises(JournalError, match="within 5 minutes"):
        delete(conn, e["id"], now=e["created_at"] + 360)
    delete(conn, e["id"], now=e["created_at"] + 240)
    assert list_entries(conn) == []


# --- the resolution rule -------------------------------------------------------------------------------

def _bars(closes, lows=None, highs=None, start="2026-06-01", freq="1h"):
    idx = pd.date_range(start, periods=len(closes), freq=freq, tz="UTC")
    c = np.array(closes, float)
    return pd.DataFrame({"open": c, "high": highs if highs is not None else c + 0.5,
                         "low": lows if lows is not None else c - 0.5, "close": c, "volume": 1.0}, index=idx)


def _entry(direction="up", price=100.0, inv=95.0, bar_time=None, end_bars=5, tf="1h"):
    bt = bar_time if bar_time is not None else int(pd.Timestamp("2026-06-01", tz="UTC").timestamp())
    return {"direction": direction, "price": price, "invalidation": inv, "bar_time": bt, "timeframe": tf,
            "end_time": end_time_for(bt, tf, end_bars, "bars")}


def test_judge_every_outcome():
    df = _bars([100, 101, 102, 103, 104, 105, 106, 107])
    assert judge(_entry(), df) == ("correct", 105.0)                          # bars 1..5 -> last close 105
    assert judge(_entry(direction="down", inv=110.0), df) == ("incorrect", 105.0)
    dip = _bars([100, 99, 94, 99, 101, 102, 103, 104], lows=np.array([99.5, 98.5, 93.5, 98.5, 100.5, 101.5, 102.5, 103.5]))
    assert judge(_entry(), dip)[0] == "invalidated"                           # touched, even though it ended higher
    flat = _bars([100, 101, 99, 100, 100, 100, 100, 100])
    assert judge(_entry(), flat) == ("incorrect", 100.0)                      # an exactly equal close is incorrect


def test_no_judgement_before_the_data_covers_the_window():
    assert judge(_entry(end_bars=5), _bars([100, 101, 102, 103, 104])) is None      # last close before end_time


def test_a_forex_weekend_end_waits_for_the_next_bar():
    fri = pd.date_range("2026-06-05 18:00", periods=3, freq="1h", tz="UTC")           # Fri 18:00–20:00
    mon = pd.date_range("2026-06-08 00:00", periods=2, freq="1h", tz="UTC")
    bt = int(fri[0].timestamp())
    e = {"direction": "up", "price": 1.10, "invalidation": 1.09, "bar_time": bt, "timeframe": "1h",
         "end_time": int(pd.Timestamp("2026-06-06 12:00", tz="UTC").timestamp())}   # a Saturday end
    only_fri = pd.DataFrame({"open": 1.1, "high": 1.102, "low": 1.099, "close": [1.10, 1.101, 1.102], "volume": 0.0}, index=fri)
    assert judge(e, only_fri) is None                                         # waits for Monday
    both = pd.concat([only_fri, pd.DataFrame({"open": 1.1, "high": 1.11, "low": 1.1, "close": [1.105, 1.106], "volume": 0.0}, index=mon)])
    assert judge(e, both) == ("correct", 1.102)                               # judged on the Friday bars only


def test_resolve_due_is_idempotent_and_only_fetches_due_markets(cfg, candles):
    conn = connect(":memory:")
    e = _log(conn, candles.iloc[:300], cfg, horizon_value=10)
    fetched = []

    def feed(sym, tf):
        fetched.append((sym, tf))
        return candles
    assert resolve_due(conn, feed, now=e["end_time"] - 1) == 0 and fetched == []   # not due: no fetch
    assert resolve_due(conn, feed, now=e["end_time"] + 1) == 1
    assert resolve_due(conn, feed, now=e["end_time"] + 2) == 0
    assert list_entries(conn)[0]["outcome"] in ("correct", "incorrect", "invalidated")


# --- calibration maths ---------------------------------------------------------------------------------------

def _res(conf, outcome, **kw):
    return {"confidence": conf, "outcome": outcome, "timeframe": "1h", "source": "analysis",
            "verdict_visible": False, "explanation_visible": False, "engine": {"regime": "ranging", "patterns": ["double top"]}, **kw}


def test_brier_overconfidence_and_the_50_percent_baseline():
    s = C.summary([_res(80, "correct"), _res(80, "incorrect"), _res(60, "invalidated"), _res(90, "correct")])
    assert s["brier"] == pytest.approx(((0.2) ** 2 + 0.8 ** 2 + 0.6 ** 2 + 0.1 ** 2) / 4)
    assert s["overconfidence"] == pytest.approx(0.775 - 0.5) and s["accuracy"] is None   # n < 20: no rate
    assert C.summary([_res(50, "correct"), _res(50, "incorrect")])["brier"] == C.BASELINE_BRIER


def test_curve_bins_counts_and_a_rate_only_with_20_calls():
    rows = [_res(72, "correct")] * 15 + [_res(75, "incorrect")] * 10 + [_res(55, "correct")] * 3
    cv = {b["bin"]: b for b in C.curve(rows)}
    assert (cv["70–79"]["n"], cv["70–79"]["hits"], cv["70–79"]["rate"]) == (25, 15, 0.6)
    assert (cv["50–59"]["n"], cv["50–59"]["rate"]) == (3, None)
    assert C.curve([_res(100, "correct")])[-1]["n"] == 1                                 # 100 lands in 90–100


def test_breakdowns_split_blind_from_anchored_and_count_pending():
    rows = [_res(70, "correct"), _res(70, "incorrect", verdict_visible=True), _res(70, None)]
    cal = C.calibration(rows)
    assert cal["pending"] == 1 and cal["overall"]["n"] == 2
    assert cal["by_view"]["blind"]["n"] == 1 and cal["by_view"]["anchored"]["n"] == 1
    assert cal["by_pattern"]["double top"]["n"] == 2 and cal["by_regime"]["ranging"]["hits"] == 1


# --- API ------------------------------------------------------------------------------------------------------

def test_api_log_list_and_delete(candles, monkeypatch, tmp_path):
    from fastapi.testclient import TestClient

    import src.api.app as api
    import src.data.registry as registry
    import src.service.analyze as service
    monkeypatch.setattr(registry, "get_candles", lambda *a, **k: candles)
    monkeypatch.setattr(service, "get_candles", lambda *a, **k: candles)
    monkeypatch.setattr(api, "_TRADES_DB", str(tmp_path / "j.db"))
    api._HITS.clear()
    client = TestClient(api.app)
    close = float(candles["close"].iloc[-1])
    body = {"symbol": "BTC/USDT", "timeframe": "1h", "direction": "down", "confidence": 70,
            "invalidation": close * 1.01, "verdict_visible": False, "explanation_visible": False}
    e = client.post("/journal", json=body).json()
    assert e["direction"] == "down" and e["price"] == pytest.approx(close)
    assert client.post("/journal", json=body).status_code == 400                        # no second call on the bar
    assert client.post("/journal", json={**body, "invalidation": close * 0.99}).status_code == 400
    assert client.post("/journal", json={**body, "source": "blind"}).status_code == 400  # D6 only
    got = client.get("/journal").json()
    assert got["entries"][0]["id"] == e["id"] and got["stats"]["pending"] == 1 and got["rule"]["version"] == 1
    assert client.delete(f"/journal/{e['id']}").json() == {"deleted": e["id"]}
