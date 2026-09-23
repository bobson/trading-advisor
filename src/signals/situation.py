"""ROADMAP A3 — the situation tier, decided by Layer 1 (not by Claude).

`classify_situation(facts, cfg)` is a PURE function of the facts dict `build_facts` produced: the
same facts always give the same tier, and since the facts are computed from bars <= N only, the
tier is look-ahead-safe by construction. The tier selects the explanation's template and word
budget (analyst guide §8); Layer 2 receives it and may not change it.

Tiers (`mtf_synthesis` is set only by the multi-timeframe synthesis path, never here):

  confirmed — the guide's §4 "shape of a confirmed setup": a CONFIRMED chart pattern whose
              direction matches a triggered (categories-aligned) confluence bias, with its
              confirmation profile showing price support, expansion (volume OR volatility
              supports), momentum not contradicting and the higher timeframe not contradicting.
              The profile already encodes §4, so it is reused rather than re-derived.
  no_setup  — any of the §2 "say there is no clear setup when" criteria holds (codes below).
  notable   — everything else: e.g. categories aligned at a level, or a confirmed/failed pattern
              without full agreement.

§2 criteria → reason codes (each independent; ALL that hold are reported):
  no_pattern_no_confluence — no confirmed/failed pattern AND confluence not triggered.
  away_from_levels         — S/R and Fibonacci votes are neutral (price at neither), price is not
                             near a round number, AND no confirmed/failed pattern.
  conflicting_signals      — bullish and bearish categories both present, and no side wins.
  neutral_indicators       — RSI in its neutral zone, ADX below `adx_trend_threshold`, trend
                             sideways (flat structure/MAs), and price not at an S/R level (the
                             "no range structure" clause).
  single_weak_signal       — exactly one directional category and no confirmed/failed pattern.

Precedence: confirmed > no_setup > notable. Taken literally, §2's "away from levels" demotes even
a mid-range trend+momentum agreement to no_setup — deliberate: the guide says a setup needs a place.

FORMING patterns are context only: they never enter the tier (not as evidence, not as range
structure), so a forming-only chart can never be `confirmed` or be lifted out of `no_setup`.
Limitation: there is no "bars since confirmation" yet (ROADMAP A5), so an old confirmed pattern
still counts as confirmed.
"""

from __future__ import annotations

from src.config import Config

NO_SETUP = "no_setup"
NOTABLE = "notable"
CONFIRMED = "confirmed"
MTF_SYNTHESIS = "mtf_synthesis"
TIERS = (NO_SETUP, NOTABLE, CONFIRMED, MTF_SYNTHESIS)

# The guide's §8 word ceilings and output formats, keyed by tier.
WORD_BUDGET = {NO_SETUP: 30, NOTABLE: 70, CONFIRMED: 130, MTF_SYNTHESIS: 150}
TEMPLATE = {
    NO_SETUP: "One or two sentences: what's absent, what would change it. Stop.",
    NOTABLE: "Three lines: Read. Why (2–3 named facts). Invalidation.",
    CONFIRMED: "Four lines: Read. Why (2–3 named facts). Invalidation. What to watch.",
    MTF_SYNTHESIS: "One cross-timeframe read: higher-timeframe direction, ALIGN or CONFLICT, timing.",
}

# Reason codes (one per §2 bullet, plus the positive ones).
R_NO_PATTERN_NO_CONFLUENCE = "no_pattern_no_confluence"
R_AWAY_FROM_LEVELS = "away_from_levels"
R_CONFLICTING = "conflicting_signals"
R_NEUTRAL_INDICATORS = "neutral_indicators"
R_SINGLE_WEAK = "single_weak_signal"

_DIRECTIONAL = ("bullish", "bearish")
_STRUCTURE_LEVEL_VOTERS = ("support_resistance", "fibonacci")


def situation(tier: str, reasons: list[str]) -> dict:
    return {"tier": tier, "reasons": reasons, "word_budget": WORD_BUDGET[tier],
            "template": TEMPLATE[tier]}


def _votes(confluence: dict) -> dict[str, str]:
    return {s["name"]: s["direction"] for s in confluence.get("signals", [])}


def _resolved_patterns(facts: dict) -> list[dict]:
    """Directional patterns that have RESOLVED (confirmed or failed). Forming ones are excluded."""
    return [p for p in (facts.get("chart_patterns") or [])
            if p.get("state") in ("confirmed", "failed") and p.get("direction") in _DIRECTIONAL]


def _meets_confirmed_shape(p: dict, bias: str) -> bool:
    prof = p.get("confirmation") or {}
    return (p.get("state") == "confirmed" and p.get("direction") == bias
            and prof.get("price") == "supports"
            and "supports" in (prof.get("volume"), prof.get("volatility"))
            and prof.get("momentum") != "contradicts"
            and prof.get("higher_tf") != "contradicts")


def classify_situation(facts: dict, cfg: Config) -> dict:
    """The tier + the reason codes behind it + its word budget/template (see module docstring)."""
    conf = facts.get("confluence") or {}
    bias = conf.get("bias")
    triggered = bool(conf.get("triggered"))
    categories = conf.get("categories") or {}
    resolved = _resolved_patterns(facts)

    # 1. confirmed — §4's full shape, agreeing with a triggered cross-category bias.
    if triggered and bias in _DIRECTIONAL:
        agreeing = [p for p in resolved if _meets_confirmed_shape(p, bias)]
        if agreeing:
            return situation(CONFIRMED, [f"confirmed_pattern:{p['type']}" for p in agreeing])

    # 2. no_setup — any §2 criterion.
    votes = _votes(conf)
    directional = [d for d in categories.values() if d in _DIRECTIONAL]
    at_sr = votes.get("support_resistance") in _DIRECTIONAL
    at_level = at_sr or votes.get("fibonacci") in _DIRECTIONAL \
        or bool((facts.get("round_number") or {}).get("is_near"))
    momentum = facts.get("momentum") or {}
    adx = (facts.get("volatility") or {}).get("adx")
    trend = (facts.get("trend") or {}).get("label")

    reasons: list[str] = []
    if not resolved and not triggered:
        reasons.append(R_NO_PATTERN_NO_CONFLUENCE)
    if not resolved and not at_level:
        reasons.append(R_AWAY_FROM_LEVELS)
    if "bullish" in directional and "bearish" in directional and bias not in _DIRECTIONAL:
        reasons.append(R_CONFLICTING)
    if (momentum.get("rsi_zone") == "neutral" and adx is not None
            and adx < cfg.indicators.adx_trend_threshold and trend == "sideways" and not at_sr):
        reasons.append(R_NEUTRAL_INDICATORS)
    if len(directional) == 1 and not resolved:
        reasons.append(R_SINGLE_WEAK)
    if reasons:
        return situation(NO_SETUP, reasons)

    # 3. notable — what lifted it.
    notable = []
    if triggered:
        notable.append("categories_aligned")
    notable += [f"{p['state']}_pattern:{p['type']}" for p in resolved]
    if at_level:
        notable.append("at_level")
    return situation(NOTABLE, notable)
