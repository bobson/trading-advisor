"""ROADMAP A8 — the morning report / forward record: schedule (incl. DST), the versioned outcome
rule for every case, no-setup scoring, closed candles, idempotency, gaps, weekends, review never
feeding the read, the report, OANDA, and the API."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pytest

from src.config import load_config
from src.forward import rule as R
from src.forward.record import (
    ALREADY_READ,
    NO_NEW_CANDLE,
    closed_only,
    connect,
    freeze_read,
    run_morning,
)
from src.forward.report import build_report, scoreboard
from src.forward.schedule import next_run, run_date

FIXTURE = Path(__file__).parent / "fixtures" / "btc_1h_sample.csv"
UTC = timezone.utc
ENGINE = {"commit": "test", "dirty": False, "config_hash": "cfg"}


# --- schedule: 08:00 Europe/Skopje, DST-aware ----------------------------------------------------

def test_next_run_is_0800_skopje_across_the_spring_dst_change():
    # EU summer time starts Sun 29 Mar 2026 02:00 -> 08:00 Skopje = 07:00 UTC before, 06:00 UTC after
    assert next_run(datetime(2026, 3, 27, 12, tzinfo=UTC)) == datetime(2026, 3, 28, 7, tzinfo=UTC)
    assert next_run(datetime(2026, 3, 28, 12, tzinfo=UTC)) == datetime(2026, 3, 29, 6, tzinfo=UTC)


def test_next_run_is_0800_skopje_across_the_autumn_dst_change():
    # summer time ends Sun 25 Oct 2026 03:00 -> 06:00 UTC on the 24th, 07:00 UTC on the 25th
    assert next_run(datetime(2026, 10, 23, 12, tzinfo=UTC)) == datetime(2026, 10, 24, 6, tzinfo=UTC)
    assert next_run(datetime(2026, 10, 24, 12, tzinfo=UTC)) == datetime(2026, 10, 25, 7, tzinfo=UTC)


def test_next_run_is_strictly_after_now_and_run_date_is_the_skopje_date():
    at = datetime(2026, 9, 25, 6, tzinfo=UTC)                          # exactly 08:00 CEST
    assert next_run(at) == datetime(2026, 9, 26, 6, tzinfo=UTC)
    assert next_run(at - timedelta(seconds=1)) == at
    assert str(run_date(datetime(2026, 9, 25, 22, 30, tzinfo=UTC))) == "2026-09-26"   # 00:30 local


# --- the outcome rule (v1), every case ---------------------------------------------------------------

def _dir(direction, bars, nxt=110.0, inv=95.0):
    return R.resolve_v1({"read_kind": R.DIRECTIONAL, "direction": direction, "next_level": nxt,
                         "invalidation": inv}, bars)


def test_directional_first_touch_wins_bullish():
    assert _dir("bullish", [(105, 99), (111, 100)]) == R.FOLLOWED
    assert _dir("bullish", [(105, 99), (106, 94)]) == R.INVALIDATED
    assert _dir("bullish", [(106, 94), (111, 100)]) == R.INVALIDATED          # invalidation came first
    assert _dir("bullish", [(111, 94)]) == R.AMBIGUOUS                        # both in one bar: never guess
    assert _dir("bullish", [(105, 99), (109, 96)]) == R.EXPIRED
    assert _dir("bullish", [(110, 95.01)]) == R.FOLLOWED                      # a touch is >= the level


def test_directional_first_touch_wins_bearish():
    kw = {"nxt": 90.0, "inv": 105.0}
    assert _dir("bearish", [(101, 95), (100, 89)], **kw) == R.FOLLOWED
    assert _dir("bearish", [(106, 95)], **kw) == R.INVALIDATED
    assert _dir("bearish", [(106, 89)], **kw) == R.AMBIGUOUS
    assert _dir("bearish", [(104, 91)], **kw) == R.EXPIRED


def test_directional_without_levels_is_unscorable():
    assert _dir("bullish", [(200, 1)], nxt=None) == R.UNSCORABLE


def test_no_setup_reads_are_scored_too():
    read = {"read_kind": R.RANGE, "range_low": 95.0, "range_high": 110.0}
    assert R.resolve_v1(read, [(109, 96), (110, 95)]) == R.CORRECT             # touching the edge is inside
    assert R.resolve_v1(read, [(109, 96), (110.5, 97)]) == R.MISSED
    assert R.resolve_v1(read, [(100, 94.9)]) == R.MISSED


def test_levels_come_from_zones_with_atr_fallback():
    sup, res = {"lower": 90.0, "upper": 94.0}, {"lower": 108.0, "upper": 112.0}
    b = R.levels_for("bullish", 100.0, 2.0, sup, res)
    assert (b["next_level"], b["invalidation"]) == (108.0, 90.0)
    s = R.levels_for("bearish", 100.0, 2.0, sup, res)
    assert (s["next_level"], s["invalidation"]) == (94.0, 112.0)
    rng = R.levels_for(None, 100.0, 2.0, sup, res)
    assert (rng["range_low"], rng["range_high"], rng["next_level"]) == (90.0, 112.0, None)
    inside = R.levels_for("bullish", 110.0, 2.0, sup, res)                 # already inside resistance
    assert inside["next_level"] == 112.0
    none = R.levels_for("bullish", 100.0, 2.0, None, None)
    assert (none["next_level"], none["invalidation"], none["source_above"]) == (106.0, 94.0, "atr")


def test_rule_v1_text_is_frozen():
    """Editing the v1 rule text changes the record's meaning: bump RULE_VERSION instead."""
    assert R.rule_hash(1) == "c705f49e077ef209", "v1 rule text changed — add a new rule version instead"


def test_coin_flip_baseline_is_reproducible_and_mixed():
    dirs = [R.baseline_direction("BTC/USDT", "1h", t) for t in range(0, 3600 * 200, 3600)]
    assert dirs == [R.baseline_direction("BTC/USDT", "1h", t) for t in range(0, 3600 * 200, 3600)]
    assert 60 < dirs.count("bullish") < 140


# --- candles ------------------------------------------------------------------------------------------

@pytest.fixture(scope="module")
def candles():
    df = pd.read_csv(FIXTURE, index_col="timestamp", parse_dates=["timestamp"])
    df.index = pd.to_datetime(df.index, utc=True)
    return df


def test_closed_only_drops_the_forming_bar(candles):
    last = candles.index[-1]
    assert len(closed_only(candles, "1h", last + timedelta(minutes=59))) == len(candles) - 1
    assert len(closed_only(candles, "1h", last + timedelta(hours=1))) == len(candles)


# --- the morning run ------------------------------------------------------------------------------------

@pytest.fixture
def cfg():
    c = load_config()
    mr = c.morning_report.model_copy(update={"symbols": ["BTC/USDT", "EUR/USD"], "timeframes": ["1h"],
                                             "synthesis": False})
    return c.model_copy(update={"morning_report": mr})


class Feed:
    """Candles as of bar k for each symbol (EUR/USD can be frozen to mimic a weekend)."""
    def __init__(self, df, k):
        self.df, self.k, self.frozen = df, {"BTC/USDT": k, "EUR/USD": k}, {}

    def __call__(self, sym, tf):
        if sym == "WTI/USD":
            raise RuntimeError("needs OANDA_API_TOKEN")
        return self.df.iloc[: self.k[sym]]

    def now(self):
        return self.df.index[max(self.k.values()) - 1].to_pydatetime() + timedelta(hours=1, minutes=1)


def _run(cfg, conn, feed, **kw):
    return run_morning(cfg, conn, now=feed.now(), candles_for=feed, engine=ENGINE, **kw)


def test_run_freezes_one_read_per_market_with_engine_version(cfg, candles):
    conn = connect(":memory:")
    out = _run(cfg, conn, Feed(candles, 300))
    assert out["new_reads"] == 2 and out["status"] == "ok"
    r = dict(conn.execute("SELECT * FROM forward_reads WHERE symbol='BTC/USDT'").fetchone())
    assert r["bar_time"] == int(candles.index[299].timestamp()) and r["engine_commit"] == "test"
    assert r["rule_version"] == R.RULE_VERSION and r["horizon"] == 24 and r["outcome"] is None
    assert r["read_kind"] in (R.DIRECTIONAL, R.RANGE) and len(r["facts_hash"]) == 16
    if r["read_kind"] == R.DIRECTIONAL:
        assert r["invalidation"] is not None and r["next_level"] is not None
    assert conn.execute("SELECT text FROM forward_rules WHERE version=1").fetchone()[0] == R.RULE_TEXT[1]


def test_running_twice_in_a_day_does_not_duplicate(cfg, candles):
    conn, feed = connect(":memory:"), Feed(candles, 300)
    _run(cfg, conn, feed)
    feed.k["BTC/USDT"] = 301                                        # a newer bar, same Skopje day
    again = run_morning(cfg, conn, now=feed.now() - timedelta(minutes=58), candles_for=feed, engine=ENGINE)
    assert again["new_reads"] == 0 and {s["reason"] for s in again["skipped"]} == {ALREADY_READ}
    assert conn.execute("SELECT COUNT(*) FROM forward_reads").fetchone()[0] == 2
    assert conn.execute("SELECT attempts FROM forward_runs").fetchone()[0] == 2


def test_weekend_market_with_no_new_closed_candle_is_skipped_not_reread(cfg, candles):
    conn, feed = connect(":memory:"), Feed(candles, 300)
    _run(cfg, conn, feed)
    feed.k["BTC/USDT"] = 324                                        # crypto moved on a day; EUR/USD didn't
    feed.k["EUR/USD"] = 300
    out = _run(cfg, conn, feed)
    assert out["new_reads"] == 1 and out["status"] == "ok"
    assert {"symbol": "EUR/USD", "timeframe": "1h", "reason": NO_NEW_CANDLE} in out["skipped"]


def test_review_resolves_after_the_horizon_with_the_baseline(cfg, candles):
    conn2, feed2 = connect(":memory:"), Feed(candles, 300)
    _run(cfg, conn2, feed2)
    feed2.k.update({"BTC/USDT": 324, "EUR/USD": 324})
    out = _run(cfg, conn2, feed2)
    assert out["resolved"] == 2
    for r in conn2.execute("SELECT * FROM forward_reads WHERE outcome IS NOT NULL"):
        assert r["outcome"] in R.DIRECTIONAL_OUTCOMES + R.RANGE_OUTCOMES + (R.UNSCORABLE,)
        assert r["baseline_direction"] in ("bullish", "bearish") and r["baseline_outcome"]
        # recompute by hand from the 24 bars after the read
        after = candles[candles.index > pd.Timestamp(r["bar_time"], unit="s", tz="UTC")].iloc[:24]
        assert r["outcome"] == R.resolve_v1(dict(r), list(zip(after["high"], after["low"])))


def test_review_is_not_resolved_before_the_horizon_ends(cfg, candles):
    conn, feed = connect(":memory:"), Feed(candles, 300)
    _run(cfg, conn, feed)
    feed.k.update({"BTC/USDT": 323, "EUR/USD": 323})
    run_morning(cfg, conn, now=feed.now() + timedelta(days=1), candles_for=feed, engine=ENGINE)
    assert conn.execute("SELECT COUNT(*) FROM forward_reads WHERE outcome IS NOT NULL").fetchone()[0] == 0


def test_the_review_never_feeds_the_read(cfg, candles):
    """The same candles give the same frozen facts whether or not old reads were just resolved."""
    feed = Feed(candles, 300)
    busy = connect(":memory:")
    _run(cfg, busy, feed)
    feed.k.update({"BTC/USDT": 324, "EUR/USD": 324})
    assert _run(cfg, busy, feed)["resolved"] == 2
    fresh = connect(":memory:")
    _run(cfg, fresh, feed)
    q = "SELECT facts_hash FROM forward_reads WHERE symbol='BTC/USDT' AND bar_time=?"
    bt = int(candles.index[323].timestamp())
    assert busy.execute(q, (bt,)).fetchone()[0] == fresh.execute(q, (bt,)).fetchone()[0]
    assert freeze_read.__code__.co_varnames[:4] == ("df", "symbol", "timeframe", "cfg")   # no DB argument


def test_missed_mornings_are_gaps_never_backfilled(cfg, candles):
    conn, feed = connect(":memory:"), Feed(candles, 250)
    first = _run(cfg, conn, feed)
    feed.k.update({"BTC/USDT": 322, "EUR/USD": 322})                # three days later
    out = _run(cfg, conn, feed)
    d0 = datetime.fromisoformat(first["run_date"])
    expect = [(d0 + timedelta(days=i)).date().isoformat() for i in (1, 2)]
    assert out["gaps"] == expect
    rows = {r["run_date"]: r["status"] for r in conn.execute("SELECT run_date, status FROM forward_runs")}
    assert [rows[d] for d in expect] == ["gap", "gap"]
    assert conn.execute("SELECT COUNT(*) FROM forward_reads WHERE run_date IN (?, ?)", expect).fetchone()[0] == 0


def test_a_market_that_cannot_load_is_skipped_and_the_run_continues(cfg, candles):
    c = cfg.model_copy(update={"morning_report": cfg.morning_report.model_copy(
        update={"symbols": ["BTC/USDT", "WTI/USD"]})})
    conn = connect(":memory:")
    out = run_morning(c, conn, now=Feed(candles, 300).now(), candles_for=Feed(candles, 300), engine=ENGINE)
    assert out["status"] == "partial" and out["new_reads"] == 1
    assert any(s["symbol"] == "WTI/USD" and "OANDA" in s["reason"] for s in out["skipped"])


def test_optional_synthesis_is_one_call_per_symbol_from_todays_facts(cfg, candles):
    c = cfg.model_copy(update={"morning_report": cfg.morning_report.model_copy(
        update={"symbols": ["BTC/USDT"], "timeframes": ["1h", "4h"], "synthesis": True})})
    calls = []

    class Client:
        class messages:
            @staticmethod
            def create(**kw):
                calls.append(kw)
                return type("R", (), {"content": [type("B", (), {"type": "text", "text": "cross-TF read"})()]})()

    conn, feed = connect(":memory:"), Feed(candles, 300)
    run_morning(c, conn, now=feed.now() + timedelta(hours=3), candles_for=feed, engine=ENGINE, synth_client=Client)
    assert len(calls) == 1
    assert conn.execute("SELECT text FROM forward_syntheses").fetchone()[0] == "cross-TF read"
    assert "followed_through" not in str(calls[0]["messages"])


# --- the report ------------------------------------------------------------------------------------------

def test_report_shows_review_then_grid_and_a_scoreboard_beside_the_baseline(cfg, candles):
    conn, feed = connect(":memory:"), Feed(candles, 300)
    _run(cfg, conn, feed)
    feed.k.update({"BTC/USDT": 324, "EUR/USD": 324})
    out = _run(cfg, conn, feed)
    rep = build_report(conn, cfg, now=feed.now())
    assert rep["run_date"] == out["run_date"] and len(rep["review"]) == 2 and len(rep["grid"]) == 2
    assert list(rep).index("review") < list(rep).index("grid") < list(rep).index("syntheses")
    assert rep["rule"]["version"] == 1 and rep["next_run"] and rep["first_run"]
    for row in rep["scoreboard"]:
        assert row["engine"]["rate"] is None                            # < 20 cases: counts only
        if row["read_kind"] == R.DIRECTIONAL:
            assert row["baseline"]["n"] == row["engine"]["n"]


def test_scoreboard_rate_needs_twenty_cases():
    rows = [{"rule_version": 1, "timeframe": "4h", "tier": "notable", "read_kind": R.DIRECTIONAL,
             "outcome": R.FOLLOWED if k < 8 else R.INVALIDATED, "baseline_outcome": R.EXPIRED} for k in range(20)]
    sb = scoreboard(rows)[0]
    assert sb["engine"]["rate"] == 0.4 and sb["baseline"]["rate"] == 0.0
    assert scoreboard(rows[:19])[0]["engine"]["rate"] is None


# --- OANDA (oil) -----------------------------------------------------------------------------------------

def test_oanda_keeps_complete_candles_only_and_needs_a_token():
    from src.data.oanda import OandaProvider
    payload = {"candles": [
        {"complete": True, "time": "2026-09-24T00:00:00.000000000Z", "volume": 10,
         "mid": {"o": "70.1", "h": "71.0", "l": "69.5", "c": "70.8"}},
        {"complete": False, "time": "2026-09-25T00:00:00.000000000Z", "volume": 3,
         "mid": {"o": "70.8", "h": "70.9", "l": "70.2", "c": "70.4"}}]}
    seen = {}
    p = OandaProvider(token="t", fetch=lambda url, params, headers: (seen.update(url=url, params=params), payload)[1])
    df = p.fetch("WTI/USD", "1d", 300)
    assert len(df) == 1 and df["close"].iloc[0] == 70.8 and "WTICO_USD" in seen["url"]
    assert seen["params"]["granularity"] == "D" and seen["params"]["dailyAlignment"] == 0
    with pytest.raises(RuntimeError, match="OANDA_API_TOKEN"):
        OandaProvider(token=None).fetch("WTI/USD", "1d", 10)


def test_oil_routes_to_oanda_and_gold_to_twelve_data_without_joining_the_research_markets():
    from src.data.forex_api import ForexProvider
    from src.data.oanda import OandaProvider
    from src.data.registry import all_pairs, asset_class_for, list_pairs, provider_for
    c = load_config()
    assert isinstance(provider_for("WTI/USD", c), OandaProvider)
    assert isinstance(provider_for("XAU/USD", c), ForexProvider)
    assert asset_class_for("XAU/USD") == "forex"
    assert "XAU/USD" not in [p.symbol for p in list_pairs()]              # encyclopedia/scan unchanged
    assert {"XAU/USD", "WTI/USD"} <= {p.symbol for p in all_pairs()}


# --- API ---------------------------------------------------------------------------------------------------

def test_api_morning_report_and_manual_trigger(cfg, candles, monkeypatch, tmp_path):
    from fastapi.testclient import TestClient

    import src.api.app as api
    db = str(tmp_path / "m.db")
    conn = connect(db)
    _run(cfg, conn, Feed(candles, 300))
    conn.close()
    monkeypatch.setattr(api, "_MORNING_DB", db)
    api._HITS.clear()
    client = TestClient(api.app)
    body = client.get("/morning").json()
    assert body["run_date"] and len(body["grid"]) == 2 and body["rule"]["version"] == 1
    started = []
    monkeypatch.setattr("subprocess.Popen", lambda args, **kw: started.append(args))
    assert client.post("/morning/run").json() == {"started": True}
    assert "morning_report.py" in started[0][1] and db in started[0] and "api" in started[0]
