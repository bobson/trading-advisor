"""ROADMAP B3 — the Empirical Pattern Encyclopedia: outcome measurement, the n<20 rule, roll-ups and
splits, SQLite round-trip, reuse of THE backtest walk, look-ahead safety, the textbook reader, API."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.config import load_config
from src.indicators.features import COL_ATR
from src.research import encyclopedia as enc
from src.research.encyclopedia import ALL, MIN_N, Instance, aggregate, load_rows, save_rows
from src.store.db import connect

FIXTURE = Path(__file__).parent / "fixtures" / "btc_1h_sample.csv"


@pytest.fixture(scope="module")
def cfg():
    return load_config()


@pytest.fixture(scope="module")
def candles():
    df = pd.read_csv(FIXTURE, index_col="timestamp", parse_dates=["timestamp"])
    df.index = pd.to_datetime(df.index, utc=True)
    return df


def _df(closes, highs=None, lows=None, atr=2.0):
    c = np.asarray(closes, dtype=float)
    idx = pd.date_range("2024-01-01", periods=len(c), freq="D", tz="UTC")
    df = pd.DataFrame({"open": c, "high": c + 0.5 if highs is None else highs,
                       "low": c - 0.5 if lows is None else lows, "close": c}, index=idx)
    feat = df.copy()
    feat[COL_ATR] = atr
    return df, feat


def _inst(**kw):
    base = dict(pattern_type="double top", symbol="X", timeframe="1d", bars=(0, 1, 2), first_seen=2,
                first_state="forming", regime="ranging", direction="bearish", breakout=100.0,
                invalidation=110.0, target=90.0)
    return Instance(**{**base, **kw})


# --- breakout + outcome measurement ----------------------------------------------------------

def test_forming_pattern_confirms_on_the_first_close_through_the_breakout():
    x = _inst()
    enc._resolve_breakout(x, np.array([105, 103, 99.5, 98.0]), 0, 4)
    assert x.confirmed_bar == 2 and not x.invalidated


def test_invalidation_first_means_never_confirmed():
    x = _inst()
    enc._resolve_breakout(x, np.array([105, 111.0, 99.0]), 0, 3)
    assert x.invalidated and x.confirmed_bar is None


def test_neutral_coil_takes_its_direction_from_the_edge_it_breaks():
    x = _inst(pattern_type="symmetric triangle", direction="neutral", breakout=110.0, invalidation=100.0)
    enc._resolve_breakout(x, np.array([105, 104, 99.0]), 0, 3)
    assert (x.direction, x.breakout, x.invalidation, x.confirmed_bar) == ("bearish", 100.0, 110.0, 2)


def test_target_reached_by_a_wick_counts_as_follow_through(cfg):
    closes = [101, 99, 97, 95, 94, 93]
    lows = [c - 0.5 for c in closes]
    lows[4] = 89.5                                   # the wick tags the 90 target on bar 4
    df, feat = _df(closes, lows=lows)
    x = _inst(confirmed_bar=1)
    enc._measure_after(x, df, feat, cfg, horizon=3)
    assert x.outcome == "target" and x.bars_to_resolution == 3
    assert x.move_atr == pytest.approx((99 - 94) / 2.0)      # bearish: a fall is a positive move


def test_close_back_through_the_breakout_is_a_failure(cfg):
    df, feat = _df([101, 99, 98, 101.0, 102, 103])   # back above 100 by > 0.25×ATR (0.5) on bar 3
    x = _inst(confirmed_bar=1)
    enc._measure_after(x, df, feat, cfg, horizon=4)
    assert x.outcome == "failed" and x.bars_to_resolution == 2


def test_neither_within_the_horizon_is_open(cfg):
    df, feat = _df([101, 99, 98, 97.5, 98, 97])
    x = _inst(confirmed_bar=1)
    enc._measure_after(x, df, feat, cfg, horizon=3)
    assert x.outcome == "open" and x.bars_to_resolution is None


# --- aggregation: n<20 never becomes a percentage ----------------------------------------------

def _population(n, *, confirmed_every=1, hit_every=2):
    out = []
    for k in range(n):
        x = _inst(bars=(k, k + 1, k + 2), symbol="A" if k % 2 else "B", regime="ranging" if k % 3 else "volatile")
        if k % confirmed_every == 0:
            x.confirmed_bar, x.outcome, x.move_atr, x.bars_to_resolution = k + 5, "target" if k % hit_every == 0 else "failed", 1.0, 3
            x.profile = {"volume": "supports" if k % 2 == 0 else "neutral", "momentum": "neutral",
                         "volatility": "neutral", "candlestick": "neutral"}
        out.append(x)
    return out


def _row(rows, **kw):
    return next(r for r in rows if all(r[k] == v for k, v in kw.items()))


def test_small_samples_keep_counts_but_no_rates():
    rows = aggregate(_population(12))
    r = _row(rows, symbol=ALL, regime=ALL, split="all")
    assert r["sample_size"] == 12 and r["insufficient_data"] is True
    assert r["confirmation_rate"] is None and r["follow_through_rate"] is None and r["move_atr_median"] is None
    assert (r["confirmed_n"], r["target_hit_n"], r["failed_n"]) == (12, 6, 6)


def test_large_samples_get_rates_and_quantiles():
    rows = aggregate(_population(40))
    r = _row(rows, symbol=ALL, regime=ALL, split="all")
    assert r["insufficient_data"] is False and r["confirmation_rate"] == 1.0
    assert r["follow_through_rate"] == 0.5 and r["failure_rate"] == 0.5
    assert r["move_atr_median"] == 1.0 and r["bars_to_resolution_median"] == 3.0


def test_rollups_and_splits_exist_and_add_up():
    rows = aggregate(_population(40))
    per_sym = [_row(rows, symbol=s, regime=ALL, split="all")["sample_size"] for s in ("A", "B")]
    assert sum(per_sym) == 40
    sup = _row(rows, symbol=ALL, regime=ALL, split="volume=supports")["confirmed_n"]
    nsup = _row(rows, symbol=ALL, regime=ALL, split="volume=not")["confirmed_n"]
    assert sup + nsup == 40 and sup == 20


def test_patterns_first_seen_after_the_breakout_are_kept_out_of_the_rates():
    pop = _population(25)
    late = [_inst(bars=(900 + k,), first_state="confirmed") for k in range(10)]
    r = _row(aggregate(pop + late), symbol=ALL, regime=ALL, split="all")
    assert r["sample_size"] == 35 and r["seen_forming"] == 25 and r["confirmed_n"] == 25


def test_examples_open_at_the_breakout_bar_with_outcomes_mixed():
    rows = aggregate(_population(40))
    ex = _row(rows, symbol=ALL, regime=ALL, split="all")["examples"]
    assert ex and all(e["bar"] >= 5 for e in ex)
    assert {e["outcome"] for e in ex} >= {"target", "failed"}


def test_sqlite_round_trip_and_market_replacement(tmp_path):
    conn = connect(str(tmp_path / "e.db"))
    save_rows(conn, aggregate(_population(30)), built_at=1, params={"horizon": 24}, replace_markets=[("A", "1d"), ("B", "1d")])
    got = load_rows(conn, "double top")
    assert got and all("sample_size" in r and "insufficient_data" in r for r in got)
    save_rows(conn, aggregate(_population(5)), built_at=2, params={}, replace_markets=[("A", "1d"), ("B", "1d")])
    top = next(r for r in load_rows(conn) if r["symbol"] == ALL and r["regime"] == ALL and r["split"] == "all")
    assert top["sample_size"] == 5 and top["built_at"] == 2               # rebuilt, not duplicated


# --- the walk: reused, look-ahead-safe --------------------------------------------------------

def test_encyclopedia_iterates_the_backtest_walk(cfg, candles, monkeypatch):
    import importlib
    ev = importlib.import_module("src.backtest.evaluate")
    calls = []
    real = ev.walk

    def spy(*a, **k):
        calls.append(1)
        return real(*a, **k)
    monkeypatch.setattr(enc, "walk", spy)
    enc.collect_instances(candles, cfg, "BTC/USDT", "1h", step=10)
    assert calls == [1]
    assert enc.walk is spy and real is ev.walk                           # same function the backtest uses


def test_detection_is_look_ahead_safe(cfg, candles):
    """Patterns first seen at bar <= k (and their state then) don't change when bars after k change."""
    k = 250
    a = enc.collect_instances(candles, cfg, "BTC/USDT", "1h", step=5)
    mutated = candles.copy()
    mutated.iloc[k + 1:, mutated.columns.get_loc("close")] *= 1.3
    mutated.iloc[k + 1:, mutated.columns.get_loc("high")] *= 1.3
    b = enc.collect_instances(mutated, cfg, "BTC/USDT", "1h", step=5)
    early = lambda xs: {(x.pattern_type, x.bars, x.first_seen, x.first_state, x.breakout) for x in xs if x.first_seen <= k}  # noqa: E731
    assert early(a) and early(a) == early(b)


# --- textbook claim + API ---------------------------------------------------------------------

def test_textbook_claim_for_every_detector_type():
    from src.labels.gold import DETECTOR_TYPES
    from src.research.textbook import textbook_claim
    for t in DETECTOR_TYPES:
        c = textbook_claim(t)
        assert c and c["shape"] and c["trigger"] and c["claims"], t
    assert textbook_claim("cup and handle") is None


def test_api_index_and_page(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient

    import src.api.app as api
    db = str(tmp_path / "w.db")
    monkeypatch.setattr(api, "_TRADES_DB", db)
    api._HITS.clear()
    client = TestClient(api.app)
    assert client.get("/encyclopedia").json()["types"] == []                   # not built yet
    conn = connect(db)
    save_rows(conn, aggregate(_population(30)), built_at=7, params={"horizon": 24, "max_wait": 50}, replace_markets=[])
    conn.close()
    idx = client.get("/encyclopedia").json()
    assert idx["built_at"] == 7 and idx["types"][0]["pattern_type"] == "double top"
    page = client.get("/encyclopedia/double top").json()
    assert page["textbook"]["claims"] and page["rows"]
    assert page["detector_precision"]["1d"]["status"] == "unmeasured"
    assert MIN_N == 20


# --- too recent to judge = pending, never "went nowhere" --------------------------------------

def test_breakout_too_recent_for_the_horizon_is_pending(cfg):
    df, feat = _df([101, 99, 98.5])                         # confirmed at bar 1, only 1 bar after it
    x = _inst(confirmed_bar=1)
    enc._measure_after(x, df, feat, cfg, horizon=5)
    assert x.outcome == "pending" and x.move_atr is None


def test_forming_pattern_whose_window_hasnt_closed_is_pending():
    x = _inst()
    enc._resolve_breakout(x, np.array([105, 104]), 0, 2, window_complete=False)
    assert x.pending_breakout and x.confirmed_bar is None and not x.invalidated


def test_pending_cases_are_counted_but_left_out_of_the_rates():
    pop = _population(30)
    for x in pop[:10]:
        x.outcome = "pending"                                # 10 breakouts too recent to judge
    extra = [_inst(bars=(500 + k,), pending_breakout=True) for k in range(5)]
    r = _row(aggregate(pop + extra), symbol=ALL, regime=ALL, split="all")
    assert r["seen_forming"] == 35 and r["decided_n"] == 30 and r["pending_breakout_n"] == 5
    assert r["confirmed_n"] == 30 and r["pending_outcome_n"] == 10 and r["judged_n"] == 20
    assert r["target_hit_n"] + r["failed_n"] == 20 and r["follow_through_rate"] == 0.5
