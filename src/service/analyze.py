"""Phase 12 — the service core: one orchestration returning JSON-serializable results.

This is the seam every front door sits on. `advise(symbol, timeframe, cfg)` runs the whole
Layer 1 + Layer 2 pipeline for ONE market/timeframe and returns an `AnalysisResult` whose
`.to_payload()` is a plain, JSON-serializable dict (the computed facts plus Claude's
explanation) — **not** file paths. The CLI (`scripts/analyze.py`) and, later, `serialize.py`
/ the API render or serialize the same computed objects this result carries.

Per-request market: `symbol`/`timeframe` are arguments, not read from `config.yaml`. We build
a request-scoped config by overriding `cfg.market`, so `build_facts`, the cache filename, and
any slug all reflect the requested pair consistently — `config.yaml`'s market becomes just the
default the caller supplies.

Compute-once holds exactly as in Phase 7/8: swings are computed a single time and drive both
the facts (via `build_facts`) and the detector objects (levels/trendlines/fib) carried on the
result, so the JSON facts and any drawn/serialized geometry describe the same numbers.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

import pandas as pd

from src.advisor.explain import explain
from src.advisor.facts import build_facts, facts_to_prompt
from src.advisor.verify import verify_explanation
from src.backtest.base_rate import base_rate_entry
from src.config import Config
from src.data.registry import get_candles
from src.indicators.features import add_features
from src.structure.fibonacci import FibRetracement, fib_retracement
from src.structure.support_resistance import find_support_resistance
from src.structure.swings import find_swings
from src.structure.trendlines import find_trendlines


@dataclass
class AnalysisResult:
    """Everything one analysis produced.

    `facts` + `explanation` are the JSON-serializable payload (see `to_payload`). The rest are
    in-memory detector objects, kept so a renderer/serializer can draw the SAME geometry the
    facts describe without recomputing (compute-once). `cfg` is request-scoped — its `market`
    reflects the symbol/timeframe this analysis was run for.
    """

    facts: dict
    facts_text: str
    explanation: Optional[str]  # None when ANTHROPIC_API_KEY is absent

    # In-memory artifacts (not part of the JSON payload) for rendering / later serialization.
    df: pd.DataFrame
    featured: pd.DataFrame
    swings: pd.DataFrame
    levels: pd.DataFrame
    trendlines: Any
    fib: Optional[FibRetracement]
    cfg: Config

    # Phase 20 — Layer-2 consistency check ({ok, issues}); None when there is no explanation.
    verification: Optional[dict] = None

    # Feature 1 — total bars in the FULL frame before any `as_of_bar` truncation, so a scrubbing
    # UI knows the maximum bar it can seek to (candles are capped to `limit`, so length != total).
    total_bars: int = 0

    def to_payload(self) -> dict:
        """The JSON-serializable result: the computed facts plus Claude's explanation.

        Provisional shape — Phase 24's `serialize.py` owns the real API contract; this is an
        internal convenience for the CLI and the "done when" check.
        """
        return {**self.facts, "explanation": self.explanation, "verification": self.verification}


_TF_UNIT_MINUTES = {"m": 1, "h": 60, "d": 1440}


def _timeframe_minutes(timeframe: str) -> int:
    """'15m'->15, '1h'->60, '4h'->240, '1d'->1440 (for the refresh-stale threshold)."""
    return int(timeframe[:-1]) * _TF_UNIT_MINUTES[timeframe[-1]]


def _request_config(cfg: Config, symbol: str, timeframe: str) -> Config:
    """A copy of `cfg` whose market reflects THIS request (symbol/timeframe per call)."""
    market = cfg.market.model_copy(update={"symbol": symbol, "timeframe": timeframe})
    return cfg.model_copy(update={"market": market})


def advise(
    symbol: str,
    timeframe: str,
    cfg: Config,
    *,
    df: Optional[pd.DataFrame] = None,
    client: Any = None,
    context: Optional[dict] = None,
    derivatives: Optional[dict] = None,
    explain_enabled: bool = True,
    refresh_stale: bool = False,
    base_rate: Optional[dict] = None,
    as_of_bar: Optional[int] = None,
    explanation_style: Optional[str] = None,
) -> AnalysisResult:
    """Run the full pipeline for one market/timeframe and return a JSON-able result.

    `df` is injectable (tests pass synthetic candles; otherwise candles are obtained via the
    data facade `registry.get_candles`, which picks a provider by asset class and is
    cache-first). `client` is the injectable Anthropic client forwarded to
    `explain` (tests run keyless). The explanation is attempted and falls back to `None` when
    no API key is available, so the deterministic result is always produced.
    """
    req = _request_config(cfg, symbol, timeframe)
    # Per-request explanation mode (brief/teaching) overrides config, without mutating the caller's.
    if explanation_style is not None:
        req = req.model_copy(update={
            "advisor": req.advisor.model_copy(update={"explanation_style": explanation_style})
        })
    m = req.market

    if df is None:
        # refresh_stale: re-pull once the cached data is older than ~one bar (live API/UI).
        stale = _timeframe_minutes(m.timeframe) if refresh_stale else None
        df = get_candles(m.symbol, m.timeframe, req, stale_after_minutes=stale)

    total_bars = len(df)
    # Feature 1 — historical scrubbing. `as_of_bar=N` recomputes the WHOLE pipeline on bars
    # <= N only, so the result is exactly what the engine would have seen at that bar. This is
    # look-ahead-safe by construction: it's literally a run on the truncated frame `df[:N+1]`
    # (`find_swings`' confirmed-interior filter can't see past the cut, `add_features` is causal).
    # Clamp up to a feature-warmup floor since `add_features` is fragile on very short frames.
    if as_of_bar is not None and total_bars:
        floor = req.indicators.slow_ma
        cut = min(max(int(as_of_bar), floor), total_bars - 1)
        df = df.iloc[: cut + 1]

    featured = add_features(df, req)
    assert len(featured) == len(df), "featured frame desynced from candles"
    swings = find_swings(df, req.structure.swing_sensitivity)

    facts = build_facts(featured, swings, req)
    # Phase 21: context (sentiment/calendar/news) is CURRENT-state, live-only. It is injected by
    # the caller (CLI/API), never fetched here and never inside build_facts (which runs per-bar
    # in the backtest). Default None -> tests/backtest touch no network.
    if context is not None:
        facts = {**facts, "context": context}
    if derivatives is not None:
        facts = {**facts, "derivatives": derivatives}
    # Rec #2: attach the historical track record for THIS setup's bias (honest, not a forecast).
    if base_rate is not None:
        entry = base_rate_entry(base_rate, facts["confluence"]["bias"])
        if entry:
            facts = {**facts, "base_rate": entry}
    facts_text = facts_to_prompt(facts)

    # Same swings + params as build_facts used internally -> byte-identical geometry.
    levels = find_support_resistance(swings, req.structure.sr_cluster_tolerance_pct)
    trendlines = find_trendlines(swings)
    fib = fib_retracement(swings)

    explanation: Optional[str] = None
    if explain_enabled:
        try:
            explanation = explain(facts_text, req, client=client, situation=facts.get("situation"))
        except RuntimeError:
            explanation = None  # no ANTHROPIC_API_KEY — deterministic facts stand on their own

    # Phase 20: enforce "Layer 2 never contradicts Layer 1" — check the explanation's numbers
    # against the facts. Advisory (never blocks); only runs when there is an explanation.
    verification: Optional[dict] = None
    if explanation is not None:
        verification = verify_explanation(explanation, facts).to_dict()

    return AnalysisResult(
        facts=facts,
        facts_text=facts_text,
        explanation=explanation,
        df=df,
        featured=featured,
        swings=swings,
        levels=levels,
        trendlines=trendlines,
        fib=fib,
        cfg=req,
        verification=verification,
        total_bars=total_bars,
    )
