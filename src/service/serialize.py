"""Phase 24 — the serialize seam: turn an AnalysisResult into JSON the web chart can draw.

This mirrors what `viz/chart.py` renders, but as data instead of a PNG — candles plus the
overlays (support/resistance lines, Fibonacci band, swing markers, and the confluence marker).
The consistency guarantee is by construction: `serialize_chart` reads the SAME detector objects
(`result.swings`, `result.levels`, `result.fib`, `result.facts`) that `build_facts` used, so the
drawn chart and the quoted numbers can't disagree.

`time` is a UNIX timestamp in seconds (what TradingView's lightweight-charts expects for
intraday). Candles are capped to the last `limit` bars for a usable view; overlays are mapped
onto that window. Trendline SEGMENTS are intentionally deferred to Phase 25 (they need
chart.py's anchor-bar logic); levels/fib/markers cover the high-value overlays.
"""

from __future__ import annotations

import pandas as pd

from src.service.analyze import AnalysisResult
from src.structure.support_resistance import annotate_roles
from src.structure.swings import SWING_HIGH


def _epoch(ts) -> int:
    return int(pd.Timestamp(ts).timestamp())


def serialize_chart(result: AnalysisResult, limit: int = 500) -> dict:
    """Candles + overlays for the given result, as lightweight-charts-ready JSON."""
    df = result.df
    window = df.iloc[-limit:]
    start_ts = _epoch(window.index[0])
    last_close = float(df["close"].iloc[-1])

    candles = [
        {
            "time": _epoch(idx),
            "open": round(float(row["open"]), 2),
            "high": round(float(row["high"]), 2),
            "low": round(float(row["low"]), 2),
            "close": round(float(row["close"]), 2),
            "volume": (None if "volume" not in window.columns or pd.isna(row["volume"])
                       else round(float(row["volume"]), 2)),
        }
        for idx, row in window.iterrows()
    ]

    # Swing markers within the window (bar index -> timestamp on the full frame).
    swings = []
    for _, s in result.swings.iterrows():
        bar = int(s["bar"])
        if 0 <= bar < len(df):
            t = _epoch(df.index[bar])
            if t >= start_ts:
                swings.append({
                    "time": t,
                    "price": round(float(s["price"]), 2),
                    "kind": "high" if s["kind"] == SWING_HIGH else "low",
                })

    # Support/resistance as horizontal price lines (role relative to the current price).
    levels = []
    if not result.levels.empty:
        roled = annotate_roles(result.levels, last_close)
        for _, lv in roled.iterrows():
            levels.append({
                "price": round(float(lv["price"]), 2),
                "role": str(lv["role"]),
                "touches": int(lv["touches"]),
            })

    fib = None
    if result.fib is not None:
        fib = {
            "direction": result.fib.direction,
            "levels": {str(r): round(float(p), 2) for r, p in result.fib.levels.items()},
        }

    # The confluence marker reflects CURRENT state only (last bar), colored by bias, only when
    # a setup is flagged — mirrors chart.py (not a rolling backtest).
    conf = result.facts["confluence"]
    marker = None
    if conf["triggered"]:
        marker = {"time": _epoch(df.index[-1]), "bias": conf["bias"]}

    return {
        "candles": candles,
        "overlays": {"swings": swings, "levels": levels, "fibonacci": fib, "marker": marker},
    }


def serialize_analysis(result: AnalysisResult, limit: int = 500) -> dict:
    """Full API payload: the JSON facts/explanation plus the chart data."""
    payload = result.to_payload()          # facts + explanation + verification (JSON-safe)
    payload["chart"] = serialize_chart(result, limit=limit)
    return payload
