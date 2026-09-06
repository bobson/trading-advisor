#!/usr/bin/env python3
"""Phase 6 check: run every detector on the cached candles, collect their votes, and print
whether the confluence engine flags a setup and why.

Usage (from repo root, venv active; run download_data.py first):
    python scripts/show_confluence.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.config import load_config  # noqa: E402
from src.data.cache import load_candles  # noqa: E402
from src.indicators.features import add_features  # noqa: E402
from src.signals.confluence import (  # noqa: E402
    NEUTRAL,
    evaluate_confluence,
    gather_signals,
)
from src.structure.swings import find_swings  # noqa: E402


def main() -> None:
    cfg = load_config()
    m = cfg.market
    sens = cfg.structure.swing_sensitivity
    min_agree = cfg.confluence.min_agreeing_signals

    df = load_candles(m.symbol, m.timeframe, m.exchange)
    featured = add_features(df, cfg)
    assert len(featured) == len(df), "featured frame desynced from candles"

    swings = find_swings(df, sens)
    signals = gather_signals(featured, swings, cfg)
    result = evaluate_confluence(signals, min_agree)

    last_close = float(df["close"].iloc[-1])
    print(f"{m.symbol} {m.timeframe} on {m.exchange} — confluence")
    print(f"Last close: {last_close:.2f}\n")

    print("Every vote:")
    for s in signals:
        print(f"  [{s.direction.upper():>7}] {s.name}: {s.reason}")

    print()
    if result.triggered:
        print(f"SETUP FLAGGED: {result.bias.upper()} "
              f"({result.agreeing} signals agree, need {min_agree})")
        print("Why:")
        for r in result.reasons:
            print(f"  - {r}")
    elif result.bias == NEUTRAL:
        print(f"No setup: votes are tied / neutral (need {min_agree} to agree).")
    else:
        print(f"No setup: {result.bias} leads with {result.agreeing} "
              f"but needs {min_agree} to flag.")


if __name__ == "__main__":
    main()
