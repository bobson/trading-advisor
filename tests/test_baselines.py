"""ROADMAP A7 — honest baselines: the random-entry luck band for paper trading and the
cost-adjusted coin flip that the risk calculator defaults to."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.config import load_config
from src.risk.coin_flip import coin_flip_win_rate, cost_adjusted_coin_flip
from src.store.db import connect
from src.trading import paper
from src.trading.baseline import baseline_for_symbol, random_entry_baseline


@pytest.fixture(scope="module")
def cfg():
    return load_config()


# --- cost-adjusted coin flip ------------------------------------------------------------------

def test_coin_flip_formula():
    assert coin_flip_win_rate(0.0, 1.0) == 0.5                 # free trading at 1:1 -> a plain coin flip
    assert coin_flip_win_rate(0.0, 1.5) == pytest.approx(0.4)  # zero edge at 1.5:1 is 40%, NOT 50%
    assert coin_flip_win_rate(0.281, 1.5) == pytest.approx((1 - 0.281) / 2.5)
    assert coin_flip_win_rate(10.0, 1.0) == 0.0                # clipped, never negative
    with pytest.raises(ValueError):
        coin_flip_win_rate(0.1, 0.0)


def test_default_never_implies_an_edge():
    """The default's expectancy is exactly −cost (never positive) at ANY payoff ratio — the bug
    this guards against: '50% at 1.5:1' quietly assumed a +0.25R edge and showed 0% ruin."""
    for c, r in [(0.0, 1.0), (0.0, 1.5), (0.05, 1.0), (0.2, 2.0), (0.3, 0.8), (0.1, 3.0)]:
        p = coin_flip_win_rate(c, r)
        assert p * r - (1 - p) == pytest.approx(-c)


def test_cost_adjusted_coin_flip_is_below_half_and_scales_with_risk(cfg):
    wide = cost_adjusted_coin_flip("BTC/USDT", "1h", cfg, entry=100, stop=96, payoff_ratio=1.5, atr_pct=0.01)
    tight = cost_adjusted_coin_flip("BTC/USDT", "1h", cfg, entry=100, stop=98, payoff_ratio=1.5, atr_pct=0.01)
    assert 0 < wide["win_rate"] < wide["fair_win_rate"] == pytest.approx(0.4)
    assert tight["cost_in_r"] == pytest.approx(2 * wide["cost_in_r"], rel=1e-3)   # half the risk -> double c
    assert tight["win_rate"] < wide["win_rate"]
    with pytest.raises(ValueError):
        cost_adjusted_coin_flip("BTC/USDT", "1h", cfg, entry=100, stop=100, payoff_ratio=1.5, atr_pct=0.01)


def test_crypto_funding_makes_long_daily_holds_cost_more(cfg):
    h1 = cost_adjusted_coin_flip("BTC/USDT", "1h", cfg, entry=100, stop=96, payoff_ratio=1.5, atr_pct=0.01)
    d1 = cost_adjusted_coin_flip("BTC/USDT", "1d", cfg, entry=100, stop=96, payoff_ratio=1.5, atr_pct=0.01)
    assert d1["cost_pct"] > h1["cost_pct"]                     # 24 days of funding vs 24 hours


# --- random-entry baseline --------------------------------------------------------------------

def _walk(n=2000, seed=3):
    rng = np.random.default_rng(seed)
    return 100 * np.exp(np.cumsum(rng.normal(0, 0.01, n)))


def test_baseline_is_seeded_and_ordered():
    closes = _walk()
    a = random_entry_baseline(closes, [5, 10, 3], [100, 200, 50], n_runs=500, seed=7)
    b = random_entry_baseline(closes, [5, 10, 3], [100, 200, 50], n_runs=500, seed=7)
    assert a == b
    assert a["total_p05"] <= a["total_p50"] <= a["total_p95"]
    assert 0 <= a["wins_p05"] <= a["wins_p50"] <= a["wins_p95"] <= 3


def test_flat_prices_give_a_zero_band():
    out = random_entry_baseline(np.full(300, 50.0), [4, 4], [100, 100], n_runs=200)
    assert (out["total_p05"], out["total_p50"], out["total_p95"]) == (0.0, 0.0, 0.0)


def test_random_sides_centre_luck_near_zero_even_in_a_trend():
    closes = np.linspace(100, 200, 3000)                      # strong steady uptrend
    out = random_entry_baseline(closes, [20] * 10, [100] * 10, n_runs=4000, seed=1)
    assert abs(out["total_p50"]) < 0.2 * (out["total_p95"] - out["total_p05"])


def test_band_scales_with_exposure():
    closes = _walk()
    small = random_entry_baseline(closes, [10, 10], [100, 100], n_runs=1000, seed=2)
    big = random_entry_baseline(closes, [10, 10], [200, 200], n_runs=1000, seed=2)
    assert big["total_p95"] == pytest.approx(2 * small["total_p95"], rel=1e-6)


def test_your_result_is_placed_in_the_distribution():
    closes = _walk()
    lucky = random_entry_baseline(closes, [10], [100], n_runs=1000, your_total=1e9)
    unlucky = random_entry_baseline(closes, [10], [100], n_runs=1000, your_total=-1e9)
    typical = random_entry_baseline(closes, [10], [100], n_runs=1000, your_total=0.0)
    assert lucky["your_percentile"] == 100.0 and not lucky["inside_luck_band"]
    assert unlucky["your_percentile"] == 0.0 and not unlucky["inside_luck_band"]
    assert typical["inside_luck_band"]


def test_no_trades_means_no_baseline():
    assert random_entry_baseline(_walk(), [], [], n_runs=100) == {"n_trades": 0, "n_runs": 0}


def test_holds_longer_than_history_are_clipped_not_crashing():
    out = random_entry_baseline(np.linspace(1, 2, 10), [500], [100], n_runs=50)
    assert out["n_runs"] == 50


def test_baseline_for_symbol_uses_real_holding_times(cfg):
    conn = connect(":memory:")
    t0 = 1_700_000_000
    paper.open_or_close(conn, "BTC/USDT", "1h", "buy", 1000, price=100.0, now=t0)
    paper.open_or_close(conn, "BTC/USDT", "1h", "sell", 1000, price=110.0, now=t0 + 5 * 3600)  # 5 bars
    idx = pd.date_range("2024-01-01", periods=500, freq="h", tz="UTC")
    candles = pd.DataFrame({"close": _walk(500)}, index=idx)
    out = baseline_for_symbol(conn, "BTC/USDT", cfg, candles=candles, n_runs=300)
    assert out["n_trades"] == 1 and out["timeframe"] == "1h" and out["history_bars"] == 500
    assert out["your_total"] == pytest.approx(100.0)          # 1000$ long, +10%
    assert "total_p05" in out and "your_percentile" in out
    assert baseline_for_symbol(connect(":memory:"), "BTC/USDT", cfg, candles=candles) == {"n_trades": 0, "n_runs": 0}


# --- the API endpoints (offline) --------------------------------------------------------------

def test_api_coin_flip_and_baseline(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient

    import src.api.app as api
    import src.data.registry as registry

    idx = pd.date_range("2024-01-01", periods=400, freq="h", tz="UTC")
    c = _walk(400)
    df = pd.DataFrame({"open": c, "high": c * 1.002, "low": c * 0.998, "close": c, "volume": 1.0}, index=idx)
    monkeypatch.setattr(registry, "get_candles", lambda *a, **k: df)
    monkeypatch.setattr(api, "_TRADES_DB", str(tmp_path / "t.db"))
    api._HITS.clear()
    client = TestClient(api.app)

    r = client.get("/risk/coin_flip", params={"symbol": "BTC/USDT", "timeframe": "1h",
                                              "entry": 100, "stop": 96, "payoff_ratio": 1.5})
    assert r.status_code == 200 and 0 < r.json()["win_rate"] < 0.5
    assert client.get("/risk/coin_flip", params={"symbol": "BTC/USDT", "entry": 100, "stop": 100}).status_code == 400

    assert client.get("/trades/baseline", params={"symbol": "BTC/USDT"}).json() == {"n_trades": 0, "n_runs": 0}
    conn = connect(str(tmp_path / "t.db"))
    paper.open_or_close(conn, "BTC/USDT", "1h", "buy", 500, price=100.0, now=1_700_000_000)
    paper.open_or_close(conn, "BTC/USDT", "1h", "sell", 500, price=98.0, now=1_700_000_000 + 3 * 3600)
    conn.close()
    out = client.get("/trades/baseline", params={"symbol": "BTC/USDT"}).json()
    assert out["n_trades"] == 1 and out["n_runs"] == 1000 and out["your_total"] == pytest.approx(-10.0)
