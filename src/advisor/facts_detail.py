"""ROADMAP A5 — facts complete enough that Claude never guesses or calculates.

Pure helpers used by `build_facts`. Everything here is Layer 1 arithmetic done ONCE, so the
explanation layer only ever quotes numbers it was handed:

  - `distance()`                 signed distance from price to a level, in ATR units and percent
  - `nearest_structural_levels()` the nearest structural level ABOVE and BELOW price
  - `strongest_opposing_fact()`  the heaviest category voting against the read, named
  - `mtf_signal_alignment()`     each detector's vote on each higher timeframe
  - `reliability_placeholder()`  detector reliability — unmeasured until ROADMAP B2

Sign convention for distances: POSITIVE = the level is above price, NEGATIVE = below.
"""

from __future__ import annotations

import math

import pandas as pd

from src.config import Config
from src.market.precision import fmt_price, round_price

_DIRECTIONAL = ("bullish", "bearish")


def distance(level: float | None, price: float, atr: float | None) -> dict | None:
    """Signed distance from `price` to `level`: `distance_atr` (level − price)/ATR and
    `distance_pct` (level − price)/price × 100. None when there is no level."""
    if level is None or price <= 0:
        return None
    d = float(level) - price
    return {
        "distance_atr": round(d / atr, 2) if atr and atr > 0 else None,
        "distance_pct": round(d / price * 100.0, 2),
    }


def zone_edge_distance(lower: float, upper: float, price: float, atr: float | None) -> dict:
    """Distance to a zone's NEARER edge (0 when price is inside the band)."""
    if lower <= price <= upper:
        return {"distance_atr": 0.0, "distance_pct": 0.0}
    edge = lower if lower > price else upper
    return distance(edge, price, atr)


def round_levels_around(price: float) -> tuple[float, float] | None:
    """The psychological round levels just below and just above price (same step as
    `nearest_round_number`: one order of magnitude below the price)."""
    if price <= 0:
        return None
    step = 10 ** (math.floor(math.log10(price)) - 1)
    below = math.floor(price / step) * step
    above = math.ceil(price / step) * step
    if above == below:                      # price exactly on a round level
        above += step
    return round(below, 6), round(above, 6)


def nearest_structural_levels(
    price: float, atr: float | None, *, zones: pd.DataFrame, fib_levels: dict | None,
    patterns: list[dict],
) -> dict:
    """The nearest STRUCTURAL level above and below price, from: support/resistance zone edges,
    key Fibonacci levels, the round numbers either side, and the breakout/invalidation levels of
    resolved-or-forming chart patterns. Moving averages are excluded (dynamic, not structure).
    A zone price sits INSIDE counts on both sides via its edges. Each side is None if nothing."""
    cands: list[tuple[float, str]] = []
    if zones is not None and not zones.empty:
        for _, z in zones.iterrows():
            band = f"{fmt_price(z['lower'], price)}–{fmt_price(z['upper'], price)}"
            cands.append((float(z["lower"]), f"S/R zone {band} (lower edge)"))
            cands.append((float(z["upper"]), f"S/R zone {band} (upper edge)"))
    for ratio, lvl in (fib_levels or {}).items():
        cands.append((float(lvl), f"Fibonacci {float(ratio) * 100:.1f}%"))
    rl = round_levels_around(price)
    if rl:
        cands += [(rl[0], "round number"), (rl[1], "round number")]
    for p in patterns:
        for key, label in (("breakout_level", "breakout"), ("invalidation_level", "invalidation")):
            if p.get(key) is not None:
                cands.append((float(p[key]), f"{p['type']} {label} ({p['state']})"))

    def pick(side: str) -> dict | None:
        pool = [(lvl, src) for lvl, src in cands if (lvl > price if side == "above" else lvl < price)]
        if not pool:
            return None
        lvl, src = min(pool, key=lambda c: abs(c[0] - price))
        return {"price": round_price(lvl, price), "source": src, **distance(lvl, price, atr)}

    return {"above": pick("above"), "below": pick("below")}


def strongest_opposing_fact(confluence: dict, cfg: Config) -> dict | None:
    """When any category votes AGAINST the read, name the strongest one: the opposing category
    with the highest configured weight (ties → the category listed first), and the detector
    inside it that voted that way. None when the read is neutral or nothing opposes it."""
    bias = confluence.get("bias")
    if bias not in _DIRECTIONAL:
        return None
    opposite = "bearish" if bias == "bullish" else "bullish"
    weights = cfg.confluence.category_weights or {}
    opposing = [cat for cat, d in (confluence.get("categories") or {}).items() if d == opposite]
    if not opposing:
        return None
    cat = max(opposing, key=lambda c: weights.get(c, 1.0))
    sig = next((s for s in confluence.get("signals", [])
                if s.get("category") == cat and s.get("direction") == opposite), None)
    return {
        "category": cat,
        "direction": opposite,
        "weight": float(weights.get(cat, 1.0)),
        "detector": sig["name"] if sig else None,
        "reason": sig["reason"] if sig else None,
        "opposing_categories": opposing,
    }


def mtf_signal_alignment(featured_df: pd.DataFrame, base_votes: dict[str, str], cfg: Config) -> dict:
    """Each detector's vote on the base timeframe AND on every configured higher timeframe,
    e.g. {"trend": {"1h": "bullish", "4h": "neutral", "1d": "bearish"}, ...}. Higher timeframes
    come from `mtf.facts_from` (information only — never the veto, which uses `context_from`),
    are RESAMPLED from the base candles (look-ahead-safe on a slice) and only included once they
    have `slow_ma` bars — the same dormancy rule as the Phase-16 gate. Empty per-TF entries are
    simply absent; `timeframes` lists which were available. `base_votes` are the base-timeframe
    votes build_facts already computed (reused, never recomputed)."""
    # local imports: facts_detail must stay importable without pulling the whole engine at load
    from src.indicators.features import add_features
    from src.signals.confluence import gather_signals
    from src.structure.mtf import _tf_minutes, _tf_to_rule, resample_ohlcv
    from src.structure.swings import find_swings

    base_tf = cfg.market.timeframe
    per: dict[str, dict[str, str]] = {name: {base_tf: d} for name, d in base_votes.items()}
    available = [base_tf]
    ohlcv_cols = [c for c in ("open", "high", "low", "close", "volume") if c in featured_df.columns]
    for tf in cfg.mtf.facts_from:
        if _tf_minutes(tf) <= _tf_minutes(base_tf):
            continue
        htf = resample_ohlcv(featured_df[ohlcv_cols], _tf_to_rule(tf))
        if len(htf) < cfg.indicators.slow_ma:
            continue
        feat = add_features(htf, cfg)
        votes = gather_signals(feat, find_swings(htf, cfg.structure.swing_sensitivity), cfg)
        for s in votes:
            per.setdefault(s.name, {})[tf] = s.direction
        available.append(tf)
    return {"timeframes": available, "signals": per}


def apply_measured_reliability(facts: dict, table: dict | None) -> None:
    """ROADMAP B2: replace the placeholder with MEASURED precision from `scripts/eval_detectors.py`
    (`data/detector_reliability.json`, keyed 'detector|timeframe'), for this chart's timeframe.
    Entries not in the table stay unmeasured. Injected by the caller (like the base rate) — never read
    inside build_facts, so offline tests and the snapshot don't depend on a local file."""
    rel = facts.get("detector_reliability")
    if not rel or not table:
        return
    tf = facts["market"]["timeframe"]
    measured = 0
    for group in ("detectors", "chart_patterns"):
        for name in rel[group]:
            entry = table.get(f"{name}|{tf}")
            if entry and entry.get("precision") is not None:
                rel[group][name] = {"precision": entry["precision"], "n": entry["n"],
                                    "status": entry.get("status", "measured")}
                measured += 1
    if measured:
        rel["status"] = (f"measured against the user's gold labels for {measured} detector(s) on {tf} "
                         "(precision = share of detections that matched a label); the rest unmeasured")


def reliability_placeholder(detectors: list[str], pattern_types: list[str]) -> dict:
    """Detector reliability as a FIELD (ROADMAP A5). Unmeasured for now — B2 fills `precision`
    and `n` from hand-labelled charts. Until then every detection is unverified."""
    entry = {"precision": None, "n": 0, "status": "unmeasured"}
    return {
        "status": "unmeasured — detector precision is filled in by ROADMAP B2",
        "detectors": {d: dict(entry) for d in detectors},
        "chart_patterns": {t: dict(entry) for t in sorted(set(pattern_types))},
    }
