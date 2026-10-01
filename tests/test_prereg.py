"""ROADMAP D2 — pre-registration: register before running, exact parameters, append-only (enforced by
the database), one result per registration, the multiple-comparison correction, the dashboard with
every miss and the prediction hit rate — and every experiment script refuses to run unregistered."""

from __future__ import annotations

import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from src.research import prereg as P

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def conn():
    return P.connect(":memory:")


def _reg(conn, **kw):
    args = dict(script="backtest", params={"symbol": "BTC/USDT", "step": 10}, question="Beats a coin flip?",
                hypothesis="wins > half", metric="win_rate", direction=">=", threshold=0.55, baseline=0.5,
                predicted_pass=False)
    args.update(kw)
    return P.register(conn, **args)


def test_registration_is_validated(conn):
    with pytest.raises(P.PreregError, match="reports"):
        _reg(conn, metric="sharpe")
    with pytest.raises(P.PreregError, match="baseline"):
        _reg(conn, baseline=None)
    with pytest.raises(P.PreregError, match="direction"):
        _reg(conn, direction=">")
    e = _reg(conn)
    assert e["question"] == "beats a coin flip?" and len(e["hash"]) == 16


def test_registrations_and_results_are_append_only(conn):
    e = _reg(conn)
    P.record(conn, e["id"], {"win_rate": (0.5, 100)})
    for sql in ("UPDATE experiments SET threshold = 0.4", "DELETE FROM experiments",
                "UPDATE experiment_results SET passed = 1", "DELETE FROM experiment_results"):
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            conn.execute(sql)


def test_the_gate_refuses_unregistered_mismatched_foreign_or_finished_runs(conn):
    with pytest.raises(P.PreregError, match="isn't registered"):
        P.check_runnable(conn, None, "backtest", {})
    e = _reg(conn)
    with pytest.raises(P.PreregError, match="registered for backtest"):
        P.check_runnable(conn, e["id"], "ml_eval", {"symbol": "BTC/USDT", "step": 10})
    with pytest.raises(P.PreregError, match="differ"):
        P.check_runnable(conn, e["id"], "backtest", {"symbol": "BTC/USDT", "step": 5})
    assert P.check_runnable(conn, e["id"], "backtest", {"step": 10, "symbol": "BTC/USDT"})["id"] == e["id"]
    P.record(conn, e["id"], {"win_rate": (0.5, 100)})
    with pytest.raises(P.PreregError, match="already has a result"):
        P.check_runnable(conn, e["id"], "backtest", {"symbol": "BTC/USDT", "step": 10})


def test_the_correction_tightens_with_every_variation_of_a_question(conn):
    a = _reg(conn, threshold=0.55)
    first = P.record(conn, a["id"], {"win_rate": (0.60, 200)})          # p ~ 0.003 < 0.05
    assert first["passed"] and first["variations"] == 1 and first["passed_corrected"] == 1
    b = _reg(conn, params={"symbol": "BTC/USDT", "step": 5}, supersedes=a["id"])
    second = P.record(conn, b["id"], {"win_rate": (0.57, 200)})        # p ~ 0.03 > 0.05 / 2
    assert second["passed"] and second["variations"] == 2 and second["corrected_alpha"] == pytest.approx(0.025)
    assert second["passed_corrected"] == 0


def test_non_rate_metrics_show_their_variation_count_but_are_not_corrected(conn):
    e = _reg(conn, script="ml_eval", params={}, metric="auc", threshold=0.55, baseline=None)
    out = P.record(conn, e["id"], {"auc": (0.51, None), "model_acc": (0.52, 3000)})
    assert out["passed"] is False and out["passed_corrected"] is None and out["variations"] == 1


def test_dashboard_lists_every_miss_and_your_prediction_hit_rate(conn):
    a = _reg(conn, predicted_pass=False)
    P.record(conn, a["id"], {"win_rate": (0.50, 100)})                  # miss, predicted right
    b = _reg(conn, params={"step": 1}, predicted_pass=True, supersedes=a["id"])
    P.record(conn, b["id"], {"win_rate": (0.52, 100)})                  # miss, predicted wrong
    _reg(conn, params={"step": 2}, question="another question")         # never run
    d = P.dashboard(conn)
    assert d["summary"] == {"registered": 3, "ran": 2, "never_ran": 1, "passed": 0, "misses": 2,
                            "prediction_hits": 1, "prediction_n": 2}
    assert {e["id"]: e["superseded"] for e in d["experiments"]}[a["id"]] is True
    assert d["questions"]["beats a coin flip?"] == {"registered": 2, "ran": 2, "passed": 0, "passed_corrected": 0}


@pytest.mark.parametrize("script", ["backtest", "backtest_suite", "ml_eval", "funding_study", "exit_lab",
                                    "measure_caution", "measure_exits"])
def test_every_experiment_script_refuses_to_run_unregistered(script, tmp_path):
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / f"{script}.py"), "--prereg-db", str(tmp_path / "p.db")],
                       capture_output=True, text=True, cwd=ROOT, timeout=120)
    assert r.returncode == 2 and "isn't registered" in r.stderr


def test_api_dashboard(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient

    import src.api.app as api
    db = str(tmp_path / "w.db")
    c = P.connect(db)
    P.record(c, _reg(c)["id"], {"win_rate": (0.5, 100)})
    c.close()
    monkeypatch.setattr(api, "_TRADES_DB", db)
    api._HITS.clear()
    body = TestClient(api.app).get("/experiments").json()
    assert body["summary"]["misses"] == 1 and body["experiments"][0]["params"] == {"symbol": "BTC/USDT", "step": 10}
