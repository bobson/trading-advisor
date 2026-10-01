#!/usr/bin/env python
"""Feature 8 — run the exit-rule laboratory on cached candles and print the table + verdict.

Holds the entry fixed and sweeps the eight exits; holds the exit fixed and sweeps the entries;
tells you which choice moves outcomes more on your data. Net of Feature-10 costs.

    python scripts/exit_lab.py                 # uses config.yaml market
    python scripts/exit_lab.py ETH/USDT 1d     # a specific pair/timeframe
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.backtest.exits import run_exit_lab  # noqa: E402
from src.config import load_config  # noqa: E402
from src.data.cache import load_candles  # noqa: E402


def main() -> None:
    import argparse

    from src.research import prereg
    cfg = load_config()
    p = argparse.ArgumentParser(description="Exit-rule laboratory (Feature 8).")
    p.add_argument("symbol", nargs="?", default=cfg.market.symbol)
    p.add_argument("timeframe", nargs="?", default=cfg.market.timeframe)
    prereg.add_args(p)
    args = p.parse_args()
    conn, exp = prereg.gate(args, "exit_lab", prereg.run_params(args))   # D2: registered first
    symbol, timeframe = args.symbol, args.timeframe
    cfg = cfg.model_copy(update={"market": cfg.market.model_copy(
        update={"symbol": symbol, "timeframe": timeframe})})
    df = load_candles(symbol, timeframe, cfg.market.exchange)
    rep = run_exit_lab(df, cfg)
    print(rep.summary())
    means = [s.mean_return for s in rep.exits.values() if s.n]
    prereg.finish(conn, exp, {"spread_across_exits": (rep.spread_across_exits, None),
                              "spread_across_entries": (rep.spread_across_entries, None),
                              "best_exit_mean_return": (max(means) if means else None, None)})


if __name__ == "__main__":
    main()
