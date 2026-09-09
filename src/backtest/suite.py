"""Recommendation #1 — out-of-sample backtesting: is the ~51% real, or one lucky window?

`evaluate_periods` runs the forward-return backtest on the FULL history plus its first and
second halves — a simple in-sample / out-of-sample split. If the win-rate holds across both
halves (and, via the CLI, across several coins), the read is at least consistent; if it swings
wildly between halves, the "edge" is noise. This adds no new engine logic — it just replays the
existing look-ahead-safe `evaluate` over different windows.
"""

from __future__ import annotations

import pandas as pd

from src.backtest.evaluate import BacktestReport, evaluate


def evaluate_periods(
    df: pd.DataFrame,
    cfg,
    *,
    horizon: int = 24,
    step: int = 1,
    require_categories: int | None = None,
) -> dict[str, BacktestReport | None]:
    """Backtest the full frame + each half. A window too short for warmup+horizon maps to None."""
    half = len(df) // 2
    windows = {"full": df, "1st half": df.iloc[:half], "2nd half": df.iloc[half:]}
    out: dict[str, BacktestReport | None] = {}
    for name, window in windows.items():
        try:
            out[name] = evaluate(window, cfg, horizon=horizon, step=step, require_categories=require_categories)
        except ValueError:
            out[name] = None  # not enough history in this window
    return out


def format_periods(symbol: str, periods: dict[str, BacktestReport | None]) -> str:
    """One block per symbol: win-rate for full / 1st half / 2nd half, side by side."""
    lines = [f"{symbol}:"]
    for name, rep in periods.items():
        if rep is None or rep.overall.n == 0:
            lines.append(f"  {name:9} — no setups / too little history")
            continue
        s = rep.overall
        lines.append(
            f"  {name:9} n={s.n:<4} win-rate={s.win_rate * 100:5.1f}%  avg={s.avg_return * 100:+.2f}%"
        )
    return "\n".join(lines)
