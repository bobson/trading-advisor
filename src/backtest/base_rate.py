"""Recommendation #2 — the honest track record shown next to each live setup.

The backtest is slow (multi-timeframe resample per bar), so we don't run it per request.
Instead `compute_base_rate` is run OFFLINE (scripts/compute_base_rates.py) into a small JSON
file; the live path just loads it and attaches the win-rate for the current setup's bias:
"setups like this resolved favorably X% of the time (N cases) — not a prediction."

Given the out-of-sample finding (no demonstrable edge; ~40-61% across coins/periods), this is
the point: the number keeps the confidence honest rather than letting it pose as a forecast.
"""

from __future__ import annotations

import json
from pathlib import Path

from src.backtest.evaluate import evaluate
from src.data.cache import DATA_DIR

BASE_RATES_PATH = DATA_DIR / "base_rates.json"


def _stat(s) -> dict:
    return {"n": s.n, "win_rate": round(s.win_rate, 3)} if s.n else {"n": 0, "win_rate": None}


def compute_base_rate(df, cfg, *, horizon: int = 24, step: int = 3, require_categories=None) -> dict:
    """Backtest `df` and summarize the historical win-rate overall and per bias."""
    rep = evaluate(df, cfg, horizon=horizon, step=step, require_categories=require_categories)
    return {
        "horizon": horizon,
        "overall": _stat(rep.overall),
        "bullish": _stat(rep.by_bias["bullish"]),
        "bearish": _stat(rep.by_bias["bearish"]),
    }


def load_base_rates(path: Path | None = None) -> dict:
    """Load the precomputed base-rate table (keyed "SYMBOL|TF"), or {} if not generated yet."""
    p = path or BASE_RATES_PATH
    if not Path(p).exists():
        return {}
    try:
        return json.loads(Path(p).read_text())
    except Exception:
        return {}


def base_rate_entry(rates_for_pair: dict | None, bias: str) -> dict | None:
    """The track-record line for the current setup's bias (falls back to overall)."""
    if not rates_for_pair:
        return None
    entry = rates_for_pair.get(bias) or rates_for_pair.get("overall")
    if not entry or not entry.get("n") or entry.get("win_rate") is None:
        return None
    return {
        "bias": bias,
        "win_rate": entry["win_rate"],
        "n": entry["n"],
        "horizon": rates_for_pair.get("horizon"),
    }
