#!/usr/bin/env python3
"""Phase 5 check: compute Fibonacci retracement for the latest leg, print it, and save an
annotated chart so you can confirm 0% sits on the last swing, 100% on the older anchor,
and 0.5 at the midpoint.

Usage (from repo root, venv active; run download_data.py first):
    python scripts/show_fibonacci.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import mplfinance as mpf  # noqa: E402

from src.config import PROJECT_ROOT, load_config  # noqa: E402
from src.data.cache import load_candles  # noqa: E402
from src.structure.fibonacci import fib_retracement  # noqa: E402
from src.structure.swings import find_swings  # noqa: E402

PLOT_BARS = 250
OUTPUTS_DIR = PROJECT_ROOT / "outputs"


def main() -> None:
    cfg = load_config()
    m = cfg.market
    sens = cfg.structure.swing_sensitivity

    df = load_candles(m.symbol, m.timeframe, m.exchange)
    swings = find_swings(df, sens)
    fib = fib_retracement(swings)
    if fib is None:
        print("No valid leg found for Fibonacci retracement.")
        return

    print(f"{m.symbol} {m.timeframe} on {m.exchange} — Fibonacci retracement")
    print(f"Leg: {fib.direction.upper()}  "
          f"high bar {fib.high_bar} @ {fib.high_price:.2f}  |  "
          f"low bar {fib.low_bar} @ {fib.low_price:.2f}")
    for r in sorted(fib.levels):
        print(f"  {r:>5.3f}  ->  {fib.levels[r]:.2f}")

    # --- draw the recent window ---
    marked = df.iloc[-PLOT_BARS:]
    first_bar, last_bar = len(df) - PLOT_BARS, len(df) - 1
    plot_df = marked.rename(columns=str.capitalize)

    # Each level: horizontal segment from the leg start (clamped into the window) to now.
    x0 = max(fib.start_bar, first_bar)
    alines = [
        [(df.index[x0], price), (df.index[last_bar], price)]
        for price in fib.levels.values()
    ]

    # Mark both anchors so the band's endpoints are checkable by eye.
    high_marks = marked["high"].where(marked.index == df.index[fib.high_bar]) * 1.003 \
        if fib.high_bar >= first_bar else marked["high"] * float("nan")
    low_marks = marked["low"].where(marked.index == df.index[fib.low_bar]) * 0.997 \
        if fib.low_bar >= first_bar else marked["low"] * float("nan")
    aps = []
    if high_marks.notna().any():
        aps.append(mpf.make_addplot(high_marks, type="scatter", marker="v", markersize=90, color="crimson"))
    if low_marks.notna().any():
        aps.append(mpf.make_addplot(low_marks, type="scatter", marker="^", markersize=90, color="green"))

    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUTS_DIR / f"fibonacci_{m.symbol.replace('/', '-')}_{m.timeframe}.png"
    mpf.plot(
        plot_df,
        type="candle",
        style="charles",
        addplot=aps or None,
        alines=dict(alines=alines, colors=["#1f77b4"] * len(alines), linestyle="--", linewidths=0.9),
        volume=False,
        figsize=(16, 8),
        title=f"{m.symbol} {m.timeframe} — Fib retracement ({fib.direction} leg)",
        savefig=dict(fname=str(out_path), dpi=110, bbox_inches="tight"),
    )
    print(f"\nSaved annotated chart to {out_path}")


if __name__ == "__main__":
    main()
