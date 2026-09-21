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

from src.indicators.features import (
    COL_ADX,
    COL_ATR,
    COL_MACD,
    COL_MACD_HIST,
    COL_MACD_SIGNAL,
    COL_RSI,
    COL_SMA_LONG,
    COL_SMA_SLOW,
    COL_VOLUME_MA,
)
from src.market.regime import classify_regime
from src.patterns.chart_patterns import find_patterns
from src.service.analyze import AnalysisResult
from src.structure.divergence import find_rsi_divergence
from src.structure.support_resistance import RESISTANCE, SUPPORT, annotate_roles
from src.structure.swings import SWING_HIGH, SWING_LOW


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


def _serialize_patterns(result: AnalysisResult, df: pd.DataFrame, rp) -> list[dict]:
    """Chart patterns (Feature 2) as drawable JSON. Same keys the chart already reads
    (type/direction/state/points/breakout_level/invalidation_level/target) PLUS quality and the
    confirmation profile — state now comes from the real look-ahead-safe machine, not a heuristic.
    Recomputed from the SAME featured/swings/cfg the facts used, so drawn == quoted."""
    n = len(df)
    conf = result.facts.get("confluence", {})
    mtf_trends = conf.get("mtf_trends") or {}
    htf = list(mtf_trends.values())[-1] if mtf_trends else None
    levels = (result.levels["price"].tolist()
              if result.levels is not None and not result.levels.empty else None)
    out: list[dict] = []
    for pat in find_patterns(result.featured, result.swings, result.cfg,
                             higher_tf_trend=htf, structure_levels=levels, fib=result.fib):
        points = [{"time": _epoch(df.index[bar]), "price": rp(price)}
                  for bar, price in pat.points if 0 <= bar < n]
        if len(points) < 2:
            continue
        # Actual boundary geometry (channel/triangle boundaries, neckline/rectangle edges) as
        # time/price polylines, so the chart draws the real shape, not just the swing zigzag.
        lines = [[{"time": _epoch(df.index[bar]), "price": rp(price)}
                  for bar, price in line if 0 <= bar < n]
                 for line in pat.lines]
        lines = [ln for ln in lines if len(ln) >= 2]
        out.append({
            "type": pat.type,
            "direction": pat.direction,
            "state": pat.state,
            "quality": pat.quality,
            "points": points,
            "lines": lines,
            "breakout_level": None if pat.breakout_level is None else rp(pat.breakout_level),
            "invalidation_level": None if pat.invalidation_level is None else rp(pat.invalidation_level),
            "target": None if pat.target is None else rp(pat.target),
            "confirmation": pat.confirmation.to_dict(),
        })
    return out


def _series(fw: pd.DataFrame, col: str, decimals: int) -> list[dict]:
    """A {time,value} series for a sub-pane, dropping warm-up NaNs; time is epoch seconds."""
    if col not in fw.columns:
        return []
    out = []
    for t, v in zip(fw.index, fw[col]):
        if pd.isna(v):
            continue
        out.append({"time": _epoch(t), "value": round(float(v), decimals)})
    return out


def _serialize_divergence(result: AnalysisResult, df: pd.DataFrame) -> dict | None:
    """The current RSI divergence (if any), with the two swing times it spans so the RSI pane can
    mark it. Same detector `build_facts` used."""
    div = find_rsi_divergence(result.featured, result.swings)
    if div is None:
        return None
    kind_col = SWING_HIGH if div.kind == "bearish" else SWING_LOW
    pts = result.swings[result.swings["kind"] == kind_col].sort_values("bar").tail(2)
    times = [_epoch(df.index[int(b)]) for b in pts["bar"] if 0 <= int(b) < len(df)]
    return {"kind": div.kind, "reason": div.reason, "times": times}


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

    # Feature 1 — pattern geometry (drawn on the main chart, styled by state) and the RSI
    # divergence span (marked on the RSI sub-pane).
    patterns = _serialize_patterns(result, df, rp)
    divergence = _serialize_divergence(result, df)

    # TEMP (Feature 6 eyeball): per-bar regime label over the window, for a colored strip under
    # the candles. Warm-up bars (no label yet) are dropped. Standalone — not wired into any vote.
    regime_full = classify_regime(result.featured, result.cfg)
    regime = [
        {"time": _epoch(t), "label": str(v)}
        for t, v in regime_full.loc[window.index].items()
        if v is not None and not pd.isna(v)
    ]

    # Feature 1 — synchronised sub-pane series (volume MA, RSI, MACD, ADX, ATR) over the window.
    fw = result.featured.loc[window.index]
    indicators = {
        "volume_ma": _series(fw, COL_VOLUME_MA, 2),
        "rsi": _series(fw, COL_RSI, 2),
        "adx": _series(fw, COL_ADX, 2),
        "atr": _series(fw, COL_ATR, prec),
        "macd": {
            "line": _series(fw, COL_MACD, prec + 2),
            "signal": _series(fw, COL_MACD_SIGNAL, prec + 2),
            "hist": _series(fw, COL_MACD_HIST, prec + 2),
        },
    }

    return {
        "candles": candles,
        "price_precision": prec,
        "min_move": 10 ** -prec,
        # `total_bars` is the FULL history length (candles are capped to `limit`), so a scrubbing
        # UI knows the highest bar it can seek to.
        "total_bars": result.total_bars,
        "indicators": indicators,
        # Moving averages drawn ON the price pane (50 + 200 by default).
        "mas": [
            {"key": "slow", "period": result.cfg.indicators.slow_ma, "values": _series(fw, COL_SMA_SLOW, prec)},
            {"key": "long", "period": result.cfg.indicators.long_ma, "values": _series(fw, COL_SMA_LONG, prec)},
        ],
        "overlays": {"swings": swings, "levels": levels, "fibonacci": fib, "marker": marker,
                     "patterns": patterns, "divergence": divergence, "regime": regime},
    }


def serialize_analysis(result: AnalysisResult, limit: int = 500) -> dict:
    """Full API payload: the JSON facts/explanation plus the chart data."""
    payload = result.to_payload()          # facts + explanation + verification (JSON-safe)
    payload["chart"] = serialize_chart(result, limit=limit)
    return payload
