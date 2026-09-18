"""Feature 9 — risk-of-ruin & position-sizing maths.

The load-bearing checks are the ones a point-tolerance misses: monotonicity (ruin rises with
risk, falls with win rate and payoff) catches sign inversions, and the MC↔analytic agreement is
only meaningful once the unresolved fraction is ~0 (a truncated path counted as "survived" would
understate ruin).
"""

from __future__ import annotations

import numpy as np
import pytest

from src.risk.ruin import (
    bootstrap_drawdowns,
    gather_measured_stats,
    kelly,
    kelly_drawdown_pain,
    longest_losing_streak,
    max_drawdown,
    position_size,
    risk_of_ruin_analytic,
    risk_of_ruin_mc,
    ruin_table,
)


# --- Kelly ----------------------------------------------------------------------------------

def test_kelly_formula():
    # p=0.6, b=2 -> f* = p - q/b = 0.6 - 0.4/2 = 0.4
    k = kelly(0.6, 2.0)
    assert k.full == pytest.approx(0.4, abs=1e-6)
    assert k.half == pytest.approx(0.2, abs=1e-6)
    assert k.quarter == pytest.approx(0.1, abs=1e-6)
    assert k.has_edge


def test_kelly_no_edge_is_zero():
    k = kelly(0.4, 1.0)          # edge = 0.4·1 − 0.6 < 0
    assert k.full == 0.0 and not k.has_edge


# --- Analytic risk of ruin: edge cases + monotonicity ---------------------------------------

def test_analytic_edge_cases():
    assert risk_of_ruin_analytic(1.0, 1.0, 0.02) == 0.0     # never lose -> never ruined
    assert risk_of_ruin_analytic(0.0, 1.0, 0.02) == 1.0     # never win -> certain ruin
    # driftless, symmetric log-barriers (p=.5, b=2, f=.5 -> mean log-return 0) -> exactly 0.5
    assert risk_of_ruin_analytic(0.5, 2.0, 0.5) == pytest.approx(0.5, abs=1e-6)


def test_ruin_rises_with_risk_fraction():
    r = [risk_of_ruin_analytic(0.55, 1.0, f) for f in (0.005, 0.01, 0.02, 0.05)]
    assert r == sorted(r) and r[0] < r[-1]


def test_ruin_falls_with_win_rate_and_payoff():
    by_wr = [risk_of_ruin_analytic(p, 1.0, 0.02) for p in (0.40, 0.50, 0.60)]
    assert by_wr == sorted(by_wr, reverse=True)
    by_b = [risk_of_ruin_analytic(0.5, b, 0.02) for b in (0.5, 1.0, 2.0)]
    assert by_b == sorted(by_b, reverse=True)


def test_fraction_at_or_above_one_does_not_crash():
    # f>=1 would make log(1-f) undefined; it's clamped and must still return a valid probability.
    # (At f=1, p=.5, b=1 the first trade decides — win doubles, loss halves — so ~0.5, not ~1.)
    val = risk_of_ruin_analytic(0.5, 1.0, 1.0)
    assert 0.0 <= val <= 1.0


# --- Monte Carlo agrees with analytic (and actually resolves) -------------------------------

def test_mc_matches_analytic_and_resolves():
    a = risk_of_ruin_analytic(0.55, 1.0, 0.01)
    mc = risk_of_ruin_mc(0.55, 1.0, 0.01, n_paths=8000, seed=7)
    assert mc.unresolved < 0.01, "paths timed out -> ruin would be understated"
    assert abs(mc.prob - a) < 0.05
    assert mc.ci_low <= mc.prob <= mc.ci_high


# --- Position sizing ------------------------------------------------------------------------

def test_position_size_basic():
    ps = position_size(account=10_000, entry=100.0, stop=95.0, risk_fraction=0.01)
    assert ps.risk_amount == 100.0          # 1% of 10k
    assert ps.stop_distance == 5.0
    assert ps.units == 20.0                 # 100 / 5
    assert ps.position_value == 2000.0
    assert ps.leverage == 0.2


def test_position_size_rejects_zero_stop_and_bad_fraction():
    with pytest.raises(ValueError):
        position_size(10_000, 100.0, 100.0, 0.01)     # zero-width stop -> infinite size
    with pytest.raises(ValueError):
        position_size(10_000, 100.0, 95.0, 1.5)       # risk fraction out of (0,1)


# --- The ruin table -------------------------------------------------------------------------

def test_ruin_table_shows_the_cliff():
    t = ruin_table(payoff_ratio=1.0)
    # every cell a probability
    assert all(0.0 <= v <= 1.0 for row in t["rows"] for v in row["ruin"])
    # down a column WITH AN EDGE (win rate 0.60), rising risk raises ruin (monotone only holds for
    # a positive edge — a losing system can lower ruin with more variance, which is real).
    edge_col = t["win_rates"].index(0.60)
    col = [row["ruin"][edge_col] for row in t["rows"]]
    assert col == sorted(col) and col[0] < col[-1]
    # across the highest-risk row, rising win rate never raises ruin
    assert t["rows"][-1]["ruin"] == sorted(t["rows"][-1]["ruin"], reverse=True)
    # the cliff: high risk + low win rate is near-certain ruin; low risk + high win rate is safe
    assert t["rows"][-1]["ruin"][0] > 0.9 and t["rows"][0]["ruin"][-1] < 0.2


# --- Bootstrap drawdowns + helpers ----------------------------------------------------------

def test_max_drawdown_and_streak():
    assert max_drawdown(np.array([1.0, 1.2, 0.6, 0.9])) == pytest.approx(0.5)  # 1.2 -> 0.6
    assert longest_losing_streak(np.array([-1, -1, 1, -1, -1, -1])) == 3


def test_bootstrap_drawdowns_from_real_returns():
    rng = np.random.default_rng(0)
    returns = rng.normal(0.005, 0.03, 200)          # a fat-ish real-ish return series
    d = bootstrap_drawdowns(returns, n_paths=1000, seed=1)
    assert 0.0 <= d.median <= d.p90 <= d.worst <= 1.0
    assert d.worst_losing_streak >= d.median_losing_streak >= 0
    assert "bootstrap" in d.note


def test_all_wins_have_no_drawdown():
    d = bootstrap_drawdowns([0.01, 0.02, 0.03], n_paths=200, seed=2)
    assert d.median == 0.0 and d.worst == 0.0


def test_kelly_drawdown_pain_orders_full_worst():
    pain = kelly_drawdown_pain(0.55, 1.5, horizon=150, n_paths=1500, seed=3)
    assert pain["full"]["median_drawdown"] >= pain["half"]["median_drawdown"] >= pain["quarter"]["median_drawdown"]


# --- Measured stats -------------------------------------------------------------------------

def test_measured_stats_from_backtest_with_thin_flag_and_ci():
    rates = {"BTC/USDT|1h": {"overall": {"n": 12, "win_rate": 0.5}}}
    m = gather_measured_stats("BTC/USDT", "1h", base_rates=rates)
    assert m.win_rate == 0.5 and m.n == 12 and m.source == "backtest"
    assert m.payoff_ratio is None                    # not reconstructable from backtest
    assert m.thin                                    # n=12 < 30
    lo, hi = m.win_rate_ci
    assert lo < 0.5 < hi and (hi - lo) > 0.2         # thin sample -> wide interval


def test_measured_stats_absent_is_graceful():
    m = gather_measured_stats("XXX/USDT", "1h", base_rates={})
    assert m.win_rate is None and m.n == 0 and m.source == "none" and not m.thin


# --- API (pure math, no market data needed) -------------------------------------------------

def test_risk_api_returns_ruin_kelly_table_and_position():
    from fastapi.testclient import TestClient

    from src.api.app import app

    c = TestClient(app)
    r = c.get("/risk", params={"win_rate": 0.45, "payoff_ratio": 1.0, "risk_fraction": 0.02,
                               "account": 10_000, "entry": 100, "stop": 96})
    assert r.status_code == 200
    j = r.json()
    assert 0.0 <= j["ruin"]["analytic"] <= 1.0
    assert 0.0 <= j["ruin"]["monte_carlo"]["prob"] <= 1.0
    assert j["kelly"]["full"] == 0.0                 # 45% at 1:1 has no edge
    assert j["position"]["units"] == 50.0            # 200 risk / 4 stop distance
    assert j["table"]["rows"]


def test_risk_measured_api_is_graceful_without_data():
    from fastapi.testclient import TestClient

    from src.api.app import app

    j = TestClient(app).get("/risk/measured", params={"symbol": "XXX/USDT", "timeframe": "1h"}).json()
    assert j["source"] in ("none", "backtest", "journal")
