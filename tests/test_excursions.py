"""ROADMAP R4 — exits: noise floor and typical run from the held-back reads, the exit comparison,
the risk-calculator warning, and the wiring into facts / facts text / API."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from src.config import load_config
from src.risk import excursions as X

FIXTURE = Path(__file__).parent / "fixtures" / "btc_1h_sample.csv"


def _case(part="test", mae=1.0, mfe=1.5, end=0.5, tf="1h", sym="BTC/USDT", regime="ranging"):
    return {"symbol": sym, "timeframe": tf, "part": part, "mae_atr": mae, "mfe_atr": mfe, "end_atr": end,
            "regime": regime, "i": 0, "direction": "bullish"}


def _pop(n=100, part="test", mae_win=0.8, mae_lose=2.0, mfe=1.4):
    """Half end in profit with MAE mae_win (± spread), half end in loss with MAE mae_lose."""
    out = []
    for k in range(n):
        win = k % 2 == 0
        out.append(_case(part, mae=(mae_win if win else mae_lose) + (k % 5 - 2) * 0.05, mfe=mfe + (k % 7 - 3) * 0.1,
                         end=0.5 if win else -0.5))
    return out


def test_noise_floor_is_the_median_adverse_move_of_eventual_winners():
    s = X.summarize(_pop() + _pop(part="tune"))["1h"]
    assert s["test"]["noise_floor"] == pytest.approx(0.8, abs=0.06)       # winners only, not the 2.0 losers
    assert s["test"]["typical_run"] == pytest.approx(1.4, abs=0.1)
    assert s["test"]["winners"] == 50 and s["test"]["n"] == 100
    assert s["stable"] == {"noise_floor": True, "typical_run": True}


def test_stop_touch_counts_all_reads_and_winners_separately():
    t = X.summarize(_pop())["1h"]["test"]["stop_touch"]
    assert t["0.5"]["winners"] == 1.0 and t["1.0"]["winners"] == 0.0     # every winner went ~0.7-0.9 against
    assert t["1.0"]["all"] == 0.5                                         # the losers went 2 ATR against


def test_a_different_older_period_is_flagged_unstable():
    s = X.summarize(_pop() + _pop(part="tune", mae_win=1.6))["1h"]
    assert s["stable"]["noise_floor"] is False


def test_too_few_reads_give_no_number():
    s = X.summarize(_pop(n=20))["1h"]["test"]                              # 10 winners < 20
    assert s["noise_floor"] is None and s["typical_run"] is not None
    assert "not enough history" in X.text({"test": s, "stable": {}})


def test_exit_table_carries_holding_time_and_counts():
    tbl = X.exit_table({"time": [[0.01, 20]] * 25, "stop_only": [[-0.02, 150]] * 5})
    assert tbl["time"] == {"n": 25, "mean_pct": 1.0, "win_rate": 1.0, "avg_bars": 20.0}
    assert tbl["stop_only"]["mean_pct"] is None and tbl["stop_only"]["n"] == 5    # < 20: no mean


def test_stop_warning_inside_and_outside_the_noise_floor():
    s = X.summarize(_pop())["1h"]
    tight = X.stop_warning(0.3, s)
    assert tight["inside"] is True and tight["winners_beyond_stop_in_10"] == 9      # "more than 9 in 10"
    wide = X.stop_warning(1.5, s)
    assert wide["inside"] is False and wide["winners_beyond_stop_in_10"] == 0       # "fewer than 1 in 10"
    mid = X.stop_warning(0.8, s)
    assert 3 <= mid["winners_beyond_stop_in_10"] <= 6                                 # about half
    assert X.stop_warning(0.3, None) is None


# --- the exit lab on held-back reads + the shared collector's new fields -----------------------------

@pytest.fixture(scope="module")
def cfg():
    return load_config()


@pytest.fixture(scope="module")
def candles():
    df = pd.read_csv(FIXTURE, index_col="timestamp", parse_dates=["timestamp"])
    df.index = pd.to_datetime(df.index, utc=True)
    return df


def test_collect_records_excursions_and_exits_run_on_held_back_reads_only(cfg, candles):
    from src.backtest.exits import EXIT_RULES
    from src.risk.caution_stats import collect
    from src.service.analyze import _request_config
    req = _request_config(cfg, "BTC/USDT", "1h")
    cases = collect(candles, req, "BTC/USDT", "1h", step=3)
    assert cases and all({"mfe_atr", "end_atr", "regime", "tier"} <= set(c) for c in cases)
    assert all(c["mae_atr"] >= 0 and c["mfe_atr"] >= 0 for c in cases)
    rets = X.simulate_exits(candles, req, cases)
    n_test = sum(1 for c in cases if c["part"] == "test")
    assert set(rets) == set(EXIT_RULES) and all(len(v) == n_test for v in rets.values())


# --- wiring: facts, facts text, API ------------------------------------------------------------------------

def test_facts_carry_noise_floor_and_typical_run_in_atr_and_price(cfg, candles):
    from src.service.analyze import advise
    stats = X.summarize(_pop() + _pop(part="tune"))
    r = advise("BTC/USDT", "1h", cfg, df=candles, explain_enabled=False, exit_stats=stats)
    ex = r.facts["exits"]
    atr = r.facts["volatility"]["atr"]
    assert ex["noise_floor_atr"] == stats["1h"]["test"]["noise_floor"]
    assert ex["noise_floor_price"] == pytest.approx(ex["noise_floor_atr"] * atr, rel=1e-3)
    assert "EXITS on this timeframe, from history" in r.facts_text
    assert "exits" not in advise("BTC/USDT", "1h", cfg, df=candles, explain_enabled=False).facts


def test_api_noise_floor_endpoint(candles, monkeypatch, tmp_path):
    from fastapi.testclient import TestClient

    import src.api.app as api
    import src.data.registry as registry
    from src.store.db import connect
    monkeypatch.setattr(registry, "get_candles", lambda *a, **k: candles)
    db = str(tmp_path / "x.db")
    monkeypatch.setattr(api, "_TRADES_DB", db)
    api._HITS.clear()
    client = TestClient(api.app)
    close = float(candles["close"].iloc[-1])
    q = {"symbol": "BTC/USDT", "timeframe": "1h", "entry": close, "stop": close * 0.999}
    unmeasured = client.get("/risk/noise_floor", params=q).json()
    assert unmeasured["measured"] is False and unmeasured["stop_atr"] > 0
    conn = connect(db)
    X.save(conn, X.summarize(_pop() + _pop(part="tune")), built_at=1, params={})
    conn.close()
    body = client.get("/risk/noise_floor", params=q).json()
    assert body["measured"] is True and body["inside"] is True and body["last_close"] == pytest.approx(close)
