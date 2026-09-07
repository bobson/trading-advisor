#!/usr/bin/env python3
"""Phase 14 — run the forward-return backtest on cached candles and print a report.

This is the validation instrument: it does NOT trade, it measures what price did in the next
N bars after each bar the confluence engine would have flagged a setup. Use it to see whether
the current signals show any forward-return difference before trusting or tuning them.

Usage (from repo root, venv active; run download_data.py first for the pair):
    python scripts/backtest.py
    python scripts/backtest.py --symbol ETH/USDT --timeframe 4h --horizon 12 --min-agreeing 3
    python scripts/backtest.py --step 4 --save
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.backtest.evaluate import evaluate  # noqa: E402
from src.config import PROJECT_ROOT, load_config  # noqa: E402
from src.data.registry import get_candles  # noqa: E402

OUTPUTS_DIR = PROJECT_ROOT / "outputs"


def main() -> None:
    cfg = load_config()
    p = argparse.ArgumentParser(description="Forward-return backtest of the confluence engine.")
    p.add_argument("--symbol", default=cfg.market.symbol)
    p.add_argument("--timeframe", default=cfg.market.timeframe)
    p.add_argument("--horizon", type=int, default=24, help="bars ahead to measure the return over")
    p.add_argument("--min-agreeing", type=int, default=None, help="override confluence.min_agreeing_signals")
    p.add_argument("--warmup", type=int, default=None, help="bars to skip before the first setup")
    p.add_argument("--step", type=int, default=1, help="scan every Nth bar (larger = faster, fewer/less-overlapping setups)")
    p.add_argument("--save", action="store_true", help="also write the report to outputs/")
    args = p.parse_args()

    # Request-scoped config so report labels + detectors match the chosen market.
    market = cfg.market.model_copy(update={"symbol": args.symbol, "timeframe": args.timeframe})
    rcfg = cfg.model_copy(update={"market": market})

    df = get_candles(args.symbol, args.timeframe, rcfg)
    report = evaluate(
        df,
        rcfg,
        horizon=args.horizon,
        warmup=args.warmup,
        min_agreeing=args.min_agreeing,
        step=args.step,
    )
    print(report.summary())

    if args.save:
        OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
        slug = args.symbol.replace("/", "-")
        out = OUTPUTS_DIR / f"backtest_{slug}_{args.timeframe}_h{args.horizon}.md"
        out.write_text("```\n" + report.summary() + "\n```\n")
        print(f"\nSaved: {out}")


if __name__ == "__main__":
    main()
