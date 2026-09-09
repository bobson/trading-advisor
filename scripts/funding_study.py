#!/usr/bin/env python3
"""Recommendation #3 — measure whether crowded funding precedes contrarian moves.

Run it, read the verdict. Funding gets promoted to a confluence VOTE only if extremes clearly
skew forward returns the contrarian way vs baseline.

    python scripts/funding_study.py                       # BTC/USDT 1h, 24-bar horizon
    python scripts/funding_study.py --symbol ETH/USDT --horizon 12
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.config import load_config  # noqa: E402
from src.data.registry import get_candles  # noqa: E402
from src.derivatives.funding_study import align_funding, fetch_funding_history, study_funding  # noqa: E402
from src.derivatives.gather import _perp_symbol  # noqa: E402


def main() -> None:
    cfg = load_config()
    p = argparse.ArgumentParser(description="Does crowded funding precede contrarian moves?")
    p.add_argument("--symbol", default="BTC/USDT")
    p.add_argument("--timeframe", default="1h")
    p.add_argument("--horizon", type=int, default=24)
    p.add_argument("--months", type=int, default=6)
    args = p.parse_args()

    import ccxt

    exchange = ccxt.binanceusdm()
    perp = _perp_symbol(args.symbol)
    since = exchange.milliseconds() - args.months * 30 * 24 * 3600 * 1000

    funding = fetch_funding_history(exchange, perp, since)
    candles = get_candles(args.symbol, args.timeframe, cfg)
    funding_bar = align_funding(candles.index, funding)
    r = study_funding(candles, funding_bar, cfg, horizon=args.horizon)

    print(f"Funding study — {args.symbol} {args.timeframe}, {args.horizon}-bar forward return  "
          f"({len(funding)} funding points; high/low = period's top/bottom decile of funding)")
    print(f"  crowding thresholds: high >= {r['hi_threshold']}, low <= {r['lo_threshold']}\n")
    for k in ("all", "high_funding", "low_funding"):
        s = r[k]
        if s["n"]:
            print(f"  {k:13} n={s['n']:<4} mean forward {s['mean_fwd_pct']:+.3f}%   went up {s['pct_up']:.0f}% of the time")
        else:
            print(f"  {k:13} n=0")

    base = r["all"]["pct_up"]
    hi, lo = r["high_funding"], r["low_funding"]
    print("\nVerdict (contrarian = fade the crowd):")
    edge = False
    if hi["n"] >= 30 and hi["pct_up"] is not None and hi["pct_up"] <= base - 5:
        print(f"  most crowded-long -> up only {hi['pct_up']:.0f}% vs {base:.0f}% baseline: contrarian-DOWN skew")
        edge = True
    if lo["n"] >= 30 and lo["pct_up"] is not None and lo["pct_up"] >= base + 5:
        print(f"  most crowded-short -> up {lo['pct_up']:.0f}% vs {base:.0f}% baseline: contrarian-UP skew")
        edge = True
    print("  => funding shows a usable contrarian skew — consider promoting to a vote." if edge
          else "  => no clear, sized contrarian edge — keep funding as a FACT, do NOT promote to a vote.")


if __name__ == "__main__":
    main()
