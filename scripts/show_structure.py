#!/usr/bin/env python3
"""Phase 4 check: detect structure (support/resistance, trendlines, trend) on the cached
candles, print it, and save an annotated chart to confirm it looks reasonable.

Usage (from repo root, venv active; run download_data.py first):
    python scripts/show_structure.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import mplfinance as mpf  # noqa: E402

from src.config import PROJECT_ROOT, load_config  # noqa: E402
from src.data.cache import load_candles  # noqa: E402
from src.indicators.features import add_features  # noqa: E402
from src.structure.support_resistance import (  # noqa: E402
    RESISTANCE,
    SUPPORT,
    annotate_roles,
    find_support_resistance,
)
from src.structure.swings import find_swings  # noqa: E402
from src.structure.trend import classify_trend  # noqa: E402
from src.structure.trendlines import find_trendlines  # noqa: E402

PLOT_BARS = 250
LEVELS_PER_SIDE = 3          # cap drawn levels so the chart stays readable
MIN_TRENDLINE_R2 = 0.5       # don't draw a near-random best-fit line
OUTPUTS_DIR = PROJECT_ROOT / "outputs"


def _top_levels(levels, role, last_close, n):
    side = annotate_roles(levels, last_close)
    side = side[side["role"] == role].copy()
    side["distance"] = (side["price"] - last_close).abs()
    # nearest first (so the drawn levels sit on the recent-window chart), strongest to
    # break ties — the far-away all-time-strong zones aren't useful on a 250-bar view
    return side.sort_values(["distance", "touches"], ascending=[True, False]).head(n)


def main() -> None:
    cfg = load_config()
    m = cfg.market
    sens = cfg.structure.swing_sensitivity
    tol = cfg.structure.sr_cluster_tolerance_pct

    df = load_candles(m.symbol, m.timeframe, m.exchange)
    featured = add_features(df, cfg)
    assert len(featured) == len(df), "featured frame desynced from candles"

    swings = find_swings(df, sens)
    levels = find_support_resistance(swings, tol)
    trend = classify_trend(featured, swings)
    lines = find_trendlines(swings)
    last_close = float(df["close"].iloc[-1])

    print(f"{m.symbol} {m.timeframe} on {m.exchange} — structure")
    print(f"TREND: {trend.label.upper()}")
    for r in trend.reasons:
        print(f"  - {r}")

    supports = _top_levels(levels, SUPPORT, last_close, LEVELS_PER_SIDE)
    resistances = _top_levels(levels, RESISTANCE, last_close, LEVELS_PER_SIDE)
    print(f"\nLast close: {last_close:.2f}")
    print(f"Nearest resistance levels:\n{resistances[['price', 'touches']].to_string(index=False)}")
    print(f"Nearest support levels:\n{supports[['price', 'touches']].to_string(index=False)}")

    # --- draw the most recent window ---
    marked = df.iloc[-PLOT_BARS:]
    first_bar, last_bar = len(df) - PLOT_BARS, len(df) - 1
    plot_df = marked.rename(columns=str.capitalize)

    hlines, hcolors = [], []
    for _, row in supports.iterrows():
        hlines.append(row["price"]); hcolors.append("green")
    for _, row in resistances.iterrows():
        hlines.append(row["price"]); hcolors.append("crimson")

    alines, acolors = [], []
    for line in lines.values():
        if line.r2 < MIN_TRENDLINE_R2:
            continue
        # Draw from the first anchor swing (clamped into the window) forward to now —
        # extending a short local fit backward across the whole window looks absurd.
        x0 = max(min(line.bars), first_bar)
        x1 = last_bar
        alines.append([(df.index[x0], line.value_at(x0)), (df.index[x1], line.value_at(x1))])
        acolors.append("green" if line.kind == SUPPORT else "crimson")

    plot_kwargs = dict(
        type="candle", style="charles", volume=False, figsize=(16, 8),
        title=f"{m.symbol} {m.timeframe} — {trend.label.upper()} (last {PLOT_BARS} bars)",
    )
    if hlines:
        plot_kwargs["hlines"] = dict(hlines=hlines, colors=hcolors, linestyle="--", linewidths=0.9)
    if alines:
        plot_kwargs["alines"] = dict(alines=alines, colors=acolors, linewidths=1.3)

    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUTS_DIR / f"structure_{m.symbol.replace('/', '-')}_{m.timeframe}.png"
    mpf.plot(plot_df, savefig=dict(fname=str(out_path), dpi=110, bbox_inches="tight"), **plot_kwargs)
    print(f"\nSaved annotated chart to {out_path}")


if __name__ == "__main__":
    main()
