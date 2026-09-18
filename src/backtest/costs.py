"""Feature 10 — the honest cost model. A backtest without costs is fiction.

Transaction costs explain a large share of documented retail underperformance, and many
strategies that look profitable GROSS are negative NET. So `evaluate` applies this to every
result by default (config `costs.enabled`), reporting gross vs net side by side, what fraction
of gross profit the costs consume, and the breakeven win rate / payoff those costs demand.

Every component is a round-trip fraction of notional (so it subtracts directly from a setup's
aligned return):
  - **spread** — crypto: a bps order-book spread; forex: a pip spread per pair, WIDENED by session
    (Asian/thin hours are wider), converted to a fraction of price.
  - **fees** — exchange taker fee, charged on entry AND exit.
  - **slippage** — volatility-scaled: `slippage_atr_mult × ATR/price` per side. Fixed slippage is
    a lie — it's worst exactly when you most need to exit.
  - **funding** — perp funding × holding period, SIGNED by direction (longs pay positive funding);
    this is what quietly kills long holds on perps. Crypto only.
  - **financing** — overnight/weekend financing × holding days, for forex CFD-style positions.
  - **tax** — a configurable drag on REALISED gains only (applied per winning trade).

Nothing here is a prediction; it makes the backtest's numbers honest rather than flattering.
"""

from __future__ import annotations

from dataclasses import dataclass
from statistics import mean, median
from typing import Optional

import pandas as pd

from src.config import Config
from src.data.base import CRYPTO, FOREX
from src.data.registry import asset_class_for
from src.indicators.features import COL_ATR
from src.market.adaptation import _forex_session
from src.signals.confluence import BULLISH

_TF_UNIT_MIN = {"m": 1, "h": 60, "d": 1440}
# Spread widens in thin sessions; the London/NY overlap is the tightest. Keyed by substring of
# `_forex_session`'s label so it stays in step with Phase 19's session names.
_SESSION_SPREAD_MULT = {"overlap": 0.8, "london": 1.0, "new york": 1.0, "tokyo": 1.6, "sydney": 1.9}


def _tf_minutes(timeframe: str) -> int:
    return int(timeframe[:-1]) * _TF_UNIT_MIN[timeframe[-1]]


def _session_mult(session: Optional[str]) -> float:
    if not session:
        return 1.0
    s = session.lower()
    for key, m in _SESSION_SPREAD_MULT.items():
        if key in s:
            return m
    return 1.2


def _pip_size(symbol: str) -> float:
    return 0.01 if "JPY" in symbol.upper() else 0.0001


@dataclass
class TradeCost:
    spread: float
    fees: float
    slippage: float
    funding: float          # signed (a short can EARN positive funding -> negative cost)
    financing: float

    @property
    def total(self) -> float:
        return self.spread + self.fees + self.slippage + self.funding + self.financing


class CostModel:
    """Per-trade round-trip cost as a fraction of notional, from config + the pair's asset class."""

    def __init__(self, symbol: str, cfg: Config):
        self.symbol = symbol
        self.asset = asset_class_for(symbol)
        self.c = cfg.costs
        self.tf_min = _tf_minutes(cfg.market.timeframe)

    def trade_cost(self, bias: str, entry: float, atr_pct: float, holding_hours: float,
                   session: Optional[str] = None) -> TradeCost:
        c = self.c
        if self.asset == FOREX:
            spread = (c.forex_spread_pips * _pip_size(self.symbol) / entry) * _session_mult(session)
        else:
            spread = c.crypto_spread_bps / 1e4
        fees = 2 * c.taker_fee_bps / 1e4
        slippage = 2 * c.slippage_atr_mult * max(0.0, atr_pct)

        funding = 0.0
        if self.asset == CRYPTO and c.funding_bps_8h:
            periods = holding_hours / 8.0
            direction = 1.0 if bias == BULLISH else -1.0    # longs pay positive funding
            funding = direction * (c.funding_bps_8h / 1e4) * periods

        financing = 0.0
        if self.asset == FOREX and c.forex_financing_bps_day:
            financing = (c.forex_financing_bps_day / 1e4) * (holding_hours / 24.0)

        return TradeCost(spread=spread, fees=fees, slippage=slippage, funding=funding, financing=financing)


@dataclass
class CostStats:
    n: int
    win_rate: Optional[float]
    avg_return: Optional[float]
    median_return: Optional[float]

    @classmethod
    def of(cls, returns: list[float]) -> "CostStats":
        if not returns:
            return cls(0, None, None, None)
        wins = sum(1 for r in returns if r > 0)
        return cls(len(returns), wins / len(returns), mean(returns), float(median(returns)))


@dataclass
class CostReport:
    """Gross vs net for a backtest, the cost breakdown, and the breakeven those costs demand."""

    gross: CostStats
    net: CostStats
    avg_cost: float                              # mean round-trip cost, fraction of notional
    avg_cost_bps: dict                           # per-component mean, in bps (incl. tax)
    tax_rate: float
    cost_share_of_gross_profit: Optional[float]  # total costs / gross P&L edge (>1 => net negative; None if edge <= 0)
    current_win_rate: Optional[float]
    current_payoff: Optional[float]              # avg win / avg loss (gross)
    breakeven_win_rate: Optional[float]          # win rate needed to net zero at the current payoff
    breakeven_payoff: Optional[float]            # payoff needed to net zero at the current win rate
    net_positive: bool

    def summary(self) -> str:
        def line(label: str, s: CostStats) -> str:
            if not s.n or s.win_rate is None:
                return f"  {label:6} n=0"
            return (f"  {label:6} n={s.n:<4} win-rate={s.win_rate * 100:5.1f}%  "
                    f"avg={s.avg_return * 100:+6.2f}%  median={s.median_return * 100:+6.2f}%")

        L = ["COSTS (net of spread + fees + slippage + funding/financing"
             + (f" + {self.tax_rate * 100:g}% tax" if self.tax_rate else "") + "):",
             line("gross", self.gross), line("net", self.net),
             "  per-trade cost: " + ", ".join(f"{k} {v:.1f}bps" for k, v in self.avg_cost_bps.items())]
        if self.cost_share_of_gross_profit is not None:
            L.append(f"  costs consume {self.cost_share_of_gross_profit * 100:.0f}% of the gross edge "
                     "(pre-cost P&L; >100% = net negative)")
        if self.breakeven_win_rate is not None:
            L.append(f"  BREAKEVEN: need win-rate {self.breakeven_win_rate * 100:.1f}% "
                     f"(current {self.current_win_rate * 100:.1f}%) at payoff {self.current_payoff:.2f}, "
                     f"OR payoff {self.breakeven_payoff:.2f} at the current win-rate")
        L.append("  => strategy is NET " + ("positive" if self.net_positive else "NEGATIVE after costs"))
        return "\n".join(L)


def apply_costs(outcomes, cfg: Config, *, featured: Optional[pd.DataFrame] = None,
                symbol: Optional[str] = None) -> Optional[CostReport]:
    """Subtract modelled costs from each setup's aligned return and summarise gross vs net.

    `outcomes` is any sequence of objects carrying `aligned_return`, `bias`, `entry`, `bar`,
    `time`, `horizon` (duck-typed so this module doesn't import the evaluator — no cycle).
    `featured` supplies ATR for volatility-scaled slippage; without it slippage is 0.
    """
    outcomes = list(outcomes)
    if not outcomes:
        return None
    model = CostModel(symbol or cfg.market.symbol, cfg)
    atr_col = featured[COL_ATR] if (featured is not None and COL_ATR in featured.columns) else None

    gross, net = [], []
    comp = {k: 0.0 for k in ("spread", "fees", "slippage", "funding", "financing", "tax")}
    total_cost = 0.0
    for o in outcomes:
        atr = atr_col.iloc[o.bar] if atr_col is not None and 0 <= o.bar < len(atr_col) else float("nan")
        atr_pct = 0.0 if pd.isna(atr) else float(atr) / o.entry
        session = _forex_session(pd.Timestamp(o.time).hour) if model.asset == FOREX else None
        tc = model.trade_cost(o.bias, o.entry, atr_pct, o.horizon * model.tf_min / 60.0, session)

        net_pre_tax = o.aligned_return - tc.total
        tax = cfg.costs.tax_rate * max(0.0, net_pre_tax)
        gross.append(o.aligned_return)
        net.append(net_pre_tax - tax)
        for k in ("spread", "fees", "slippage", "funding", "financing"):
            comp[k] += getattr(tc, k)
        comp["tax"] += tax
        total_cost += tc.total + tax

    n = len(outcomes)
    avg_cost_bps = {k: round(v / n * 1e4, 2) for k, v in comp.items()}
    wins = [r for r in gross if r > 0]
    losses = [-r for r in gross if r < 0]
    gross_pnl = sum(gross)     # the pre-cost edge; costs eating >100% of it => net negative
    W = mean(wins) if wins else None
    Lavg = mean(losses) if losses else None
    p = len(wins) / n
    c = total_cost / n     # avg all-in cost per trade (incl. tax)

    breakeven_win_rate = breakeven_payoff = current_payoff = None
    if W is not None and Lavg is not None and Lavg > 0:
        current_payoff = round(W / Lavg, 3)
        breakeven_win_rate = round((Lavg + c) / (W + Lavg), 4)
        if p > 0:
            breakeven_payoff = round((1 - p + c / Lavg) / p, 3)

    net_stats = CostStats.of(net)
    return CostReport(
        gross=CostStats.of(gross),
        net=net_stats,
        avg_cost=round(c, 6),
        avg_cost_bps=avg_cost_bps,
        tax_rate=cfg.costs.tax_rate,
        cost_share_of_gross_profit=(round(total_cost / gross_pnl, 4) if gross_pnl > 0 else None),
        current_win_rate=round(p, 4),
        current_payoff=current_payoff,
        breakeven_win_rate=breakeven_win_rate,
        breakeven_payoff=breakeven_payoff,
        net_positive=bool(net_stats.avg_return is not None and net_stats.avg_return > 0),
    )
