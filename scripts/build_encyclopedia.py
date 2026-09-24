"""ROADMAP B3 — build the Empirical Pattern Encyclopedia into SQLite `encyclopedia_stats`.

    python scripts/build_encyclopedia.py                              # all registered pairs, 1d
    python scripts/build_encyclopedia.py --timeframes 1d,4h,1h        # more timeframes (slower)
    python scripts/build_encyclopedia.py --symbols BTC/USDT,SOL/USDT --db /tmp/x.db

Walks each market with THE look-ahead-safe backtest walk (`backtest.evaluate.walk`), records every
distinct chart pattern at the bar it was first detected, measures what happened next, and writes
per pattern × timeframe × symbol × regime (+ 'all' roll-ups) statistics with sample sizes. Rates
with fewer than 20 cases are stored as counts only. Candles come cache-first from data/. Takes about
a minute per daily market. The API only READS the table — re-run this to refresh it.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import load_config  # noqa: E402
from src.data.registry import get_candles, list_pairs  # noqa: E402
from src.research.encyclopedia import aggregate, collect_instances, save_rows  # noqa: E402
from src.store.db import connect  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--symbols", default=None, help="comma list (default: every registered pair)")
    ap.add_argument("--timeframes", default="1d")
    ap.add_argument("--horizon", type=int, default=24, help="bars after the breakout to measure")
    ap.add_argument("--max-wait", type=int, default=50, help="bars a forming pattern has to break out")
    ap.add_argument("--db", default="data/wizard.db")
    args = ap.parse_args()

    cfg = load_config()
    symbols = args.symbols.split(",") if args.symbols else [p.symbol for p in list_pairs()]
    tfs = args.timeframes.split(",")
    instances, markets = [], []
    for tf in tfs:
        for sym in symbols:
            t0 = time.time()
            try:
                df = get_candles(sym, tf, cfg)
            except Exception as exc:                      # e.g. forex without an API key and no cache
                print(f"  skip {sym} {tf}: {exc}")
                continue
            got = collect_instances(df, cfg, sym, tf, horizon=args.horizon, max_wait=args.max_wait)
            instances += got
            markets.append((sym, tf))
            print(f"  {sym:9} {tf:3} {len(df):5} bars → {len(got):4} patterns  ({time.time() - t0:.0f}s)")

    rows = aggregate(instances)
    conn = connect(args.db)
    save_rows(conn, rows, built_at=int(time.time()),
              params={"horizon": args.horizon, "max_wait": args.max_wait, "min_n": 20}, replace_markets=markets)
    conn.close()
    print(f"\nWrote {len(rows)} rows for {len(markets)} markets to {args.db} (encyclopedia_stats).")


if __name__ == "__main__":
    main()
