#!/usr/bin/env python3
"""ML Phase C — walk-forward evaluation: does a model beat a coin flip out-of-sample?

    python scripts/ml_eval.py                          # BTC/USDT 1h
    python scripts/ml_eval.py --symbol ETH/USDT --horizon 12 --folds 5

Reports pooled out-of-sample accuracy, AUC, and calibration vs the majority-class baseline.
An HONEST result is likely "no edge" (AUC ~0.5) — that's a valid, useful finding.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.config import load_config  # noqa: E402
from src.data.registry import get_candles  # noqa: E402
from src.ml.walkforward import walk_forward_eval  # noqa: E402


def main() -> None:
    cfg = load_config()
    p = argparse.ArgumentParser(description="Walk-forward ML evaluation (out-of-sample).")
    p.add_argument("--symbol", default="BTC/USDT")
    p.add_argument("--timeframe", default="1h")
    p.add_argument("--horizon", type=int, default=24)
    p.add_argument("--atr-mult", type=float, default=1.0)
    p.add_argument("--folds", type=int, default=5)
    args = p.parse_args()

    df = get_candles(args.symbol, args.timeframe, cfg)
    r = walk_forward_eval(df, cfg, horizon=args.horizon, atr_mult=args.atr_mult, n_folds=args.folds)

    print(f"Walk-forward ML — {args.symbol} {args.timeframe}, horizon {args.horizon}, "
          f"{args.folds} folds, {r['features']} features")
    print(f"  out-of-sample samples : {r['n_oos']}  (up rate {r['up_rate'] * 100:.1f}%)")
    print(f"  baseline accuracy     : {r['baseline_acc'] * 100:.1f}%  (always predict majority)")
    print(f"  MODEL accuracy        : {r['model_acc'] * 100:.1f}%")
    print(f"  AUC                   : {r['auc']}   (0.5 = coin flip)")
    print("  calibration (predicted -> actual win rate):")
    for c in r["calibration"]:
        print(f"    prob {c['bin']}: predicted {c['predicted']} vs actual {c['actual']}  (n={c['n']})")

    beats = r["auc"] is not None and r["auc"] >= 0.55 and r["model_acc"] > r["baseline_acc"] + 0.01
    print("\n  => model beats the baseline out-of-sample — worth pursuing (validate costs/multi-coin next)."
          if beats else
          "\n  => no meaningful edge over a coin flip (AUC ~0.5). Honest result — the features don't predict this.")


if __name__ == "__main__":
    main()
