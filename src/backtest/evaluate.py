"""Phase 14 — backtest / forward-return evaluator (the validation instrument).

Not a trade simulator. For an *advisor*, this walks history and measures WHAT PRICE DID in the
next N bars after each bar the confluence engine would have flagged a setup. It is the
instrument that lets later phases (multi-timeframe, volume, weighting, derivatives) tune
thresholds with data instead of intuition, and proves whether an added signal actually moves
forward returns before it earns a vote.

LOOK-AHEAD SAFETY is the whole game. The signal "as of bar i" is computed from ``df[:i+1]``
only: swings are RECOMPUTED on that slice, so the confirmed-interior filter in `find_swings`
excludes any pivot that would need bars after ``i`` to confirm, and `gather_signals` reads
just the last row + those swings. Indicators (SMA/RSI/MACD) are causal — each row depends only
on the past — so `add_features` is computed ONCE on the full frame and sliced (a big speedup);
`tests/test_backtest.py` verifies that causality end-to-end by mutating future bars and
asserting the signal at ``i`` is unchanged. The forward window (``df[i+1 : i+1+horizon]``) is
never used to compute the signal.

Caveat baked into the report: with ``step`` small the forward windows of consecutive setups
overlap heavily, so N is NOT independent trials and a good number here is not proof of an
edge. Sample size is printed next to every statistic for exactly this reason.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from statistics import median
from typing import Optional

import pandas as pd

from src.config import Config
from src.indicators.features import add_features
from src.signals.confluence import (
    BEARISH,
    BULLISH,
    ConfluenceResult,
    evaluate_confluence,
    gather_signals,
)
from src.structure.swings import find_swings


@dataclass
class SetupOutcome:
    """One flagged setup and what price did over the horizon after it."""

    bar: int
    time: str
    bias: str
    agreeing: int
    entry: float
    exit: float
    forward_return: float  # raw (exit - entry) / entry
    aligned_return: float  # signed so positive = price moved the way the setup implied
    horizon: int


@dataclass
class Stats:
    n: int
    win_rate: Optional[float]      # fraction of aligned_return > 0 (None when n == 0)
    avg_return: Optional[float]    # mean aligned_return
    median_return: Optional[float]

    @classmethod
    def from_outcomes(cls, outcomes: list[SetupOutcome]) -> "Stats":
        n = len(outcomes)
        if n == 0:
            return cls(0, None, None, None)
        aligned = [o.aligned_return for o in outcomes]
        wins = sum(1 for a in aligned if a > 0)
        return cls(n, wins / n, sum(aligned) / n, float(median(aligned)))


@dataclass
class BacktestReport:
    symbol: str
    timeframe: str
    horizon: int
    warmup: int
    min_agreeing: int
    step: int
    bars_scanned: int
    overall: Stats
    by_bias: dict[str, Stats]
    outcomes: list[SetupOutcome] = field(default_factory=list)

    def summary(self) -> str:
        lines = [
            f"BACKTEST {self.symbol} {self.timeframe} — forward-return evaluator",
            f"horizon={self.horizon} bars, min_agreeing={self.min_agreeing}, "
            f"warmup={self.warmup}, step={self.step}, bars scanned={self.bars_scanned}",
            "",
            f"Setups flagged: {self.overall.n}",
        ]

        def fmt(label: str, s: Stats) -> str:
            if s.n == 0:
                return f"  {label:8} n=0   (no setups)"
            return (
                f"  {label:8} n={s.n:<4} win-rate={s.win_rate * 100:5.1f}%  "
                f"avg={s.avg_return * 100:+6.2f}%  median={s.median_return * 100:+6.2f}%"
            )

        lines.append(fmt("overall", self.overall))
        for bias in (BULLISH, BEARISH):
            lines.append(fmt(bias, self.by_bias.get(bias, Stats(0, None, None, None))))
        lines += [
            "",
            "Returns are aligned to each setup's bias (positive = price moved the way the "
            "setup implied), close[i] -> close[i+horizon].",
            "CAVEAT: with step small the forward windows overlap, so N is NOT independent "
            "trials and a good number is not proof of an edge. Always read win-rate next to n.",
        ]
        return "\n".join(lines)


def signal_at(
    df: pd.DataFrame,
    i: int,
    cfg: Config,
    *,
    featured: Optional[pd.DataFrame] = None,
    min_agreeing: Optional[int] = None,
) -> ConfluenceResult:
    """The confluence verdict AS OF bar ``i``, using only data at or before ``i``.

    `featured` may be a precomputed full-frame features table (evaluate passes this for speed,
    relying on indicator causality); when None it is computed on the slice, giving a fully
    self-contained, look-ahead-free path.
    """
    sub = df.iloc[: i + 1]
    feat = featured.iloc[: i + 1] if featured is not None else add_features(sub, cfg)
    swings = find_swings(sub, cfg.structure.swing_sensitivity)
    signals = gather_signals(feat, swings, cfg)
    return evaluate_confluence(signals, min_agreeing or cfg.confluence.min_agreeing_signals)


def evaluate(
    df: pd.DataFrame,
    cfg: Config,
    *,
    horizon: int = 24,
    warmup: Optional[int] = None,
    min_agreeing: Optional[int] = None,
    step: int = 1,
) -> BacktestReport:
    """Walk `df`, flag setups with the confluence engine, and measure forward returns.

    Returns a `BacktestReport` with per-bias and overall stats. Raises `ValueError` when there
    is not enough history for the warmup + horizon.
    """
    if horizon < 1:
        raise ValueError("horizon must be >= 1 bar")
    if step < 1:
        raise ValueError("step must be >= 1")
    min_agreeing = min_agreeing or cfg.confluence.min_agreeing_signals
    if warmup is None:
        # Enough history for the slow MA to exist and a few swings to have formed.
        warmup = cfg.indicators.slow_ma + cfg.structure.swing_sensitivity * 3

    # Last valid i is len-1-horizon (need `horizon` future bars) -> range stop is len-horizon.
    last_exclusive = len(df) - horizon
    if warmup >= last_exclusive:
        raise ValueError(
            f"Not enough history: need more than warmup+horizon = {warmup + horizon} bars, "
            f"have {len(df)}."
        )

    featured_full = add_features(df, cfg)
    close = df["close"]

    outcomes: list[SetupOutcome] = []
    scanned = 0
    for i in range(warmup, last_exclusive, step):
        scanned += 1
        res = signal_at(df, i, cfg, featured=featured_full, min_agreeing=min_agreeing)
        if not res.triggered or res.bias not in (BULLISH, BEARISH):
            continue
        entry = float(close.iloc[i])
        exit_ = float(close.iloc[i + horizon])
        fwd = (exit_ - entry) / entry
        aligned = fwd if res.bias == BULLISH else -fwd
        outcomes.append(
            SetupOutcome(
                bar=i,
                time=str(df.index[i]),
                bias=res.bias,
                agreeing=res.agreeing,
                entry=entry,
                exit=exit_,
                forward_return=fwd,
                aligned_return=aligned,
                horizon=horizon,
            )
        )

    by_bias = {
        BULLISH: Stats.from_outcomes([o for o in outcomes if o.bias == BULLISH]),
        BEARISH: Stats.from_outcomes([o for o in outcomes if o.bias == BEARISH]),
    }
    return BacktestReport(
        symbol=cfg.market.symbol,
        timeframe=cfg.market.timeframe,
        horizon=horizon,
        warmup=warmup,
        min_agreeing=min_agreeing,
        step=step,
        bars_scanned=scanned,
        overall=Stats.from_outcomes(outcomes),
        by_bias=by_bias,
        outcomes=outcomes,
    )
