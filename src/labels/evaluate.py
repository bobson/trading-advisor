"""ROADMAP B2 — measure the detectors against the user's gold labels (B1).

For every labelled chart (symbol, timeframe, bar) the detectors are re-run on the candles up to that
bar — exactly what the chart showed while labelling — and compared with the labels:

  chart patterns — a detection MATCHES a gold pattern when the TYPE is the same and both ENDPOINTS
      (first and last key point) line up: within `bar_tol` bars in time and `atr_tol` × ATR in price
      (ATR at the labelled bar — scale-free across BTC and EUR/USD). Middle points are ignored (you
      may click 3 points where the detector used 6). Matching is one-to-one, closest first.
  support/resistance — the zones the chart draws (nearest `zones_per_side` per side) vs your zones:
      a match needs the same role and the bands overlapping once each is widened by `zone_atr_tol`
      × ATR. Scored only on charts where you marked at least one zone ("nothing here" is about
      patterns, not zones).

precision = matched detections / all detections   ("when it fires, is it right?")
recall    = matched gold labels / all gold labels  ("does it find what I marked?")
Both are always reported with their counts. A chart you labelled is taken as COMPLETE: anything the
detector finds there that you didn't mark is a false positive ("nothing here" charts are the
cleanest test of that).

Honesty rules: the split is fixed by a hash of (symbol, timeframe, bar) — ~30% HOLDOUT, never used
for tuning, and a chart never changes side as the gold set grows. Tuning evaluates candidate
parameters on the TUNE split only; the chosen setting is then reported on the holdout, before vs
after. Below `min_n` the numbers are flagged thin rather than trusted.
"""

from __future__ import annotations

import hashlib
import itertools
import json
from dataclasses import dataclass, field

import pandas as pd

from src.indicators.features import COL_ATR, add_features
from src.patterns.chart_patterns import find_patterns
from src.structure.support_resistance import annotate_roles, sr_zones, zone_distance
from src.structure.swings import find_swings

SR = "support_resistance"


def is_holdout(symbol: str, timeframe: str, bar: int, frac: float = 0.3) -> bool:
    """Stable ~`frac` holdout membership from a hash — never random, never moves."""
    h = int(hashlib.sha1(f"{symbol}|{timeframe}|{int(bar)}".encode()).hexdigest(), 16)
    return (h % 1000) < int(frac * 1000)


@dataclass
class Tally:
    tp: int = 0        # detections that matched a gold label
    fp: int = 0        # detections with no matching gold label
    fn: int = 0        # gold labels no detection matched

    def add(self, other: "Tally") -> None:
        self.tp += other.tp
        self.fp += other.fp
        self.fn += other.fn

    @property
    def detections(self) -> int:
        return self.tp + self.fp

    @property
    def gold(self) -> int:
        return self.tp + self.fn

    @property
    def precision(self) -> float | None:
        return self.tp / self.detections if self.detections else None

    @property
    def recall(self) -> float | None:
        return self.tp / self.gold if self.gold else None

    @property
    def f1(self) -> float | None:
        p, r = self.precision, self.recall
        return None if not p or not r else 2 * p * r / (p + r)


@dataclass
class Report:
    """Tallies keyed (detector, timeframe), plus how many charts went in."""
    tallies: dict = field(default_factory=dict)
    charts: int = 0

    def tally(self, detector: str, timeframe: str) -> Tally:
        return self.tallies.setdefault((detector, timeframe), Tally())


def _endpoints(points: list[tuple[int, float]]) -> tuple[tuple[int, float], tuple[int, float]]:
    pts = sorted(points)
    return pts[0], pts[-1]


def _pattern_matches(gold: list[tuple[int, float]], det: list[tuple[int, float]], atr: float,
                     bar_tol: int, atr_tol: float) -> float | None:
    """Distance score if the endpoints line up (smaller = closer), else None."""
    (g0, g1), (d0, d1) = _endpoints(gold), _endpoints(det)
    score = 0.0
    for (gb, gp), (db, dp) in ((g0, d0), (g1, d1)):
        if abs(gb - db) > bar_tol or abs(gp - dp) > atr_tol * atr:
            return None
        score += abs(gb - db) / max(bar_tol, 1) + abs(gp - dp) / (atr_tol * atr)
    return score


def _match(gold: list, det: list, score) -> tuple[int, int, int]:
    """Greedy one-to-one matching by best score. Returns (tp, fp, fn)."""
    pairs = sorted((s, gi, di) for gi, g in enumerate(gold) for di, d in enumerate(det)
                   if (s := score(g, d)) is not None)
    used_g, used_d = set(), set()
    for _, gi, di in pairs:
        if gi not in used_g and di not in used_d:
            used_g.add(gi)
            used_d.add(di)
    return len(used_g), len(det) - len(used_d), len(gold) - len(used_g)


def detect_at(candles: pd.DataFrame, bar: int, cfg) -> dict:
    """Run the detectors on candles[:bar+1] — what the chart showed at that bar."""
    df = candles.iloc[: int(bar) + 1]
    feat = add_features(df, cfg)
    swings = find_swings(df, cfg.structure.swing_sensitivity)
    atr = float(feat[COL_ATR].iloc[-1]) if pd.notna(feat[COL_ATR].iloc[-1]) else float(df["close"].iloc[-1]) * 0.01
    return {"df": df, "atr": atr, "patterns": find_patterns(feat, swings, cfg),
            "zones": sr_zones(feat, swings, cfg)}


def evaluate_chart(label: dict, candles: pd.DataFrame, cfg, report: Report, *, bar_tol: int | None = None,
                   atr_tol: float = 1.0, zone_atr_tol: float = 0.25, zones_per_side: int = 3,
                   detector_types: list[str] | None = None) -> None:
    """Score one labelled chart into `report`. `label` is a gold_labels row (dict)."""
    tf, bar = label["timeframe"], int(label["bar"])
    if bar >= len(candles):
        return
    bar_tol = bar_tol if bar_tol is not None else 2 * cfg.structure.swing_sensitivity
    d = detect_at(candles, bar, cfg)
    idx = d["df"].index
    pos = {int(pd.Timestamp(t).timestamp()): i for i, t in enumerate(idx)}
    labels = label["labels"]
    report.charts += 1

    # --- chart patterns, per type -----------------------------------------------------------
    gold_by_type: dict[str, list] = {}
    for p in labels["patterns"]:
        pts = [(pos[q["time"]], q["price"]) for q in p["points"] if q["time"] in pos]
        if len(pts) >= 2:
            gold_by_type.setdefault(p["type"], []).append(pts)
    det_by_type: dict[str, list] = {}
    for p in d["patterns"]:
        pts = [(int(b), float(pr)) for b, pr in p.points]
        if len(pts) >= 2:
            det_by_type.setdefault(p.type, []).append(pts)
    types = set(gold_by_type) | set(det_by_type)
    if detector_types is not None:           # tuning one detector: score only its types
        types &= set(detector_types)
    for t in types:
        tp, fp, fn = _match(gold_by_type.get(t, []), det_by_type.get(t, []),
                            lambda g, x: _pattern_matches(g, x, d["atr"], bar_tol, atr_tol))
        report.tally(t, tf).add(Tally(tp, fp, fn))

    # --- support/resistance zones — scored only on charts where you marked zones ("nothing here"
    # means no PATTERN, not no zones); the zones you marked are then taken as complete ------------
    if labels["zones"]:
        close = float(d["df"]["close"].iloc[-1])
        shown = []
        if not d["zones"].empty:
            roled = annotate_roles(d["zones"], close).assign(_d=zone_distance(d["zones"], close))
            for role in ("support", "resistance"):
                side = roled[roled["role"] == role].sort_values("_d").head(zones_per_side)
                shown += [(role, float(z["lower"]), float(z["upper"])) for _, z in side.iterrows()]
        gold_z = [(z["role"], z["lower"], z["upper"]) for z in labels["zones"]]
        m = zone_atr_tol * d["atr"]

        def zscore(g, x):
            if g[0] != x[0] or g[1] - m > x[2] + m or x[1] - m > g[2] + m:
                return None
            return abs((g[1] + g[2]) / 2 - (x[1] + x[2]) / 2)
        report.tally(SR, tf).add(Tally(*_match(gold_z, shown, zscore)))


def evaluate(labels: list[dict], cfg, candles_for, **kw) -> Report:
    """Evaluate every labelled chart. `candles_for(symbol, timeframe) -> DataFrame` (cache it)."""
    report = Report()
    for lab in labels:
        evaluate_chart(lab, candles_for(lab["symbol"], lab["timeframe"]), cfg, report, **kw)
    return report


def split(labels: list[dict], frac: float = 0.3) -> tuple[list[dict], list[dict]]:
    """(tune, holdout) by the stable hash."""
    tune = [lab for lab in labels if not is_holdout(lab["symbol"], lab["timeframe"], lab["bar"], frac)]
    hold = [lab for lab in labels if is_holdout(lab["symbol"], lab["timeframe"], lab["bar"], frac)]
    return tune, hold


def with_patterns(cfg, **overrides):
    return cfg.model_copy(update={"patterns": cfg.patterns.model_copy(update=overrides)})


def combined(report: Report, detectors: list[str]) -> Tally:
    total = Tally()
    for (det, _), t in report.tallies.items():
        if det in detectors:
            total.add(t)
    return total


def tune(tune_labels: list[dict], cfg, candles_for, detectors: list[str], grid: dict[str, list],
         *, min_detections: int = 3) -> dict:
    """Grid-search `grid` (patterns-config overrides) on the TUNE split only, scoring the combined
    F1 of `detectors`. Candidates with fewer than `min_detections` fires are skipped (a detector that
    never fires has undefined precision, not perfect precision). Returns the best overrides + a log."""
    keys = list(grid)
    log, best, best_f1 = [], {}, -1.0
    for combo in itertools.product(*(grid[k] for k in keys)):
        ov = dict(zip(keys, combo))
        t = combined(evaluate(tune_labels, with_patterns(cfg, **ov), candles_for,
                              detector_types=detectors), detectors)
        f1 = t.f1 if t.detections >= min_detections else None
        log.append({"params": ov, "tp": t.tp, "fp": t.fp, "fn": t.fn, "f1": f1})
        if f1 is not None and f1 > best_f1:
            best, best_f1 = ov, f1
    return {"best": best, "best_f1": best_f1 if best else None, "log": log}


def reliability_table(report: Report, *, min_n: int = 10) -> dict:
    """The measured-precision table that fills the A5 reliability field, keyed 'detector|timeframe'."""
    out = {}
    for (det, tf), t in sorted(report.tallies.items()):
        out[f"{det}|{tf}"] = {
            "precision": None if t.precision is None else round(t.precision, 3),
            "recall": None if t.recall is None else round(t.recall, 3),
            "n": t.detections, "gold": t.gold, "tp": t.tp, "fp": t.fp, "fn": t.fn,
            "status": "measured" if t.detections >= min_n else f"thin (n<{min_n})",
        }
    return out


def load_reliability(path: str = "data/detector_reliability.json") -> dict:
    try:
        with open(path) as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}
