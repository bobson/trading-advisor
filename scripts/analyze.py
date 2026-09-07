#!/usr/bin/env python3
"""CLI front door — a thin wrapper over the service core (Phase 12).

The analysis itself lives in `src/service/analyze.py::advise`, which returns a
JSON-serializable result. This script is presentation only: it calls `advise()` for the
config's default market and saves the two CLI artifacts in `outputs/` — the annotated chart
PNG (Layer 1) and a markdown file with the computed facts + Claude's explanation (Layer 2),
side by side. The chart is always saved; the explanation is key-gated and falls back to a
facts-only note when `ANTHROPIC_API_KEY` is absent.

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

from src.config import PROJECT_ROOT, Config, load_config  # noqa: E402
from src.service.analyze import AnalysisResult, advise  # noqa: E402
from src.viz.chart import render_chart  # noqa: E402

OUTPUTS_DIR = PROJECT_ROOT / "outputs"


@dataclass
class SavedAnalysis:
    """The two artifacts this CLI writes (paths), plus the facts/explanation behind them."""

    chart_path: Path
    text_path: Path
    facts: dict
    explanation: Optional[str]  # None when the API key is absent


def _write_outputs(result: AnalysisResult, outputs_dir: Path) -> SavedAnalysis:
    """Render the annotated chart + write the markdown from an already-computed result.

    Uses the result's carried detector objects (compute-once), so the drawn geometry is the
    same numbers the facts/explanation quote.
    """
    m = result.cfg.market
    slug = m.symbol.replace("/", "-")
    outputs_dir = Path(outputs_dir)
    chart_path = outputs_dir / f"analysis_{slug}_{m.timeframe}.png"
    text_path = outputs_dir / f"analysis_{slug}_{m.timeframe}.md"

    render_chart(
        result.df, result.swings, result.levels, result.trendlines, result.fib,
        bias=result.facts["confluence"]["bias"],
        triggered=result.facts["confluence"]["triggered"],
        cfg=result.cfg,
        out_path=chart_path,
    )

    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    body = [
        f"# {m.symbol} {m.timeframe} on {m.exchange} — analysis",
        f"_generated {generated}_",
        "",
        f"Annotated chart: `{chart_path.name}`",
        "",
        "## Computed facts (Layer 1)",
        "```",
        result.facts_text,
        "```",
        "",
        "## Explanation (Layer 2)",
    ]
    if result.explanation:
        body.append(result.explanation)
    else:
        body.append(
            "_No explanation generated — ANTHROPIC_API_KEY is not set. "
            "Copy .env.example to .env and add your key, then re-run. "
            "The computed facts above are complete on their own._"
        )
    outputs_dir.mkdir(parents=True, exist_ok=True)
    text_path.write_text("\n".join(body) + "\n")

    return SavedAnalysis(chart_path, text_path, result.facts, result.explanation)


def run_analysis(df: pd.DataFrame, cfg: Config, outputs_dir: Path) -> SavedAnalysis:
    """Analyze `df` for the config's market and save both CLI artifacts.

    Thin wrapper kept for callers/tests: it runs the service core on the given candles (the
    config's symbol/timeframe) and writes the chart + markdown.
    """
    m = cfg.market
    result = advise(m.symbol, m.timeframe, cfg, df=df)
    return _write_outputs(result, outputs_dir)


def main() -> None:
    cfg = load_config()
    m = cfg.market
    result = advise(m.symbol, m.timeframe, cfg)
    saved = _write_outputs(result, OUTPUTS_DIR)

    print(f"Saved annotated chart: {saved.chart_path}")
    print(f"Saved analysis text:   {saved.text_path}")
    if saved.explanation is None:
        print("\nNote: no ANTHROPIC_API_KEY set — wrote computed facts only (no explanation).")
    else:
        c = saved.facts["confluence"]
        print(f"\nConfluence: {c['bias'].upper()} "
              f"({'setup flagged' if c['triggered'] else 'no setup'})")


if __name__ == "__main__":
    main()
