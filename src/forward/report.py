"""ROADMAP A8 — the morning report, assembled from the forward tables (read-only).

Order on the page: the REVIEW (reads resolved that morning), then that morning's symbol × timeframe
GRID, then the per-symbol synthesis; plus a running SCOREBOARD per rule version × timeframe × tier,
directional reads beside the coin-flip baseline scored with the same rule on the same reads. Rates
only with 20+ cases (the app-wide rule); below that, counts.

ROADMAP R2: each read also carries the caution conditions frozen at the read, and the CAUTION SPLIT
compares, per condition, the reads it flagged with the reads it didn't. That's the forward test of
Phase R: on data nobody could fit to, did flagged reads really go worse?

Simplification pass 1: the page leads with a plain SUMMARY (directional reads that followed through
vs the coin flip on the same reads; range reads), and MISSES IN COMMON — the caution split re-read
as "of the reads that went wrong, how many had this condition flagged — and of the ones that went
right?". Misses are `invalidated` reads only (expired / ambiguous are neither). Only the caution
conditions are compared — slicing by timeframe or pattern after the fact would be fishing.
`market_box` is the same record narrowed to one market + timeframe, for the Analysis page.
"""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone

from src.config import Config
from src.forward.rule import (CORRECT, DIRECTIONAL_OUTCOMES, FOLLOWED, INVALIDATED, RANGE_OUTCOMES, RULE_TEXT,
                              RULE_VERSION)
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


def summary(resolved: list[dict], version: int = RULE_VERSION) -> dict:
    """The whole record under one rule version, scored exactly like the scoreboard (N includes
    expired / ambiguous), directional beside the coin flip on the same reads."""
    rows = [r for r in resolved if r["rule_version"] == version]
    return {"rule_version": version,
            "directional": _side([r for r in rows if r["read_kind"] == "directional"], "directional"),
            "range": _side([r for r in rows if r["read_kind"] == "range"], "range")["engine"]}


def misses_in_common(split_rows: list[dict], version: int = RULE_VERSION) -> list[dict]:
    """Per caution condition (directional reads, one rule version): how many of the MISSES
    (invalidated) had it flagged, beside how many of the HITS (followed through) had it. Each side's
    denominator is the reads where the condition could be judged. `enough` = 20+ on both sides."""
    out = []
    for c in split_rows:
        if c["rule_version"] != version or c["read_kind"] != "directional":
            continue
        f, nf = c["flagged"]["engine"]["counts"], c["not_flagged"]["engine"]["counts"]
        misses, hits = f[INVALIDATED] + nf[INVALIDATED], f[FOLLOWED] + nf[FOLLOWED]
        if not misses and not hits:
            continue
        out.append({"code": c["code"], "label": c["label"], "misses_flagged": f[INVALIDATED], "misses": misses,
                    "hits_flagged": f[FOLLOWED], "hits": hits, "enough": misses >= MIN_N and hits >= MIN_N})
    return sorted(out, key=lambda x: (-x["misses_flagged"], x["label"]))


def market_box(conn, symbol: str, timeframe: str) -> dict:
    """One market + timeframe: its latest frozen read, its last judged read, and its record."""
    one = lambda sql: (lambda r: _read(r) if r else None)(conn.execute(sql, (symbol, timeframe)).fetchone())  # noqa: E731
    resolved = [_read(r) for r in conn.execute(
        "SELECT * FROM forward_reads WHERE symbol=? AND timeframe=? AND outcome IS NOT NULL", (symbol, timeframe))]
    pending = conn.execute("SELECT COUNT(*) FROM forward_reads WHERE symbol=? AND timeframe=? AND outcome IS NULL",
                           (symbol, timeframe)).fetchone()[0]
    return {
        "symbol": symbol, "timeframe": timeframe,
        "latest": one("SELECT * FROM forward_reads WHERE symbol=? AND timeframe=? ORDER BY run_date DESC, id DESC LIMIT 1"),
        "last_judged": one("SELECT * FROM forward_reads WHERE symbol=? AND timeframe=? AND outcome IS NOT NULL "
                           "ORDER BY resolved_run_date DESC, run_date DESC, id DESC LIMIT 1"),
        "summary": summary(resolved), "pending": pending,
        "caution_labels": _labels(), "caution_status": _statuses(conn),
    }


def entry_forward(conn, version: int = RULE_VERSION) -> list[dict]:
    """Entry points in the forward record, per type: judged textbook side vs its mirror (rule v1, first
    touch; same candles, same distances). Rates only with 20+ judged; `pending` = still waiting."""
    rows = {}
    for r in conn.execute("SELECT type, outcome, mirror_outcome FROM forward_entries WHERE rule_version=?", (version,)):
        d = rows.setdefault(r["type"], {"type": r["type"], "judged": 0, "pending": 0, "target": 0, "invalidated": 0,
                                        "mirror_target": 0})
        if r["outcome"] is None:
            d["pending"] += 1
            continue
        d["judged"] += 1
        d["target"] += r["outcome"] == FOLLOWED
        d["invalidated"] += r["outcome"] == INVALIDATED
        d["mirror_target"] += r["mirror_outcome"] == FOLLOWED
    for d in rows.values():
        n = d["judged"]
        d["target_rate"] = round(d["target"] / n, 3) if n >= MIN_N else None
        d["mirror_rate"] = round(d["mirror_target"] / n, 3) if n >= MIN_N else None
    return sorted(rows.values(), key=lambda d: (-d["judged"], d["type"]))


def _experiments_live(conn) -> list[dict]:
    from src.research.entry_fade import live
    return live(conn)


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
    split = caution_split(resolved)
    entries_today = [dict(r) for r in conn.execute(
        "SELECT symbol, timeframe, type, direction, level, next_level, invalidation FROM forward_entries "
        "WHERE run_date=? ORDER BY symbol, timeframe, type", (day,))] if day else []
    return {
        "run_date": day, "run": run, "runs": runs,
        "gaps": [r["run_date"] for r in runs if r["status"] == "gap"],
        "first_run": first,
        "review": review, "grid": grid, "syntheses": synth,
        "pending": pending, "scoreboard": scoreboard(resolved), "caution_split": split,
        "summary": summary(resolved), "misses_in_common": misses_in_common(split["rows"]),
        "entries_today": entries_today, "entry_forward": entry_forward(conn),
        "experiments_live": _experiments_live(conn),
        "watchlist": {"symbols": mr.symbols, "timeframes": mr.timeframes, "horizons": mr.horizons},
        "next_run": next_run(now, mr.timezone, mr.run_at).isoformat(),
        "schedule": f"{mr.run_at} {mr.timezone}",
        "rule": {"version": RULE_VERSION, "text": RULE_TEXT[RULE_VERSION]},
        "caution_labels": _labels(),
        "caution_status": _statuses(conn),
    }


def _statuses(conn) -> dict:
    """R3: what held-back history said about each condition (empty until measured)."""
    from src.risk.caution_stats import load
    return {code: s["status"] for code, s in load(conn).items()}


def _labels() -> dict:
    from src.risk.caution import LABELS
    return dict(LABELS)
