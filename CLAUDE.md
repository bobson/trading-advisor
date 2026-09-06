# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Status

`PLAN.md` is the authoritative spec; build in its phase order and folder layout, one phase per session, with a git commit as a checkpoint after each phase.

**Done:** Phase 0 (skeleton), Phase 1 (`src/data/`), Phase 2 (`src/indicators/features.py`), Phase 3 (`src/structure/swings.py`), Phase 4 (`support_resistance.py`, `trendlines.py`, `trend.py`), Phase 5 (`src/structure/fibonacci.py`, `scripts/show_fibonacci.py`), Phase 6 (`src/signals/confluence.py`, `scripts/show_confluence.py`), Phase 7 (`src/advisor/facts.py`, `src/advisor/explain.py`, `scripts/show_explanation.py`), Phase 8 (`src/viz/chart.py`, `scripts/analyze.py`), Phase 9 (`src/patterns/chart_patterns.py`, `scripts/show_patterns.py`, wired into `facts.py`), Phase 10 (`src/advisor/vision.py`, `scripts/analyze_image.py`). **ALL PHASES 0–10 COMPLETE.**

Phase 3 conventions: swings via `scipy.argrelextrema` on `high`/`low` (not close), filtered to fully-confirmed interior positions `[sensitivity, n-1-sensitivity]` — argrelextrema's default `mode='clip'` otherwise flags spurious unconfirmed pivots on the newest bars. `find_swings` returns a tidy frame keyed by integer `bar` (not timestamp — an outside bar can be both high and low). Structure detectors build on `bar`.

Phase 4 conventions: S/R `tolerance_pct` is a PERCENT (÷100 to a fraction — a 0.4%-merge/0.6%-no-merge test guards this). Detectors return ALL levels; capping/proximity selection lives in the display script, not the detector. Trendlines are least-squares fits (`numpy.polyfit`) through the last 3 swings with an `r2` quality gate; draw them from the first anchor bar forward (never extend a short local fit backward across the window). `classify_trend` reads `COL_SMA_SLOW` and requires the featured frame to be row-aligned with the swings' candles; `sideways` is the neutral fallback, and an unconfirmed HH/HL (MA not rising) downgrades to sideways.

Phase 10 conventions (OPTIONAL, secondary path): `advisor/vision.py`'s `explain_chart_image(image_path, cfg, client=None, question=None)` sends a chart SCREENSHOT to Claude's vision. Deliberately secondary — pixels are a worse data source than the computed numbers, and `VISION_SYSTEM_PROMPT` says so (read what's visible, be explicit about what can't be measured, defer to the data pipeline for precision, no advice). Same conventions as `explain.py`: config-driven model, injectable client, cached system prompt, `type=="text"` extraction. New piece: base64 image content block via `build_image_messages`; `_media_type` maps extension→MIME and raises on unsupported. `scripts/analyze_image.py <path> [question]`. **Phase 10 VERIFIED live 2026-09-06 against `outputs/analysis_BTC-USDT_1h.png`: correctly read the S/R zones, resistance trendline, and the bullish marker as a pullback-to-support, appropriately hedged.** Offline tests cover plumbing only (media type, base64 packing, model, extraction).

Phase 9 conventions (OPTIONAL, fuzziest detector): `patterns/chart_patterns.py` detects double top/bottom, head & shoulders / inverse, and triangles (asc/desc/sym) via geometry on the recent tail of swings (`find_chart_patterns`, default lookback 7). Anti-over-call is the whole game: TWO tolerances — peaks "equal" within `patterns.price_tolerance_pct` AND the trough/peak between them deep enough (`patterns.min_trough_pct`) to be a real reversal; H&S head must clear shoulders by > tolerance. Triangle flatness is NORMALIZED by price (`slope*span/mean_price*100` vs `patterns.flat_slope_pct`) — raw price-per-bar slope is meaningless across symbols. Walkers read highs/lows independently and tolerate non-alternating swings. Patterns CAN co-occur (an ascending triangle's near-equal highs also read as a double top) — that's by design; tests assert the expected label is PRESENT, not exclusive. New `PatternsConfig` (default via `Field(default_factory=...)` so `config.yaml` can omit the block without breaking `load_config`) + a `patterns:` yaml block. Wired into `facts.py` as an additive `chart_patterns` field (NOT a confluence vote — preserves Phase 6/7 semantics), rendered in `facts_to_prompt` LABELED best-effort/approximate so the model calibrates confidence; explain.py's system prompt says the same. Phase 9 is FULLY verified offline (textbook fixtures are the "done when"); also runs clean/no-false-positives on real cached swings via `show_patterns.py`.

Phase 8 conventions: `viz/chart.py`'s `render_chart` is a PURE renderer — it takes already-computed detector objects (swings/levels/trendlines/fib) and never recomputes. `scripts/analyze.py` computes `swings` ONCE and derives levels/trendlines/fib from it with config params, so the drawn geometry is byte-identical to what `build_facts` computed (same pure functions, same inputs) — the nearest-support line on the chart is the number the explanation quotes. `render_chart` is the display layer, so it owns selection (nearest-N-per-side S/R via `_top_levels`, r²-gated anchor-forward trendlines, fib band clamped to `start_bar`) — mirrors the show_* scripts. Sets `matplotlib.use("Agg")` at import (headless PNG). Pass mplfinance kwargs (`addplot`/`hlines`/`alines`) ONLY when non-empty — `addplot=None` raises. The confluence marker reflects CURRENT state only (engine votes on `.iloc[-1]`, no per-bar history): mark the last candle colored by bias, only when `triggered` — NOT a rolling backtest. `analyze.run_analysis(df, cfg, outputs_dir)` is the testable core returning saved paths; it saves the chart UNCONDITIONALLY and only the explanation is key-gated (falls back to facts-only markdown on `RuntimeError` from a missing key). Two artifacts in `outputs/` (gitignored): `analysis_<slug>_<tf>.png` + `.md` — "side by side", not a composite. **Full "done when" VERIFIED live 2026-09-06: `analyze.py` wrote the annotated PNG plus a markdown carrying the real Claude explanation, side by side in `outputs/`.**

Phase 7 conventions: `facts.py` is the Layer1→Layer2 seam. `build_facts` computes each detector (trend/S/R/fib) EXACTLY ONCE with config params and feeds the same objects into both the confluence evaluation AND the facts dict — this is the consistency guarantee that makes "Layer 2 never contradicts Layer 1" provable (a second differently-parameterized pass would let display and vote disagree by luck; a test pins it). It does NOT call `analyze_confluence` (which recomputes); it wires the per-signal functions itself over the shared objects. `explain.py` is Layer 2: `client.messages.create` with the CONFIG-DRIVEN model (`cfg.advisor.model` — the user's `config.yaml` choice IS them naming a model; do not hardcode opus), no `thinking` param (keeps it model-agnostic across whatever the config names), `cache_control` on the stable `SYSTEM_PROMPT` (a no-op below Sonnet's 2048-token cache minimum but correct placement). `explain(facts_text, cfg, client=None)` takes an injectable client so tests run without a key; extracts only `type=="text"` blocks. System prompt tells the model the facts are complementary (distance-ranked "nearest resistance" vs proximity-gated S/R vote answer different questions) so it doesn't manufacture contradictions. **Phase 7 "done when" VERIFIED live 2026-09-06 with `claude-sonnet-4-6`: `show_explanation.py` produced a clear, accurate, teaching explanation matching every computed fact with no Layer 1 contradiction (it framed the bearish MACD as disagreeing rather than manufacturing a conflict). Key lives in gitignored `.env`; `.env.example` holds only the placeholder.**

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
