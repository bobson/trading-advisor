# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Status

`PLAN.md` is the authoritative spec; build in its phase order and folder layout, one phase per session, with a git commit as a checkpoint after each phase.

**Done:** Phase 0 (skeleton), Phase 1 (`src/data/`), Phase 2 (`src/indicators/features.py`), Phase 3 (`src/structure/swings.py`), Phase 4 (`support_resistance.py`, `trendlines.py`, `trend.py`), Phase 5 (`src/structure/fibonacci.py`, `scripts/show_fibonacci.py`), Phase 6 (`src/signals/confluence.py`, `scripts/show_confluence.py`). **Next:** Phase 7 (Claude explanation layer in `src/advisor/`).

Phase 3 conventions: swings via `scipy.argrelextrema` on `high`/`low` (not close), filtered to fully-confirmed interior positions `[sensitivity, n-1-sensitivity]` — argrelextrema's default `mode='clip'` otherwise flags spurious unconfirmed pivots on the newest bars. `find_swings` returns a tidy frame keyed by integer `bar` (not timestamp — an outside bar can be both high and low). Structure detectors build on `bar`.

Phase 4 conventions: S/R `tolerance_pct` is a PERCENT (÷100 to a fraction — a 0.4%-merge/0.6%-no-merge test guards this). Detectors return ALL levels; capping/proximity selection lives in the display script, not the detector. Trendlines are least-squares fits (`numpy.polyfit`) through the last 3 swings with an `r2` quality gate; draw them from the first anchor bar forward (never extend a short local fit backward across the window). `classify_trend` reads `COL_SMA_SLOW` and requires the featured frame to be row-aligned with the swings' candles; `sideways` is the neutral fallback, and an unconfirmed HH/HL (MA not rising) downgrades to sideways.

Phase 6 conventions: confluence is still Layer 1 — it *tallies*, it doesn't reason. Split in two: `evaluate_confluence(signals, min_agreeing)` is pure (hand it a `Signal` list, assert the flag — this is the "done when" check); `gather_signals(featured_df, swings, cfg)` wires the real detectors. Vote rule: the side with STRICTLY more directional votes wins, and fires only if it reaches `min_agreeing_signals`; a tie (equal bull/bear) never fires (bias `neutral`). Neutral votes are recorded but never count toward the threshold; NaN indicator values on short frames vote NEUTRAL, not a NaN comparison. `ConfluenceResult.reasons`/`.contributing` return the WINNING side's signals only. Six votes: trend, rsi, macd, candlestick, support_resistance, fibonacci (no trendline vote — it overlaps S/R proximity). Proximity uses a NEW config field `confluence.proximity_pct` ("is price at a level now"), deliberately distinct from `structure.sr_cluster_tolerance_pct` (swing-merge). Detectors are recomputed here; Phase 7's `facts.py` will recompute too — fine to refactor later.

Phase 5 conventions: `fib_retracement` auto-picks the latest leg (last swing + most recent opposite swing before it). Invariant: `levels[0.0]` is the most-recent swing's price (impulse end), `levels[1.0]` the older anchor's — this pins the up/down branch (the 0.5 midpoint can't). Returns `None` on a degenerate `high <= low` leg (from non-alternating swings). Returns `FibRetracement` (dataclass), not columns on the frame.

Env note: developed on Python 3.14; all deps (incl. the `pandas-ta-classic` git build) install cleanly. `fetch_ohlcv` pages with a `since` cursor because exchanges cap ~1000 candles/call. `normalize_ohlcv` is kept network-free and unit-tested; the real fetch is a `@pytest.mark.network` test (skip offline with `pytest -m "not network"`).

Phase 2 conventions: TA-Lib is **not** installed, so candlestick patterns are hand-rolled boolean columns in `features.py` (not `cdl_pattern`). Indicator/pattern column names are exported as `COL_*` constants + `INDICATOR_COLUMNS`/`PATTERN_COLUMNS` — import those downstream, don't hardcode strings. `add_features` keeps warmup NaNs (never drops rows). MAs are SMA; RSI/MACD use pandas-ta defaults (match TradingView against the last *closed* bar).

## What this project is

A **visual trading advisor** (Python) that analyzes market candles, computes chart structure (trend, support/resistance, trendlines, Fibonacci, patterns), flags higher-confidence setups when signals agree, and explains its reasoning in plain trading language. It **does not place trades and does not predict the future** — its value is clarity and education.

## Core architecture: two layers (do not blur them)

The single most important design rule: **separate the facts from the explanation.**

- **Layer 1 — the eyes (deterministic).** Pure math/rules on price data: indicators, candlestick patterns, swing points, S/R, trendlines, trend direction, Fibonacci. Outputs plain structured facts (numbers + labels). Lives in `src/indicators/`, `src/structure/`, `src/patterns/`, `src/signals/`.
- **Layer 2 — the brain/voice.** A Claude model (`src/advisor/`) receives Layer 1's structured facts and reasons about them in trading language. It reasons over **computed facts, never raw pixels**.

**Layer 2 must never override or contradict Layer 1.** Layer 1 facts are authoritative; if the explanation disagrees with the computed facts, that is a bug in how facts are assembled/fed, not a value judgment. `advisor/facts.py` assembles facts into a structured summary; `advisor/explain.py` sends them to Claude.

**Swing-point detection (`structure/swings.py`) is the foundation.** Support/resistance, trendlines, trend direction, and named patterns are all built on top of swing points. Prioritize getting it correct and well-tested before anything downstream.

## Data flow

`src/advisor_run.py` orchestrates the pipeline:
`data (ccxt) → indicators + structure detectors → confluence → facts → Claude explanation → annotated chart`

The confluence engine (`signals/confluence.py`) collects a bullish/bearish/neutral vote plus a short reason from each detector, and flags a setup only when a configurable number agree (`config.yaml: confluence.min_agreeing_signals`), recording *why*.

## Key libraries & conventions

- Use **`pandas-ta-classic`** (the fork), **not** the original `pandas-ta` — install via `pip install "git+https://github.com/xgboosted/pandas-ta-classic"`.
- Market data via **`ccxt`**, public OHLCV only — this app never needs trade or withdrawal permissions; read-only at most.
- `pandas` DataFrame is the core data structure; indicators are added as columns.
- `scipy` for peak/valley (swing) detection, `numpy` for line fitting/clustering, `mplfinance` for annotated charts.
- Config: `pydantic`-validated `config.yaml` (symbol, timeframe, detector sensitivity, model) + `.env` for `ANTHROPIC_API_KEY` only. `.env` is never committed; commit `.env.example` with the key name only.
- Sensitivity/thresholds (swing sensitivity, S/R cluster tolerance, RSI periods, min agreeing signals, model name) are config-driven — do not hardcode them in detectors.

## Environment & commands

Python 3.11+. Intended setup (per PLAN.md):

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt          # once requirements.txt exists

# run the advisor: prints explanation + saves annotated chart to outputs/
python scripts/analyze.py

# one-off history download into data/ (gitignored cache)
python scripts/download_data.py

# tests (detectors and confluence are the priority to test)
pytest
pytest tests/test_swings.py              # run a single test file
pytest tests/test_swings.py::test_name   # run a single test
```

`data/` (cached candles) and `outputs/` (charts + explanations) are gitignored working directories.

## Build order (phases in PLAN.md)

Build the deterministic tier and structure detection *before* the reasoning layer, so Claude always has correct facts. Order: 0 skeleton → 1 data → 2 indicators/candlestick patterns → 3 **swings** → 4 structure (S/R, trendlines, trend) → 5 Fibonacci → 6 confluence → 7 Claude explanation → 8 visualization. Phases 9 (named chart patterns) and 10 (chart-image/vision analysis) are optional and added last. Each phase has a "done when" check in `PLAN.md`; verify it before moving on.
