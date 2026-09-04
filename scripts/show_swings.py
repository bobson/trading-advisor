#!/usr/bin/env python3
"""Phase 3 check: detect swings on the cached candles, print a sanity summary, and save
an annotated chart so you can confirm the markers land on the highs/lows your eye picks.

Usage (from repo root, venv active; run download_data.py first):
    python scripts/show_swings.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import mplfinance as mpf  # noqa: E402

from src.config import PROJECT_ROOT, load_config  # noqa: E402
from src.data.cache import load_candles  # noqa: E402
from src.structure.swings import SWING_HIGH, SWING_LOW, add_swing_columns, find_swings  # noqa: E402

PLOT_BARS = 250

OUTPUTS_DIR = PROJECT_ROOT / "outputs"


def main() -> None:
    cfg = load_config()
    m = cfg.market
    sens = cfg.structure.swing_sensitivity

    df = load_candles(m.symbol, m.timeframe, m.exchange)
    swings = find_swings(df, sens)
    n_high = int((swings["kind"] == SWING_HIGH).sum())
    n_low = int((swings["kind"] == SWING_LOW).sum())

    print(f"{m.symbol} {m.timeframe} on {m.exchange} — swing detection (sensitivity={sens})")
    print(f"{len(df)} candles -> {len(swings)} swings ({n_high} highs, {n_low} lows)")
    print("Sanity: at sensitivity=5 on ~4320 bars expect a few hundred, roughly alternating.")
    print("\nLast 8 swings:")
    print(swings.tail(8).to_string())

    # Detect on full history, plot only the most recent window.
    marked = add_swing_columns(df, sens).iloc[-PLOT_BARS:]
    high_marks = marked["high"].where(marked["swing_high"]) * 1.003
    low_marks = marked["low"].where(marked["swing_low"]) * 0.997

    plot_df = marked.rename(columns=str.capitalize)  # mplfinance wants Open/High/Low/Close
    aps = []
    if high_marks.notna().any():
        aps.append(mpf.make_addplot(high_marks, type="scatter", marker="v", markersize=45, color="crimson"))
    if low_marks.notna().any():
        aps.append(mpf.make_addplot(low_marks, type="scatter", marker="^", markersize=45, color="green"))

    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUTS_DIR / f"swings_{m.symbol.replace('/', '-')}_{m.timeframe}.png"
    mpf.plot(
        plot_df,
        type="candle",
        style="charles",
        addplot=aps,
        volume=False,
        figsize=(16, 8),
        title=f"{m.symbol} {m.timeframe} — swings (sensitivity={sens}), last {PLOT_BARS} bars",
        savefig=dict(fname=str(out_path), dpi=110, bbox_inches="tight"),
    )
    print(f"\nSaved annotated chart to {out_path}")


if __name__ == "__main__":
    main()
