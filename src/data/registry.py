"""Phase 13 — pair registry + the app-facing data facade.

`get_candles(symbol, timeframe, cfg)` is the single call the rest of the app uses to obtain
candles: it selects a provider by the pair's asset class, so callers never branch on
crypto-vs-forex. It is CACHE-FIRST — a cached CSV is reused as-is (this keeps the offline
workflow and makes the Phase-12 regression byte-identical); only on a miss (or `refresh=True`)
does it hit the live provider and cache the result. Every returned frame passes through the
quality gate.

NOTE (conscious deferral): cache-first has no TTL — a cached symbol won't see new candles
until `refresh=True`. That's correct for Phase 13 (preserves offline + regression); freshness
is Phase 24's short-TTL cache.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from src.config import Config
from src.data.base import CRYPTO, FOREX, DataProvider
from src.data.cache import DATA_DIR, cache_path, load_candles, save_candles
from src.data.crypto_ccxt import CryptoProvider
from src.data.forex_api import ForexProvider
from src.data.quality import check_candles, clean_candles

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Pair:
    symbol: str
    asset_class: str
    label: str


# The pairs the UI offers. Crypto works today; forex pairs are registered but not fetchable
# until Phase 26 — selecting one raises a clear error from ForexProvider.
PAIRS: list[Pair] = [
    Pair("BTC/USDT", CRYPTO, "Bitcoin / Tether"),
    Pair("ETH/USDT", CRYPTO, "Ethereum / Tether"),
    Pair("SOL/USDT", CRYPTO, "Solana / Tether"),
    Pair("XRP/USDT", CRYPTO, "XRP / Tether"),
    Pair("EUR/USD", FOREX, "Euro / US Dollar"),
    Pair("GBP/USD", FOREX, "British Pound / US Dollar"),
]

# ROADMAP A8: gold and oil — traded 24/5 over the counter with tick (not real) volume, so they use
# the forex asset class (the market adaptation then flags volume, sessions and weekend gaps). Kept
# OUT of `PAIRS` on purpose: the encyclopedia / verdict-record builds and the scanner default to
# `list_pairs()`, and must not silently mix commodities into their all-markets rows or spend
# Twelve Data credits on every scan. The UI and the morning report reach them via `all_pairs()`.
COMMODITIES: list[Pair] = [
    Pair("XAU/USD", FOREX, "Gold (spot) / US Dollar"),
    Pair("WTI/USD", FOREX, "Crude oil WTI / US Dollar"),
]

# Symbols whose candles come from a different provider than their asset class's default.
# WTI isn't on Twelve Data's free plan -> OANDA (practice account).
PROVIDER_OVERRIDE = {"WTI/USD": "oanda"}

_BY_SYMBOL = {p.symbol: p for p in PAIRS + COMMODITIES}


def all_pairs() -> list[Pair]:
    """Every registered pair, commodities included (the UI's picker and the morning report)."""
    return list(PAIRS) + list(COMMODITIES)


def list_pairs(asset_class: str | None = None) -> list[Pair]:
    """The selectable pairs, optionally filtered to one asset class."""
    if asset_class is None:
        return list(PAIRS)
    return [p for p in PAIRS if p.asset_class == asset_class]


def asset_class_for(symbol: str) -> str:
    """Asset class for a symbol. Registered pairs are authoritative; an unknown symbol
    defaults to crypto (the only live provider), so an ad-hoc ccxt symbol still works.
    """
    pair = _BY_SYMBOL.get(symbol)
    return pair.asset_class if pair else CRYPTO


def provider_for(symbol: str, cfg: Config) -> DataProvider:
    """The data provider for a symbol, chosen by its asset class (or a per-symbol override)."""
    if PROVIDER_OVERRIDE.get(symbol) == "oanda":
        from src.data.oanda import OandaProvider
        return OandaProvider(token=cfg.oanda_api_token)
    if asset_class_for(symbol) == FOREX:
        return ForexProvider(api_key=cfg.twelvedata_api_key)
    return CryptoProvider(exchange_id=cfg.market.exchange)


def get_candles(
    symbol: str,
    timeframe: str,
    cfg: Config,
    *,
    limit: int | None = None,
    refresh: bool = False,
    data_dir: Path = DATA_DIR,
    stale_after_minutes: int | None = None,
) -> pd.DataFrame:
    """Return clean candles for `symbol`/`timeframe`, cache-first, via the asset-class provider.

    `stale_after_minutes`: when set, a cached frame whose newest bar is older than this is
    re-fetched live (so the live API/UI shows up-to-the-latest-closed-bar data). Default None
    keeps pure cache-first behavior (deterministic for tests/backtest).
    """
    limit = limit or cfg.market.history_candles
    exchange_id = cfg.market.exchange

    path = cache_path(symbol, timeframe, exchange_id, data_dir)
    df = None
    if not refresh and path.exists():
        cached = load_candles(symbol, timeframe, exchange_id, data_dir)
        fresh = (
            stale_after_minutes is None
            or cached.empty
            or (pd.Timestamp.now(tz="UTC") - cached.index[-1]).total_seconds() / 60.0 <= stale_after_minutes
        )
        if fresh:
            df = cached
    if df is None:
        provider = provider_for(symbol, cfg)
        df = provider.fetch(symbol, timeframe, limit)
        save_candles(df, symbol, timeframe, exchange_id, data_dir)

    df = clean_candles(df)
    if df.empty:
        raise ValueError(f"No candles for {symbol} {timeframe} (empty after cleaning).")

    report = check_candles(df)
    if not report.ok:
        logger.warning("Data quality issues for %s %s: %s", symbol, timeframe, report.summary())
    return df
