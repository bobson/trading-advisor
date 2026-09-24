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
    COL_SMA_LONG,
    COL_SMA_SLOW,
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
from src.advisor.facts_detail import (
    distance,
    mtf_signal_alignment,
    nearest_structural_levels,
    reliability_placeholder,
    strongest_opposing_fact,
    zone_edge_distance,
)
from src.market.adaptation import market_context
from src.market.precision import price_decimals, round_price
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
            "price": round_price(row["price"], last_close),   # band centre
            "lower": round_price(row["lower"], last_close),
            "upper": round_price(row["upper"], last_close),
            "touches": int(row["touches"]),
            "bars_since_touch": int(row["bars_since_touch"]),
            "strength": float(row["strength"]),
            "stale": bool(row["stale"]),
            "inside": bool(row["distance"] == 0),
        }
    return out


def _harden(facts: dict, featured_df: pd.DataFrame, zones: pd.DataFrame, confluence, last_close: float,
            atr: float | None, cfg: Config) -> None:
    """ROADMAP A5 — make the facts complete enough that Claude never guesses or calculates:
    distances (ATR + %) to every level, the nearest structural level above/below, per-signal
    higher-timeframe votes, the strongest opposing fact, a reliability field, and an explicit
    list of what was NOT found. Mutates `facts` in place (all values JSON-safe)."""
    # distances to every level
    for key in ("nearest_support", "nearest_resistance"):
        z = facts["support_resistance"][key]
        if z:
            z.update(zone_edge_distance(z["lower"], z["upper"], last_close, atr))
    fib = facts["fibonacci"]
    if fib:
        fib["key_level_distances"] = {r: distance(v, last_close, atr) for r, v in fib["key_levels"].items()}
    rn = facts["round_number"]
    if rn:
        rn.update({f"signed_{k}": v for k, v in distance(rn["nearest"], last_close, atr).items()})
    for p in facts["chart_patterns"]:
        p["distances"] = {k: distance(p.get(f"{k}_level" if k != "target" else k), last_close, atr)
                          for k in ("breakout", "invalidation", "target")}
    mas = {}
    for key, col, period in (("slow", COL_SMA_SLOW, cfg.indicators.slow_ma),
                             ("long", COL_SMA_LONG, cfg.indicators.long_ma)):
        v = _num(_last(featured_df, col), price_decimals(last_close))
        mas[key] = None if v is None else {"period": period, "value": v, **distance(v, last_close, atr)}
    facts["moving_averages"] = mas

    facts["nearest_levels"] = nearest_structural_levels(
        last_close, atr, zones=zones, fib_levels=fib["key_levels"] if fib else None,
        patterns=facts["chart_patterns"])
    facts["strongest_opposing_fact"] = strongest_opposing_fact(facts["confluence"], cfg)
    facts["mtf_signals"] = mtf_signal_alignment(
        featured_df, {s.name: s.direction for s in confluence.signals}, cfg)
    facts["detector_reliability"] = reliability_placeholder(
        [s.name for s in confluence.signals], [p["type"] for p in facts["chart_patterns"]])

    # explicit absences — never a silent omission
    pats = facts["chart_patterns"]
    absent = []
    if facts["divergence"] is None:
        absent.append("no RSI divergence detected")
    if not any(p["state"] == "confirmed" for p in pats):
        absent.append("no confirmed chart pattern")
    if not any(p["state"] == "failed" for p in pats):
        absent.append("no failed chart pattern")
    if not pats:
        absent.append("no chart pattern detected at all (not even forming)")
    if (facts["candlestick"] or {}).get("pattern") in (None, "none"):
        absent.append("no candlestick pattern on the last closed bar")
    if facts["support_resistance"]["nearest_support"] is None:
        absent.append("no support zone below price")
    if facts["support_resistance"]["nearest_resistance"] is None:
        absent.append("no resistance zone above price")
    if facts["fibonacci"] is None:
        absent.append("no clean price leg for Fibonacci")
    if facts["volume"] is None:
        absent.append("no volume data")
    if not facts["confluence"].get("mtf_trends"):
        absent.append("no higher-timeframe veto applies to this chart (the veto timeframes are not above it, or lack enough history yet)")
    if facts["confluence"]["bias"] in ("bullish", "bearish") and facts["strongest_opposing_fact"] is None:
        absent.append("no category votes against the read")
    if facts["nearest_levels"]["above"] is None:
        absent.append("no structural level above price")
    if facts["nearest_levels"]["below"] is None:
        absent.append("no structural level below price")
    facts["absences"] = absent


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
    pdp = price_decimals(last_close)          # price-denominated values keep the instrument's precision
    macd_val = None if pd.isna(macd) else round(float(macd), pdp)
    macd_sig_val = None if pd.isna(macd_signal) else round(float(macd_signal), pdp)

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
    atr = _num(_last(featured_df, COL_ATR), pdp)
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
            "impulse_low": round_price(fib.low_price, last_close),
            "impulse_high": round_price(fib.high_price, last_close),
            "key_levels": {
                str(r): round_price(fib.levels[r], last_close)
                for r in _DISPLAY_FIB_RATIOS
                if r in fib.levels
            },
        }

    facts = {
        "market": {
            "symbol": m.symbol,
            "timeframe": m.timeframe,
            "exchange": m.exchange,
            "last_close": round_price(last_close),
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
    _harden(facts, featured_df, levels, confluence, last_close, atr, cfg)

    # ROADMAP A3: the situation tier is decided HERE (Layer 1), from the finished facts — it picks
    # the explanation's template and word budget, and Layer 2 may not change it.
    facts["situation"] = classify_situation(facts, cfg)
    return facts


def _fear_greed_read(value) -> str:
    """Layer-1 informativeness of a Fear & Greed value, per the analyst guide's §5 bands: only
    the extremes (<20 / >80) describe crowded positioning (no implied direction); mid-range is
    deliberately uninformative.
    This is NOT a directional vote — it tells Layer 2 how much (if any) weight to give it."""
    try:
        v = int(value)
    except (TypeError, ValueError):
        return "unclassified"
    if v < 20:
        return "extreme fear — crowded pessimistic positioning, no implied direction"
    if v > 80:
        return "extreme greed — crowded optimistic positioning, no implied direction"
    return "mid-range — no directional information (only the <20 / >80 extremes are read contrarily)"


_STAGE_LABEL = {"forming": "FORMING", "fresh": "CONFIRMED · FRESH", "in_play": "CONFIRMED · IN PLAY",
                "completed": "COMPLETED · HISTORY", "expired": "EXPIRED · HISTORY", "failed": "FAILED"}


def _stage(p: dict) -> str:
    return _STAGE_LABEL.get(p.get("lifecycle") or p["state"], p["state"].upper())


def _stage_text(p: dict) -> str:
    """Where the pattern is in its life cycle, in words — so an old signal is never read as current."""
    life, since = p.get("lifecycle") or p["state"], p.get("bars_since_state_change")
    ago = _bars(since) + " ago"
    if life == "forming":
        return "not broken out yet — a shape still developing, not a setup"
    if life == "fresh":
        return f"broke out {ago} — a recent breakout; target not reached yet"
    if life == "in_play":
        return f"broke out {ago} — breakout still being tested (target not reached, not failed)"
    if life == "completed":
        hit_ago = (p["state_bar"] + since - p["target_hit_bar"]) if p.get("target_hit_bar") is not None else None
        return (f"broke out {ago} and reached its target {_bars(hit_ago)} ago — the move is DONE; "
                "HISTORY, not a current setup")
    if life == "expired":
        return (f"broke out {ago} and has neither reached its target nor failed for longer than it took to "
                "form — HISTORY, not a current setup")
    return f"failed {ago}"


def _bars(n) -> str:
    """'1 bar' / 'N bars' (and 'n/a' when unknown)."""
    return "n/a bars" if n is None else f"{n} bar" if n == 1 else f"{n} bars"


def _d(dist: dict | None) -> str:
    """Render a pre-computed distance: '+1.34 ATR / +0.91%' (+ = above price, − = below)."""
    if not dist:
        return "distance n/a"
    atr = "n/a ATR" if dist.get("distance_atr") is None else f"{dist['distance_atr']:+.2f} ATR"
    return f"{atr} / {dist['distance_pct']:+.2f}%"


def facts_to_prompt(facts: dict) -> str:
    """Render the facts dict as a readable text block for the model (and for debugging).

    ROADMAP A5: sections follow the analyst guide's §3 priority order — (1) trend & regime,
    (2) structure, (3) patterns, (4) momentum, (5) volatility, (6) volume, (7) context — then the
    confluence verdict. Every distance is pre-computed (ATR units and %, + above / − below price)
    and every absence is stated, so the model never calculates or infers what is missing."""
    m = facts["market"]
    lines: list[str] = []
    add = lines.append
    sit = facts.get("situation")
    if sit:
        add(f"SITUATION TIER: {sit['tier']} — decided by Layer 1; use it, never change it.")
        add(f"  Word budget: {sit['word_budget']}. Format: {sit['template']}")
        add(f"  Why this tier: {', '.join(sit['reasons']) or 'n/a'}")
        add("")
    add(f"MARKET: {m['symbol']} on {m['exchange']}, {m['timeframe']} timeframe")
    add(f"Last closed candle: {m['last_close']} at {m['last_time']}")
    ma = facts.get("market_adaptation")
    if ma:
        if ma["is_24_7"]:
            add(f"  {ma['asset_class']}, 24/7 — volume is real exchange volume.")
        else:
            gap = " (WEEKEND GAP — Sunday opened away from Friday's close)" if ma["weekend_gap"] else ""
            add(f"  {ma['asset_class']} — active session: {ma['active_session']}{gap}.")
            add("  Volume is TICK volume (a proxy): treat volume signals as weaker than in crypto.")
        if ma["significant_move_pct"] is not None:
            add(f"  A 'significant move' for this market is ~{ma['significant_move_pct']}% (ATR-based).")
    add("All distances below are PRE-COMPUTED: + = level above price, − = below. Quote them; never recompute.")
    add("")

    c = facts["confluence"]
    vt = facts.get("volatility") or {}

    # --- (1) TREND & REGIME ---------------------------------------------------------------
    t = facts["trend"]
    add("1. TREND & REGIME")
    add(f"  - TREND: {t['label']}")
    for r in t["reasons"]:
        add(f"  - {r}")
    for key, mav in (facts.get("moving_averages") or {}).items():
        add(f"  - SMA{mav['period']}: {mav['value']} ({_d(mav)})" if mav
            else f"  - {key} moving average: not available (not enough history)")
    if vt:
        add(f"  - ADX: {vt.get('adx')} ({vt.get('regime')})")
    mtf_trends = c.get("mtf_trends")
    if mtf_trends:
        tf_str = ", ".join(f"{tf} {label}" for tf, label in mtf_trends.items())
        align = c.get("mtf_alignment")
        add(f"  - Higher-timeframe veto check: {tf_str} — the setup is {align} with the bigger picture")
        if align == "conflict":
            add("    (downgraded: this base-timeframe setup fights the higher-timeframe trend)")
    else:
        add("  - Higher-timeframe veto check: none applies to this chart (the veto timeframes are not above it, or lack "
            "enough history yet); see the per-timeframe votes below for the wider picture")
    ms = facts.get("mtf_signals")
    if ms and len(ms.get("timeframes", [])) > 1:
        add("  - Each detector's vote per timeframe (base first):")
        for name, per in ms["signals"].items():
            add(f"      {name}: " + " / ".join(f"{tf} {d}" for tf, d in per.items()))
    add("")

    # --- (2) STRUCTURE --------------------------------------------------------------------
    add("2. STRUCTURE")
    nl = facts.get("nearest_levels") or {}
    for side in ("above", "below"):
        lv = nl.get(side)
        add(f"  - Nearest structural level {side} price: {lv['price']} — {lv['source']} ({_d(lv)})" if lv
            else f"  - Nearest structural level {side} price: none detected")
    sr = facts["support_resistance"]

    def _zone(z: dict) -> str:
        where = "price is INSIDE this zone" if z.get("inside") else _d(z)
        stale = ", STALE — no reversal here for a long time" if z.get("stale") else ""
        return (f"{z['lower']}–{z['upper']} (centre {z['price']}; {where}; {z['touches']} swing "
                f"reversals, last one {_bars(z['bars_since_touch'])} ago, recency-weighted strength "
                f"{z['strength']}{stale})")
    add("  - Support/resistance ZONES (bands, not exact lines):")
    add(f"      support: {_zone(sup)}" if (sup := sr["nearest_support"]) else "      support: no support zone below price")
    add(f"      resistance: {_zone(res)}" if (res := sr["nearest_resistance"]) else "      resistance: no resistance zone above price")
    fib = facts["fibonacci"]
    if fib:
        add(f"  - Fibonacci (latest {fib['direction']}-leg, {fib['impulse_low']} to {fib['impulse_high']}):")
        dists = fib.get("key_level_distances") or {}
        for ratio, price in fib["key_levels"].items():
            add(f"      {float(ratio) * 100:.1f}% retracement: {price} ({_d(dists.get(ratio))})")
    else:
        add("  - Fibonacci: no clean price leg to measure")
    rn = facts.get("round_number")
    if rn:
        near = "AT it" if rn["is_near"] else "not near it"
        signed = {"distance_atr": rn.get("signed_distance_atr"), "distance_pct": rn.get("signed_distance_pct")}
        add(f"  - ROUND NUMBER: nearest psychological level {rn['nearest']} "
            f"({_d(signed) if signed['distance_pct'] is not None else ''}; {near})")
    else:
        add("  - ROUND NUMBER: none")
    add("")

    # --- (3) PATTERNS ---------------------------------------------------------------------
    patterns = facts.get("chart_patterns", [])
    add("3. PATTERNS — CHART PATTERNS (best-effort geometry — approximate; NOT part of the confluence "
        "score; detector reliability UNMEASURED):")
    if patterns:
        for p in patterns:
            conf = p.get("confirmation", {})
            sup_ = [k for k, v in conf.items() if v == "supports"]
            con = [k for k, v in conf.items() if v == "contradicts"]
            dd = p.get("distances") or {}
            add(f"  [{_stage(p)} · {p['direction']}] {p['type']} ({p['kind']}, quality {p['quality']}) — "
                f"{_stage_text(p)}; shape formed until {_bars(p.get('bars_since_completion'))} ago")
            add(f"      breakout {p['breakout_level']} ({_d(dd.get('breakout'))}), invalidation "
                f"{p['invalidation_level']} ({_d(dd.get('invalidation'))}), target {p['target']} "
                f"({_d(dd.get('target'))})")
            add(f"      confirmation supports: {', '.join(sup_) or 'none'}; contradicts: {', '.join(con) or 'none'}")
    else:
        add("  - none detected in the recent structure (not even forming)")
    if not any(p["state"] == "confirmed" for p in patterns):
        add("  - no CONFIRMED chart pattern")
    candle = facts.get("candlestick")
    if candle:
        add(f"  - Candlestick (last closed bar): {candle['pattern']} ({candle['direction']}). Three-candle "
            "patterns are context only, NOT part of the confluence score.")
    else:
        add("  - Candlestick (last closed bar): no pattern")
    add("")

    # --- (4) MOMENTUM ---------------------------------------------------------------------
    mo = facts["momentum"]
    add("4. MOMENTUM")
    add(f"  - RSI: {mo['rsi']} ({mo['rsi_zone']})")
    add(f"  - MACD: {mo['macd']} vs signal {mo['macd_signal']} ({mo['macd_state']})")
    add(f"  - Stochastic: %K {mo['stochastic_k']} / %D {mo['stochastic_d']} ({mo['stochastic_zone']})"
        if mo.get("stochastic_k") is not None else "  - Stochastic: not available")
    div = facts.get("divergence")
    add(f"  - RSI divergence ({div['kind']}): {div['reason']}" if div else "  - RSI divergence: none detected")
    add("")

    # --- (5) VOLATILITY -------------------------------------------------------------------
    add("5. VOLATILITY")
    if vt:
        add(f"  - ATR: {vt['atr']} ({vt['atr_pct']}% of price)")
        add(f"  - Bollinger: %B {vt['bollinger_pct_b']} ({vt['bollinger_position']})")
    else:
        add("  - not available")
    add("")

    # --- (6) VOLUME -----------------------------------------------------------------------
    vol = facts.get("volume")
    add("6. VOLUME:")
    if vol:
        state = "above average (confirming the move)" if vol["confirmed"] else "below the confirmation bar (thin)"
        obv = "" if vol.get("obv_rising") is None else f"; OBV {'rising' if vol['obv_rising'] else 'falling'}"
        add(f"  - Last bar {vol['last']} vs {vol['average']} average = {vol['ratio']}x — {state}{obv}")
    else:
        add("  - no volume data available")
    add("")

    # --- (7) CONTEXT ----------------------------------------------------------------------
    add("7. MARKET CONTEXT (CONTEXT ONLY — conditions, never direction. Narrate the label/state as "
        "given; NEVER assign a context item a bullish/bearish vote):")
    ctx = facts.get("context")
    if ctx:
        fg = ctx.get("fear_greed")
        if fg:
            add(f"  - Crypto Fear & Greed: {fg['value']}/100 (source label: {fg['label']}) — "
                f"{_fear_greed_read(fg['value'])}. [as of {fg['as_of']}]")
        fund = ctx.get("fundamentals")
        if fund:
            mc, v = fund.get("market_cap"), fund.get("volume_24h")
            add(f"  - Fundamentals ({fund['coin']}): market cap "
                f"{('$%.1fB' % (mc / 1e9)) if mc else 'n/a'}, 24h vol "
                f"{('$%.1fB' % (v / 1e9)) if v else 'n/a'}, {fund.get('change_24h_pct')}% 24h, "
                f"{fund.get('ath_change_pct')}% from all-time high "
                "(regime/liquidity context, not a directional vote)")
        cal = ctx.get("economic_calendar") or []
        if cal:
            add("  - Upcoming high-impact economic events:")
            for e in cal:
                add(f"      {e['time']} {e['country']}: {e['event']} [{e['impact']}]")
        news = ctx.get("news") or []
        if news:
            add("  - Recent headlines:")
            for h in news:
                add(f"      ({h['when']}) {h['source']}: {h['headline']}")
        if not fg and not fund and not cal and not news:
            add("  - market context: none available")
        add(f"  (pulled {ctx.get('as_of', 'unknown')})")
    else:
        add("  - market context (sentiment, fundamentals, calendar, news): not fetched for this read")
    deriv = facts.get("derivatives")
    if deriv:
        add("  - DERIVATIVES / POSITIONING (CONTEXT ONLY — the leverage crowd, never a trigger; do not "
            "turn any of it into a bullish/bearish vote):")
        f = deriv.get("funding")
        if f:
            add(f"      Funding: {f['rate_pct']}%/8h ({f['annualized_pct']}%/yr) — state: {f['state']}. "
                "An EXTREME describes crowded positioning with no implied direction; otherwise no "
                "information.")
        oi = deriv.get("open_interest")
        if oi:
            notional = f" (~${oi['notional_usd']:,.0f})" if oi.get("notional_usd") else ""
            add(f"      Open interest: {oi['amount']:,.0f} contracts{notional}")
        add(f"      (pulled {deriv.get('as_of', 'unknown')})")
    else:
        add("  - derivatives positioning: not available for this read (not fetched, or not a crypto perp)")
    add("")

    # --- CONFLUENCE VERDICT ---------------------------------------------------------------
    conf_pct = f"{c['confidence'] * 100:.0f}%"
    total = len(c.get("categories") or {})
    count = (f"{c['agreeing_categories']} of {total} voting categories agree; "
             f"{c['require_categories']} needed to align")
    verdict = (
        f"{c['bias'].upper()} setup FLAGGED — confidence {conf_pct} ({count})"
        if c["triggered"]
        else f"no setup flagged (bias {c['bias']}, confidence {conf_pct}, {count})"
    )
    add(f"CONFLUENCE VERDICT: {verdict}")
    cats = c.get("categories") or {}
    if cats:
        add("Category reads (correlated signals collapsed): " + ", ".join(f"{cat}={d}" for cat, d in cats.items()))
    opp = facts.get("strongest_opposing_fact")
    if opp:
        add(f"STRONGEST OPPOSING FACT (always mention it): {opp['category']} votes {opp['direction']} — "
            f"{opp['detector']}: {opp['reason']} (opposing categories: {', '.join(opp['opposing_categories'])})")
    elif c["bias"] in ("bullish", "bearish"):
        add("STRONGEST OPPOSING FACT: none — no category votes against the read")
    else:
        add("STRONGEST OPPOSING FACT: n/a — there is no directional read to oppose")

    br = facts.get("base_rate")
    add(f"TRACK RECORD: historically, {br['bias']} setups like this resolved favorably "
        f"{br['win_rate'] * 100:.0f}% of the time ({br['n']} past cases, {br['horizon']}-bar "
        "horizon). This is a base rate, NOT a prediction." if br
        else "TRACK RECORD: not available for this pair/timeframe")

    add("Every detector's PRE-COMPUTED vote and category (authoritative Layer-1 "
        "classification — narrate these, NEVER re-classify a signal yourself):")
    for s_ in c["signals"]:
        cat = s_.get("category", "other")
        add(f"  [{s_['direction'].upper()} · {cat}] {s_['name']}: {s_['reason']}")

    rel = facts.get("detector_reliability")
    if rel:
        measured = [f"{name} precision {v['precision']} over {v['n']} detections ({v['status']})"
                    for group in ("chart_patterns", "detectors") for name, v in rel[group].items()
                    if v.get("precision") is not None]
        if measured:
            add(f"DETECTOR RELIABILITY: {rel['status']}: " + "; ".join(measured) + ". Quote a precision "
                "only with its count; everything not listed is unverified.")
        else:
            add(f"DETECTOR RELIABILITY: {rel['status']}. Treat every detection as unverified; "
                "do not describe any detector as reliable or accurate.")
    absences = facts.get("absences")
    if absences:
        add("NOT PRESENT (explicitly checked): " + "; ".join(absences) + ".")

    return "\n".join(lines)
