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

    def to_payload(self) -> dict:
        """The JSON-serializable result: the computed facts plus Claude's explanation.

        Provisional shape — Phase 24's `serialize.py` owns the real API contract; this is an
        internal convenience for the CLI and the "done when" check.
        """
        return {**self.facts, "explanation": self.explanation, "verification": self.verification}


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
) -> AnalysisResult:
    """Run the full pipeline for one market/timeframe and return a JSON-able result.

    `df` is injectable (tests pass synthetic candles; otherwise candles are obtained via the
    data facade `registry.get_candles`, which picks a provider by asset class and is
    cache-first). `client` is the injectable Anthropic client forwarded to
    `explain` (tests run keyless). The explanation is attempted and falls back to `None` when
    no API key is available, so the deterministic result is always produced.
    """
    req = _request_config(cfg, symbol, timeframe)
    m = req.market

    if df is None:
        df = get_candles(m.symbol, m.timeframe, req)

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
    facts_text = facts_to_prompt(facts)

    # Same swings + params as build_facts used internally -> byte-identical geometry.
    levels = find_support_resistance(swings, req.structure.sr_cluster_tolerance_pct)
    trendlines = find_trendlines(swings)
    fib = fib_retracement(swings)

    explanation: Optional[str] = None
    if explain_enabled:
        try:
            explanation = explain(facts_text, req, client=client)
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
    )
