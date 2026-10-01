"""ROADMAP R4 — exits: noise floor, typical run and an exit-rule comparison on the held-back reads.
Writes `exit_stats`.

    python scripts/measure_exits.py                                  # research pairs + gold, 1h/4h/1d, step 4
    python scripts/measure_exits.py --from-cases data/exit_cases.json --exits data/exit_returns.json

Same walk and 70/30 split as R3 (`caution_stats.collect`). Cache-first candles. About 80 minutes;
run it in the background. On the droplet: copy data/exit_cases.json and data/exit_returns.json up and
use --from-cases (writes only the exit_stats table). Never copy a whole wizard.db over the droplet's.
Definitions are fixed in src/risk/excursions.py; read its docstring first.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import load_config  # noqa: E402
from src.data.registry import get_candles, list_pairs  # noqa: E402
from src.risk.caution_stats import collect  # noqa: E402
from src.risk.excursions import exit_table, save, simulate_exits, summarize  # noqa: E402
from src.service.analyze import _request_config  # noqa: E402
from src.store.db import connect  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--symbols", default=None)
    ap.add_argument("--timeframes", default="1h,4h,1d")
    ap.add_argument("--step", type=int, default=4)
    ap.add_argument("--db", default="data/wizard.db")
    ap.add_argument("--cases", default="data/exit_cases.json")
    ap.add_argument("--exits", default="data/exit_returns.json")
    ap.add_argument("--from-cases", default=None, help="skip the walk: summarize saved cases (+ --exits file)")
    from src.research import prereg
    prereg.add_args(ap)
    args = ap.parse_args()
    # D2: a new measurement must be registered; re-summarizing saved cases (deploying) is not a new run
    gated = None if args.from_cases else prereg.gate(args, "measure_exits", prereg.run_params(args, ignore=("db", "cases", "exits", "from_cases")))

    cfg0 = load_config()
    symbols = args.symbols.split(",") if args.symbols else [p.symbol for p in list_pairs()] + ["XAU/USD"]
    if args.from_cases:
        cases = json.loads(Path(args.from_cases).read_text())
        returns = json.loads(Path(args.exits).read_text()) if Path(args.exits).exists() else {}
    else:
        cases, returns = [], defaultdict(lambda: defaultdict(list))
        for tf in args.timeframes.split(","):
            for sym in symbols:
                t0 = time.time()
                try:
                    df = get_candles(sym, tf, cfg0)
                except Exception as exc:
                    print(f"  skip {sym} {tf}: {exc}", flush=True)
                    continue
                req = _request_config(cfg0, sym, tf)
                got = collect(df, req, sym, tf, step=args.step)
                for rule, r in simulate_exits(df, req, got).items():
                    returns[tf][rule] += r
                cases += got
                print(f"  {sym:9} {tf:3} {len(df):5} bars → {len(got):5} reads ({time.time() - t0:.0f}s)", flush=True)
        Path(args.cases).write_text(json.dumps(cases))
        Path(args.exits).write_text(json.dumps(returns))
    summary = summarize(cases, {tf: exit_table(r) for tf, r in returns.items()})
    conn = connect(args.db)
    save(conn, summary, built_at=int(time.time()),
         params={"step": args.step, "symbols": sorted({c["symbol"] for c in cases}), "from_cases": args.from_cases})
    conn.close()

    for tf, s in summary.items():
        t, u = s["test"], s["tune"]
        print(f"\n{tf}: {t['n']} held-back reads ({t['winners']} ended in profit) · markets {', '.join(s['markets'])}")
        print(f"  noise floor  {t['noise_floor']} ATR   (older part {u['noise_floor']}; stable={s['stable']['noise_floor']})")
        print(f"  typical run  {t['typical_run']} ATR   (older part {u['typical_run']}; stable={s['stable']['typical_run']})")
        print("  stop touched (all / winners): " + "  ".join(
            f"{k}ATR {v['all']}/{v['winners']}" for k, v in t["stop_touch"].items()))
        for rule, e in (s["exits"] or {}).items():
            print(f"    exit {rule:13} n={e['n']:<5} mean {e['mean_pct']}%/trade  win {e['win_rate']}  held {e['avg_bars']} bars")
    print(f"\nWrote exit_stats to {args.db}; cases to {args.cases}; exit returns to {args.exits}.")
    if gated:
        prereg.finish(*gated, {f"noise_floor_{tf}": (s["test"]["noise_floor"], None) for tf, s in summary.items()})


if __name__ == "__main__":
    main()
