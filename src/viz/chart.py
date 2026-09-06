"""Phase 8 — render the annotated chart: candles + S/R + trendlines + Fib + a confluence marker.

`render_chart` is a *pure renderer*: it draws already-computed detector objects and never
recomputes anything. Callers compute `swings` once and derive `levels`/`trendlines`/`fib`
from it with the config's params, so what's drawn here is byte-identical to what the facts
layer described — the nearest-support line on the chart is the same number the explanation
quotes.

This module is the DISPLAY layer, so per the Phase 4 convention it owns *selection*: the
detectors return all levels, and we cap to the nearest few per side here (a 250-bar view
can't show every all-time zone). It mirrors the drawing conventions already validated by eye
in the show_* scripts — anchor-forward trendlines behind an r² gate (show_structure) and the
fib band clamped to `start_bar` (show_fibonacci) — rather than inventing new geometry.

The confluence marker reflects *current* state only: the engine votes on the latest bar
(`.iloc[-1]`), there is no per-bar history, so we mark the last candle — colored by bias —
only when a setup actually fired. No rolling backtest.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib
matplotlib.use("Agg")  # headless: save PNGs without a display server

import mplfinance as mpf
import pandas as pd

from src.config import Config
from src.signals.confluence import BEARISH, BULLISH
from src.structure.fibonacci import FibRetracement
from src.structure.support_resistance import (
    RESISTANCE,
    SUPPORT,
    annotate_roles,
)
from src.structure.trendlines import Trendline

# Display-layer knobs (selection/quality gates live here, not in the detectors).
DEFAULT_PLOT_BARS = 250
LEVELS_PER_SIDE = 3
MIN_TRENDLINE_R2 = 0.5

_SUPPORT_COLOR = "green"
_RESISTANCE_COLOR = "crimson"
_FIB_COLOR = "#1f77b4"


def _top_levels(levels: pd.DataFrame, role: str, last_close: float, n: int) -> pd.DataFrame:
    """Nearest `n` levels of a role to the current price (strongest breaks ties)."""
    side = annotate_roles(levels, last_close)
    side = side[side["role"] == role].copy()
    if side.empty:
        return side
    side["distance"] = (side["price"] - last_close).abs()
    return side.sort_values(["distance", "touches"], ascending=[True, False]).head(n)


def render_chart(
    df: pd.DataFrame,
    swings: pd.DataFrame,
    levels: pd.DataFrame,
    trendlines: dict[str, Trendline],
    fib: FibRetracement | None,
    *,
    bias: str,
    triggered: bool,
    cfg: Config,
    out_path: Path,
    plot_bars: int = DEFAULT_PLOT_BARS,
) -> Path:
    """Draw the annotated chart for the most recent `plot_bars` candles and save it to `out_path`.

    `levels`, `trendlines`, `fib` must have been derived from the same `swings` (with config
    params) so they agree with the computed facts. `bias`/`triggered` come from the confluence
    verdict; a marker is drawn on the last candle only when `triggered`.
    """
    m = cfg.market
    n = min(plot_bars, len(df))
    marked = df.iloc[-n:]
    first_bar, last_bar = len(df) - n, len(df) - 1
    plot_df = marked.rename(columns=str.capitalize)
    last_close = float(df["close"].iloc[-1])

    # --- horizontal support/resistance (nearest few per side) ---
    hlines, hcolors = [], []
    for _, row in _top_levels(levels, SUPPORT, last_close, LEVELS_PER_SIDE).iterrows():
        hlines.append(row["price"]); hcolors.append(_SUPPORT_COLOR)
    for _, row in _top_levels(levels, RESISTANCE, last_close, LEVELS_PER_SIDE).iterrows():
        hlines.append(row["price"]); hcolors.append(_RESISTANCE_COLOR)

    # --- sloped trendlines (r²-gated, drawn from the first anchor forward) ---
    alines, acolors = [], []
    for line in trendlines.values():
        if line.r2 < MIN_TRENDLINE_R2:
            continue
        x0 = max(min(line.bars), first_bar)
        alines.append([(df.index[x0], line.value_at(x0)), (df.index[last_bar], line.value_at(last_bar))])
        acolors.append(_SUPPORT_COLOR if line.kind == SUPPORT else _RESISTANCE_COLOR)

    # --- Fibonacci band (dashed, from the leg start clamped into the window) ---
    if fib is not None:
        x0 = max(fib.start_bar, first_bar)
        for price in fib.levels.values():
            alines.append([(df.index[x0], price), (df.index[last_bar], price)])
            acolors.append(_FIB_COLOR)

    # --- confluence marker on the latest bar, only when a setup fired ---
    aps = []
    if triggered and bias in (BULLISH, BEARISH):
        series = pd.Series(float("nan"), index=marked.index)
        if bias == BULLISH:
            series.iloc[-1] = float(marked["low"].iloc[-1]) * 0.99
            marker, color = "^", _SUPPORT_COLOR
        else:
            series.iloc[-1] = float(marked["high"].iloc[-1]) * 1.01
            marker, color = "v", _RESISTANCE_COLOR
        aps.append(mpf.make_addplot(series, type="scatter", marker=marker, markersize=200, color=color))

    setup = f"{bias.upper()} setup" if triggered else "no setup"
    plot_kwargs = dict(
        type="candle",
        style="charles",
        volume=False,
        figsize=(16, 8),
        title=f"{m.symbol} {m.timeframe} — {setup} (last {n} bars)",
    )
    if aps:
        plot_kwargs["addplot"] = aps
    if hlines:
        plot_kwargs["hlines"] = dict(hlines=hlines, colors=hcolors, linestyle="--", linewidths=0.9)
    if alines:
        plot_kwargs["alines"] = dict(alines=alines, colors=acolors, linewidths=1.2)

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    mpf.plot(plot_df, savefig=dict(fname=str(out_path), dpi=110, bbox_inches="tight"), **plot_kwargs)
    return out_path
