"""Feature 10 — the honest cost model.

Unit-tests the per-component maths (spread/fees/slippage/funding/financing/tax), the gross→net
subtraction, the breakeven analysis, and that `evaluate` applies costs by default.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import pytest

from src.backtest.costs import CostModel, apply_costs
from src.config import CostsConfig, load_config
from src.indicators.features import add_features
from src.structure.swings import find_swings

_FIXTURE = Path(__file__).parent / "fixtures" / "btc_1h_sample.csv"


@pytest.fixture(scope="module")
def cfg():
    return load_config()


def _zero_costs(cfg, **over):
    z = dict(crypto_spread_bps=0, forex_spread_pips=0, taker_fee_bps=0, slippage_atr_mult=0,
             funding_bps_8h=0, forex_financing_bps_day=0, tax_rate=0)
    z.update(over)
    return cfg.model_copy(update={"costs": CostsConfig(**z)})


@dataclass
class _O:                       # duck-typed setup outcome
    aligned_return: float
    bias: str = "bullish"
    entry: float = 100.0
    bar: int = 0
    time: str = "2025-01-01 10:00:00"
    horizon: int = 24


# --- per-component maths --------------------------------------------------------------------

def test_crypto_components(cfg):
    m = CostModel("BTC/USDT", cfg)               # crypto
    tc = m.trade_cost("bullish", entry=100.0, atr_pct=0.02, holding_hours=24)
    assert tc.spread == cfg.costs.crypto_spread_bps / 1e4
    assert tc.fees == 2 * cfg.costs.taker_fee_bps / 1e4
    assert tc.slippage == pytest.approx(2 * cfg.costs.slippage_atr_mult * 0.02)
    assert tc.financing == 0.0                   # crypto has no CFD financing


def test_funding_is_signed_by_direction(cfg):
    m = CostModel("BTC/USDT", cfg)
    long_c = m.trade_cost("bullish", 100.0, 0.0, holding_hours=48)
    short_c = m.trade_cost("bearish", 100.0, 0.0, holding_hours=48)
    assert long_c.funding > 0 and short_c.funding < 0          # longs pay positive funding, shorts earn
    assert long_c.funding == pytest.approx(-short_c.funding)


def test_forex_spread_is_session_aware(cfg):
    m = CostModel("EUR/USD", cfg)
    assert m.asset == "forex"
    tokyo = m.trade_cost("bullish", 1.10, 0.0, 24, session="Tokyo").spread
    overlap = m.trade_cost("bullish", 1.10, 0.0, 24, session="London/New York overlap").spread
    assert tokyo > overlap > 0                                 # Asian hours are wider
    assert m.trade_cost("bullish", 1.10, 0.0, 24).financing > 0   # forex has overnight financing


# --- gross -> net + breakeven ---------------------------------------------------------------

def test_net_below_gross_and_flags_negative(cfg):
    outs = [_O(0.02), _O(-0.01), _O(0.015), _O(-0.02)]
    r = apply_costs(outs, cfg)
    assert r.net.avg_return < r.gross.avg_return                # costs drag every trade
    assert r.avg_cost > 0 and r.avg_cost_bps["fees"] > 0
    assert isinstance(r.net_positive, bool)


def test_zero_costs_leave_net_equal_gross_and_zero_cost_breakeven(cfg):
    outs = [_O(0.10), _O(-0.05), _O(0.10), _O(-0.05)]          # W=0.10, L=0.05, p=0.5
    r = apply_costs(outs, _zero_costs(cfg))
    assert r.net.avg_return == pytest.approx(r.gross.avg_return)
    assert r.avg_cost == pytest.approx(0.0, abs=1e-9)
    # zero-cost breakeven win rate = L/(W+L) = 0.05/0.15 = 1/3
    assert r.breakeven_win_rate == pytest.approx(1 / 3, abs=1e-3)
    assert r.current_payoff == pytest.approx(2.0)              # W/L


def test_tax_hits_only_winners(cfg):
    # only spread etc. off; tax 50%. winner +0.10 -> net 0.05; loser -0.10 -> unchanged.
    c = _zero_costs(cfg, tax_rate=0.5)
    r = apply_costs([_O(0.10), _O(-0.10)], c)
    assert r.net.avg_return == pytest.approx((0.05 + -0.10) / 2)
    assert r.avg_cost_bps["tax"] == pytest.approx(0.10 * 0.5 / 2 * 1e4)   # tax averaged over both trades


def test_cost_share_of_gross_profit(cfg):
    r = apply_costs([_O(0.05), _O(0.05)], cfg)                 # all winners -> gross profit = 0.10
    assert 0.0 < r.cost_share_of_gross_profit < 1.0
    assert apply_costs([_O(-0.01)], cfg).cost_share_of_gross_profit is None   # no gross profit


# --- applied by default through evaluate ----------------------------------------------------

def test_evaluate_applies_costs_by_default(cfg):
    df = pd.read_csv(_FIXTURE, index_col="timestamp", parse_dates=["timestamp"])
    df.index = pd.to_datetime(df.index, utc=True)
    add_features(df, cfg); find_swings(df, cfg.structure.swing_sensitivity)  # smoke: shapes ok
    from src.backtest.evaluate import evaluate

    rep = evaluate(df, cfg, horizon=12, step=2)
    if rep.overall.n:
        assert rep.costs is not None
        assert rep.costs.gross.n == rep.overall.n
        assert rep.costs.net.avg_return <= rep.costs.gross.avg_return
        assert "net" in rep.summary().lower() and "breakeven" in rep.summary().lower()
    # disabling turns it off
    off = cfg.model_copy(update={"costs": cfg.costs.model_copy(update={"enabled": False})})
    assert evaluate(df, off, horizon=12, step=2).costs is None
