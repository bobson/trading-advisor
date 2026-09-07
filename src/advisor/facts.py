"""Phase 7 — assemble every Layer 1 fact into one structured summary for the reasoning layer.

This is the seam between the two layers. Everything the deterministic tier computed —
trend, momentum, support/resistance, Fibonacci, candlestick patterns, and the confluence
verdict — is gathered here into a plain dict, then rendered to readable text for Claude.
The model reasons over *these facts*, never over raw candles or pixels.

**Consistency is the whole point.** The confluence engine (Phase 6) votes on trend, S/R,
and Fibonacci; this module also *displays* trend, S/R, and Fibonacci. If the two computed
those independently they could disagree by luck of differing parameters. So we compute each
detector exactly once here, with the config's sensitivity/tolerance/proximity, and feed the
*same objects* into both the confluence evaluation and the facts dict. Same inputs → the
displayed trend and the trend vote provably can't contradict each other. That's what lets
Layer 2's instruction "never contradict Layer 1" actually hold.
"""

from __future__ import annotations

import pandas as pd

from src.config import Config
from src.indicators.features import (
    COL_ADX,
    COL_ATR,
    COL_BB_LOWER,
    COL_BB_PCT,
    COL_BB_UPPER,
    COL_MACD,
    COL_MACD_SIGNAL,
    COL_OBV,
    COL_RSI,
    COL_STOCH_D,
    COL_STOCH_K,
    COL_VOLUME,
    COL_VOLUME_MA,
)
from src.patterns.chart_patterns import find_chart_patterns
from src.signals.confluence import (
    evaluate_confluence,
    signal_from_fibonacci,
    signal_from_macd,
    signal_from_patterns,
    signal_from_rsi,
    signal_from_support_resistance,
    signal_from_trend,
    signal_from_volume,
)
from src.structure.divergence import find_rsi_divergence
from src.structure.fibonacci import fib_retracement
from src.structure.mtf import resolve_mtf
from src.structure.round_numbers import nearest_round_number
from src.structure.support_resistance import (
    RESISTANCE,
    SUPPORT,
    annotate_roles,
    find_support_resistance,
)
from src.structure.trend import classify_trend

# Fib ratios worth showing the model (the endpoints 0.0/1.0 are just the leg extremes).
_DISPLAY_FIB_RATIOS = [0.382, 0.5, 0.618, 0.786]


def _num(value, digits: int = 2):
    """Round to a plain Python float, or None if NaN — keeps the facts dict JSON-serializable."""
    if value is None or pd.isna(value):
        return None
    return round(float(value), digits)


def _last(df: pd.DataFrame, col: str):
    """Last value of a column, or NaN if the column is absent — so build_facts tolerates a
    frame that doesn't carry every toolkit column (e.g. a hand-built test fixture)."""
    return df[col].iloc[-1] if col in df.columns else float("nan")


def _bollinger_position(featured_df: pd.DataFrame) -> str | None:
    """Where the last close sits relative to the Bollinger envelope."""
    if COL_BB_UPPER not in featured_df.columns or COL_BB_LOWER not in featured_df.columns:
        return None
    close = featured_df["close"].iloc[-1]
    upper = featured_df[COL_BB_UPPER].iloc[-1]
    lower = featured_df[COL_BB_LOWER].iloc[-1]
    if pd.isna(upper) or pd.isna(lower):
        return None
    if close >= upper:
        return "above upper band"
    if close <= lower:
        return "below lower band"
    return "inside bands"


def _obv_rising(featured_df: pd.DataFrame, lookback: int = 5) -> bool | None:
    """Whether OBV is higher than `lookback` bars ago (volume-momentum direction)."""
    if COL_OBV not in featured_df.columns or len(featured_df) <= lookback:
        return None
    obv = featured_df[COL_OBV]
    now, prev = obv.iloc[-1], obv.iloc[-1 - lookback]
    if pd.isna(now) or pd.isna(prev):
        return None
    return bool(now > prev)


def _rsi_zone(rsi: float | None, cfg: Config) -> str:
    if rsi is None:
        return "unknown"
    ind = cfg.indicators
    if rsi <= ind.rsi_oversold:
        return "oversold"
    if rsi >= ind.rsi_overbought:
        return "overbought"
    return "neutral"


def _nearest_levels(levels: pd.DataFrame, last_close: float) -> dict:
    """Nearest support (below price) and resistance (above price), by distance."""
    out: dict[str, dict | None] = {"nearest_support": None, "nearest_resistance": None}
    if levels.empty:
        return out
    roled = annotate_roles(levels, last_close)
    for role, key in ((SUPPORT, "nearest_support"), (RESISTANCE, "nearest_resistance")):
        side = roled[roled["role"] == role].copy()
        if side.empty:
            continue
        side["distance"] = (side["price"] - last_close).abs()
        row = side.sort_values("distance").iloc[0]
        out[key] = {"price": round(float(row["price"]), 2), "touches": int(row["touches"])}
    return out


def build_facts(featured_df: pd.DataFrame, swings: pd.DataFrame, cfg: Config) -> dict:
    """Gather all Layer 1 facts into one structured dict.

    `featured_df` must be the frame the swings were derived from (row-aligned), so the
    trend detector's SMA lookup lines up with the swing bars.
    """
    m = cfg.market
    tol = cfg.structure.sr_cluster_tolerance_pct
    prox = cfg.confluence.proximity_pct

    last_close = float(featured_df["close"].iloc[-1])
    last_time = str(featured_df.index[-1])

    # --- detectors: compute ONCE, share with both confluence and display ---
    trend = classify_trend(featured_df, swings)
    levels = find_support_resistance(swings, tol)
    fib = fib_retracement(swings)

    signals = [
        signal_from_trend(trend),
        signal_from_rsi(featured_df, cfg),
        signal_from_macd(featured_df),
        signal_from_patterns(featured_df),
        signal_from_support_resistance(levels, last_close, prox),
        signal_from_fibonacci(fib, last_close, prox),
        signal_from_volume(featured_df, cfg),
    ]
    confluence = evaluate_confluence(signals, cfg)
    # Phase 16: gate the setup against the higher-timeframe trend (context flows down only).
    confluence = resolve_mtf(confluence, featured_df, cfg)

    # --- momentum readings (for display; the votes above already encode direction) ---
    rsi = featured_df[COL_RSI].iloc[-1]
    macd = featured_df[COL_MACD].iloc[-1]
    macd_signal = featured_df[COL_MACD_SIGNAL].iloc[-1]
    rsi_val = None if pd.isna(rsi) else round(float(rsi), 1)
    macd_val = None if pd.isna(macd) else round(float(macd), 2)
    macd_sig_val = None if pd.isna(macd_signal) else round(float(macd_signal), 2)

    # Volume vs its average (Phase 15). None when the frame carries no usable volume.
    vol = featured_df[COL_VOLUME].iloc[-1] if COL_VOLUME in featured_df.columns else float("nan")
    vol_ma = featured_df[COL_VOLUME_MA].iloc[-1] if COL_VOLUME_MA in featured_df.columns else float("nan")
    volume_facts = None
    if not (pd.isna(vol) or pd.isna(vol_ma)) and float(vol_ma) > 0:
        ratio = float(vol) / float(vol_ma)
        volume_facts = {
            "last": round(float(vol), 2),
            "average": round(float(vol_ma), 2),
            "ratio": round(ratio, 2),
            "confirmed": ratio >= cfg.confluence.volume_confirm_factor,
            "obv_rising": _obv_rising(featured_df),
        }

    # --- Phase 18 toolkit (facts/context, not votes) ---
    ind = cfg.indicators
    atr = _num(_last(featured_df, COL_ATR))
    adx = _num(_last(featured_df, COL_ADX), 1)
    bb_pct = _num(_last(featured_df, COL_BB_PCT), 3)
    volatility_facts = {
        "atr": atr,
        "atr_pct": _num(atr / last_close * 100) if atr is not None else None,
        "adx": adx,
        "regime": None if adx is None else ("trending" if adx >= ind.adx_trend_threshold else "ranging"),
        "bollinger_pct_b": bb_pct,
        "bollinger_position": _bollinger_position(featured_df),
    }

    stoch_k = _num(_last(featured_df, COL_STOCH_K), 1)
    stoch_d = _num(_last(featured_df, COL_STOCH_D), 1)
    stoch_zone = (
        None if stoch_k is None
        else "oversold" if stoch_k <= ind.stoch_oversold
        else "overbought" if stoch_k >= ind.stoch_overbought
        else "neutral"
    )

    div = find_rsi_divergence(featured_df, swings)
    divergence_facts = None if div is None else {"kind": div.kind, "reason": div.reason}

    rn = nearest_round_number(last_close, cfg)
    round_number_facts = (
        None if rn is None
        else {"nearest": rn.nearest, "distance_pct": rn.distance_pct, "is_near": rn.is_near}
    )

    # Chart patterns are best-effort geometry (Phase 9) — additive context, not a vote.
    chart_patterns = [
        {
            "name": p.name,
            "direction": p.direction,
            "reason": p.reason,
            "neckline": p.neckline,
            "target": p.target,
        }
        for p in find_chart_patterns(swings, cfg)
    ]

    fib_facts = None
    if fib is not None:
        fib_facts = {
            "direction": fib.direction,
            "impulse_low": round(fib.low_price, 2),
            "impulse_high": round(fib.high_price, 2),
            "key_levels": {
                str(r): round(fib.levels[r], 2)
                for r in _DISPLAY_FIB_RATIOS
                if r in fib.levels
            },
        }

    return {
        "market": {
            "symbol": m.symbol,
            "timeframe": m.timeframe,
            "exchange": m.exchange,
            "last_close": round(last_close, 2),
            "last_time": last_time,
        },
        "trend": {"label": trend.label, "reasons": list(trend.reasons)},
        "momentum": {
            "rsi": rsi_val,
            "rsi_zone": _rsi_zone(rsi_val, cfg),
            "macd": macd_val,
            "macd_signal": macd_sig_val,
            "macd_state": "bullish" if (macd_val is not None and macd_sig_val is not None and macd_val > macd_sig_val)
            else "bearish" if (macd_val is not None and macd_sig_val is not None and macd_val < macd_sig_val)
            else "unknown",
            "stochastic_k": stoch_k,
            "stochastic_d": stoch_d,
            "stochastic_zone": stoch_zone,
        },
        "volatility": volatility_facts,
        "divergence": divergence_facts,
        "round_number": round_number_facts,
        "volume": volume_facts,
        "support_resistance": _nearest_levels(levels, last_close),
        "chart_patterns": chart_patterns,
        "fibonacci": fib_facts,
        "confluence": {
            "bias": confluence.bias,
            "triggered": confluence.triggered,
            "confidence": confluence.confidence,
            "agreeing_categories": confluence.agreeing_categories,
            "require_categories": cfg.confluence.require_categories,
            "categories": confluence.categories,
            "signals": [
                {"name": s.name, "direction": s.direction, "reason": s.reason}
                for s in confluence.signals
            ],
            "mtf_alignment": confluence.mtf_alignment,
            "mtf_trends": confluence.mtf_trends,
        },
    }


def facts_to_prompt(facts: dict) -> str:
    """Render the facts dict as a readable text block for the model (and for debugging)."""
    m = facts["market"]
    lines: list[str] = []
    lines.append(f"MARKET: {m['symbol']} on {m['exchange']}, {m['timeframe']} timeframe")
    lines.append(f"Last closed candle: {m['last_close']} at {m['last_time']}")
    lines.append("")

    t = facts["trend"]
    lines.append(f"TREND: {t['label']}")
    for r in t["reasons"]:
        lines.append(f"  - {r}")
    lines.append("")

    mo = facts["momentum"]
    lines.append("MOMENTUM:")
    lines.append(f"  - RSI: {mo['rsi']} ({mo['rsi_zone']})")
    lines.append(f"  - MACD: {mo['macd']} vs signal {mo['macd_signal']} ({mo['macd_state']})")
    if mo.get("stochastic_k") is not None:
        lines.append(f"  - Stochastic: %K {mo['stochastic_k']} / %D {mo['stochastic_d']} ({mo['stochastic_zone']})")
    div = facts.get("divergence")
    if div:
        lines.append(f"  - RSI divergence ({div['kind']}): {div['reason']}")
    lines.append("")

    vt = facts.get("volatility")
    if vt:
        lines.append("VOLATILITY & TREND STRENGTH:")
        lines.append(f"  - ATR: {vt['atr']} ({vt['atr_pct']}% of price)")
        lines.append(f"  - ADX: {vt['adx']} ({vt['regime']})")
        lines.append(f"  - Bollinger: %B {vt['bollinger_pct_b']} ({vt['bollinger_position']})")
        lines.append("")

    vol = facts.get("volume")
    lines.append("VOLUME:")
    if vol:
        state = "above average (confirming the move)" if vol["confirmed"] else "below the confirmation bar (thin)"
        obv = "" if vol.get("obv_rising") is None else f"; OBV {'rising' if vol['obv_rising'] else 'falling'}"
        lines.append(f"  - Last bar {vol['last']} vs {vol['average']} average = {vol['ratio']}x — {state}{obv}")
    else:
        lines.append("  - no volume data available")
    lines.append("")

    rn = facts.get("round_number")
    if rn:
        near = "AT" if rn["is_near"] else f"{rn['distance_pct']}% from"
        lines.append(f"ROUND NUMBER: price is {near} the psychological level {rn['nearest']}")
        lines.append("")

    sr = facts["support_resistance"]
    lines.append("NEAREST SUPPORT/RESISTANCE (by distance from price):")
    sup, res = sr["nearest_support"], sr["nearest_resistance"]
    lines.append(
        f"  - Support: {sup['price']} ({sup['touches']} touches)" if sup else "  - Support: none detected below price"
    )
    lines.append(
        f"  - Resistance: {res['price']} ({res['touches']} touches)" if res else "  - Resistance: none detected above price"
    )
    lines.append("")

    patterns = facts.get("chart_patterns", [])
    lines.append("CHART PATTERNS (best-effort geometry — approximate, may over-call):")
    if patterns:
        for p in patterns:
            extra = f" [neckline {p['neckline']}, target {p['target']}]" if p.get("neckline") is not None else ""
            lines.append(f"  [{p['direction'].upper()}] {p['name']}: {p['reason']}{extra}")
    else:
        lines.append("  - none detected in the recent structure")
    lines.append("")

    fib = facts["fibonacci"]
    if fib:
        lines.append(f"FIBONACCI (latest {fib['direction']}-leg, {fib['impulse_low']} to {fib['impulse_high']}):")
        for ratio, price in fib["key_levels"].items():
            lines.append(f"  - {float(ratio) * 100:.1f}% retracement: {price}")
    else:
        lines.append("FIBONACCI: no clean price leg to measure")
    lines.append("")

    c = facts["confluence"]
    conf_pct = f"{c['confidence'] * 100:.0f}%"
    verdict = (
        f"{c['bias'].upper()} setup FLAGGED — confidence {conf_pct} "
        f"({c['agreeing_categories']} independent categories agree, need {c['require_categories']})"
        if c["triggered"]
        else f"no setup flagged (bias {c['bias']}, confidence {conf_pct}, "
        f"{c['agreeing_categories']} of {c['require_categories']} categories agree)"
    )
    lines.append(f"CONFLUENCE VERDICT: {verdict}")
    cats = c.get("categories") or {}
    if cats:
        lines.append("Category reads (correlated signals collapsed): "
                     + ", ".join(f"{cat}={d}" for cat, d in cats.items()))

    mtf_trends = c.get("mtf_trends")
    if mtf_trends:
        tf_str = ", ".join(f"{tf} {label}" for tf, label in mtf_trends.items())
        align = c.get("mtf_alignment")
        lines.append(f"HIGHER TIMEFRAMES: {tf_str} — the setup is {align} with the bigger picture")
        if align == "conflict":
            lines.append("  (downgraded: this base-timeframe setup fights the higher-timeframe trend)")

    lines.append("Every detector's vote:")
    for s in c["signals"]:
        lines.append(f"  [{s['direction'].upper()}] {s['name']}: {s['reason']}")

    return "\n".join(lines)
