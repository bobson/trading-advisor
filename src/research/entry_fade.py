"""Experiment: on the daily chart, does going AGAINST a textbook entry beat the textbook side?

The hint came from the training pool (history, 1d, all markets): when exactly one side reached its next
level first, the MIRROR (same distances, other direction) won 2,110 of 3,632 times (58%) for trendline
touch, MA pullback, resistance rejection and support bounce. Found by looking, so it proves nothing on that
data. The test uses ONLY the forward record — entry points frozen at 08:00 from now on
(`forward_entries`), judged after their horizon — never the pool that suggested it.

  metric  mirror_win_rate = mirror wins / decisive entries (exactly one side reached its next level first),
          a rate vs the 0.5 baseline (D2's binomial test + the multiple-comparison correction).

The experiment is pre-registered (D2: `scripts/entry_fade_study.py --register …`, append-only). The morning
job calls `auto_record` every day: once a registered, unrun experiment has its `min_n` decisive entries, the
result is recorded against the registration — nobody picks the moment.
"""

from __future__ import annotations

import json

from src.forward.rule import FOLLOWED, RULE_VERSION

SCRIPT = "entry_fade"
METRIC = "mirror_win_rate"
DEFAULT_TYPES = ("MA pullback", "resistance rejection", "support bounce", "trendline touch")


def measure(conn, params: dict) -> dict:
    """Decisive forward entries on `params` (timeframe, types): how often the mirror was the side that won."""
    types = list(params["types"])
    q = (f"SELECT type, outcome, mirror_outcome FROM forward_entries WHERE timeframe=? AND rule_version=? "
         f"AND outcome IS NOT NULL AND type IN ({', '.join('?' * len(types))})")
    by_type: dict = {}
    for r in conn.execute(q, (params["timeframe"], RULE_VERSION, *types)):
        own, mir = r["outcome"] == FOLLOWED, r["mirror_outcome"] == FOLLOWED
        d = by_type.setdefault(r["type"], {"judged": 0, "mirror": 0, "textbook": 0})
        d["judged"] += 1
        if own != mir:
            d["mirror" if mir else "textbook"] += 1
    mirror = sum(d["mirror"] for d in by_type.values())
    n = mirror + sum(d["textbook"] for d in by_type.values())
    return {"n": n, "mirror": mirror, "value": round(mirror / n, 4) if n else None,
            "judged": sum(d["judged"] for d in by_type.values()), "by_type": by_type}


def _open(conn) -> list[dict]:
    try:
        rows = conn.execute("""SELECT e.* FROM experiments e WHERE e.script=? AND NOT EXISTS
                               (SELECT 1 FROM experiment_results r WHERE r.experiment_id = e.id)
                               AND e.id NOT IN (SELECT supersedes FROM experiments WHERE supersedes IS NOT NULL)""",
                            (SCRIPT,)).fetchall()
    except Exception:                       # no experiments table on this DB yet
        return []
    return [dict(r) for r in rows]


def live(conn) -> list[dict]:
    """Progress of every registered, not-yet-recorded entry_fade experiment (for the morning report)."""
    out = []
    for e in _open(conn):
        p = json.loads(e["params"])
        m = measure(conn, p)
        out.append({"id": e["id"], "hypothesis": e["hypothesis"], "threshold": e["threshold"], "min_n": p["min_n"],
                    "timeframe": p["timeframe"], "types": p["types"], **m})
    return out


def auto_record(conn, engine_commit: str | None = None) -> list[dict]:
    """Record every open experiment that has reached its `min_n` decisive entries (called by the morning job)."""
    from src.research.prereg import record
    done = []
    for e in _open(conn):
        p = json.loads(e["params"])
        m = measure(conn, p)
        if m["n"] >= p["min_n"]:
            done.append(record(conn, e["id"], {METRIC: (m["value"], m["n"])}, details=m, engine_commit=engine_commit))
    return done
