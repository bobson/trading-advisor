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
    candlestick_read,
)
from src.patterns.chart_patterns import find_patterns
from src.signals.confluence import (
    SIGNAL_CATEGORY,
    evaluate_confluence,
    signal_from_fibonacci,
    signal_from_macd,
    signal_from_patterns,
    signal_from_rsi,
    signal_from_support_resistance,
    signal_from_trend,
    signal_from_volume,
)
from src.market.adaptation import market_context
from src.signals.situation import classify_situation
from src.structure.divergence import find_rsi_divergence
from src.structure.fibonacci import fib_retracement
from src.structure.mtf import resolve_mtf
from src.structure.round_numbers import nearest_round_number
from src.structure.support_resistance import (
    RESISTANCE,
    SUPPORT,
    annotate_roles,
    current_atr,
    sr_zones,
    zone_distance,
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


def _nearest_levels(zones: pd.DataFrame, last_close: float) -> dict:
    """Nearest support ZONE (centre below price) and resistance zone (centre above), by distance
    to the band (0 when price is inside it). ROADMAP A4: each is a band, not a single line."""
    out: dict[str, dict | None] = {"nearest_support": None, "nearest_resistance": None}
    if zones.empty:
        return out
    roled = annotate_roles(zones, last_close)
    roled = roled.assign(distance=zone_distance(roled, last_close))
    for role, key in ((SUPPORT, "nearest_support"), (RESISTANCE, "nearest_resistance")):
        side = roled[roled["role"] == role]
        if side.empty:
            continue
        row = side.sort_values(["distance", "strength"], ascending=[True, False]).iloc[0]
        out[key] = {
            "price": round(float(row["price"]), 2),          # band centre
            "lower": round(float(row["lower"]), 2),
            "upper": round(float(row["upper"]), 2),
            "touches": int(row["touches"]),
            "bars_since_touch": int(row["bars_since_touch"]),
            "strength": float(row["strength"]),
            "stale": bool(row["stale"]),
            "inside": bool(row["distance"] == 0),
        }
    return out


def build_facts(featured_df: pd.DataFrame, swings: pd.DataFrame, cfg: Config) -> dict:
    """Gather all Layer 1 facts into one structured dict.

    `featured_df` must be the frame the swings were derived from (row-aligned), so the
    trend detector's SMA lookup lines up with the swing bars.
    """
    m = cfg.market
    prox = cfg.confluence.proximity_pct

    last_close = float(featured_df["close"].iloc[-1])
    last_time = str(featured_df.index[-1])

    # --- detectors: compute ONCE, share with both confluence and display ---
    trend = classify_trend(featured_df, swings)
    levels = sr_zones(featured_df, swings, cfg)          # A4: zones (centre in `price`)
    fib = fib_retracement(swings)

    signals = [
        signal_from_trend(trend),
        signal_from_rsi(featured_df, cfg),
        signal_from_macd(featured_df),
        signal_from_patterns(featured_df),
        signal_from_support_resistance(levels, last_close, current_atr(featured_df),
                                       cfg.structure.sr_near_atr_mult),
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

    # Market adaptation (Phase 19) — crypto vs forex context; tags volume as real/tick.
    mc = market_context(m.symbol, featured_df, cfg)
    if volume_facts is not None:
        volume_facts["type"] = mc.volume_type

    # Chart patterns (Feature 2) — each carries state, levels, quality, and a confirmation profile.
    # Kept OUT of the confluence score (additive context only). Reuses the already-computed levels/
    # fib/round-number and the higher-timeframe trend for the structure/higher_tf confirmations.
    mtf_trends = confluence.mtf_trends or {}
    htf_trend = list(mtf_trends.values())[-1] if mtf_trends else None
    chart_patterns = [
        p.to_dict()
        for p in find_patterns(
            featured_df, swings, cfg,
            higher_tf_trend=htf_trend,
            structure_levels=(levels["price"].tolist() if not levels.empty else None),
            fib=fib, round_number=rn,
        )
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

    facts = {
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
        "market_adaptation": {
            "asset_class": mc.asset_class,
            "volume_type": mc.volume_type,
            "is_24_7": mc.is_24_7,
            "active_session": mc.active_session,
            "weekend_gap": mc.weekend_gap,
            "significant_move_pct": mc.significant_move_pct,
        },
        "volume": volume_facts,
        "candlestick": candlestick_read(featured_df),
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
            # Every signal carries its Layer-1 vote AND category (from the confluence engine's own
            # SIGNAL_CATEGORY). This is the authoritative classification — Layer 2 narrates it and
            # must never re-decide bullish/bearish/neutral for a signal.
            "signals": [
                {
                    "name": s.name,
                    "direction": s.direction,
                    "category": SIGNAL_CATEGORY.get(s.name, "other"),
                    "reason": s.reason,
                }
                for s in confluence.signals
            ],
            "mtf_alignment": confluence.mtf_alignment,
            "mtf_trends": confluence.mtf_trends,
        },
    }
    # ROADMAP A3: the situation tier is decided HERE (Layer 1), from the finished facts — it picks
    # the explanation's template and word budget, and Layer 2 may not change it.
    facts["situation"] = classify_situation(facts, cfg)
    return facts


def _fear_greed_read(value) -> str:
    """Layer-1 informativeness of a Fear & Greed value, per the analyst guide's §5 bands: only
    the extremes (<20 / >80) carry a contrarian read; mid-range is deliberately uninformative.
    This is NOT a directional vote — it tells Layer 2 how much (if any) weight to give it."""
    try:
        v = int(value)
    except (TypeError, ValueError):
        return "unclassified"
    if v < 20:
        return "extreme fear — contrarian caution only, not a directional signal"
    if v > 80:
        return "extreme greed — contrarian caution only, not a directional signal"
    return "mid-range — no directional information (only the <20 / >80 extremes are read contrarily)"


def facts_to_prompt(facts: dict) -> str:
    """Render the facts dict as a readable text block for the model (and for debugging)."""
    m = facts["market"]
    lines: list[str] = []
    sit = facts.get("situation")
    if sit:
        lines.append(f"SITUATION TIER: {sit['tier']} — decided by Layer 1; use it, never change it.")
        lines.append(f"  Word budget: {sit['word_budget']}. Format: {sit['template']}")
        lines.append(f"  Why this tier: {', '.join(sit['reasons']) or 'n/a'}")
        lines.append("")
    lines.append(f"MARKET: {m['symbol']} on {m['exchange']}, {m['timeframe']} timeframe")
    lines.append(f"Last closed candle: {m['last_close']} at {m['last_time']}")
    ma = facts.get("market_adaptation")
    if ma:
        if ma["is_24_7"]:
            lines.append(f"  {ma['asset_class']}, 24/7 — volume is real exchange volume.")
        else:
            gap = " (WEEKEND GAP — Sunday opened away from Friday's close)" if ma["weekend_gap"] else ""
            lines.append(f"  {ma['asset_class']} — active session: {ma['active_session']}{gap}.")
            lines.append("  Volume is TICK volume (a proxy): treat volume signals as weaker than in crypto.")
        if ma["significant_move_pct"] is not None:
            lines.append(f"  A 'significant move' for this market is ~{ma['significant_move_pct']}% (ATR-based).")
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
    lines.append("NEAREST SUPPORT/RESISTANCE ZONES (bands, not exact lines; by distance from price):")

    def _zone(z: dict) -> str:
        where = " — price is INSIDE this zone" if z.get("inside") else ""
        stale = ", STALE — no reversal here for a long time" if z.get("stale") else ""
        return (f"{z['lower']}–{z['upper']} (centre {z['price']}; {z['touches']} swing reversals, "
                f"last one {z['bars_since_touch']} bars ago, recency-weighted strength "
                f"{z['strength']}{stale}){where}")
    lines.append(f"  - Support: {_zone(sup)}" if (sup := sr["nearest_support"]) else "  - Support: none detected below price")
    lines.append(f"  - Resistance: {_zone(res)}" if (res := sr["nearest_resistance"]) else "  - Resistance: none detected above price")
    lines.append("")

    candle = facts.get("candlestick")
    if candle:
        lines.append(
            f"CANDLESTICK (last closed bar): {candle['pattern']} ({candle['direction']}). "
            "Three-candle patterns (stars, soldiers/crows) are noted here for context but are NOT "
            "part of the confluence score."
        )
        lines.append("")

    patterns = facts.get("chart_patterns", [])
    lines.append("CHART PATTERNS (best-effort geometry — approximate; NOT part of the confluence score):")
    if patterns:
        for p in patterns:
            conf = p.get("confirmation", {})
            sup = [k for k, v in conf.items() if v == "supports"]
            con = [k for k, v in conf.items() if v == "contradicts"]
            lines.append(
                f"  [{p['state'].upper()} · {p['direction']}] {p['type']} ({p['kind']}, quality {p['quality']}): "
                f"breakout {p['breakout_level']}, invalidation {p['invalidation_level']}, target {p['target']}"
            )
            lines.append(f"      confirmation supports: {', '.join(sup) or 'none'}; "
                         f"contradicts: {', '.join(con) or 'none'}")
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

    ctx = facts.get("context")
    if ctx:
        lines.append("MARKET CONTEXT (CONTEXT ONLY — conditions, never direction. Narrate the "
                     "label/state as given; NEVER assign a context item a bullish/bearish vote):")
        fg = ctx.get("fear_greed")
        if fg:
            lines.append(
                f"  - Crypto Fear & Greed: {fg['value']}/100 (source label: {fg['label']}) — "
                f"{_fear_greed_read(fg['value'])}. [as of {fg['as_of']}]"
            )
        fund = ctx.get("fundamentals")
        if fund:
            mc, v = fund.get("market_cap"), fund.get("volume_24h")
            lines.append(
                f"  - Fundamentals ({fund['coin']}): market cap "
                f"{('$%.1fB' % (mc / 1e9)) if mc else 'n/a'}, 24h vol "
                f"{('$%.1fB' % (v / 1e9)) if v else 'n/a'}, {fund.get('change_24h_pct')}% 24h, "
                f"{fund.get('ath_change_pct')}% from all-time high "
                "(regime/liquidity context, not a directional vote)"
            )
        cal = ctx.get("economic_calendar") or []
        if cal:
            lines.append("  - Upcoming high-impact economic events:")
            for e in cal:
                lines.append(f"      {e['time']} {e['country']}: {e['event']} [{e['impact']}]")
        news = ctx.get("news") or []
        if news:
            lines.append("  - Recent headlines:")
            for h in news:
                lines.append(f"      ({h['when']}) {h['source']}: {h['headline']}")
        if not fg and not fund and not cal and not news:
            lines.append("  - none available")
        lines.append(f"  (pulled {ctx.get('as_of', 'unknown')})")
        lines.append("")

    deriv = facts.get("derivatives")
    if deriv:
        lines.append("DERIVATIVES / POSITIONING (CONTEXT ONLY — the leverage crowd, never a "
                     "trigger; do not turn any of it into a bullish/bearish vote):")
        f = deriv.get("funding")
        if f:
            lines.append(
                f"  - Funding: {f['rate_pct']}%/8h ({f['annualized_pct']}%/yr) — state: {f['state']}. "
                "Only an EXTREME is a contrarian flag; otherwise no directional information."
            )
        oi = deriv.get("open_interest")
        if oi:
            notional = f" (~${oi['notional_usd']:,.0f})" if oi.get("notional_usd") else ""
            lines.append(f"  - Open interest: {oi['amount']:,.0f} contracts{notional}")
        lines.append(f"  (pulled {deriv.get('as_of', 'unknown')})")
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

    br = facts.get("base_rate")
    if br:
        lines.append(
            f"TRACK RECORD: historically, {br['bias']} setups like this resolved favorably "
            f"{br['win_rate'] * 100:.0f}% of the time ({br['n']} past cases, {br['horizon']}-bar "
            "horizon). This is a base rate, NOT a prediction."
        )

    lines.append("Every detector's PRE-COMPUTED vote and category (authoritative Layer-1 "
                 "classification — narrate these, NEVER re-classify a signal yourself):")
    for s in c["signals"]:
        cat = s.get("category", "other")
        lines.append(f"  [{s['direction'].upper()} · {cat}] {s['name']}: {s['reason']}")

    return "\n".join(lines)
