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


class IndicatorsConfig(_Strict):
    rsi_period: int = 14
    rsi_oversold: int = 30
    rsi_overbought: int = 70
    fast_ma: int = 20
    slow_ma: int = 50


class ConfluenceConfig(_Strict):
    min_agreeing_signals: int = 2
    # How close (percent) the last price must sit to a level/fib for it to vote. This is
    # "is price at a level right now", distinct from S/R's swing-merge tolerance.
    proximity_pct: float = 0.5


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


class AdvisorConfig(_Strict):
    model: str = "claude-sonnet-4-6"
    explanation_style: str = "teaching"


class Config(_Strict):
    market: MarketConfig
    structure: StructureConfig
    indicators: IndicatorsConfig
    confluence: ConfluenceConfig
    advisor: AdvisorConfig
    # Optional (Phase 9): defaults apply if config.yaml omits the `patterns:` block.
    patterns: PatternsConfig = Field(default_factory=PatternsConfig)

    # Injected from .env, not from config.yaml. Optional so the deterministic
    # Layer 1 pipeline (data + detectors) runs without an API key.
    anthropic_api_key: Optional[str] = None

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
    return Config(**raw, anthropic_api_key=os.getenv("ANTHROPIC_API_KEY"))
