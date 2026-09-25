"""ROADMAP A8 — the forward record's outcome rule. FIXED and VERSIONED before the first run.

Every frozen read stores the rule version it will be judged by. Changing anything below means a new
version (a new entry in RULES / RULE_TEXT); old reads keep resolving under their original version.
`test_forward.py` pins the hash of the v1 text, so an edit can't slip in silently.

The levels a read is judged against are frozen WITH the read (see `levels_for`), from the support /
resistance ZONES the engine computed at that bar — never round numbers (one is almost always a
fraction of an ATR away, which would make every read resolve on its first bar).
"""

from __future__ import annotations

import hashlib

BULLISH, BEARISH = "bullish", "bearish"
DIRECTIONAL, RANGE = "directional", "range"

# Outcomes
FOLLOWED, INVALIDATED, EXPIRED, AMBIGUOUS = "followed_through", "invalidated", "expired", "ambiguous"
CORRECT, MISSED = "correct", "missed_move"
UNSCORABLE = "unscorable"
DIRECTIONAL_OUTCOMES = (FOLLOWED, INVALIDATED, EXPIRED, AMBIGUOUS)
RANGE_OUTCOMES = (CORRECT, MISSED)

RULE_VERSION = 1
FALLBACK_ATR = {1: 3.0}         # part of the rule: a missing zone -> close ± this × ATR

RULE_TEXT = {1: """Forward-record outcome rule v1

Which reads are directional: situation tier is not "no_setup" AND the confluence bias is bullish or
bearish. The read's direction is that bias. Every other read is a no-setup (range) read.

Levels, frozen at the read (from the engine's nearest support zone below and nearest resistance zone
above; a missing zone falls back to close ± 3 × ATR — or 3% of price without an ATR — tagged "atr"):
  bullish: next level = the resistance zone's lower edge (its upper edge if price is already inside
           the zone); invalidation = the support zone's lower edge.
  bearish: next level = the support zone's upper edge (its lower edge if price is already inside the
           zone); invalidation = the resistance zone's upper edge.
  range:   low = the support zone's lower edge; high = the resistance zone's upper edge.

Judged on the first `horizon` CLOSED bars after the read's bar (30m 48, 1h 24, 4h 42, 1d 21),
using bar highs and lows, once all of them have closed:
  directional — first touch wins, bar by bar:
      the next level touched first            -> followed_through
      the invalidation touched first          -> invalidated
      both touched inside the same bar        -> ambiguous (OHLC can't tell the order; never guess)
      neither within the horizon              -> expired
      (bullish: next touched = high >= next, invalidation touched = low <= invalidation; bearish mirrored)
  range — correct if every bar stayed within [low, high] (no high above high, no low below low);
      otherwise missed_move.

Coin-flip baseline: every read also gets a direction from a hash of (symbol, timeframe, bar time) —
reproducible, not a signal — scored with the directional rule on levels derived the same way.
"""}


def rule_hash(version: int) -> str:
    return hashlib.sha256(RULE_TEXT[version].encode()).hexdigest()[:16]


def levels_for(direction: str | None, close: float, atr: float | None, support: dict | None,
               resistance: dict | None, fallback_atr: float = FALLBACK_ATR[RULE_VERSION]) -> dict:
    """The frozen levels for one read direction (bullish / bearish / None = range), per rule v1.
    `support` / `resistance` are {lower, upper} zones or None. Returns the levels plus where each
    came from ("zone" or "atr")."""
    step = (atr or 0.0) * fallback_atr or close * 0.03          # no ATR at all: 3% of price
    s_lo, s_up = (support["lower"], support["upper"]) if support else (close - step, close - step)
    r_lo, r_up = (resistance["lower"], resistance["upper"]) if resistance else (close + step, close + step)
    src_below, src_above = ("zone" if support else "atr"), ("zone" if resistance else "atr")
    out = {"source_below": src_below, "source_above": src_above,
           "near_above": r_lo if r_lo > close else r_up, "near_below": s_up if s_up < close else s_lo,
           "range_low": s_lo, "range_high": r_up}
    if direction == BULLISH:
        out.update(next_level=out["near_above"], invalidation=s_lo)
    elif direction == BEARISH:
        out.update(next_level=out["near_below"], invalidation=r_up)
    else:
        out.update(next_level=None, invalidation=None)
    return out


def _resolve_directional(direction: str, next_level: float | None, invalidation: float | None,
                         bars: list[tuple[float, float]]) -> str:
    if next_level is None or invalidation is None:
        return UNSCORABLE
    bull = direction == BULLISH
    for high, low in bars:
        hit_next = high >= next_level if bull else low <= next_level
        hit_inv = low <= invalidation if bull else high >= invalidation
        if hit_next and hit_inv:
            return AMBIGUOUS
        if hit_inv:
            return INVALIDATED
        if hit_next:
            return FOLLOWED
    return EXPIRED


def _resolve_range(low: float, high: float, bars: list[tuple[float, float]]) -> str:
    return CORRECT if all(h <= high and lo >= low for h, lo in bars) else MISSED


def resolve_v1(read: dict, bars: list[tuple[float, float]]) -> str:
    """`bars` = (high, low) of exactly the read's horizon of closed bars after its bar."""
    if read["read_kind"] == DIRECTIONAL:
        return _resolve_directional(read["direction"], read["next_level"], read["invalidation"], bars)
    return _resolve_range(read["range_low"], read["range_high"], bars)


RULES = {1: resolve_v1}


def baseline_direction(symbol: str, timeframe: str, bar_time: int) -> str:
    """The coin-flip direction for a read: a hash of its identity (reproducible, not random-state)."""
    h = hashlib.sha256(f"{symbol}|{timeframe}|{bar_time}".encode()).digest()[0]
    return BULLISH if h % 2 == 0 else BEARISH


def resolve_baseline(read: dict, bars: list[tuple[float, float]]) -> tuple[str, str]:
    """(direction, outcome) for the coin-flip baseline on this read, under the directional rule."""
    d = baseline_direction(read["symbol"], read["timeframe"], read["bar_time"])
    sup = {"lower": read["sup_lower"], "upper": read["sup_upper"]} if read["sup_lower"] is not None else None
    res = {"lower": read["res_lower"], "upper": read["res_upper"]} if read["res_lower"] is not None else None
    lv = levels_for(d, read["price"], read["atr"], sup, res, FALLBACK_ATR[read["rule_version"]])
    return d, _resolve_directional(d, lv["next_level"], lv["invalidation"], bars)
