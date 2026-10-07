"""The forward-only 'fade the textbook entry' experiment: measured on forward_entries only, registered via D2,
recorded by the morning job once it has its sample (and never before)."""

from __future__ import annotations

import json

from src.forward import rule as R
from src.forward.record import connect
from src.research import entry_fade as F
from src.research import prereg

PARAMS = {"timeframe": "1d", "types": sorted(F.DEFAULT_TYPES), "min_n": 4}


def _db():
    conn = connect(":memory:")
    conn.executescript(prereg.SCHEMA)
    return conn


def _entry(conn, k, typ, own, mirror, tf="1d"):
    conn.execute("INSERT INTO forward_entries (read_id, run_date, symbol, timeframe, bar_time, price, type, direction, "
                 "level, next_level, invalidation, mirror_next, mirror_invalidation, horizon, rule_version, outcome, "
                 "mirror_outcome) VALUES (?,?,?,?,?,1,?,'bullish',1,2,0,0,2,21,?,?,?)",
                 (k, "2026-10-08", "BTC/USDT", tf, k, typ, R.RULE_VERSION, own, mirror))
    conn.commit()


def test_measure_counts_only_decisive_entries_of_the_registered_types_and_timeframe():
    conn = _db()
    _entry(conn, 1, "trendline touch", R.INVALIDATED, R.FOLLOWED)        # mirror won
    _entry(conn, 2, "MA pullback", R.FOLLOWED, R.INVALIDATED)            # textbook won
    _entry(conn, 3, "support bounce", R.FOLLOWED, R.FOLLOWED)            # both: not decisive
    _entry(conn, 4, "zone breakout", R.INVALIDATED, R.FOLLOWED)          # type not registered
    _entry(conn, 5, "trendline touch", R.INVALIDATED, R.FOLLOWED, tf="1h")  # other timeframe
    m = F.measure(conn, PARAMS)
    assert (m["n"], m["mirror"], m["value"], m["judged"]) == (2, 1, 0.5, 3)


def test_the_morning_job_records_it_only_once_the_sample_is_reached():
    conn = _db()
    exp = prereg.register(conn, script="entry_fade", params=PARAMS, question="daily: fade textbook entries?",
                          hypothesis="mirror wins >= 55%", metric="mirror_win_rate", direction=">=", threshold=0.55,
                          baseline=0.5, predicted_pass=True, predicted_value=0.58)
    for k in range(3):
        _entry(conn, k, "trendline touch", R.INVALIDATED, R.FOLLOWED)
    assert F.auto_record(conn) == [] and F.live(conn)[0]["n"] == 3        # 3 < min_n: nothing recorded
    _entry(conn, 9, "MA pullback", R.FOLLOWED, R.INVALIDATED)
    done = F.auto_record(conn, engine_commit="abc")
    assert len(done) == 1 and done[0]["value"] == 0.75 and done[0]["n"] == 4 and done[0]["passed"]
    assert done[0]["p_value"] is not None                                   # a rate: binomial test vs 0.5
    assert json.loads(conn.execute("SELECT details FROM experiment_results").fetchone()[0])["mirror"] == 3
    assert F.auto_record(conn) == [] and F.live(conn) == []                 # recorded once, append-only
    assert prereg.get(conn, exp["id"])["script"] == "entry_fade"


def test_live_is_empty_without_an_experiments_table():
    assert F.live(connect(":memory:")) == []
