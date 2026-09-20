"""Feature 8 — exit-rule laboratory. In trend following, returns come overwhelmingly from how long
you hold winners, not from entry precision. This holds the ENTRY fixed, varies only the EXIT, and
reports whether the exit or the entry matters more on YOUR data.

Eight exit rules, all ATR-scaled and simulated bar-by-bar FORWARD (never using a bar beyond the one
being simulated):
  fixed_target   — take profit at target_atr × ATR
  stop_only      — ride until a stop_atr × ATR stop (no target)
  trailing_atr   — close-based trail, trail_atr × ATR under the running close-high
  chandelier     — wick-based trail, chandelier_atr × ATR under the highest HIGH since entry
  regime_flip    — close when the regime leaves trending (Feature 6)
  structure      — close beyond a rolling swing-low/high PROXY (rolling N-bar low; not the swing
                   detector — named honestly)
  time           — close after time_bars regardless
  ma_cross       — close on a close through the slow MA

Intrabar honesty: no rule combines a stop AND a target in the same rule (they're deliberately
isolated), so a bar can't straddle both and flatter the result. The one intrabar subtlety —
chandelier's wick stop — is handled conservatively: the stop is measured from the highest high
THROUGH THE PREVIOUS bar, so a bar's own new high can't loosen the stop its own low then hits.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from statistics import mean, median, pstdev

from src.backtest.costs import CostModel, _tf_minutes
from src.config import Config
from src.indicators.features import COL_ATR, COL_SMA_FAST, COL_SMA_SLOW, add_features
from src.market.regime import TRENDING_DOWN, TRENDING_UP, classify_regime

BULLISH = "bullish"
BEARISH = "bearish"

EXIT_RULES = ("fixed_target", "stop_only", "trailing_atr", "chandelier",
              "regime_flip", "structure", "time", "ma_cross")


@dataclass
class Trade:
    entry_bar: int
    exit_bar: int
    direction: str
    entry_price: float
    exit_price: float
    bars_held: int
    reason: str
    ret: float          # aligned GROSS return (positive = profit), before costs


def _aligned(direction: str, entry: float, exit_: float) -> float:
    r = (exit_ - entry) / entry
    return r if direction == BULLISH else -r


def _trade(entry_bar, exit_bar, direction, entry, exit_, reason) -> Trade:
    return Trade(entry_bar=entry_bar, exit_bar=exit_bar, direction=direction,
                 entry_price=round(float(entry), 6), exit_price=round(float(exit_), 6),
                 bars_held=exit_bar - entry_bar, reason=reason,
                 ret=_aligned(direction, entry, exit_))


def simulate_exit(featured: pd.DataFrame, entry_bar: int, direction: str, cfg: Config,
                  rule: str, *, regime: pd.Series | None = None) -> Trade:
    """Walk forward from `entry_bar` applying `rule` until it triggers or `max_hold`/data ends.
    Look-ahead-safe: bar j reads only bars <= j (ATR is fixed at entry; regime/MA are causal)."""
    x = cfg.exits
    high = featured["high"].to_numpy(float)
    low = featured["low"].to_numpy(float)
    close = featured["close"].to_numpy(float)
    atr = featured[COL_ATR].to_numpy(float) if COL_ATR in featured.columns else np.full(len(close), np.nan)
    slow = featured[COL_SMA_SLOW].to_numpy(float) if COL_SMA_SLOW in featured.columns else np.full(len(close), np.nan)
    reg = regime.to_numpy() if regime is not None else np.array([None] * len(close), dtype=object)

    n = len(close)
    entry = close[entry_bar]
    a = atr[entry_bar]
    if np.isnan(a) or a <= 0:
        a = entry * 0.01                     # ATR-less fixture: fall back to 1% of price
    long = direction == BULLISH
    end = min(entry_bar + x.max_hold, n - 1)

    peak_close = trough_close = close[entry_bar]
    peak_high = high[entry_bar]
    trough_low = low[entry_bar]

    for j in range(entry_bar + 1, end + 1):
        if rule == "fixed_target":
            tgt = entry + x.target_atr * a if long else entry - x.target_atr * a
            if (long and high[j] >= tgt) or (not long and low[j] <= tgt):
                return _trade(entry_bar, j, direction, entry, tgt, "target")

        elif rule == "stop_only":
            stop = entry - x.stop_atr * a if long else entry + x.stop_atr * a
            if (long and low[j] <= stop) or (not long and high[j] >= stop):
                return _trade(entry_bar, j, direction, entry, stop, "stop")

        elif rule == "trailing_atr":              # close-based trail from the running close-extreme
            if long:
                if close[j] < peak_close - x.trail_atr * a:
                    return _trade(entry_bar, j, direction, entry, close[j], "trail")
                peak_close = max(peak_close, close[j])
            else:
                if close[j] > trough_close + x.trail_atr * a:
                    return _trade(entry_bar, j, direction, entry, close[j], "trail")
                trough_close = min(trough_close, close[j])

        elif rule == "chandelier":                # wick trail from the highest high THROUGH j-1
            if long:
                stop = peak_high - x.chandelier_atr * a
                if low[j] <= stop:
                    return _trade(entry_bar, j, direction, entry, stop, "chandelier")
                peak_high = max(peak_high, high[j])
            else:
                stop = trough_low + x.chandelier_atr * a
                if high[j] >= stop:
                    return _trade(entry_bar, j, direction, entry, stop, "chandelier")
                trough_low = min(trough_low, low[j])

        elif rule == "regime_flip":
            want = TRENDING_UP if long else TRENDING_DOWN
            if reg[j] != want:
                return _trade(entry_bar, j, direction, entry, close[j], "regime")

        elif rule == "structure":                 # rolling swing-low/high PROXY (not the detector)
            lo_i = max(entry_bar + 1, j - x.structure_lookback)
            if j > lo_i:
                level = np.min(low[lo_i:j]) if long else np.max(high[lo_i:j])
                if (long and close[j] < level) or (not long and close[j] > level):
                    return _trade(entry_bar, j, direction, entry, close[j], "structure")

        elif rule == "time":
            if j - entry_bar >= x.time_bars:
                return _trade(entry_bar, j, direction, entry, close[j], "time")

        elif rule == "ma_cross":
            m = slow[j]
            if not np.isnan(m) and ((long and close[j] < m) or (not long and close[j] > m)):
                return _trade(entry_bar, j, direction, entry, close[j], "ma")

    return _trade(entry_bar, end, direction, entry, close[end], "max_hold")


# --- entry rules (causal) + the grid, so we can vary entries too --------------------------------

ENTRY_RULES = ("confluence", "ma_cross", "breakout")


def _entries(rule: str, df, featured, cfg, *, warmup: int, step: int, breakout_lookback: int):
    """Entries as (bar, direction), each computed from bars <= bar (look-ahead-safe)."""
    n = len(df)
    close = df["close"].to_numpy(float)
    last = n - 2                        # need at least one forward bar to simulate an exit
    out: list[tuple[int, str]] = []
    if rule == "confluence":
        from src.backtest.evaluate import signal_at
        for i in range(warmup, last + 1, step):
            res = signal_at(df, i, cfg, featured=featured)
            if res.triggered and res.bias in (BULLISH, BEARISH):
                out.append((i, res.bias))
    elif rule == "ma_cross":
        fast = featured[COL_SMA_FAST].to_numpy(float)
        slow = featured[COL_SMA_SLOW].to_numpy(float)
        for i in range(warmup, last + 1):
            if np.isnan(fast[i]) or np.isnan(slow[i]) or np.isnan(fast[i - 1]):
                continue
            if fast[i] > slow[i] and fast[i - 1] <= slow[i - 1]:
                out.append((i, BULLISH))
            elif fast[i] < slow[i] and fast[i - 1] >= slow[i - 1]:
                out.append((i, BEARISH))
    elif rule == "breakout":
        high = df["high"].to_numpy(float)
        low = df["low"].to_numpy(float)
        for i in range(max(warmup, breakout_lookback), last + 1):
            if close[i] > np.max(high[i - breakout_lookback:i]):
                out.append((i, BULLISH))
            elif close[i] < np.min(low[i - breakout_lookback:i]):
                out.append((i, BEARISH))
    return out


def _max_drawdown(equity: np.ndarray) -> float:
    peak = np.maximum.accumulate(equity)
    return float(np.max((peak - equity) / peak))


def _net_return(t: Trade, cfg: Config, featured) -> float:
    """Trade return net of Feature-10 costs (spread/fees/slippage/funding + tax on a gain)."""
    if not cfg.costs.enabled:
        return t.ret
    model = CostModel(cfg.market.symbol, cfg)
    atr = featured[COL_ATR].iloc[t.entry_bar] if COL_ATR in featured.columns else float("nan")
    atr_pct = 0.0 if pd.isna(atr) else float(atr) / t.entry_price
    hrs = t.bars_held * _tf_minutes(cfg.market.timeframe) / 60.0
    tc = model.trade_cost(t.direction, t.entry_price, atr_pct, hrs)
    pre = t.ret - tc.total
    return pre - cfg.costs.tax_rate * max(0.0, pre)


@dataclass
class ExitStats:
    n: int
    total_return: float
    mean_return: float                      # per-trade — the fair, count-independent axis
    median_win: float | None
    median_loss: float | None
    win_rate: float | None
    largest_winner_share: float | None      # biggest winner / sum of winners
    avg_holding: float
    max_drawdown: float

    @classmethod
    def from_trades(cls, trades: list[Trade], cfg: Config, featured) -> "ExitStats":
        if not trades:
            return cls(0, 0.0, 0.0, None, None, None, None, 0.0, 0.0)
        order = sorted(range(len(trades)), key=lambda k: trades[k].entry_bar)
        nets = [_net_return(trades[k], cfg, featured) for k in order]
        wins = [r for r in nets if r > 0]
        losses = [r for r in nets if r < 0]
        equity = np.cumprod([1.0] + [1.0 + r for r in nets])
        return cls(
            n=len(trades), total_return=round(sum(nets), 4), mean_return=round(mean(nets), 5),
            median_win=round(median(wins), 4) if wins else None,
            median_loss=round(median(losses), 4) if losses else None,
            win_rate=round(len(wins) / len(nets), 4),
            largest_winner_share=round(max(wins) / sum(wins), 4) if wins else None,
            avg_holding=round(mean(t.bars_held for t in trades), 2),
            max_drawdown=round(_max_drawdown(equity), 4),
        )


@dataclass
class ExitLabReport:
    symbol: str
    timeframe: str
    primary_entry: str
    canonical_exit: str
    exits: dict           # exit rule -> ExitStats (entry fixed = primary_entry)
    entries: dict         # entry rule -> ExitStats (exit fixed = canonical_exit)
    grid: dict            # (entry, exit) -> ExitStats
    spread_across_exits: float      # std of per-trade mean-return across exits (entry fixed)
    spread_across_entries: float    # std of per-trade mean-return across entries (exit fixed)
    verdict: str          # "exit" | "entry" — which choice moves outcomes more, on this data

    def summary(self) -> str:
        def row(name, s: ExitStats) -> str:
            if not s.n:
                return f"  {name:14} n=0"
            return (f"  {name:14} n={s.n:<4} mean={s.mean_return * 100:+6.3f}%/trade  "
                    f"win={s.win_rate * 100:4.0f}%  hold={s.avg_holding:5.1f}b  "
                    f"maxDD={s.max_drawdown * 100:4.0f}%  bigWin={('%.0f%%' % (s.largest_winner_share * 100)) if s.largest_winner_share else '  -'}")

        L = [f"EXIT LAB {self.symbol} {self.timeframe} — net of costs, look-ahead-safe forward walk",
             f"\nEXITS (entry fixed = {self.primary_entry}):"]
        L += [row(x, self.exits[x]) for x in self.exits]
        L += [f"\nENTRIES (exit fixed = {self.canonical_exit}):"]
        L += [row(e, self.entries[e]) for e in self.entries]
        L += [
            "",
            f"spread of mean-return ACROSS EXITS (entry fixed): {self.spread_across_exits * 100:.3f}%",
            f"spread of mean-return ACROSS ENTRIES (exit fixed): {self.spread_across_entries * 100:.3f}%",
            f"=> on this data the {self.verdict.upper()} choice moves outcomes more.",
            "CAVEAT: overlapping forward windows -> N is not independent; read mean next to n.",
        ]
        return "\n".join(L)


def run_exit_lab(df, cfg, *, entry_rules=ENTRY_RULES, exit_rules=EXIT_RULES,
                 primary_entry="confluence", canonical_exit="trailing_atr",
                 warmup: int | None = None, step: int = 3, breakout_lookback: int = 20) -> ExitLabReport:
    """Hold the entry fixed and sweep exits; hold the exit fixed and sweep entries; report which
    spread is wider. Reuses the look-ahead-safe entry walk and simulates every exit forward."""
    featured = add_features(df, cfg)
    regime = classify_regime(featured, cfg)
    if warmup is None:
        warmup = cfg.indicators.slow_ma + cfg.structure.swing_sensitivity * 3

    entries = {er: _entries(er, df, featured, cfg, warmup=warmup, step=step,
                            breakout_lookback=breakout_lookback) for er in entry_rules}
    grid = {}
    for er, ents in entries.items():
        for xr in exit_rules:
            trades = [simulate_exit(featured, b, d, cfg, xr, regime=regime) for b, d in ents]
            grid[(er, xr)] = ExitStats.from_trades(trades, cfg, featured)

    exits_tbl = {xr: grid[(primary_entry, xr)] for xr in exit_rules}
    entries_tbl = {er: grid[(er, canonical_exit)] for er in entry_rules}
    spread_x = _spread([exits_tbl[xr].mean_return for xr in exit_rules if exits_tbl[xr].n])
    spread_e = _spread([entries_tbl[er].mean_return for er in entry_rules if entries_tbl[er].n])
    return ExitLabReport(
        symbol=cfg.market.symbol, timeframe=cfg.market.timeframe,
        primary_entry=primary_entry, canonical_exit=canonical_exit,
        exits=exits_tbl, entries=entries_tbl, grid=grid,
        spread_across_exits=spread_x, spread_across_entries=spread_e,
        verdict=("exit" if spread_x >= spread_e else "entry"),
    )


def _spread(values: list[float]) -> float:
    return round(pstdev(values), 6) if len(values) > 1 else 0.0
