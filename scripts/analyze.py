#!/usr/bin/env python3
"""Phase 8 — the full pipeline in one command: data → structure → confluence → facts →
explanation → annotated chart. Saves two artifacts side by side in outputs/: the annotated
chart PNG and a markdown file with the computed facts + Claude's explanation.

The chart (Layer 1) is always saved. The explanation (Layer 2) needs ANTHROPIC_API_KEY; if
it's missing, the markdown still gets the computed facts plus a note, so the command stays
useful offline.

Usage (from repo root, venv active; run download_data.py first):
    python scripts/analyze.py
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd  # noqa: E402

from src.advisor.explain import explain  # noqa: E402
from src.advisor.facts import build_facts, facts_to_prompt  # noqa: E402
from src.config import PROJECT_ROOT, Config, load_config  # noqa: E402
from src.data.cache import load_candles  # noqa: E402
from src.indicators.features import add_features  # noqa: E402
from src.structure.fibonacci import fib_retracement  # noqa: E402
from src.structure.support_resistance import find_support_resistance  # noqa: E402
from src.structure.swings import find_swings  # noqa: E402
from src.structure.trendlines import find_trendlines  # noqa: E402
from src.viz.chart import render_chart  # noqa: E402

OUTPUTS_DIR = PROJECT_ROOT / "outputs"


@dataclass
class AnalysisResult:
    chart_path: Path
    text_path: Path
    facts: dict
    explanation: Optional[str]  # None when the API key is absent


def run_analysis(df: pd.DataFrame, cfg: Config, outputs_dir: Path) -> AnalysisResult:
    """Run the pipeline on `df` and save the chart + markdown to `outputs_dir`.

    `swings` is computed once and drives both the facts (via build_facts) and the drawn
    geometry, so the chart and the explanation describe the same numbers. The chart is saved
    unconditionally; the explanation is attempted and falls back to facts-only without a key.
    """
    m = cfg.market
    featured = add_features(df, cfg)
    assert len(featured) == len(df), "featured frame desynced from candles"
    swings = find_swings(df, cfg.structure.swing_sensitivity)

    facts = build_facts(featured, swings, cfg)
    facts_text = facts_to_prompt(facts)

    # Same swings + config params as build_facts used internally -> identical geometry.
    levels = find_support_resistance(swings, cfg.structure.sr_cluster_tolerance_pct)
    trendlines = find_trendlines(swings)
    fib = fib_retracement(swings)

    slug = m.symbol.replace("/", "-")
    outputs_dir = Path(outputs_dir)
    chart_path = outputs_dir / f"analysis_{slug}_{m.timeframe}.png"
    text_path = outputs_dir / f"analysis_{slug}_{m.timeframe}.md"

    render_chart(
        df, swings, levels, trendlines, fib,
        bias=facts["confluence"]["bias"],
        triggered=facts["confluence"]["triggered"],
        cfg=cfg,
        out_path=chart_path,
    )

    explanation: Optional[str]
    try:
        explanation = explain(facts_text, cfg)
    except RuntimeError:
        explanation = None

    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    body = [
        f"# {m.symbol} {m.timeframe} on {m.exchange} — analysis",
        f"_generated {generated}_",
        "",
        f"Annotated chart: `{chart_path.name}`",
        "",
        "## Computed facts (Layer 1)",
        "```",
        facts_text,
        "```",
        "",
        "## Explanation (Layer 2)",
    ]
    if explanation:
        body.append(explanation)
    else:
        body.append(
            "_No explanation generated — ANTHROPIC_API_KEY is not set. "
            "Copy .env.example to .env and add your key, then re-run. "
            "The computed facts above are complete on their own._"
        )
    outputs_dir.mkdir(parents=True, exist_ok=True)
    text_path.write_text("\n".join(body) + "\n")

    return AnalysisResult(chart_path, text_path, facts, explanation)


def main() -> None:
    cfg = load_config()
    m = cfg.market
    df = load_candles(m.symbol, m.timeframe, m.exchange)
    result = run_analysis(df, cfg, OUTPUTS_DIR)

    print(f"Saved annotated chart: {result.chart_path}")
    print(f"Saved analysis text:   {result.text_path}")
    if result.explanation is None:
        print("\nNote: no ANTHROPIC_API_KEY set — wrote computed facts only (no explanation).")
    else:
        print(f"\nConfluence: {result.facts['confluence']['bias'].upper()} "
              f"({'setup flagged' if result.facts['confluence']['triggered'] else 'no setup'})")


if __name__ == "__main__":
    main()
