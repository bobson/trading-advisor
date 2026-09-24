"""ROADMAP B4 — build the verdict records into SQLite `verdict_records`.

    python scripts/build_verdict_records.py                       # all registered pairs, 1d
    python scripts/build_verdict_records.py --timeframes 1d,1h --step 3

Walks each market with THE backtest walk, records every directional verdict (bias × agreeing
categories × aligned) and whether price moved that way over the next --horizon bars. About 4 minutes
per daily market at --step 2. The API only reads the table — re-run to refresh.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import load_config  # noqa: E402
from src.data.registry import get_candles, list_pairs  # noqa: E402
from src.research.verdict_records import aggregate, collect, save  # noqa: E402
from src.store.db import connect  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--symbols", default=None)
    ap.add_argument("--timeframes", default="1d")
    ap.add_argument("--horizon", type=int, default=24)
    ap.add_argument("--step", type=int, default=2, help="scan every Nth bar (1 = every bar, slowest)")
    ap.add_argument("--db", default="data/wizard.db")
    args = ap.parse_args()

    cfg = load_config()
    symbols = args.symbols.split(",") if args.symbols else [p.symbol for p in list_pairs()]
    per_market = {}
    for tf in args.timeframes.split(","):
        for sym in symbols:
            t0 = time.time()
            try:
                df = get_candles(sym, tf, cfg)
            except Exception as exc:
                print(f"  skip {sym} {tf}: {exc}", flush=True)
                continue
            per_market[(sym, tf)] = collect(df, cfg, horizon=args.horizon, step=args.step)
            print(f"  {sym:9} {tf:3} {len(df):5} bars → {len(per_market[(sym, tf)]):5} directional verdicts "
                  f"({time.time() - t0:.0f}s)", flush=True)
    rows = aggregate(per_market)
    conn = connect(args.db)
    save(conn, rows, horizon=args.horizon, built_at=int(time.time()), markets=list(per_market))
    conn.close()
    print(f"\nWrote {len(rows)} rows to {args.db} (verdict_records).")


if __name__ == "__main__":
    main()
