"""ROADMAP D5 — the behavioural circuit breaker: YOUR declared rules, checked on every decision.

You declare a rule set; each change is a new VERSION (append-only, enforced by the database), and
every decision is checked against the version that was active when it was made. Violations are
RECORDED, never blocked. Checked on two records, compared separately:
  paper trades   (position opens; outcome = realised P&L of the closed position)
  journal calls  (live calls; outcome = correct under the journal rule). Blind training is practice
                 and isn't checked.

Rules (each optional — an undeclared rule is never checked):
  max_position_pct        position value ≤ this % of `account_size`            (paper trades)
  max_open_positions      open positions INCLUDING this one ≤ this              (paper trades)
  required_regimes        the engine's regime at the decision is one of these    (both)
  min_categories_aligned  the engine's agreeing categories ≥ this                (both)
  allowed_symbols         only these markets                                     (both)
  max_per_week            decisions in the 7 days up to and including this ≤ it  (both, per record)
  cooling_off_hours       no new decision within this many hours of a loss       (both, per record)
A rule whose input wasn't recorded (e.g. an old trade without an engine snapshot) is "can't check",
never a violation.

Observations (after the fact, neutral, never a verdict): decisions inside a post-loss window,
positions over 1.5× your median size, decisions outside the required regimes, weeks with more than
twice your median weekly count.
"""

from __future__ import annotations

import json
import time
from collections import defaultdict
from datetime import datetime, timezone
from statistics import median

MIN_N = 20
FIELDS = ("account_size", "max_position_pct", "max_open_positions", "required_regimes", "min_categories_aligned",
          "allowed_symbols", "max_per_week", "cooling_off_hours")
LABELS = {"max_position_pct": "position size", "max_open_positions": "open positions",
          "required_regimes": "regime", "min_categories_aligned": "categories aligned",
          "allowed_symbols": "allowed markets", "max_per_week": "per-week limit", "cooling_off_hours": "cooling-off"}

SCHEMA = """
CREATE TABLE IF NOT EXISTS trading_rules (
    version INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at INTEGER NOT NULL,
    rules TEXT NOT NULL,              -- JSON, see rules.FIELDS
    note TEXT
);
CREATE TRIGGER IF NOT EXISTS trading_rules_no_update BEFORE UPDATE ON trading_rules
BEGIN SELECT RAISE(ABORT, 'rule versions are append-only: declare a new version'); END;
CREATE TRIGGER IF NOT EXISTS trading_rules_no_delete BEFORE DELETE ON trading_rules
BEGIN SELECT RAISE(ABORT, 'rule versions are append-only'); END;
"""


class RulesError(ValueError):
    pass


def connect(path: str = "data/wizard.db"):
    from src.journal.store import connect as jconnect
    conn = jconnect(path)                     # journal_entries (+ the base schema with `trades`)
    conn.executescript(SCHEMA)
    return conn


def declare(conn, rules: dict, *, note: str = "", now: float | None = None) -> dict:
    clean = {k: v for k, v in rules.items() if k in FIELDS and v not in (None, "", [])}
    if "max_position_pct" in clean and not clean.get("account_size"):
        raise RulesError("a position-size limit needs your account size")
    for k in ("account_size", "max_position_pct", "max_open_positions", "min_categories_aligned", "max_per_week",
              "cooling_off_hours"):
        if k in clean and not float(clean[k]) > 0:
            raise RulesError(f"{k} must be positive")
    cur = conn.execute("INSERT INTO trading_rules (created_at, rules, note) VALUES (?,?,?)",
                       (int(now or time.time()), json.dumps(clean), note))
    conn.commit()
    return {"version": cur.lastrowid, "created_at": int(now or time.time()), "rules": clean, "note": note}


def versions(conn) -> list[dict]:
    return [{"version": r["version"], "created_at": r["created_at"], "rules": json.loads(r["rules"]), "note": r["note"]}
            for r in conn.execute("SELECT * FROM trading_rules ORDER BY version")]


def _active(vers: list[dict], t: int) -> dict | None:
    act = [v for v in vers if v["created_at"] <= t]
    return act[-1] if act else None


# --- the records ------------------------------------------------------------------------------------------

def _decisions(conn) -> list[dict]:
    """Paper-trade opens and live journal calls as uniform decisions."""
    out = []
    for r in conn.execute("SELECT * FROM trades ORDER BY opened_at, id"):
        snap = json.loads(r["snapshot"] or "{}")
        eng = snap.get("engine") or {}
        out.append({"kind": "trade", "id": r["id"], "t": r["opened_at"], "symbol": r["symbol"],
                    "size": r["amount_usd"], "closed_at": r["closed_at"],
                    "outcome": None if r["status"] != "closed" else ("win" if (r["realized_pnl"] or 0) > 0 else "loss"),
                    "pnl": r["realized_pnl"], "loss_at": r["closed_at"] if (r["realized_pnl"] or 0) < 0 else None,
                    "regime": eng.get("regime"),
                    "agreeing": eng.get("agreeing", snap.get("agreeing_categories"))})
    for r in conn.execute("SELECT * FROM journal_entries WHERE source != 'blind' ORDER BY created_at, id"):
        eng = json.loads(r["engine"] or "{}")
        bad = r["outcome"] in ("incorrect", "invalidated")
        out.append({"kind": "call", "id": r["id"], "t": r["created_at"], "symbol": r["symbol"], "size": None,
                    "closed_at": None,
                    "outcome": None if r["outcome"] is None else ("win" if r["outcome"] == "correct" else "loss"),
                    "pnl": None, "loss_at": r["resolved_at"] if bad else None,
                    "regime": eng.get("regime"), "agreeing": eng.get("agreeing")})
    return sorted(out, key=lambda d: (d["t"], d["kind"], d["id"]))


def check(decisions: list[dict], vers: list[dict]) -> list[dict]:
    """Each decision with its violations and can't-check list under the rule version active at its time."""
    out = []
    for d in decisions:
        v = _active(vers, d["t"])
        rules = v["rules"] if v else {}
        same = [x for x in decisions if x["kind"] == d["kind"]]
        viol, cant = [], []

        def flag(rule, detail):
            viol.append({"rule": rule, "detail": detail})

        if d["kind"] == "trade":
            if "max_position_pct" in rules:
                pct = d["size"] / float(rules["account_size"]) * 100
                if pct > float(rules["max_position_pct"]):
                    flag("max_position_pct", f"position {pct:.1f}% of the account > {rules['max_position_pct']}%")
            if "max_open_positions" in rules:
                n_open = sum(1 for x in same if x["t"] <= d["t"] and (x["closed_at"] is None or x["closed_at"] > d["t"]))
                if n_open > int(rules["max_open_positions"]):
                    flag("max_open_positions", f"{n_open} open positions > {rules['max_open_positions']}")
        if "required_regimes" in rules:
            if d["regime"] in (None, "unknown"):
                cant.append("required_regimes")
            elif d["regime"] not in rules["required_regimes"]:
                flag("required_regimes", f"regime {d['regime']} not in {', '.join(rules['required_regimes'])}")
        if "min_categories_aligned" in rules:
            if d["agreeing"] is None:
                cant.append("min_categories_aligned")
            elif int(d["agreeing"]) < int(rules["min_categories_aligned"]):
                flag("min_categories_aligned", f"{d['agreeing']} categories agreed < {rules['min_categories_aligned']}")
        if "allowed_symbols" in rules and d["symbol"] not in rules["allowed_symbols"]:
            flag("allowed_symbols", f"{d['symbol']} isn't on your list")
        if "max_per_week" in rules:
            n_week = sum(1 for x in same if d["t"] - 7 * 86400 < x["t"] <= d["t"])
            if n_week > int(rules["max_per_week"]):
                flag("max_per_week", f"{n_week} in the last 7 days > {rules['max_per_week']}")
        if "cooling_off_hours" in rules:
            h = float(rules["cooling_off_hours"])
            recent = [x for x in same if x["loss_at"] is not None and 0 <= d["t"] - x["loss_at"] < h * 3600]
            if recent:
                hrs = (d["t"] - max(x["loss_at"] for x in recent)) / 3600
                flag("cooling_off_hours", f"{hrs:.1f} h after a loss < {h:g} h")
        out.append({**d, "rule_version": v["version"] if v else None, "violations": viol, "cant_check": cant,
                    "followed": v is not None and not viol})
    return out


# --- comparison, observations, weekly review ---------------------------------------------------------------

def _outcomes(rows: list[dict]) -> dict:
    done = [r for r in rows if r["outcome"] is not None]
    wins = sum(1 for r in done if r["outcome"] == "win")
    pnl = [r["pnl"] for r in done if r["pnl"] is not None]
    return {"n": len(rows), "judged": len(done), "wins": wins,
            "win_rate": round(wins / len(done), 3) if len(done) >= MIN_N else None,
            "pnl_total": round(sum(pnl), 2) if pnl else None}


def compare(checked: list[dict]) -> dict:
    """Rule-following vs rule-breaking, per record kind, plus per broken rule."""
    out = {}
    for kind in ("trade", "call"):
        rows = [r for r in checked if r["kind"] == kind and r["rule_version"] is not None]
        per_rule = defaultdict(list)
        for r in rows:
            for v in r["violations"]:
                per_rule[v["rule"]].append(r)
        out[kind] = {"followed": _outcomes([r for r in rows if r["followed"]]),
                     "broke": _outcomes([r for r in rows if not r["followed"]]),
                     "by_rule": {k: _outcomes(v) for k, v in sorted(per_rule.items())},
                     "unchecked": sum(1 for r in checked if r["kind"] == kind and r["rule_version"] is None)}
    return out


def observations(checked: list[dict], vers: list[dict]) -> list[dict]:
    obs = []
    for kind in ("trade", "call"):
        rows = [r for r in checked if r["kind"] == kind]
        word = "trade" if kind == "trade" else "call"
        for r in rows:
            losses = [x["loss_at"] for x in rows if x["loss_at"] is not None and 0 <= r["t"] - x["loss_at"] < 6 * 3600]
            if losses:
                obs.append({"t": r["t"], "kind": "post_loss", "text": f"a {word} on {r['symbol']} "
                            f"{(r['t'] - max(losses)) / 3600:.1f} h after a loss"})
        sizes = [r["size"] for r in rows if r["size"]]
        if len(sizes) >= 5:
            med = median(sizes)
            obs += [{"t": r["t"], "kind": "oversized", "text": f"a {r['size']:,.0f} position on {r['symbol']}, "
                     f"{r['size'] / med:.1f}× your median size"} for r in rows if r["size"] and r["size"] > 1.5 * med]
        for r in rows:
            v = _active(vers, r["t"])
            req = (v or {}).get("rules", {}).get("required_regimes")
            if req and r["regime"] not in (None, "unknown") and r["regime"] not in req:
                obs.append({"t": r["t"], "kind": "off_regime", "text": f"a {word} on {r['symbol']} in a {r['regime']} regime"})
        weeks = defaultdict(int)
        for r in rows:
            weeks[_week(r["t"])] += 1
        if len(weeks) >= 3:
            med = median(weeks.values())
            obs += [{"t": None, "week": w, "kind": "frequency", "text": f"{n} {word}s in week {w}, "
                     f"{n / med:.1f}× your median week"} for w, n in weeks.items() if n > 2 * med]
    return sorted(obs, key=lambda o: o["t"] or 0, reverse=True)


def _week(t: int) -> str:
    y, w, _ = datetime.fromtimestamp(t, timezone.utc).isocalendar()
    return f"{y}-W{w:02d}"


def weekly(checked: list[dict], obs: list[dict]) -> list[dict]:
    weeks = defaultdict(list)
    for r in checked:
        weeks[_week(r["t"])].append(r)
    out = []
    for w, rows in sorted(weeks.items(), reverse=True):
        broke = [r for r in rows if r["violations"]]
        out.append({"week": w, "trades": sum(1 for r in rows if r["kind"] == "trade"),
                    "calls": sum(1 for r in rows if r["kind"] == "call"),
                    "broke": len(broke), "rules_broken": sorted({v["rule"] for r in broke for v in r["violations"]}),
                    "judged": sum(1 for r in rows if r["outcome"]), "wins": sum(1 for r in rows if r["outcome"] == "win"),
                    "observations": [o["text"] for o in obs if (o.get("week") == w) or (o["t"] and _week(o["t"]) == w)]})
    return out


def review(conn) -> dict:
    vers = versions(conn)
    checked = check(_decisions(conn), vers)
    obs = observations(checked, vers)
    return {"rules": vers[-1] if vers else None, "versions": vers, "decisions": checked[::-1][:300],
            "compare": compare(checked), "observations": obs[:100], "weekly": weekly(checked, obs),
            "labels": LABELS, "min_n": MIN_N}
