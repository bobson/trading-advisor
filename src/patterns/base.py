"""Feature 2 — the pattern machinery: every pattern carries state, levels, quality, and a
multi-category confirmation profile. Detectors (in `chart_patterns.py`) emit these; `dedupe.py`
resolves overlaps; `facts.py`/`serialize.py` display them. Patterns stay OUT of the confluence
score in this branch — facts and chart only.

Confirmation is NOT just volume. A `ConfirmationProfile` scores seven independent categories,
each `supports` / `contradicts` / `neutral` / `unavailable`:
  price       — close beyond the breakout level (a retest that holds is stronger)
  volume      — expansion vs its average on the move; drying volume contradicts
  momentum    — RSI/MACD agree with the pattern's direction; divergence contradicts
  volatility  — ATR expanding / a Bollinger squeeze resolving into the break
  candlestick — a reversal candle sitting at the level
  higher_tf   — the higher-timeframe trend agrees / opposes
  structure   — the level coincides with S/R, a Fib level, or a round number

State is look-ahead-safe: it is read from bar N's close against levels built from swings ≤ N, so a
pattern is never retroactively confirmed. `quality` is GEOMETRY only (how clean the shape is) and
is deliberately orthogonal to confirmation, so dedupe's choice among overlapping detections can't
flip as price moves.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

import pandas as pd

from src.market.precision import round_price

from src.indicators.features import (
    COL_ATR,
    COL_BEARISH_ENGULFING,
    COL_BULLISH_ENGULFING,
    COL_DOJI,
    COL_HAMMER,
    COL_MACD,
    COL_MACD_SIGNAL,
    COL_SHOOTING_STAR,
    COL_VOLUME,
    COL_VOLUME_MA,
)

# confirmation verdicts
SUPPORTS = "supports"
CONTRADICTS = "contradicts"
NEUTRAL = "neutral"
UNAVAILABLE = "unavailable"

# pattern states
FORMING = "forming"
CONFIRMED = "confirmed"
FAILED = "failed"

# pattern kinds
CONTINUATION = "continuation"
REVERSAL = "reversal"

BULLISH = "bullish"
BEARISH = "bearish"
NEUTRAL_DIR = "neutral"

CATEGORIES = ("price", "volume", "momentum", "volatility", "candlestick", "higher_tf", "structure")


@dataclass
class ConfirmationProfile:
    price: str = UNAVAILABLE
    volume: str = UNAVAILABLE
    momentum: str = UNAVAILABLE
    volatility: str = UNAVAILABLE
    candlestick: str = UNAVAILABLE
    higher_tf: str = UNAVAILABLE
    structure: str = UNAVAILABLE

    def counts(self) -> dict:
        vals = [getattr(self, c) for c in CATEGORIES]
        return {
            "supports": sum(v == SUPPORTS for v in vals),
            "contradicts": sum(v == CONTRADICTS for v in vals),
            "neutral": sum(v == NEUTRAL for v in vals),
            "available": sum(v != UNAVAILABLE for v in vals),
        }

    def score(self) -> float:
        """Net confirmation in [-1, 1]: (supports − contradicts) / available (0 when none read)."""
        c = self.counts()
        return round((c["supports"] - c["contradicts"]) / c["available"], 3) if c["available"] else 0.0

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Pattern:
    type: str                       # e.g. "ascending triangle", "double top"
    kind: str                       # continuation | reversal
    direction: str                  # bullish | bearish | neutral
    state: str                      # forming | confirmed | failed
    bars: list[int]                 # defining swing bars
    points: list[tuple] = field(default_factory=list)  # (bar, price) defining points
    lines: list = field(default_factory=list)  # boundary geometry: each a polyline [(bar, price), ...]
    breakout_level: float | None = None
    invalidation_level: float | None = None
    target: float | None = None
    quality: float = 0.0            # geometry cleanliness in [0, 1] (orthogonal to confirmation)
    confirmation: ConfirmationProfile = field(default_factory=ConfirmationProfile)
    reason: str = ""
    # ROADMAP A5 — staleness: bars from the last defining swing to bar N, and bars since the
    # current confirmed/failed state began (None while forming). Set by `find_patterns`.
    bars_since_completion: int | None = None
    bars_since_state_change: int | None = None
    # Life cycle after the breakout: forming | fresh | in_play | completed | expired | failed, plus the
    # absolute bar where the state began (the breakout / failure candle) and where the target was hit.
    lifecycle: str = "forming"
    state_bar: int | None = None
    target_hit_bar: int | None = None
    # Boundary LINES (slope, intercept) in bar units, for patterns whose breakout is a line that may
    # slope (triangles, channels, ranges, wedges) — the state is judged against the line's value on
    # each bar. Internal (not serialized).
    upper_line: tuple | None = None
    lower_line: tuple | None = None

    @property
    def span(self) -> tuple:
        return (min(self.bars), max(self.bars)) if self.bars else (0, 0)

    def to_dict(self) -> dict:
        return {
            "type": self.type,
            "kind": self.kind,
            "direction": self.direction,
            "state": self.state,
            "bars": list(self.bars),
            "points": [{"bar": int(b), "price": round_price(p)} for b, p in self.points],
            "lines": [[{"bar": int(b), "price": round_price(p)} for b, p in line] for line in self.lines],
            "breakout_level": None if self.breakout_level is None else round_price(self.breakout_level),
            "invalidation_level": None if self.invalidation_level is None else round_price(self.invalidation_level),
            "target": None if self.target is None else round_price(self.target),
            "quality": round(float(self.quality), 3),
            "confirmation": self.confirmation.to_dict(),
            "reason": self.reason,
            "bars_since_completion": self.bars_since_completion,
            "bars_since_state_change": self.bars_since_state_change,
            "lifecycle": self.lifecycle,
            "state_bar": self.state_bar,
            "target_hit_bar": self.target_hit_bar,
        }


def classify_state(direction: str, breakout_level, invalidation_level, last_close: float) -> str:
    """Look-ahead-safe state from bar N's close only. Confirmed = closed through the breakout in
    the pattern's direction; failed = closed through the invalidation the other way; else forming.
    Neutral-direction patterns (a symmetric coil) stay `forming` until a detector resolves a break."""
    if direction == BULLISH:
        if breakout_level is not None and last_close > breakout_level:
            return CONFIRMED
        if invalidation_level is not None and last_close < invalidation_level:
            return FAILED
        return FORMING
    if direction == BEARISH:
        if breakout_level is not None and last_close < breakout_level:
            return CONFIRMED
        if invalidation_level is not None and last_close > invalidation_level:
            return FAILED
        return FORMING
    return FORMING


def classify_state_history(
    direction: str, breakout_level, invalidation_level, closes, margins=None,
) -> tuple[str, bool, int | None]:
    """State with MEMORY, from every close since the pattern completed up to bar N (look-ahead-safe:
    the caller passes closes <= N only). Returns `(state, reclaimed, since)` — `since` is the
    position in `closes` where the current confirmed/failed state began (None while forming).

    Unlike `classify_state` (last close only), a break that is later RECLAIMED — price closes
    through the breakout level, then closes back on the pattern's wrong side of it by more than
    that bar's `margins` entry (ATR-scaled; None -> 0) — is `failed`, not silently back to
    `forming`. A close through the invalidation level is likewise terminal. Used for reversal
    patterns, whose breakout level is a horizontal neckline."""
    if direction not in (BULLISH, BEARISH):
        return FORMING, False, None
    bull = direction == BULLISH
    closes = [float(c) for c in closes]
    margins = [0.0] * len(closes) if margins is None else [float(m) for m in margins]
    broke_at = None
    for i, (c, m) in enumerate(zip(closes, margins)):
        if invalidation_level is not None and (c < invalidation_level if bull else c > invalidation_level):
            return FAILED, False, i
        if breakout_level is None:
            continue
        if c > breakout_level if bull else c < breakout_level:
            if broke_at is None:
                broke_at = i
        elif broke_at is not None and (c < breakout_level - m if bull else c > breakout_level + m):
            return FAILED, True, i                # broke out, then closed back inside -> reclaimed
    return (CONFIRMED, False, broke_at) if broke_at is not None else (FORMING, False, None)


def classify_state_path(direction: str, upper, lower, closes, margins) -> tuple[str, str, int | None]:
    """State with MEMORY for patterns bounded by two lines (triangles, channels, ranges, wedges).
    `upper`/`lower` are the boundary values on each bar after the pattern completed; `closes` and
    `margins` (ATR-scaled reclaim tolerance) are aligned with them. Returns (state, direction, since).

      - neutral (symmetric triangle, range): the first close beyond EITHER line confirms and sets
        the direction;
      - directional: a close beyond the breakout line confirms (upper for bullish, lower for
        bearish); a close beyond the OTHER line first = failed (invalidated before breaking out);
      - after confirming, a close back through the breakout line by more than the margin = failed.
    `since` is the index (into the arrays) where the current confirmed/failed state began."""
    broke_at = None
    for i, (c, up, lo, m) in enumerate(zip(closes, upper, lower, margins)):
        if broke_at is None:
            if direction == NEUTRAL_DIR:
                if c > up:
                    direction, broke_at = BULLISH, i
                elif c < lo:
                    direction, broke_at = BEARISH, i
                continue
            bull = direction == BULLISH
            if (c < lo) if bull else (c > up):
                return FAILED, direction, i
            if (c > up) if bull else (c < lo):
                broke_at = i
            continue
        bull = direction == BULLISH
        if (c < up - m) if bull else (c > lo + m):
            return FAILED, direction, i
    return (CONFIRMED, direction, broke_at) if broke_at is not None else (FORMING, direction, None)


def _last(df: pd.DataFrame, col: str):
    return df[col].iloc[-1] if col in df.columns and len(df) else float("nan")


def build_confirmation(
    direction: str, breakout_level, invalidation_level, featured_df: pd.DataFrame, *,
    state: str, higher_tf_trend: str | None = None, structure_hit: bool | None = None,
    vol_expand: float = 1.2, vol_contract: float = 0.7,
) -> ConfirmationProfile:
    """The seven-category profile, read at bar N (the last row). Each category degrades to
    `unavailable` when its inputs are missing, so a hand-built fixture never crashes it."""
    p = ConfirmationProfile()
    bull = direction == BULLISH

    # price — mirrors the state machine (close vs the levels), the primary confirmation
    if state == CONFIRMED:
        p.price = SUPPORTS
    elif state == FAILED:
        p.price = CONTRADICTS
    else:
        p.price = NEUTRAL

    # volume — expansion supports the move, drying volume contradicts
    vol, vol_ma = _last(featured_df, COL_VOLUME), _last(featured_df, COL_VOLUME_MA)
    if not (pd.isna(vol) or pd.isna(vol_ma)) and float(vol_ma) > 0:
        ratio = float(vol) / float(vol_ma)
        p.volume = SUPPORTS if ratio >= vol_expand else CONTRADICTS if ratio <= vol_contract else NEUTRAL

    # momentum — MACD side vs the pattern's direction
    macd, sig = _last(featured_df, COL_MACD), _last(featured_df, COL_MACD_SIGNAL)
    if not (pd.isna(macd) or pd.isna(sig)) and direction in (BULLISH, BEARISH):
        macd_bull = macd > sig
        p.momentum = SUPPORTS if macd_bull == bull else CONTRADICTS if macd != sig else NEUTRAL

    # volatility — ATR expanding accompanies a real break
    if COL_ATR in featured_df.columns and len(featured_df) > 6:
        atr = featured_df[COL_ATR]
        now, prev = atr.iloc[-1], atr.iloc[-6]
        if not (pd.isna(now) or pd.isna(prev)) and prev > 0:
            p.volatility = SUPPORTS if now > prev else NEUTRAL

    # candlestick — a reversal candle at the level, read in the pattern's direction
    bull_candle = bool(_true(featured_df, COL_BULLISH_ENGULFING) or _true(featured_df, COL_HAMMER))
    bear_candle = bool(_true(featured_df, COL_BEARISH_ENGULFING) or _true(featured_df, COL_SHOOTING_STAR))
    if COL_BULLISH_ENGULFING in featured_df.columns and direction in (BULLISH, BEARISH):
        if _true(featured_df, COL_DOJI):
            p.candlestick = NEUTRAL
        elif bull_candle or bear_candle:
            good = bull_candle if bull else bear_candle
            p.candlestick = SUPPORTS if good else CONTRADICTS
        else:
            p.candlestick = NEUTRAL

    # higher timeframe — supplied by the caller (resolve_mtf), never recomputed here
    if higher_tf_trend and direction in (BULLISH, BEARISH):
        htf_bull = higher_tf_trend == "uptrend"
        htf_bear = higher_tf_trend == "downtrend"
        if htf_bull or htf_bear:
            p.higher_tf = SUPPORTS if (htf_bull == bull) else CONTRADICTS
        else:
            p.higher_tf = NEUTRAL

    # structure — level coincides with S/R, Fib, or a round number (caller decides)
    if structure_hit is not None:
        p.structure = SUPPORTS if structure_hit else NEUTRAL

    return p


def _true(df: pd.DataFrame, col: str) -> bool:
    return col in df.columns and len(df) and bool(df[col].iloc[-1])
