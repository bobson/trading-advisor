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
from src.structure.support_resistance import RESISTANCE, SUPPORT, annotate_roles
from src.structure.swings import SWING_HIGH


def _epoch(ts) -> int:
    return int(pd.Timestamp(ts).timestamp())


def _price_precision(price: float) -> int:
    """Decimals appropriate for the price magnitude — so an FX pair (~1.1030) keeps its
    precision instead of being flattened to 1.10, while BTC (~80000) stays at 2."""
    p = abs(price)
    if p >= 100:
        return 2
    if p >= 1:
        return 5
    return 6


def serialize_chart(result: AnalysisResult, limit: int = 500, levels_per_side: int = 3) -> dict:
    """Candles + overlays for the given result, as lightweight-charts-ready JSON."""
    df = result.df
    window = df.iloc[-limit:]
    start_ts = _epoch(window.index[0])
    last_close = float(df["close"].iloc[-1])
    prec = _price_precision(last_close)

    def rp(x) -> float:
        return round(float(x), prec)

    candles = [
        {
            "time": _epoch(idx),
            "open": rp(row["open"]),
            "high": rp(row["high"]),
            "low": rp(row["low"]),
            "close": rp(row["close"]),
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
                swings.append({"time": t, "price": rp(s["price"]),
                               "kind": "high" if s["kind"] == SWING_HIGH else "low"})

    # Support/resistance as horizontal price lines — only the NEAREST few per side, so the
    # chart isn't buried under every detected level (mirrors the PNG chart's selection).
    levels = []
    if not result.levels.empty:
        roled = annotate_roles(result.levels, last_close)
        roled = roled.assign(_dist=(roled["price"] - last_close).abs())
        for role in (SUPPORT, RESISTANCE):
            side = roled[roled["role"] == role].sort_values("_dist").head(levels_per_side)
            for _, lv in side.iterrows():
                levels.append({"price": rp(lv["price"]), "role": str(lv["role"]), "touches": int(lv["touches"])})

    fib = None
    if result.fib is not None:
        fib = {"direction": result.fib.direction,
               "levels": {str(r): rp(p) for r, p in result.fib.levels.items()}}

    # The confluence marker reflects CURRENT state only (last bar), colored by bias, only when
    # a setup is flagged — mirrors chart.py (not a rolling backtest).
    conf = result.facts["confluence"]
    marker = {"time": _epoch(df.index[-1]), "bias": conf["bias"]} if conf["triggered"] else None

    return {
        "candles": candles,
        "price_precision": prec,
        "min_move": 10 ** -prec,
        "overlays": {"swings": swings, "levels": levels, "fibonacci": fib, "marker": marker},
    }


def serialize_analysis(result: AnalysisResult, limit: int = 500) -> dict:
    """Full API payload: the JSON facts/explanation plus the chart data."""
    payload = result.to_payload()          # facts + explanation + verification (JSON-safe)
    payload["chart"] = serialize_chart(result, limit=limit)
    return payload
