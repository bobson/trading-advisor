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
            "points": [{"bar": int(b), "price": round(float(p), 2)} for b, p in self.points],
            "lines": [[{"bar": int(b), "price": round(float(p), 2)} for b, p in line] for line in self.lines],
            "breakout_level": None if self.breakout_level is None else round(float(self.breakout_level), 2),
            "invalidation_level": None if self.invalidation_level is None else round(float(self.invalidation_level), 2),
            "target": None if self.target is None else round(float(self.target), 2),
            "quality": round(float(self.quality), 3),
            "confirmation": self.confirmation.to_dict(),
            "reason": self.reason,
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
) -> tuple[str, bool]:
    """State with MEMORY, from every close since the pattern completed up to bar N (look-ahead-safe:
    the caller passes closes <= N only). Returns `(state, reclaimed)`.

    Unlike `classify_state` (last close only), a break that is later RECLAIMED — price closes
    through the breakout level, then closes back on the pattern's wrong side of it by more than
    that bar's `margins` entry (ATR-scaled; None -> 0) — is `failed`, not silently back to
    `forming`. A close through the invalidation level is likewise terminal. Used for reversal
    patterns, whose breakout level is a horizontal neckline."""
    if direction not in (BULLISH, BEARISH):
        return FORMING, False
    bull = direction == BULLISH
    closes = [float(c) for c in closes]
    margins = [0.0] * len(closes) if margins is None else [float(m) for m in margins]
    broke = False
    for c, m in zip(closes, margins):
        if invalidation_level is not None and (c < invalidation_level if bull else c > invalidation_level):
            return FAILED, False
        if breakout_level is None:
            continue
        if c > breakout_level if bull else c < breakout_level:
            broke = True
        elif broke and (c < breakout_level - m if bull else c > breakout_level + m):
            return FAILED, True                   # broke out, then closed back inside -> reclaimed
    return (CONFIRMED if broke else FORMING), False


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
