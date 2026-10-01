"""ROADMAP D5 — the behavioural circuit breaker: versioned, append-only rules; every decision checked
against the version active at its time; violations recorded never blocked; "can't check" when the
input wasn't recorded; rule-following vs rule-breaking with counts; neutral observations; weekly review."""

from __future__ import annotations

import json
import sqlite3

import pytest

from src.journal import rules as R

H = 3600
T0 = 1_780_000_000          # a fixed Monday-ish epoch for the tests


def _trade(id, t, size=1000.0, closed=None, pnl=None, regime="ranging", agreeing=2, symbol="BTC/USDT"):
    return {"kind": "trade", "id": id, "t": t, "symbol": symbol, "size": size, "closed_at": closed,
            "outcome": None if closed is None else ("win" if (pnl or 0) > 0 else "loss"), "pnl": pnl,
            "loss_at": closed if (pnl or 0) < 0 else None, "regime": regime, "agreeing": agreeing}


def _call(id, t, outcome=None, resolved=None, regime="quiet", agreeing=1, symbol="EUR/USD"):
    bad = outcome in ("incorrect", "invalidated")
    return {"kind": "call", "id": id, "t": t, "symbol": symbol, "size": None, "closed_at": None,
            "outcome": None if outcome is None else ("win" if outcome == "correct" else "loss"), "pnl": None,
            "loss_at": resolved if bad else None, "regime": regime, "agreeing": agreeing}


def _v(rules, t=T0 - 10):
    return {"version": 1, "created_at": t, "rules": rules, "note": ""}


def _rules(checked, id, kind="trade"):
    r = next(x for x in checked if x["id"] == id and x["kind"] == kind)
    return [v["rule"] for v in r["violations"]], r


# --- declaring ------------------------------------------------------------------------------------------

def test_rules_are_validated_versioned_and_append_only():
    conn = R.connect(":memory:")
    with pytest.raises(R.RulesError, match="account size"):
        R.declare(conn, {"max_position_pct": 2})
    with pytest.raises(R.RulesError, match="positive"):
        R.declare(conn, {"max_per_week": 0})
    a = R.declare(conn, {"max_per_week": 3, "unknown_field": 1, "allowed_symbols": []}, now=T0)
    assert a["rules"] == {"max_per_week": 3}                                   # unknown / empty dropped
    R.declare(conn, {"max_per_week": 5}, now=T0 + 10)
    assert [v["version"] for v in R.versions(conn)] == [1, 2]
    for sql in ("UPDATE trading_rules SET rules='{}'", "DELETE FROM trading_rules"):
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            conn.execute(sql)


# --- every rule ----------------------------------------------------------------------------------------------

def test_size_and_open_position_rules_on_trades():
    vers = [_v({"account_size": 10_000, "max_position_pct": 5, "max_open_positions": 1})]
    ds = [_trade(1, T0, size=400), _trade(2, T0 + H, size=900)]                # #1 still open at #2
    c = R.check(ds, vers)
    assert _rules(c, 1)[0] == []
    assert set(_rules(c, 2)[0]) == {"max_position_pct", "max_open_positions"}


def test_regime_categories_and_markets_on_both_records():
    vers = [_v({"required_regimes": ["trending_up"], "min_categories_aligned": 2, "allowed_symbols": ["BTC/USDT"]})]
    c = R.check([_trade(1, T0, regime="trending_up", agreeing=3), _call(1, T0 + H)], vers)
    assert _rules(c, 1)[0] == []
    assert set(_rules(c, 1, "call")[0]) == {"required_regimes", "min_categories_aligned", "allowed_symbols"}


def test_per_week_and_cooling_off_are_counted_per_record():
    vers = [_v({"max_per_week": 2, "cooling_off_hours": 12})]
    ds = [_trade(1, T0, closed=T0 + H, pnl=-50), _trade(2, T0 + 2 * H), _trade(3, T0 + 3 * H),
          _call(9, T0 + 3 * H)]                                                 # a call isn't a trade
    c = R.check(ds, vers)
    assert _rules(c, 2)[0] == ["cooling_off_hours"]                            # 1 h after the loss
    assert set(_rules(c, 3)[0]) == {"max_per_week", "cooling_off_hours"}
    assert _rules(c, 9, "call")[0] == []


def test_the_version_active_at_the_time_is_used_and_old_decisions_unchecked():
    vers = [_v({"max_per_week": 1}, t=T0 + 5 * H), {"version": 2, "created_at": T0 + 10 * H, "rules": {}, "note": ""}]
    c = R.check([_trade(1, T0), _trade(2, T0 + 6 * H), _trade(3, T0 + 7 * H), _trade(4, T0 + 11 * H)], vers)
    assert _rules(c, 1)[1]["rule_version"] is None and not _rules(c, 1)[1]["followed"]   # before any rules
    assert _rules(c, 3)[0] == ["max_per_week"] and _rules(c, 3)[1]["rule_version"] == 1
    assert _rules(c, 4)[1]["rule_version"] == 2 and _rules(c, 4)[0] == []


def test_missing_inputs_are_cant_check_never_violations():
    c = R.check([_trade(1, T0, regime=None, agreeing=None)], [_v({"required_regimes": ["quiet"], "min_categories_aligned": 2})])
    assert _rules(c, 1)[0] == [] and set(_rules(c, 1)[1]["cant_check"]) == {"required_regimes", "min_categories_aligned"}


# --- comparison, observations, weekly ------------------------------------------------------------------------

def test_rule_following_vs_rule_breaking_with_counts():
    vers = [_v({"allowed_symbols": ["BTC/USDT"]})]
    ds = [_trade(i, T0 + i * H, closed=T0 + i * H + 60, pnl=10 if i % 2 else -10) for i in range(1, 5)]
    ds += [_trade(9, T0 + 9 * H, closed=T0 + 9 * H + 60, pnl=-30, symbol="SOL/USDT")]
    cmp_ = R.compare(R.check(ds, vers))["trade"]
    assert cmp_["followed"] == {"n": 4, "judged": 4, "wins": 2, "win_rate": None, "pnl_total": 0.0}
    assert cmp_["broke"]["n"] == 1 and cmp_["broke"]["pnl_total"] == -30.0
    assert cmp_["by_rule"]["allowed_symbols"]["n"] == 1


def test_observations_are_neutral_and_the_weekly_review_groups_by_iso_week():
    vers = [_v({"required_regimes": ["quiet"]})]
    ds = [_trade(1, T0, size=100, closed=T0 + H, pnl=-5)] + [_trade(i, T0 + i * H, size=100) for i in range(2, 6)]
    ds += [_trade(9, T0 + 9 * H, size=1000, regime="volatile")]
    checked = R.check(ds, vers)
    obs = R.observations(checked, vers)
    kinds = {o["kind"] for o in obs}
    assert {"post_loss", "oversized", "off_regime"} <= kinds
    assert all("!" not in o["text"] and "should" not in o["text"] for o in obs)          # no scolding
    week = R.weekly(checked, obs)
    assert sum(w["trades"] for w in week) == 6 and week[0]["observations"]


# --- the real tables + API ------------------------------------------------------------------------------------

def test_review_reads_paper_trades_and_live_journal_calls_only(tmp_path):
    conn = R.connect(str(tmp_path / "r.db"))
    R.declare(conn, {"allowed_symbols": ["BTC/USDT"]}, now=T0 - 100)
    conn.execute("""INSERT INTO trades (symbol, timeframe, side, amount_usd, price, units, opened_at, status, snapshot)
                    VALUES ('SOL/USDT','1h','buy',500,100,5,?, 'open', ?)""", (T0, json.dumps({"engine": {"regime": "quiet", "agreeing": 2}})))
    for src in ("analysis", "blind"):
        conn.execute("""INSERT INTO journal_entries (created_at, source, symbol, timeframe, bar_time, price, direction,
            confidence, invalidation, horizon_value, horizon_unit, end_time, verdict_visible, explanation_visible,
            rule_version, engine) VALUES (?,?,'BTC/USDT','1h',?,1,'up',60,0.9,2,'weeks',?,0,0,1,'{}')""",
                     (T0, src, T0 if src == "analysis" else T0 - 3600, T0 + 99))
    conn.commit()
    rev = R.review(conn)
    kinds = [(d["kind"], d["symbol"]) for d in rev["decisions"]]
    assert ("trade", "SOL/USDT") in kinds and kinds.count(("call", "BTC/USDT")) == 1     # blind is practice
    assert rev["compare"]["trade"]["broke"]["n"] == 1


def test_api_declare_and_review(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient

    import src.api.app as api
    monkeypatch.setattr(api, "_TRADES_DB", str(tmp_path / "w.db"))
    api._HITS.clear()
    c = TestClient(api.app)
    assert c.post("/rules", json={"max_position_pct": 2}).status_code == 400
    v = c.post("/rules", json={"max_per_week": 3, "required_regimes": ["trending_up"], "note": "first"}).json()
    assert v["version"] == 1 and v["rules"] == {"max_per_week": 3, "required_regimes": ["trending_up"]}
    body = c.get("/discipline").json()
    assert body["rules"]["version"] == 1 and body["decisions"] == [] and "weekly" in body
