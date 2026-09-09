#!/usr/bin/env python3
"""Recommendation #2 — precompute the historical base rates into data/base_rates.json.

Run this offline (it's the slow backtest); the live API/UI then just looks the numbers up.
Re-run it periodically to keep the track record current.

    python scripts/compute_base_rates.py
    python scripts/compute_base_rates.py --symbols BTC/USDT,ETH/USDT --timeframe 1h --step 3
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.backtest.base_rate import BASE_RATES_PATH, compute_base_rate  # noqa: E402
from src.config import load_config  # noqa: E402
from src.data.base import CRYPTO  # noqa: E402
from src.data.registry import get_candles, list_pairs  # noqa: E402


def main() -> None:
    cfg = load_config()
    p = argparse.ArgumentParser(description="Precompute historical base rates.")
    default_syms = ",".join(pair.symbol for pair in list_pairs(CRYPTO))  # crypto works keyless
    p.add_argument("--symbols", default=default_syms)
    p.add_argument("--timeframe", default=cfg.market.timeframe)
    p.add_argument("--horizon", type=int, default=24)
    p.add_argument("--step", type=int, default=3)
    args = p.parse_args()

    rates: dict = {}
    if BASE_RATES_PATH.exists():
        rates = json.loads(BASE_RATES_PATH.read_text())  # keep entries for other pairs

    for symbol in [s.strip() for s in args.symbols.split(",") if s.strip()]:
        try:
            df = get_candles(symbol, args.timeframe, cfg)
            entry = compute_base_rate(df, cfg, horizon=args.horizon, step=args.step)
        except Exception as exc:
            print(f"{symbol}: skipped — {exc}")
            continue
        rates[f"{symbol}|{args.timeframe}"] = entry
        o = entry["overall"]
        print(f"{symbol}|{args.timeframe}: overall {o['win_rate']} (n={o['n']})")

    BASE_RATES_PATH.parent.mkdir(parents=True, exist_ok=True)
    BASE_RATES_PATH.write_text(json.dumps(rates, indent=2, sort_keys=True))
    print(f"\nSaved {BASE_RATES_PATH}")


if __name__ == "__main__":
    main()
