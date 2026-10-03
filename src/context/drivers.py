"""ROADMAP D3 — what moves each market, and when markets are secretly one bet.

Three things, all CONTEXT (conditions, never direction):

  DRIVERS     a fixed table: which currencies' calendar events matter to a market (for the event list
              and the "news soon" caution), headline keywords, and its CONVENTIONAL macro drivers as
              plain labels (convention, not a measured fact).
  hypothesis  co-movement of the market's daily returns with proxies the app already has — the dollar
              (inverse EUR/USD), gold, crypto (BTC) — over a dated window, joined on common dates
              (crypto trades 7 days, forex 5). A self-proxy is excluded (EUR/USD vs the dollar is −1 by
              construction). Below |ρ| `driver_min_rho` or `corr_min_n` days it says "no clear
              co-movement". Worded as co-movement: never a cause, never a direction.
  correlation the followed markets' pairwise correlation over `corr_window_days`; ρ ≥ `corr_warn` is
              flagged as "moving as one bet" (BTC/ETH/SOL nearly always will — that's correct).
Thresholds are config values fixed before looking.
"""

from __future__ import annotations

import pandas as pd

DRIVERS = {
    "BTC/USDT": {"currencies": ["USD"], "keywords": ["bitcoin", "btc", "crypto"],
                 "conventional": ["US dollar liquidity and Fed policy", "risk appetite (stocks, tech)", "ETF flows"]},
    "ETH/USDT": {"currencies": ["USD"], "keywords": ["ether", "ethereum", "eth ", "crypto"],
                 "conventional": ["crypto market beta (BTC)", "US dollar liquidity", "risk appetite"]},
    "SOL/USDT": {"currencies": ["USD"], "keywords": ["solana", "sol ", "crypto"],
                 "conventional": ["crypto market beta (BTC)", "risk appetite"]},
    "XRP/USDT": {"currencies": ["USD"], "keywords": ["xrp", "ripple", "crypto"],
                 "conventional": ["crypto market beta (BTC)", "regulatory news"]},
    "EUR/USD": {"currencies": ["EUR", "USD"], "keywords": ["eur/usd", "euro", "ecb", "fed", "dollar"],
                "conventional": ["ECB vs Fed rate expectations", "euro-area vs US data", "risk sentiment"]},
    "GBP/USD": {"currencies": ["GBP", "USD"], "keywords": ["gbp/usd", "pound", "sterling", "boe", "fed"],
                "conventional": ["BoE vs Fed rate expectations", "UK vs US data"]},
    "XAU/USD": {"currencies": ["USD"], "keywords": ["gold", "xau"],
                "conventional": ["US real yields", "the US dollar", "safe-haven demand"]},
    "WTI/USD": {"currencies": ["USD"], "keywords": ["oil", "crude", "wti", "opec"],
                "conventional": ["supply (OPEC+, inventories)", "global demand", "the US dollar"]},
}
DEFAULT = {"currencies": ["USD"], "keywords": ["crypto"], "conventional": ["crypto market beta (BTC)"]}

# proxy label -> (symbol, sign): the dollar is the inverse of EUR/USD (the euro is ~57% of the dollar index)
PROXIES = {"the dollar (inverse EUR/USD)": ("EUR/USD", -1), "gold": ("XAU/USD", 1), "crypto (BTC)": ("BTC/USDT", 1)}


def info(symbol: str) -> dict:
    return DRIVERS.get(symbol, DEFAULT)


def daily_returns(df: pd.DataFrame) -> pd.Series:
    """Close-to-close daily returns keyed by calendar DATE (so 7-day and 5-day markets join cleanly)."""
    s = df["close"].astype(float)
    s.index = pd.to_datetime(df.index, utc=True).date
    s = s[~pd.Index(s.index).duplicated(keep="last")]
    return s.pct_change().dropna()


def _corr(a: pd.Series, b: pd.Series, window: int) -> tuple[float | None, int, str | None, str | None]:
    j = pd.concat([a, b], axis=1, join="inner").dropna().iloc[-window:]
    if len(j) < 3:
        return None, len(j), None, None
    rho = j.iloc[:, 0].corr(j.iloc[:, 1])
    return (None if pd.isna(rho) else round(float(rho), 3)), len(j), str(j.index[0]), str(j.index[-1])


def hypothesis(symbol: str, returns: dict[str, pd.Series], *, window: int = 60, min_n: int = 30,
               min_rho: float = 0.5) -> dict:
    """Co-movement with the dollar / gold / crypto — the strongest one is the 'driver hypothesis'."""
    own = returns.get(symbol)
    items = []
    for label, (proxy, sign) in PROXIES.items():
        if proxy == symbol or own is None or proxy not in returns:
            continue
        rho, n, start, end = _corr(own, returns[proxy] * sign, window)
        items.append({"proxy": label, "rho": rho, "n": n, "start": start, "end": end})
    usable = [i for i in items if i["rho"] is not None and i["n"] >= min_n]
    best = max(usable, key=lambda i: abs(i["rho"]), default=None)
    if best is None or abs(best["rho"]) < min_rho:
        tested = " or ".join(i["proxy"] for i in items) or "the available proxies"
        span = f" over the last {window} days" if items else ""
        text = f"no clear co-movement with {tested}{span} (|correlation| under {min_rho})"
        best = None
    else:
        text = (f"over {best['start']} – {best['end']} ({best['n']} common days) {symbol}'s daily moves went "
                f"{'with' if best['rho'] > 0 else 'against'} {best['proxy']} (correlation {best['rho']:+.2f}). "
                "A co-movement, not a cause — and not a direction.")
    return {"items": items, "strongest": best, "text": text, "conventional": info(symbol)["conventional"]}


def correlation(symbols: list[str], returns: dict[str, pd.Series], *, window: int = 60, warn: float = 0.7) -> dict:
    pairs, warnings = [], []
    avail = [s for s in symbols if s in returns]
    for i, a in enumerate(avail):
        for b in avail[i + 1:]:
            rho, n, start, end = _corr(returns[a], returns[b], window)
            pairs.append({"a": a, "b": b, "rho": rho, "n": n, "start": start, "end": end})
            if rho is not None and rho >= warn:
                warnings.append({"a": a, "b": b, "rho": rho, "n": n,
                                 "text": f"{a} and {b} moved almost as one over {start} – {end} (correlation {rho:.2f}, "
                                         f"{n} days): positions in both are largely the same bet."})
    return {"symbols": avail, "pairs": pairs, "warnings": warnings, "window": window, "threshold": warn}


def returns_for(symbols: list[str], candles_for) -> dict[str, pd.Series]:
    """Daily returns per symbol; a market that can't load is left out (never fatal)."""
    out = {}
    for s in symbols:
        try:
            out[s] = daily_returns(candles_for(s))
        except Exception:
            continue
    return out
