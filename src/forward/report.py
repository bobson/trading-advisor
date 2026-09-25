"""ROADMAP A8 — the morning report, assembled from the forward tables (read-only).

Order on the page: the REVIEW (reads resolved that morning), then that morning's symbol × timeframe
GRID, then the per-symbol synthesis; plus a running SCOREBOARD per rule version × timeframe × tier,
directional reads beside the coin-flip baseline scored with the same rule on the same reads. Rates
only with 20+ cases (the app-wide rule); below that, counts.

ROADMAP R2: each read also carries the caution conditions frozen at the read, and the CAUTION SPLIT
compares, per condition, the reads it flagged with the reads it didn't. That's the forward test of
Phase R: on data nobody could fit to, did flagged reads really go worse?
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
    d["caution"] = json.loads(r["caution"]) if r["caution"] else None      # None = not recorded (pre-R2)
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


def _side(rows: list[dict], kind: str) -> dict:
    """Outcome counts for one side of a split (+ the coin flip on the same reads, directional only)."""
    if kind == "directional":
        eng, base = _counts(rows, "outcome", DIRECTIONAL_OUTCOMES), _counts(rows, "baseline_outcome", DIRECTIONAL_OUTCOMES)
        for x in (eng, base):
            x["rate"] = round(x["counts"][FOLLOWED] / x["n"], 3) if x["n"] >= MIN_N else None
        return {"engine": eng, "baseline": base}
    eng = _counts(rows, "outcome", RANGE_OUTCOMES)
    eng["rate"] = round(eng["counts"][CORRECT] / eng["n"], 3) if eng["n"] >= MIN_N else None
    return {"engine": eng, "baseline": None}


def caution_split(resolved: list[dict]) -> dict:
    """ROADMAP R2 — per (rule version, read kind, caution condition): the judged reads it FLAGGED vs the
    ones it didn't, pooled across timeframes. Reads from before R2 have no flags ("not recorded") and
    reads where the condition couldn't be judged sit in neither side."""
    from src.risk.caution import LABELS
    recorded = [r for r in resolved if r["caution"] is not None]
    rows = []
    for v in sorted({r["rule_version"] for r in recorded}):
        for kind in ("directional", "range"):
            pool = [r for r in recorded if r["rule_version"] == v and r["read_kind"] == kind]
            for code in LABELS:
                on = [r for r in pool if r["caution"].get(code) is True]
                off = [r for r in pool if r["caution"].get(code) is False]
                if not on and not off:
                    continue
                rows.append({"rule_version": v, "read_kind": kind, "code": code, "label": LABELS[code],
                             "flagged": _side(on, kind), "not_flagged": _side(off, kind),
                             "cant_judge": len(pool) - len(on) - len(off)})
    return {"rows": rows, "not_recorded": len(resolved) - len(recorded)}


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
        "pending": pending, "scoreboard": scoreboard(resolved), "caution_split": caution_split(resolved),
        "watchlist": {"symbols": mr.symbols, "timeframes": mr.timeframes, "horizons": mr.horizons},
        "next_run": next_run(now, mr.timezone, mr.run_at).isoformat(),
        "schedule": f"{mr.run_at} {mr.timezone}",
        "rule": {"version": RULE_VERSION, "text": RULE_TEXT[RULE_VERSION]},
        "caution_labels": _labels(),
    }


def _labels() -> dict:
    from src.risk.caution import LABELS
    return dict(LABELS)
