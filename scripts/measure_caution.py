"""ROADMAP R3 — measure each caution condition on history (the honest test). Writes `caution_stats`.

    python scripts/measure_caution.py                          # research pairs + gold, 1h/4h/1d, step 4
    python scripts/measure_caution.py --timeframes 1d --step 2
    python scripts/measure_caution.py --from-cases data/caution_cases.json   # re-aggregate only (seconds)

Cache-first candles (no Twelve Data credits spent on cached markets). ~0.2 s per scanned bar, so the
default takes about an hour; run it in the background. On the droplet, run it away from 08:00
Skopje (the morning report) and NEVER copy a local wizard.db over the droplet's (it holds the live
forward record). Instead copy data/caution_cases.json up and run `--from-cases` there: it writes only
the caution_stats table.

The decision rules are fixed in src/risk/caution_stats.py before any run; read its docstring first.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import load_config  # noqa: E402
from src.data.registry import get_candles, list_pairs  # noqa: E402
from src.risk.caution import LABELS  # noqa: E402
from src.risk.caution_stats import MIN_EFFECT, MIN_N, TUNE_SHARE, aggregate, collect, save  # noqa: E402
from src.service.analyze import _request_config  # noqa: E402
from src.store.db import connect  # noqa: E402


def _fmt(side: dict) -> str:
    return "—" if not side or not side.get("n") else (
        f"{side['bad']}/{side['n']}" + (f" {side['rate'] * 100:.0f}%" if side["n"] >= MIN_N else ""))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--symbols", default=None, help="default: the research pairs + XAU/USD")
    ap.add_argument("--timeframes", default="1h,4h,1d")
    ap.add_argument("--step", type=int, default=4)
    ap.add_argument("--db", default="data/wizard.db")
    ap.add_argument("--cases", default="data/caution_cases.json", help="raw cases, for re-aggregation")
    ap.add_argument("--from-cases", default=None, help="skip the walk: aggregate a saved cases file")
    from src.research import prereg
    prereg.add_args(ap)
    args = ap.parse_args()
    # D2: a new measurement must be registered; re-aggregating saved cases (deploying) is not a new run
    gated = None if args.from_cases else prereg.gate(args, "measure_caution", prereg.run_params(args, ignore=("db", "cases", "from_cases")))

    cfg0 = load_config()
    symbols = args.symbols.split(",") if args.symbols else [p.symbol for p in list_pairs()] + ["XAU/USD"]
    cases = json.loads(Path(args.from_cases).read_text()) if args.from_cases else []
    for tf in ([] if args.from_cases else args.timeframes.split(",")):
        for sym in symbols:
            t0 = time.time()
            try:
                df = get_candles(sym, tf, cfg0)
            except Exception as exc:
                print(f"  skip {sym} {tf}: {exc}", flush=True)
                continue
            got = collect(df, _request_config(cfg0, sym, tf), sym, tf, step=args.step)
            cases += got
            print(f"  {sym:9} {tf:3} {len(df):5} bars → {len(got):5} directional reads ({time.time() - t0:.0f}s)",
                  flush=True)
    if not args.from_cases:
        Path(args.cases).write_text(json.dumps(cases))
    stats = aggregate(cases)
    conn = connect(args.db)
    save(conn, stats, built_at=int(time.time()),
         params={"step": args.step, "timeframes": args.timeframes, "symbols": sorted({c["symbol"] for c in cases}),
                 "from_cases": args.from_cases, "min_n": MIN_N,
                 "min_effect": MIN_EFFECT, "tune_share": TUNE_SHARE, "thresholds": cfg0.caution.model_dump()})
    conn.close()

    print(f"\n{len(cases)} directional reads · held-back = last {100 - TUNE_SHARE * 100:.0f}% per market\n")
    for code, s in stats.items():
        print(f"{LABELS[code]:36} {s['status'].upper()}")
        t = s.get("test") or {}
        if "flagged" in t and "bad" in t.get("flagged", {}):
            print(f"    test: flagged {_fmt(t['flagged'])}  vs  unflagged {_fmt(t['unflagged'])}"
                  + (f"   (tune diff {s['tune']['diff']:+.3f})" if s.get("tune", {}).get("diff") is not None else ""))
            if "markets_agreeing" in s:
                print(f"    markets with the same sign: {s['markets_agreeing']} · cells tested: {s['cells_tested']}")
        elif s["status"] == "sizing":
            print(f"    range after, median ATR: flagged {t['flagged']['range_atr']} (n={t['flagged']['n']}) vs "
                  f"{t['unflagged']['range_atr']} (n={t['unflagged']['n']})")
    print(f"\nWrote caution_stats to {args.db}; raw cases to {args.cases}.")
    if gated:
        prereg.finish(*gated, {"helps_count": (sum(1 for s in stats.values() if s["status"] == "helps"), None)})


if __name__ == "__main__":
    main()
