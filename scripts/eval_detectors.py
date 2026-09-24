"""ROADMAP B2 — measure the detectors against your gold labels, tune the weak ones honestly.

    python scripts/eval_detectors.py                      # report: precision/recall per detector × timeframe
    python scripts/eval_detectors.py --tune channels      # grid-search channel knobs on the TUNE split,
                                                          # show before/after on the HOLDOUT
    python scripts/eval_detectors.py --tune channels --write   # also save data/detector_reliability.json
                                                          # (fills the facts' reliability field; restart the API)

~30% of labelled charts are a fixed HOLDOUT (hash of symbol|timeframe|bar): tuning never sees them,
and the final numbers are reported on them. Every rate is printed with its counts. Tuned values are
printed — copy them into config.yaml yourself if you accept them (this script never edits config).
Read-only on the labels; candles come cache-first from data/.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import load_config  # noqa: E402
from src.data.registry import get_candles  # noqa: E402
from src.labels import gold  # noqa: E402
from src.labels.evaluate import (  # noqa: E402
    Report,
    combined,
    evaluate,
    reliability_table,
    split,
    tune,
    with_patterns,
)
from src.patterns.chart_patterns import ASCENDING_CHANNEL, DESCENDING_CHANNEL  # noqa: E402
from src.store.db import connect  # noqa: E402

TUNABLE = {
    "channels": {
        "detectors": [ASCENDING_CHANNEL, DESCENDING_CHANNEL],
        "grid": {"channel_min_r2": [0.6, 0.75, 0.9], "channel_min_parallel": [0.5, 0.7, 0.85],
                 "channel_respect_rails": [False, True]},
    },
}
MIN_LABELS = 30


def pct(x):
    return "   —  " if x is None else f"{x * 100:5.1f}%"


def print_report(title: str, report: Report) -> None:
    print(f"\n{title}  ({report.charts} labelled charts)")
    print(f"  {'detector':28} {'tf':4} {'precision':>10} {'(tp/fired)':>11} {'recall':>8} {'(tp/gold)':>10}")
    for (det, tf), t in sorted(report.tallies.items()):
        print(f"  {det:28} {tf:4} {pct(t.precision):>10} {f'{t.tp}/{t.detections}':>11} "
              f"{pct(t.recall):>8} {f'{t.tp}/{t.gold}':>10}")
    if not report.tallies:
        print("  (nothing to score)")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", default="data/wizard.db")
    ap.add_argument("--holdout", type=float, default=0.3)
    ap.add_argument("--tune", choices=sorted(TUNABLE), default=None)
    ap.add_argument("--write", action="store_true", help="save data/detector_reliability.json (holdout precision)")
    ap.add_argument("--force", action="store_true", help=f"run even with fewer than {MIN_LABELS} labelled charts")
    args = ap.parse_args()

    cfg = load_config()
    conn = connect(args.db)
    labels = gold.list_all(conn)
    conn.close()
    tune_set, hold_set = split(labels, args.holdout)
    print(f"Gold set: {len(labels)} labelled charts → tune {len(tune_set)} / holdout {len(hold_set)} "
          f"(fixed hash split, {args.holdout:.0%} holdout)")
    if len(labels) < MIN_LABELS and not args.force:
        print(f"\nNot enough labels yet: B2 needs at least {MIN_LABELS} labelled charts (you have {len(labels)}).\n"
              "Label charts in the app (scrub view → 🏷 Label this bar), then re-run. "
              "Use --force to run anyway on a thin set — the numbers will be flagged thin.")
        return

    cache: dict = {}

    def candles_for(symbol, timeframe):
        if (symbol, timeframe) not in cache:
            cache[(symbol, timeframe)] = get_candles(symbol, timeframe, cfg)
        return cache[(symbol, timeframe)]

    print_report("ALL LABELS — current settings", evaluate(labels, cfg, candles_for))
    before_hold = evaluate(hold_set, cfg, candles_for)
    final_cfg, chosen = cfg, None

    if args.tune:
        spec = TUNABLE[args.tune]
        res = tune(tune_set, cfg, candles_for, spec["detectors"], spec["grid"])
        print(f"\nTUNING {args.tune} on the TUNE split only ({len(tune_set)} charts), combined F1:")
        for row in sorted(res["log"], key=lambda r: -(r["f1"] or -1))[:8]:
            f1 = "   — " if row["f1"] is None else f"{row['f1']:.3f}"
            print(f"  F1 {f1}  tp {row['tp']:3} fp {row['fp']:3} fn {row['fn']:3}  {row['params']}")
        chosen = res["best"] or None
        if chosen:
            final_cfg = with_patterns(cfg, **chosen)
            after_hold = evaluate(hold_set, final_cfg, candles_for)
            b, a = combined(before_hold, spec["detectors"]), combined(after_hold, spec["detectors"])
            print(f"\nHOLDOUT ({len(hold_set)} charts) — {args.tune}, before → after:")
            print(f"  precision {pct(b.precision)} ({b.tp}/{b.detections}) → {pct(a.precision)} ({a.tp}/{a.detections})")
            print(f"  recall    {pct(b.recall)} ({b.tp}/{b.gold}) → {pct(a.recall)} ({a.tp}/{a.gold})")
            print(f"  chosen settings: {chosen}  (put them in config.yaml → patterns: to adopt)")
        else:
            print("  no candidate fired often enough on the tune split to score — keep current settings")

    final_hold = evaluate(hold_set, final_cfg, candles_for)
    print_report("HOLDOUT — final numbers" + (" (tuned)" if chosen else ""), final_hold)

    if args.write:
        out = {"generated_at": int(time.time()), "split": "holdout", "holdout_charts": final_hold.charts,
               "tuned": chosen, "table": reliability_table(final_hold)}
        Path("data").mkdir(exist_ok=True)
        Path("data/detector_reliability.json").write_text(json.dumps(out, indent=2))
        print("\nWrote data/detector_reliability.json — restart the API to show measured precision in the facts.")


if __name__ == "__main__":
    main()
