#!/usr/bin/env python3
"""Phase 9 check: detect named chart patterns on the cached candles and print them.

Chart patterns are best-effort geometry on swings — expect misses and the occasional
over-call on messy, real data. This script is mainly to confirm the detectors run cleanly
on real (non-textbook) swings without crashing or spewing false positives.

Usage (from repo root, venv active; run download_data.py first):
    python scripts/show_patterns.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.config import load_config  # noqa: E402
from src.data.cache import load_candles  # noqa: E402
from src.patterns.chart_patterns import find_chart_patterns  # noqa: E402
from src.structure.swings import find_swings  # noqa: E402


def main() -> None:
    cfg = load_config()
    m = cfg.market

    df = load_candles(m.symbol, m.timeframe, m.exchange)
    swings = find_swings(df, cfg.structure.swing_sensitivity)
    patterns = find_chart_patterns(swings, cfg)

    print(f"{m.symbol} {m.timeframe} on {m.exchange} — chart patterns "
          f"(last {len(swings)} swings, scanning recent tail)")
    if not patterns:
        print("\nNo named chart patterns detected in the recent structure.")
        return

    for p in patterns:
        print(f"\n[{p.direction.upper()}] {p.name.title()}  (bars {p.bars})")
        print(f"  {p.reason}")
        if p.neckline is not None:
            print(f"  neckline {p.neckline}  |  measured target {p.target}")


if __name__ == "__main__":
    main()
