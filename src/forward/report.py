"""ROADMAP A8 — the morning report, assembled from the forward tables (read-only).

Order on the page: the REVIEW (reads resolved that morning), then that morning's symbol × timeframe
GRID, then the per-symbol synthesis; plus a running SCOREBOARD per rule version × timeframe × tier,
directional reads beside the coin-flip baseline scored with the same rule on the same reads. Rates
only with 20+ cases (the app-wide rule); below that, counts.
"""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone

from src.config import Config
from src.forward.rule import DIRECTIONAL_OUTCOMES, FOLLOWED, RANGE_OUTCOMES, RULE_TEXT, RULE_VERSION, CORRECT
from src.forward.schedule import next_run

MIN_N = 20
_READ_KEYS = ("id", "symbol", "timeframe", "bar_time", "price", "tier", "bias", "aligned", "agreeing", "read_kind",
              "direction", "invalidation", "next_level", "near_above", "near_below", "range_low", "range_high",
              "source_above", "source_below", "horizon", "rule_version", "outcome", "run_date",
              "resolved_run_date", "baseline_direction", "baseline_outcome", "engine_commit", "engine_dirty",
              "facts_hash")


def _read(r) -> dict:
    d = {k: r[k] for k in _READ_KEYS}
    d["patterns"] = json.loads(r["patterns"] or "[]")
    return d


def _counts(rows: list[dict], key: str, outcomes: tuple) -> dict:
    c = {o: 0 for o in outcomes}
    for r in rows:
        if r[key] in c:
            c[r[key]] += 1
    n = sum(c.values())
    return {"n": n, "counts": c}


def scoreboard(resolved: list[dict]) -> list[dict]:
    """One row per (rule_version, timeframe, tier, read_kind). Directional rows carry the coin-flip
    baseline over the SAME reads; `rate` (followed-through or correct share) only with 20+ cases."""
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for r in resolved:
        groups[(r["rule_version"], r["timeframe"], r["tier"], r["read_kind"])].append(r)
    order = {"30m": 0, "1h": 1, "4h": 2, "1d": 3}
    out = []
    for (v, tf, tier, kind), rows in sorted(groups.items(), key=lambda kv: (kv[0][0], order.get(kv[0][1], 9), kv[0][2], kv[0][3])):
        if kind == "directional":
            eng = _counts(rows, "outcome", DIRECTIONAL_OUTCOMES)
            base = _counts(rows, "baseline_outcome", DIRECTIONAL_OUTCOMES)
            for s in (eng, base):
                s["rate"] = round(s["counts"][FOLLOWED] / s["n"], 3) if s["n"] >= MIN_N else None
            out.append({"rule_version": v, "timeframe": tf, "tier": tier, "read_kind": kind, "engine": eng,
                        "baseline": base})
        else:
            eng = _counts(rows, "outcome", RANGE_OUTCOMES)
            eng["rate"] = round(eng["counts"][CORRECT] / eng["n"], 3) if eng["n"] >= MIN_N else None
            out.append({"rule_version": v, "timeframe": tf, "tier": tier, "read_kind": kind, "engine": eng,
                        "baseline": None})
    return out


def build_report(conn, cfg: Config, run_date: str | None = None, now: datetime | None = None) -> dict:
    mr = cfg.morning_report
    now = now or datetime.now(timezone.utc)
    runs = [dict(r) for r in conn.execute("SELECT * FROM forward_runs ORDER BY run_date DESC LIMIT 120")]
    real = [r for r in runs if r["status"] != "gap"]
    day = run_date or (real[0]["run_date"] if real else None)
    run = next((r for r in runs if r["run_date"] == day), None)
    if run:
        run["skipped"] = json.loads(run["skipped"]) if run.get("skipped") else []
        run["attempt_log"] = json.loads(run["attempt_log"]) if run.get("attempt_log") else []
    for r in runs:
        if r is not run:
            r.pop("attempt_log", None)
            r.pop("skipped", None)
    q = lambda sql, *a: [_read(r) for r in conn.execute(sql, a)]  # noqa: E731
    review = q("SELECT * FROM forward_reads WHERE resolved_run_date=? ORDER BY symbol, timeframe", day) if day else []
    grid = q("SELECT * FROM forward_reads WHERE run_date=? ORDER BY symbol, timeframe", day) if day else []
    resolved = q("SELECT * FROM forward_reads WHERE outcome IS NOT NULL")
    pending = {r[0]: r[1] for r in conn.execute(
        "SELECT timeframe, COUNT(*) FROM forward_reads WHERE outcome IS NULL GROUP BY timeframe")}
    synth = [dict(r) for r in conn.execute("SELECT symbol, text, model FROM forward_syntheses WHERE run_date=? "
                                           "ORDER BY symbol", (day,))] if day else []
    first = conn.execute("SELECT MIN(run_date) FROM forward_runs WHERE status != 'gap'").fetchone()[0]
    return {
        "run_date": day, "run": run, "runs": runs,
        "gaps": [r["run_date"] for r in runs if r["status"] == "gap"],
        "first_run": first,
        "review": review, "grid": grid, "syntheses": synth,
        "pending": pending, "scoreboard": scoreboard(resolved),
        "watchlist": {"symbols": mr.symbols, "timeframes": mr.timeframes, "horizons": mr.horizons},
        "next_run": next_run(now, mr.timezone, mr.run_at).isoformat(),
        "schedule": f"{mr.run_at} {mr.timezone}",
        "rule": {"version": RULE_VERSION, "text": RULE_TEXT[RULE_VERSION]},
    }
