#!/usr/bin/env python3
"""Phase 7 check: assemble Layer 1 facts on the cached candles and have Claude explain them.

Prints the structured facts (Layer 1) and then Claude's plain-language explanation (Layer 2).
Requires ANTHROPIC_API_KEY (copy .env.example to .env and add your key) — this is the first
phase that calls the model. Run download_data.py first.

Usage (from repo root, venv active):
    python scripts/show_explanation.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.advisor.explain import explain  # noqa: E402
from src.advisor.facts import build_facts, facts_to_prompt  # noqa: E402
from src.config import load_config  # noqa: E402
from src.data.cache import load_candles  # noqa: E402
from src.indicators.features import add_features  # noqa: E402
from src.structure.swings import find_swings  # noqa: E402


def main() -> None:
    cfg = load_config()
    m = cfg.market

    df = load_candles(m.symbol, m.timeframe, m.exchange)
    featured = add_features(df, cfg)
    assert len(featured) == len(df), "featured frame desynced from candles"
    swings = find_swings(df, cfg.structure.swing_sensitivity)

    facts = build_facts(featured, swings, cfg)
    facts_text = facts_to_prompt(facts)

    print("=" * 70)
    print("LAYER 1 — COMPUTED FACTS")
    print("=" * 70)
    print(facts_text)

    print("\n" + "=" * 70)
    print(f"LAYER 2 — {cfg.advisor.model} EXPLAINS")
    print("=" * 70)
    try:
        explanation = explain(facts_text, cfg)
    except RuntimeError as e:  # missing API key
        print(f"\n{e}")
        sys.exit(1)
    print(explanation)


if __name__ == "__main__":
    main()
