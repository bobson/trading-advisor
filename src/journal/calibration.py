"""ROADMAP D1 — how well YOUR calls are calibrated. Plain numbers; no streaks, no praise.

  Brier score   mean of (confidence − outcome)², outcome 1 = correct, 0 = incorrect or invalidated.
                Shown beside 0.25: what always saying 50% scores. Lower is better.
  curve         10-point bins of stated confidence (50–59 … 90–100): calls, mean confidence, hits;
                a hit RATE only with 20+ calls in the bin (the app-wide rule), counts below that.
  overconfidence  mean confidence − share correct (positive = more sure than the results justify).
  breakdowns    by timeframe, source, engine regime and pattern at logging, and blind (neither the
                verdict nor the explanation on screen) vs anchored.
"""

from __future__ import annotations

from collections import defaultdict

MIN_N = 20
BASELINE_BRIER = 0.25
BINS = ((50, 59), (60, 69), (70, 79), (80, 89), (90, 100))


def _o(e: dict) -> int:
    return 1 if e["outcome"] == "correct" else 0


def summary(entries: list[dict]) -> dict:
    """n, hits, accuracy (20+), Brier and overconfidence (with n) for a group of resolved calls."""
    n = len(entries)
    if not n:
        return {"n": 0, "hits": 0, "accuracy": None, "brier": None, "overconfidence": None, "invalidated": 0}
    hits = sum(_o(e) for e in entries)
    mean_conf = sum(e["confidence"] for e in entries) / n / 100
    return {"n": n, "hits": hits, "invalidated": sum(1 for e in entries if e["outcome"] == "invalidated"),
            "accuracy": round(hits / n, 3) if n >= MIN_N else None,
            "brier": round(sum((e["confidence"] / 100 - _o(e)) ** 2 for e in entries) / n, 4),
            "mean_confidence": round(mean_conf, 3),
            "overconfidence": round(mean_conf - hits / n, 3)}


def curve(entries: list[dict]) -> list[dict]:
    out = []
    for lo, hi in BINS:
        b = [e for e in entries if lo <= e["confidence"] <= hi]
        hits = sum(_o(e) for e in b)
        out.append({"bin": f"{lo}–{hi}", "n": len(b), "hits": hits,
                    "mean_confidence": round(sum(e["confidence"] for e in b) / len(b) / 100, 3) if b else None,
                    "rate": round(hits / len(b), 3) if len(b) >= MIN_N else None})
    return out


def _by(entries: list[dict], key) -> dict:
    groups = defaultdict(list)
    for e in entries:
        for k in key(e):
            groups[k].append(e)
    return {k: summary(v) for k, v in sorted(groups.items())}


def calibration(entries: list[dict]) -> dict:
    """Everything the stats page shows, from ALL entries (pending ones only counted)."""
    done = [e for e in entries if e["outcome"] is not None]
    eng = lambda e: e.get("engine") or {}  # noqa: E731
    return {
        "overall": summary(done), "baseline_brier": BASELINE_BRIER, "curve": curve(done),
        "pending": sum(1 for e in entries if e["outcome"] is None),
        "by_timeframe": _by(done, lambda e: [e["timeframe"]]),
        "by_source": _by(done, lambda e: [e["source"]]),
        "by_regime": _by(done, lambda e: [eng(e).get("regime", "unknown")]),
        "by_pattern": _by(done, lambda e: eng(e).get("patterns") or ["no pattern"]),
        "by_view": _by(done, lambda e: ["blind" if not (e["verdict_visible"] or e["explanation_visible"]) else "anchored"]),
        "min_n": MIN_N,
    }
