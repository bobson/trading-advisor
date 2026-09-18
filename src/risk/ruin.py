"""Feature 9 — risk of ruin & position sizing: the math of survival.

The single most protective thing in the app, and the one almost nobody runs. Someone risking 5%
a trade at a 40% win rate is mathematically doomed no matter how good the analysis is — this
module makes that concrete and sobering rather than abstract.

Model. Each trade risks a fixed fraction `f` of *current* equity (multiplicative / fractional
betting). A win (prob `p`) multiplies equity by `1 + b·f`; a loss by `1 − f`, where `b` is the
payoff ratio (average win / average loss). In log-equity this is a random walk with drift, which
gives a clean two-barrier hitting probability for "ruin" (a drawdown threshold, e.g. −50%) before
"success" (e.g. doubling).

Nothing here predicts price. It quantifies survival given YOUR measured win rate and payoff ratio,
and it is deliberately framed to alarm, not reassure.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np

_EPS = 1e-9


def _clamp_fraction(f: float) -> float:
    """Risk fraction must live in (0, 1): f>=1 means a single loss wipes you out and makes
    log(1−f) undefined; f<=0 means no bet."""
    return min(max(float(f), _EPS), 1.0 - _EPS)


# --- Kelly sizing ---------------------------------------------------------------------------

@dataclass
class Kelly:
    edge: float          # p·b − q  (expected profit per unit risked; <=0 means no edge)
    full: float          # full-Kelly risk fraction (0 when there's no edge)
    half: float
    quarter: float
    has_edge: bool


def kelly(win_rate: float, payoff_ratio: float) -> Kelly:
    """Full Kelly fraction f* = p − q/b (= (p·b − q)/b) for the multiplicative model, plus the
    half- and quarter-Kelly that practitioners actually use. A non-positive edge → 0 (don't bet)."""
    p = float(win_rate)
    q = 1.0 - p
    b = float(payoff_ratio)
    if b <= 0:
        return Kelly(edge=-q, full=0.0, half=0.0, quarter=0.0, has_edge=False)
    edge = p * b - q
    full = max(0.0, edge / b)
    return Kelly(edge=round(edge, 4), full=round(full, 4), half=round(full / 2, 4),
                 quarter=round(full / 4, 4), has_edge=edge > 0)


# --- Risk of ruin: analytic (diffusion approximation) ---------------------------------------

def risk_of_ruin_analytic(
    win_rate: float, payoff_ratio: float, risk_fraction: float,
    *, drawdown: float = 0.5, target: float = 2.0,
) -> float:
    """Probability of hitting a `drawdown` (0.5 = −50%) before reaching `target` (2.0 = double).

    Log-equity is a random walk with per-trade drift μ and variance σ²; the two-barrier hitting
    probability is P = (s(U)−1)/(s(U)−s(L)) with s(x)=exp(−2μx/σ²), L=ln(drawdown)<0, U=ln(target)>0.
    (The trade count cancels — this is a hitting *probability*, not a time.) A diffusion
    approximation of the discrete process; Monte Carlo confirms it and handles the overshoot at
    large f.
    """
    p = float(win_rate)
    if p <= 0.0:
        return 1.0
    if p >= 1.0:
        return 0.0
    q = 1.0 - p
    f = _clamp_fraction(risk_fraction)
    b = float(payoff_ratio)

    up = math.log1p(b * f)          # log(1 + b·f)
    dn = math.log1p(-f)             # log(1 − f)  (negative)
    mu = p * up + q * dn
    var = p * (up - mu) ** 2 + q * (dn - mu) ** 2
    if var < _EPS:                  # degenerate (no dispersion): survival is deterministic
        return 0.0 if mu >= 0 else 1.0

    L = math.log(drawdown)          # < 0
    U = math.log(target)            # > 0
    k = -2.0 * mu / var
    if abs(k) < _EPS:               # driftless limit
        return U / (U - L)
    # clamp exponents so extreme drift can't overflow (limits to ~0 or ~1 correctly)
    def _e(x: float) -> float:
        return math.exp(max(-700.0, min(700.0, x)))
    su, sl = _e(k * U), _e(k * L)
    prob = (su - 1.0) / (su - sl)
    return float(min(1.0, max(0.0, prob)))


# --- Risk of ruin: Monte Carlo (vectorised) -------------------------------------------------

@dataclass
class MonteCarloRuin:
    prob: float              # fraction of paths that hit the drawdown barrier first
    ci_low: float
    ci_high: float
    unresolved: float        # fraction still running at max_trades (bias check — should be ~0)
    n_paths: int


def _wilson(successes: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score interval for a proportion — sane even for small n / extreme rates."""
    if n == 0:
        return (0.0, 1.0)
    phat = successes / n
    denom = 1 + z * z / n
    center = (phat + z * z / (2 * n)) / denom
    half = z * math.sqrt(phat * (1 - phat) / n + z * z / (4 * n * n)) / denom
    return (round(max(0.0, center - half), 4), round(min(1.0, center + half), 4))


def risk_of_ruin_mc(
    win_rate: float, payoff_ratio: float, risk_fraction: float,
    *, drawdown: float = 0.5, target: float = 2.0,
    n_paths: int = 10_000, max_trades: int = 20_000, seed: int | None = None,
) -> MonteCarloRuin:
    """Simulate `n_paths` equity paths of the multiplicative process to the first barrier.

    `max_trades` must be large enough that essentially every path resolves — a truncated path
    counted as "survived" would UNDER-estimate ruin, so `unresolved` is reported as a bias check.
    """
    rng = np.random.default_rng(seed)
    p = float(win_rate)
    f = _clamp_fraction(risk_fraction)
    up = math.log1p(payoff_ratio * f)
    dn = math.log1p(-f)
    lower, upper = math.log(drawdown), math.log(target)

    logeq = np.zeros(n_paths)
    active = np.ones(n_paths, dtype=bool)
    ruined = np.zeros(n_paths, dtype=bool)
    for _ in range(max_trades):
        if not active.any():
            break
        wins = rng.random(n_paths) < p
        step = np.where(wins, up, dn)
        logeq[active] += step[active]
        hit_low = active & (logeq <= lower)
        hit_high = active & (logeq >= upper)
        ruined |= hit_low
        active &= ~(hit_low | hit_high)

    n_ruined = int(ruined.sum())
    prob = n_ruined / n_paths
    lo, hi = _wilson(n_ruined, n_paths)
    return MonteCarloRuin(prob=round(prob, 4), ci_low=lo, ci_high=hi,
                          unresolved=round(active.sum() / n_paths, 4), n_paths=n_paths)


# --- Drawdown distribution from real trade returns (bootstrap) ------------------------------

def max_drawdown(equity: np.ndarray) -> float:
    """Largest peak-to-trough decline of an equity curve, as a positive fraction (0.4 = −40%)."""
    peak = np.maximum.accumulate(equity)
    return float(np.max((peak - equity) / peak))


def longest_losing_streak(returns: np.ndarray) -> int:
    """Longest run of consecutive losing trades."""
    best = cur = 0
    for r in returns:
        cur = cur + 1 if r < 0 else 0
        best = max(best, cur)
    return best


@dataclass
class DrawdownDistribution:
    median: float
    p90: float
    worst: float
    median_losing_streak: int
    worst_losing_streak: int
    horizon: int
    n_paths: int
    block_size: int
    note: str


def bootstrap_drawdowns(
    trade_returns, *, n_paths: int = 10_000, horizon: int | None = None,
    block_size: int = 1, seed: int | None = None,
) -> DrawdownDistribution:
    """Resample your ACTUAL historical per-trade returns (fat-tailed — no normal assumption) into
    `n_paths` equity curves and report the median / 90th-percentile / worst max-drawdown and the
    losing-streak distribution.

    `block_size` selects a moving-block bootstrap: block_size=1 is the plain i.i.d. bootstrap,
    which DESTROYS loss clustering and therefore *understates* the losing streak — pass a larger
    block (e.g. ~5–10) to retain some clustering. The note records which was used.
    """
    r = np.asarray(list(trade_returns), dtype=float)
    if r.size == 0:
        raise ValueError("need at least one historical trade return")
    h = int(horizon or r.size)
    rng = np.random.default_rng(seed)
    bs = max(1, int(block_size))

    dds = np.empty(n_paths)
    streaks = np.empty(n_paths, dtype=int)
    n_blocks = math.ceil(h / bs)
    for i in range(n_paths):
        if bs == 1:
            path = r[rng.integers(0, r.size, size=h)]
        else:  # circular moving-block bootstrap
            starts = rng.integers(0, r.size, size=n_blocks)
            path = np.concatenate([np.take(r, range(s, s + bs), mode="wrap") for s in starts])[:h]
        equity = np.cumprod(1.0 + path)
        dds[i] = max_drawdown(np.concatenate([[1.0], equity]))
        streaks[i] = longest_losing_streak(path)

    note = ("i.i.d. bootstrap — loss clustering is NOT modelled, so the losing streak is a lower "
            "bound" if bs == 1 else f"moving-block bootstrap (block={bs}) — partial loss clustering retained")
    return DrawdownDistribution(
        median=round(float(np.median(dds)), 4),
        p90=round(float(np.percentile(dds, 90)), 4),
        worst=round(float(np.max(dds)), 4),
        median_losing_streak=int(np.median(streaks)),
        worst_losing_streak=int(np.max(streaks)),
        horizon=h, n_paths=n_paths, block_size=bs, note=note,
    )


def kelly_drawdown_pain(
    win_rate: float, payoff_ratio: float, *, horizon: int = 200,
    n_paths: int = 5_000, seed: int | None = None,
) -> dict:
    """Show, concretely, how much full Kelly hurts: the median and 90th-percentile max-drawdown
    over `horizon` trades at full / half / quarter Kelly. Full Kelly is growth-optimal and
    psychologically unbearable — routinely 50%+ drawdowns."""
    k = kelly(win_rate, payoff_ratio)
    rng = np.random.default_rng(seed)
    out = {}
    for label, f in (("full", k.full), ("half", k.half), ("quarter", k.quarter)):
        if f <= 0:
            out[label] = {"fraction": 0.0, "median_drawdown": 0.0, "p90_drawdown": 0.0}
            continue
        up, dn = math.log1p(payoff_ratio * f), math.log1p(-f)
        wins = rng.random((n_paths, horizon)) < win_rate
        steps = np.where(wins, up, dn)
        equity = np.exp(np.cumsum(steps, axis=1))
        equity = np.concatenate([np.ones((n_paths, 1)), equity], axis=1)
        dd = [max_drawdown(equity[i]) for i in range(n_paths)]
        out[label] = {"fraction": round(f, 4), "median_drawdown": round(float(np.median(dd)), 4),
                      "p90_drawdown": round(float(np.percentile(dd, 90)), 4)}
    return out


# --- Position-size calculator (the everyday-use surface) ------------------------------------

@dataclass
class PositionSize:
    risk_amount: float       # account · risk_fraction (the most you lose if the stop hits)
    stop_distance: float     # |entry − stop| per unit
    stop_distance_pct: float
    units: float             # size in units of the instrument
    position_value: float    # units · entry
    leverage: float          # position_value / account


def position_size(account: float, entry: float, stop: float, risk_fraction: float) -> PositionSize:
    """From account size, entry, and stop, the position that risks exactly `risk_fraction` of the
    account if the stop is hit. Raises on nonsensical inputs (a zero-width stop is infinite size)."""
    if account <= 0 or entry <= 0:
        raise ValueError("account and entry must be positive")
    if not (0 < risk_fraction < 1):
        raise ValueError("risk_fraction must be in (0, 1)")
    stop_distance = abs(entry - stop)
    if stop_distance < _EPS:
        raise ValueError("stop distance is zero — that implies an infinite position")
    risk_amount = account * risk_fraction
    units = risk_amount / stop_distance
    position_value = units * entry
    return PositionSize(
        risk_amount=round(risk_amount, 2),
        stop_distance=round(stop_distance, 6),
        stop_distance_pct=round(stop_distance / entry * 100, 3),
        units=round(units, 6),
        position_value=round(position_value, 2),
        leverage=round(position_value / account, 2),
    )


# --- The risk-per-trade × win-rate ruin table ----------------------------------------------

DEFAULT_RISK_FRACTIONS = [0.0025, 0.005, 0.01, 0.02, 0.03, 0.05]
DEFAULT_WIN_RATES = [0.35, 0.40, 0.45, 0.50, 0.55, 0.60]


def ruin_table(
    payoff_ratio: float = 1.0, *,
    risk_fractions=None, win_rates=None, drawdown: float = 0.5, target: float = 2.0,
) -> dict:
    """A grid of P(50% drawdown before doubling) over risk-per-trade × win-rate at a fixed payoff
    ratio, so the cliff is visible: at 1:1 payoff, even a 50% win rate ruins you at high risk."""
    rfs = risk_fractions or DEFAULT_RISK_FRACTIONS
    wrs = win_rates or DEFAULT_WIN_RATES
    rows = []
    for rf in rfs:
        rows.append({
            "risk_fraction": rf,
            "ruin": [round(risk_of_ruin_analytic(wr, payoff_ratio, rf, drawdown=drawdown, target=target), 4)
                     for wr in wrs],
        })
    return {"payoff_ratio": payoff_ratio, "win_rates": list(wrs), "drawdown": drawdown,
            "target": target, "rows": rows}


# --- Real inputs: measured win rate / payoff, with confidence intervals ---------------------

@dataclass
class MeasuredStats:
    win_rate: float | None
    win_rate_ci: tuple[float, float] | None   # Wilson interval (wide when n is thin)
    payoff_ratio: float | None                # None when unmeasured (must be user-supplied)
    n: int
    source: str
    thin: bool                                # True when n is too small to trust a point estimate


def gather_measured_stats(
    symbol: str, timeframe: str, *, base_rates: dict | None = None,
    conn=None, thin_below: int = 30,
) -> MeasuredStats:
    """Pull win rate (and, when the journal exists, payoff ratio) from real data — the backtest
    base rates and the prediction journal — never a user guess. Where the sample is thin, a Wilson
    interval is attached and `thin` is set, so callers show a range instead of a false point.

    Sources, best-effort and graceful:
      - `data/base_rates.json` (Recommendation #2) → overall win rate + n. Payoff ratio is NOT
        stored there and CANNOT be reconstructed from win rate + avg return (underdetermined), so
        it stays None until the journal supplies it.
      - `journal_entries` (Feature 4, not built yet) → win rate AND payoff ratio from resolved
        reads. Queried defensively so it simply lights up when that table appears.
    """
    win_rate: float | None = None
    payoff_ratio: float | None = None
    n = 0
    source = "none"

    # Prefer the journal (has both win rate and payoff) if it's there.
    j = _journal_stats(symbol, timeframe, conn=conn)
    if j is not None:
        win_rate, payoff_ratio, n, source = j["win_rate"], j["payoff_ratio"], j["n"], "journal"
    else:
        rates = base_rates if base_rates is not None else _load_base_rates()
        entry = (rates or {}).get(f"{symbol}|{timeframe}", {}).get("overall")
        if entry and entry.get("n") and entry.get("win_rate") is not None:
            win_rate, n, source = float(entry["win_rate"]), int(entry["n"]), "backtest"

    ci = None
    if win_rate is not None and n > 0:
        ci = _wilson(round(win_rate * n), n)
    return MeasuredStats(win_rate=win_rate, win_rate_ci=ci, payoff_ratio=payoff_ratio,
                         n=n, source=source, thin=(0 < n < thin_below))


def _load_base_rates() -> dict:
    from src.backtest.base_rate import load_base_rates
    return load_base_rates()


def _journal_stats(symbol: str, timeframe: str, *, conn=None) -> dict | None:
    """Win rate + payoff ratio from resolved journal entries, or None if the journal/table isn't
    there yet. Defensive: Feature 4 hasn't been built, so a missing table is expected."""
    import sqlite3

    own = conn is None
    try:
        if own:
            db = Path("data/wizard.db")
            if not db.exists():
                return None
            conn = sqlite3.connect(str(db))
        rows = conn.execute(
            "SELECT outcome_return FROM journal_entries WHERE symbol=? AND timeframe=? "
            "AND outcome_return IS NOT NULL",
            (symbol, timeframe),
        ).fetchall()
    except sqlite3.Error:
        return None            # no journal_entries table yet (Feature 4) — expected
    finally:
        if own and conn is not None:
            conn.close()

    returns = [float(r[0]) for r in rows]
    if len(returns) < 1:
        return None
    wins = [x for x in returns if x > 0]
    losses = [-x for x in returns if x < 0]
    win_rate = len(wins) / len(returns)
    payoff = (np.mean(wins) / np.mean(losses)) if wins and losses else None
    return {"win_rate": win_rate, "payoff_ratio": (round(float(payoff), 3) if payoff else None),
            "n": len(returns)}
