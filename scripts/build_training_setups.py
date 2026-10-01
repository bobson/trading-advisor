"""ROADMAP D6 — build the blind-training pool (`training_setups`): past moments where a pattern confirmed.

    python scripts/build_training_setups.py                           # research pairs + gold, 1h/4h/1d
    python scripts/build_training_setups.py --from-file data/training_setups.json   # import only (seconds)

Uses the encyclopedia's look-ahead-safe walk (every bar), cache-first candles. About 30 minutes; run it
in the background. On the droplet: copy data/training_setups.json up and use --from-file (writes only
this table — never copy a whole wizard.db over the droplet's, it holds the live forward record).
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
from src.research.training import collect_setups, connect, export, options, save  # noqa: E402
from src.service.analyze import _request_config  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--symbols", default=None)
    ap.add_argument("--timeframes", default="1h,4h,1d")
    ap.add_argument("--db", default="data/wizard.db")
    ap.add_argument("--file", default="data/training_setups.json")
    ap.add_argument("--from-file", default=None)
    args = ap.parse_args()

    cfg0 = load_config()
    if args.from_file:
        setups = json.loads(Path(args.from_file).read_text())
    else:
        symbols = args.symbols.split(",") if args.symbols else [p.symbol for p in list_pairs()] + ["XAU/USD"]
        setups = []
        for tf in args.timeframes.split(","):
            horizon = cfg0.morning_report.horizons.get(tf, 24)
            for sym in symbols:
                t0 = time.time()
                try:
                    df = get_candles(sym, tf, cfg0)
                except Exception as exc:
                    print(f"  skip {sym} {tf}: {exc}", flush=True)
                    continue
                got = collect_setups(df, _request_config(cfg0, sym, tf), sym, tf, horizon=horizon)
                setups += got
                print(f"  {sym:9} {tf:3} → {len(got):4} confirmed setups ({time.time() - t0:.0f}s)", flush=True)
        export(setups, args.file)
    conn = connect(args.db)
    added = save(conn, setups)
    print(f"\n{added} new setups ({len(setups)} in the file) → {args.db}; pool now: {options(conn)}")
    conn.close()


if __name__ == "__main__":
    main()
