#!/usr/bin/env python3
"""Recommendation #1 — out-of-sample backtest across several coins and time halves.

Answers "does the ~51% hold up, or was it one lucky window?" For each symbol it fetches candles
(cache-first; live-fetches uncached ones) and prints the win-rate for the full history and each
half. If the halves disagree a lot, the edge is noise.

    python scripts/backtest_suite.py
    python scripts/backtest_suite.py --symbols BTC/USDT,ETH/USDT --timeframe 4h --step 6
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.backtest.suite import evaluate_periods, format_periods  # noqa: E402
from src.config import load_config  # noqa: E402
from src.research import prereg  # noqa: E402
from src.data.registry import get_candles  # noqa: E402


def main() -> None:
    cfg = load_config()
    p = argparse.ArgumentParser(description="Out-of-sample backtest across coins + time halves.")
    p.add_argument("--symbols", default="BTC/USDT,ETH/USDT,SOL/USDT,XRP/USDT")
    p.add_argument("--timeframe", default=cfg.market.timeframe)
    p.add_argument("--horizon", type=int, default=24)
    p.add_argument("--step", type=int, default=6, help="sample every Nth bar (larger = faster)")
    prereg.add_args(p)
    args = p.parse_args()
    conn, exp = prereg.gate(args, "backtest_suite", prereg.run_params(args))   # D2: registered first
    pooled = {"full": [0, 0], "2nd half": [0, 0]}                              # wins, n across symbols

    symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]
    print(f"Out-of-sample backtest — {args.timeframe}, horizon {args.horizon}, step {args.step}\n")
    for symbol in symbols:
        try:
            df = get_candles(symbol, args.timeframe, cfg)
        except Exception as exc:
            print(f"{symbol}: fetch failed — {exc}\n")
            continue
        periods = evaluate_periods(df, cfg, horizon=args.horizon, step=args.step)
        print(format_periods(symbol, periods))
        print()
        for name in pooled:
            rep = periods.get(name)
            if rep is not None and rep.overall.n:
                pooled[name][0] += round(rep.overall.win_rate * rep.overall.n)
                pooled[name][1] += rep.overall.n
    rate = lambda w, n: (w / n if n else None, n)  # noqa: E731
    prereg.finish(conn, exp, {"win_rate": rate(*pooled["full"]), "second_half_win_rate": rate(*pooled["2nd half"])})


if __name__ == "__main__":
    main()
