"""Phase 16 — multi-timeframe context: let the higher timeframes gate the base-timeframe read.

A base-timeframe setup that agrees with the bigger picture (the 4h/1d trend) is categorically
stronger than one fighting it — the classic "trade with the higher-timeframe trend" rule.
Context flows DOWN only: a higher timeframe informs the lower one, never the reverse.

Design choices that make this both correct and cheap:
  - We RESAMPLE the base candles up to each higher timeframe rather than fetching a separate
    series. Resampling `df[:i+1]` uses only bars at or before `i`, so it is look-ahead-safe in
    the backtest (verified by an active-context guard test), and it needs no extra data source.
  - In this (pre-Phase-17) tally era the mechanism is a GATE, not extra votes: a triggered
    setup whose bias conflicts with the aggregate higher-timeframe trend is downgraded
    (`triggered -> False`), tagged `conflict`, and its bias is left intact. Higher timeframes
    therefore never trigger a setup on their own; they can only veto one that fights them.
    Phase 17 replaces this binary gate with a graded confidence multiplier.

The aggregate higher-timeframe bias is read from the HIGHEST timeframe that is directional
(1d before 4h) — the daily has the final say, falling back to 4h only when the daily is flat.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

import pandas as pd

from src.config import Config
from src.indicators.features import add_features
from src.signals.confluence import BEARISH, BULLISH, NEUTRAL, ConfluenceResult
from src.structure.swings import find_swings
from src.structure.trend import DOWNTREND, UPTREND, classify_trend

# Alignment labels (distinct from vote directions).
ALIGNED = "aligned"
CONFLICT = "conflict"
ALIGN_NEUTRAL = "neutral"

_UNIT_TO_MINUTES = {"m": 1, "h": 60, "d": 1440}
_UNIT_TO_PANDAS = {"m": "min", "h": "h", "d": "D"}


def _tf_minutes(timeframe: str) -> int:
    """'15m'->15, '1h'->60, '4h'->240, '1d'->1440."""
    return int(timeframe[:-1]) * _UNIT_TO_MINUTES[timeframe[-1]]


def _tf_to_rule(timeframe: str) -> str:
    """ccxt-style timeframe -> pandas resample rule, e.g. '4h'->'4h', '1d'->'1D', '15m'->'15min'."""
    return f"{int(timeframe[:-1])}{_UNIT_TO_PANDAS[timeframe[-1]]}"


@dataclass
class MtfContext:
    base_timeframe: str
    trends: dict[str, str]      # {higher_timeframe: trend_label}; empty when none apply
    aggregate_bias: str         # BULLISH | BEARISH | NEUTRAL


def resample_ohlcv(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    """Aggregate finer candles into a coarser timeframe (open=first, high=max, low=min,
    close=last, volume=sum). Empty buckets are dropped.
    """
    agg = {"open": "first", "high": "max", "low": "min", "close": "last"}
    cols = ["open", "high", "low", "close"]
    if "volume" in df.columns:
        agg["volume"] = "sum"
        cols.append("volume")
    out = df[cols].resample(rule).agg(agg)
    return out.dropna(subset=["open", "high", "low", "close"])


def higher_timeframe_trend(ohlcv: pd.DataFrame, timeframe: str, cfg: Config):
    """Classify the trend on `ohlcv` resampled up to `timeframe`. Returns a TrendResult, or
    None when there aren't enough resampled bars to form even one confirmed swing.
    """
    htf = resample_ohlcv(ohlcv, _tf_to_rule(timeframe))
    # Need enough resampled bars for the indicators to compute (the slow MA subsumes MACD's
    # 26-bar minimum; below it pandas-ta returns None and add_features would raise). So a
    # higher timeframe only becomes ACTIVE once it has ~slow_ma bars — e.g. the 1d gate is
    # dormant until ~50 daily bars (~1200 hourly) exist. Until then it reads as no context.
    if len(htf) < cfg.indicators.slow_ma:
        return None
    featured = add_features(htf, cfg)
    swings = find_swings(htf, cfg.structure.swing_sensitivity)
    return classify_trend(featured, swings)


def _label_to_bias(label: str) -> str:
    if label == UPTREND:
        return BULLISH
    if label == DOWNTREND:
        return BEARISH
    return NEUTRAL


def build_mtf_context(base_featured_df: pd.DataFrame, cfg: Config) -> MtfContext:
    """Compute the higher-timeframe trends (from those strictly above the base timeframe) and
    the aggregate bias — the highest directional timeframe wins (1d before 4h).
    """
    base_min = _tf_minutes(cfg.market.timeframe)
    trends: dict[str, str] = {}
    for tf in cfg.mtf.context_from:
        if _tf_minutes(tf) <= base_min:
            continue  # never let an equal/lower timeframe act as "higher" context
        result = higher_timeframe_trend(base_featured_df, tf, cfg)
        if result is not None:
            trends[tf] = result.label

    aggregate = NEUTRAL
    for tf in sorted(trends, key=_tf_minutes, reverse=True):
        bias = _label_to_bias(trends[tf])
        if bias != NEUTRAL:
            aggregate = bias
            break
    return MtfContext(cfg.market.timeframe, trends, aggregate)


def alignment(base_bias: str, aggregate_bias: str) -> str:
    """How the base setup sits against the higher-timeframe trend."""
    if base_bias == NEUTRAL or aggregate_bias == NEUTRAL:
        return ALIGN_NEUTRAL
    return ALIGNED if base_bias == aggregate_bias else CONFLICT


def resolve_mtf(result: ConfluenceResult, base_featured_df: pd.DataFrame, cfg: Config) -> ConfluenceResult:
    """Apply the higher-timeframe gate to a base-timeframe confluence result.

    Returns a copy with `mtf_alignment`/`mtf_trends` recorded. On a `conflict` the setup is
    downgraded (`triggered -> False`, `mtf_downgraded=True`); aligned/neutral pass through
    untouched. When MTF is disabled or no higher timeframe applies, `mtf_alignment` stays
    None so callers can tell "no MTF available" from "MTF present but neutral".
    """
    if not cfg.mtf.enabled:
        return result
    ctx = build_mtf_context(base_featured_df, cfg)
    if not ctx.trends:
        return replace(result, mtf_alignment=None, mtf_trends=None)

    align = alignment(result.bias, ctx.aggregate_bias)
    downgraded = result.triggered and align == CONFLICT
    # Grade the confidence (Phase 17): agreement with the bigger picture is a small boost,
    # a fight against it a penalty. A conflict is still a hard veto of the flag (that gate was
    # validated in Phase 16), so the penalty only ever lands on an already-unflagged setup.
    multiplier = {ALIGNED: 1.1, CONFLICT: 0.5}.get(align, 1.0)
    confidence = round(min(1.0, result.confidence * multiplier), 3)
    return replace(
        result,
        triggered=result.triggered and not downgraded,
        confidence=confidence,
        mtf_alignment=align,
        mtf_trends=dict(ctx.trends),
        mtf_downgraded=downgraded,
    )
