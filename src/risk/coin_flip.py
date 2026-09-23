"""ROADMAP A7 — the risk calculator's honest default: a COST-ADJUSTED coin flip.

The testing found no edge, so the honest default is a ZERO-EDGE win rate — a fair coin flip —
minus what trading costs take. "Fair" depends on the payoff ratio R (avg win / avg loss, in units
of the amount risked): with no edge, a target R away is hit before a stop 1 away with probability
1/(1+R) — 50% only at 1:1, 40% at 1.5:1. (Using 50% at 1.5:1 would quietly assume a +0.25R edge.)
With a round-trip cost c (in units of the amount risked), the win rate whose expectancy is exactly
−c at your payoff is

    p = (1 − c) / (1 + R)        →  p·R − (1 − p) = −c

— a coin flip that pays its costs. That is the default the calculator starts from.
"""

from __future__ import annotations

from src.backtest.costs import CostModel
from src.config import Config


def coin_flip_win_rate(cost_in_r: float, payoff_ratio: float) -> float:
    """Zero-edge win rate net of costs: p = (1 − c)/(1 + R), clipped to [0, 1/(1+R)].
    `cost_in_r` = round-trip cost ÷ amount risked. Its expectancy is exactly −c."""
    if payoff_ratio <= 0:
        raise ValueError("payoff_ratio must be positive")
    fair = 1.0 / (1.0 + payoff_ratio)
    return max(0.0, min(fair, (1.0 - max(0.0, cost_in_r)) / (1.0 + payoff_ratio)))


def cost_adjusted_coin_flip(symbol: str, timeframe: str, cfg: Config, *, entry: float, stop: float,
                            payoff_ratio: float, atr_pct: float, horizon_bars: int = 24) -> dict:
    """The default win rate for `symbol`: round-trip cost from the Feature-10 cost model (spread,
    fees, ATR-scaled slippage, funding/financing over `horizon_bars` of `timeframe`), expressed in
    units of the risk (entry→stop distance), then `coin_flip_win_rate`. `atr_pct` is a fraction."""
    if entry <= 0 or stop <= 0 or entry == stop:
        raise ValueError("entry and stop must be positive and different")
    req = cfg.model_copy(update={"market": cfg.market.model_copy(update={"symbol": symbol, "timeframe": timeframe})})
    model = CostModel(symbol, req)
    holding_hours = horizon_bars * model.tf_min / 60.0
    tc = model.trade_cost("bullish", entry, atr_pct, holding_hours)
    cost_frac = max(0.0, tc.total)                    # of notional
    risk_frac = abs(entry - stop) / entry             # of notional
    cost_in_r = cost_frac / risk_frac
    return {
        "win_rate": round(coin_flip_win_rate(cost_in_r, payoff_ratio), 4),
        "fair_win_rate": round(1.0 / (1.0 + payoff_ratio), 4),     # zero edge, before costs
        "cost_pct": round(cost_frac * 100, 4),
        "risk_pct": round(risk_frac * 100, 4),
        "cost_in_r": round(cost_in_r, 4),
        "payoff_ratio": payoff_ratio,
        "horizon_bars": horizon_bars,
        "source": "coin flip, cost-adjusted",
    }
