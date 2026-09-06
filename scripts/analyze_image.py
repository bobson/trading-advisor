#!/usr/bin/env python3
"""Phase 10 (OPTIONAL) — explain an uploaded chart screenshot with Claude's vision.

This is the secondary, image-only path: it reads a chart PNG/JPG and has Claude describe it.
Pixels are a worse data source than the real numbers, so for exact analysis prefer
`scripts/analyze.py` (the data-driven pipeline). Requires ANTHROPIC_API_KEY.

Usage (from repo root, venv active):
    python scripts/analyze_image.py path/to/chart.png ["optional question"]
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.advisor.vision import explain_chart_image  # noqa: E402
from src.config import load_config  # noqa: E402


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python scripts/analyze_image.py <image_path> [question]")
        sys.exit(2)

    image_path = sys.argv[1]
    question = sys.argv[2] if len(sys.argv) > 2 else None

    cfg = load_config()
    print(f"Reading chart image: {image_path}")
    print(f"Model: {cfg.advisor.model}\n" + "=" * 70)
    try:
        explanation = explain_chart_image(image_path, cfg, question=question)
    except (RuntimeError, FileNotFoundError, ValueError) as e:
        print(e)
        sys.exit(1)
    print(explanation)


if __name__ == "__main__":
    main()
