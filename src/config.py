"""Load and validate config.yaml + .env.

Config lives in two places:
  - config.yaml  : everything about how the advisor behaves (validated here).
  - .env         : ANTHROPIC_API_KEY only (secret, gitignored).

Every sub-model uses ``extra="forbid"`` so a typo in config.yaml (e.g. ``symobl``)
raises a clear error instead of being silently ignored.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config.yaml"


class _Strict(BaseModel):
    """Base that rejects unknown keys, so typos in config.yaml fail loudly."""

    model_config = ConfigDict(extra="forbid")


class MarketConfig(_Strict):
    exchange: str = "binance"
    symbol: str = "BTC/USDT"
    timeframe: str = "1h"
    history_candles: int = 4320


class StructureConfig(_Strict):
    swing_sensitivity: int = 5
    sr_cluster_tolerance_pct: float = 0.5
    # Phase 18: how close (percent) price must be to a psychological round number to be "at" it.
    round_number_pct: float = 0.5
    # Two-point trendlines (drawn on the chart): a line through two swing lows/highs is kept only
    # while no close has crossed it by more than this × ATR; anchors come from the last N swings.
    trendline_break_atr_mult: float = 0.25
    # ROADMAP A4 — support/resistance ZONES (all ATR/bar-scaled, no fixed percent):
    sr_zone_atr_mult: float = 0.5        # swings within this × ATR cluster; also the minimum band width
    sr_near_atr_mult: float = 0.25       # price within this × ATR of a band edge counts as "at" it
    sr_stale_bars: int = 120             # untouched for this many bars -> stale
    sr_strength_halflife_bars: int = 60  # a touch's weight halves every this many bars
    trendline_max_anchors: int = 6


class IndicatorsConfig(_Strict):
    rsi_period: int = 14
    rsi_oversold: int = 30
    rsi_overbought: int = 70
    fast_ma: int = 20
    slow_ma: int = 50
    long_ma: int = 200        # the long trend MA drawn on the chart (with the 50); not a vote
    # Period of the simple moving average of volume (Phase 15). "Above/below average volume"
    # is measured against this.
    volume_ma: int = 20
    # Phase 18 toolkit (added as FACTS/context; not promoted to votes yet).
    atr_period: int = 14
    adx_period: int = 14
    adx_trend_threshold: int = 25   # ADX above this = trending (below = ranging)
    stoch_k: int = 14
    stoch_d: int = 3
    stoch_oversold: int = 20
    stoch_overbought: int = 80
    bb_period: int = 20
    bb_stddev: float = 2.0


class ConfluenceConfig(_Strict):
    # LEGACY (Phase 6, superseded by require_categories in Phase 17): kept only so old
    # configs/tests don't break. The category-aware engine no longer counts raw votes.
    min_agreeing_signals: int = 2
    # How close (percent) the last price must sit to a level/fib for it to vote. This is
    # "is price at a level right now", distinct from S/R's swing-merge tolerance.
    proximity_pct: float = 0.5
    # How many times its average volume the last bar must trade for the volume detector to
    # CONFIRM the candle's direction (Phase 15). Below this, volume votes neutral — a move on
    # thin volume is not confirmed by participation.
    volume_confirm_factor: float = 1.2
    # Phase 17: a setup must span at least this many INDEPENDENT categories (trend / momentum
    # / structure / volume / volatility) to be flagged — correlated signals inside one
    # category count once, not N times.
    require_categories: int = 2
    # Phase 17: per-category weight in the 0–1 confidence score. NOT tuned against the
    # backtest — these are sensible priors (structure/levels weighted a touch higher, the
    # softer categories lower); curve-fitting them to one sample would corrupt the evaluator.
    category_weights: dict[str, float] = Field(
        default_factory=lambda: {
            "trend": 1.0,
            "momentum": 1.0,
            "structure": 1.2,
            "volume": 0.8,
            "volatility": 0.8,
        }
    )


class PatternsConfig(_Strict):
    # Chart-pattern geometry is looser than S/R clustering — two peaks this close (percent)
    # count as "equal" for double tops / head-and-shoulders shoulders.
    price_tolerance_pct: float = 2.0
    # Minimum depth (percent) of the trough between two peaks (or peak between two troughs)
    # for it to be a real reversal rather than noise — the anti-over-call guard.
    min_trough_pct: float = 3.0
    # A fitted trendline whose price change across its own span is smaller than this
    # (percent) counts as "flat" when classifying triangles.
    flat_slope_pct: float = 1.0
    # Feature 2 — ATR-scaled tolerances (replace the percent ones above in the new `find_patterns`).
    # Two peaks/troughs count as "equal" within this multiple of ATR; a real reversal/range must be
    # at least `depth_atr_mult` × ATR deep. Scale-free across BTC (~80k) and EUR/USD (~1.10).
    equal_atr_mult: float = 0.6
    depth_atr_mult: float = 1.0
    # A broken reversal pattern only counts as RECLAIMED (-> failed) when a close gets back through
    # the neckline by at least this multiple of that bar's ATR — so a close hovering a hair past
    # the line doesn't flip the state. A neutral prior, not tuned to any backtest.
    reclaim_atr_mult: float = 0.25
    # ROADMAP B2 — channel detector knobs (defaults = the original hard-coded behaviour). Tuned ONLY
    # by scripts/eval_detectors.py on the tune split of the gold labels, never by hand.
    channel_min_r2: float = 0.6            # each rail's least-squares fit must reach this r²
    channel_min_parallel: float = 0.5      # 1 − |s1−s2|/max(|s1|,|s2|): how parallel the rails are
    channel_respect_rails: bool = False    # also require no close beyond either rail by > trendline_break_atr_mult × ATR
    # Pattern LIFE CYCLE after the breakout (see chart_patterns._lifecycle): "fresh" for this many
    # bars after confirming; "expired" once it has gone longer than expire_duration_mult × the
    # pattern's own formation length without reaching its target (or failing).
    fresh_bars: int = 3
    expire_duration_mult: float = 1.0
    # Continuation patterns (triangles, channels, ranges, wedges) start AFTER the last impulse: a
    # swing-to-swing leg of at least this × ATR. Swings from before a big rally/crash don't belong
    # to the consolidation after it (the SOL "channel" and XRP "triangle" misreads).
    impulse_atr_mult: float = 5.0
    # ...and at least this × the median swing leg in the window (a trending channel's legs are all
    # similar and each makes a new extreme — that's a trend, not an impulse)
    impulse_leg_ratio: float = 2.0
    # A wedge: both boundary lines slope the same way AND the gap between them shrinks by at least
    # this fraction from the pattern's start to its last swing (a channel's lines stay ~parallel).
    wedge_min_convergence: float = 0.25


class TimeframesConfig(_Strict):
    # Phase 23: timeframes the UI/CLI offers, and their authority weight in a cross-timeframe
    # read (higher timeframe = more weight; 5m is deliberately excluded as mostly noise).
    selectable: list[str] = Field(default_factory=lambda: ["15m", "30m", "1h", "4h", "1d"])
    weights: dict[str, float] = Field(
        default_factory=lambda: {"15m": 0.6, "30m": 0.7, "1h": 1.0, "4h": 1.2, "1d": 1.4}
    )


class MarketAdaptationConfig(_Strict):
    # Phase 19: "a significant move" for a market = this multiple of its ATR (volatility-
    # relative, so the same notion scales between a ~80k BTC and a ~1.10 EUR/USD).
    significant_move_atr_mult: float = 1.5


class MultiTimeframeConfig(_Strict):
    # Phase 16: higher timeframes whose trend gates the base-timeframe setup. Context flows
    # DOWN only (a higher TF informs the lower one, never the reverse). A base setup that
    # conflicts with the higher-TF trend is downgraded (not flagged).
    enabled: bool = True
    context_from: list[str] = Field(default_factory=lambda: ["4h", "1d"])
    # ROADMAP A5: higher timeframes shown to Claude as per-signal votes (INFORMATION ONLY — never
    # gates or changes a verdict). Includes 1w so daily/4h charts get the weekly picture; the
    # veto above stays on `context_from` until a daily backtest justifies adding 1w there.
    facts_from: list[str] = Field(default_factory=lambda: ["4h", "1d", "1w"])


class AlertsConfig(_Strict):
    # #7 watchlist: scan these on a schedule (cron) and notify when a setup fires.
    symbols: list[str] = Field(default_factory=lambda: ["BTC/USDT", "ETH/USDT", "SOL/USDT", "XRP/USDT"])
    timeframe: str = "1h"
    min_confidence: float = 0.5  # only alert on setups at least this confident (avoid spam)


class MorningReportConfig(_Strict):
    # ROADMAP A8 — the daily forward record (scripts/morning_report.py, fired 08:00 Europe/Skopje).
    # Oil (WTI/USD) is not in the default list: Twelve Data's free plan refuses it and OANDA now
    # redirects new sign-ups to FTMO (no API). The OANDA provider stays for if a token is ever available.
    symbols: list[str] = Field(default_factory=lambda: ["BTC/USDT", "ETH/USDT", "SOL/USDT", "EUR/USD", "XAU/USD"])
    timeframes: list[str] = Field(default_factory=lambda: ["30m", "1h", "4h", "1d"])
    # Review horizon per timeframe, in BARS (so forex/commodity weekends skip naturally).
    horizons: dict[str, int] = Field(default_factory=lambda: {"30m": 48, "1h": 24, "4h": 42, "1d": 21})
    run_at: str = "08:00"                      # local time in `timezone`
    timezone: str = "Europe/Skopje"
    synthesis: bool = False                    # one Claude multi-timeframe synthesis per symbol (costs credits)
    twelvedata_pause_s: float = 8.0            # free plan allows 8 requests/minute


class DerivativesConfig(_Strict):
    # Phase 22: crypto-only positioning context (funding rate + open interest) shown as FACTS.
    # Gated to crypto in code; forex has no perp funding/OI. No vote yet (pending a study).
    enabled: bool = True
    funding_extreme: float = 0.0005  # |funding per 8h| above this = crowded (contrarian) flag


class ContextConfig(_Strict):
    # Phase 21: extra background facts for Layer 2 (never touches the detectors).
    fear_greed: bool = True          # crypto Fear & Greed (alternative.me, no key)
    fundamentals: bool = True        # crypto market cap/supply/volume (CoinGecko, no key)
    economic_calendar: bool = True   # high-impact events (Finnhub, needs FINNHUB_API_KEY)
    news: bool = True                # recent headlines (Finnhub, needs FINNHUB_API_KEY)


class RegimeConfig(_Strict):
    # Feature 6 (market regime). Defaults tuned for multi-week trend following on DAILY/WEEKLY
    # bars (ADX/ATR periods come from IndicatorsConfig; adx_trend_threshold there is reused).
    atr_percentile_window: int = 100     # rolling window for the ATR-volatility percentile
    atr_percentile_min_periods: int = 30  # start labelling once this many bars exist (still rolling)
    slope_window: int = 10               # bars over which the slow-MA slope sets direction
    slope_flat_pct: float = 1.0          # |slow-MA % change over slope_window| below this = flat
    vol_high_pct: float = 0.80           # ATR percentile above this (and not trending) = volatile
    vol_low_pct: float = 0.20            # ATR percentile below this (and not trending) = quiet
    persist_bars: int = 3                # hysteresis: a new regime must hold this many bars to switch


class CostsConfig(_Strict):
    # Feature 10 — the honest cost model, applied to every backtest by default (a backtest
    # without costs is fiction). All rates are round-trip unless noted; bps = basis points.
    enabled: bool = True
    crypto_spread_bps: float = 2.0        # round-trip order-book spread, bps of price (crypto)
    forex_spread_pips: float = 1.0        # base pip spread for majors (widened by session)
    taker_fee_bps: float = 5.0            # exchange taker fee PER SIDE, bps
    slippage_atr_mult: float = 0.05       # slippage per side = mult × (ATR / price) — volatility-scaled
    funding_bps_8h: float = 1.0           # perp funding per 8h, bps of notional (crypto; longs pay when +)
    forex_financing_bps_day: float = 0.5  # overnight/weekend financing per day, bps (forex CFD)
    tax_rate: float = 0.0                 # drag on REALISED gains (0 = off; set to your rate — its absence flatters results)


class ExitsConfig(_Strict):
    # Feature 8 — the exit-rule laboratory. All thresholds ATR-scaled (scale-free across markets).
    target_atr: float = 3.0        # fixed take-profit distance, × ATR at entry
    stop_atr: float = 2.0          # fixed stop distance, × ATR at entry
    trail_atr: float = 3.0         # close-based trailing stop, × ATR from the running close-high
    chandelier_atr: float = 3.0    # wick-based trail, × ATR below the highest high since entry
    structure_lookback: int = 10   # bars for the rolling swing-low/high PROXY (structure exit)
    time_bars: int = 20            # time exit: close after this many bars
    max_hold: int = 200            # hard cap so a stop-only trade can't run forever


class AdvisorConfig(_Strict):
    model: str = "claude-sonnet-4-6"
    # Explanation mode (Layer 2). "brief" enforces the analyst guide's §8 word budgets (default);
    # "teaching" gives a fuller educational breakdown, exempt from the budgets but bound by every
    # other guide rule. See src/advisor/explain.py.
    explanation_style: str = "brief"


class Config(_Strict):
    market: MarketConfig
    structure: StructureConfig
    indicators: IndicatorsConfig
    confluence: ConfluenceConfig
    advisor: AdvisorConfig
    # Optional (Phase 9): defaults apply if config.yaml omits the `patterns:` block.
    patterns: PatternsConfig = Field(default_factory=PatternsConfig)
    # Optional (Phase 16): defaults apply if config.yaml omits the `mtf:` block.
    mtf: MultiTimeframeConfig = Field(default_factory=MultiTimeframeConfig)
    # Optional (Phase 19): defaults apply if config.yaml omits the `market_adaptation:` block.
    market_adaptation: MarketAdaptationConfig = Field(default_factory=MarketAdaptationConfig)
    # Optional (Phase 21): defaults apply if config.yaml omits the `context:` block.
    context: ContextConfig = Field(default_factory=ContextConfig)
    # Optional (Phase 22): defaults apply if config.yaml omits the `derivatives:` block.
    derivatives: DerivativesConfig = Field(default_factory=DerivativesConfig)
    # Optional (Phase 23): defaults apply if config.yaml omits the `timeframes:` block.
    timeframes: TimeframesConfig = Field(default_factory=TimeframesConfig)
    # Optional (#7 alerts): defaults apply if config.yaml omits the `alerts:` block.
    alerts: AlertsConfig = Field(default_factory=AlertsConfig)
    # Optional (ROADMAP A8): defaults apply if config.yaml omits the `morning_report:` block.
    morning_report: MorningReportConfig = Field(default_factory=MorningReportConfig)
    # Optional (Feature 6): defaults apply if config.yaml omits the `regime:` block.
    regime: RegimeConfig = Field(default_factory=RegimeConfig)
    # Optional (Feature 10): defaults apply if config.yaml omits the `costs:` block.
    costs: CostsConfig = Field(default_factory=CostsConfig)
    # Optional (Feature 8): defaults apply if config.yaml omits the `exits:` block.
    exits: ExitsConfig = Field(default_factory=ExitsConfig)

    # Injected from .env, not from config.yaml. Optional so the deterministic
    # Layer 1 pipeline (data + detectors) runs without an API key.
    anthropic_api_key: Optional[str] = None
    finnhub_api_key: Optional[str] = None  # Phase 21: economic calendar + news (optional)
    twelvedata_api_key: Optional[str] = None  # Phase 26: forex OHLC (optional; crypto needs none)
    oanda_api_token: Optional[str] = None     # A8: WTI oil candles (free OANDA practice account)
    webhook_url: Optional[str] = None  # #7 alerts: Discord/Slack-style webhook to get pinged
    # #8 API lockdown (env-injected; safe defaults for local dev).
    api_key: Optional[str] = None      # when set, the API requires X-API-Key on data endpoints
    allowed_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:5173", "http://127.0.0.1:5173"]
    )
    rate_limit_per_min: int = 60       # per-client request cap (0 disables)

    def require_api_key(self) -> str:
        """Return the Anthropic key or raise — call this from Layer 2 only."""
        if not self.anthropic_api_key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY is not set. Copy .env.example to .env and add your key."
            )
        return self.anthropic_api_key


def load_config(path: str | Path = DEFAULT_CONFIG_PATH) -> Config:
    """Read config.yaml, validate it, and attach the API key from .env."""
    load_dotenv(PROJECT_ROOT / ".env")
    raw = yaml.safe_load(Path(path).read_text()) or {}
    origins = os.getenv("ALLOWED_ORIGINS")
    api_env = {
        "anthropic_api_key": os.getenv("ANTHROPIC_API_KEY"),
        "finnhub_api_key": os.getenv("FINNHUB_API_KEY"),
        "twelvedata_api_key": os.getenv("TWELVEDATA_API_KEY"),
        "oanda_api_token": os.getenv("OANDA_API_TOKEN"),
        "webhook_url": os.getenv("WEBHOOK_URL"),
        "api_key": os.getenv("API_KEY"),
        "rate_limit_per_min": int(os.getenv("RATE_LIMIT_PER_MIN", "60")),
    }
    if origins:
        api_env["allowed_origins"] = [o.strip() for o in origins.split(",") if o.strip()]
    return Config(**raw, **api_env)
