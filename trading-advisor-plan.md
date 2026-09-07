# Trading Advisor — Master Plan

A **visual trading advisor** (crypto now, forex later): it analyzes candles, computes chart
structure (trend, support/resistance, trendlines, Fibonacci, patterns), flags
higher-confidence setups when signals agree, and **explains its reasoning in plain trading
language** — so you decide and trade, and you learn as you go.

**What this is NOT:** it does not place trades, and it does not "learn to become profitable."
It knows trading concepts and applies them consistently to what it sees. Its value is clarity
and education — seeing the market better and understanding *why* — not predicting the future.
Nothing predicts the future reliably. **None of this is financial advice.**

> This is the **forward roadmap** (Phases 11+). The original build (Phases 0–10) is described
> in [`PLAN.md`](./PLAN.md) and is **complete** — the Layer-1 deterministic tier, Claude's
> explanation layer, mplfinance charts, named patterns, and the vision path all exist and are
> tested. This document merges and supersedes the old `PLAN2.md` (now retired) and the earlier
> Parts 2–7 draft into one linear, de-duplicated, **validation-first** sequence.

---

## 1. Core design (unchanged — do not break these)

**Two layers, kept separate:**

- **Layer 1 — the eyes (deterministic).** Pure math/rules on price data: indicators,
  candlestick patterns, swing points, S/R, trendlines, trend, Fibonacci. Outputs structured
  facts (numbers + labels). Lives in `indicators/`, `structure/`, `patterns/`, `signals/`.
- **Layer 2 — the brain/voice.** A Claude model receives Layer 1's facts and reasons in
  trading language. It reasons over **computed facts, never raw pixels**. Lives in `advisor/`.

Non-negotiable rules carried through every phase below:

1. **Swing detection is the foundation.** Everything structural builds on it.
2. **Layer 2 never contradicts Layer 1.** If the explanation disagrees with the facts, that's
   a bug in how facts are fed, not a judgment call. Later a `verify.py` pass *enforces* this.
3. **Config-driven thresholds.** Sensitivities, tolerances, model name live in `config.yaml`.
   In this arc, **`symbol`/`timeframe` become per-request**, not global.
4. **The clean extension point is the facts summary.** Most upgrades just add new fields to
   `advisor/facts.py` that Layer 2 reads — volume confirmation, higher-TF alignment, sentiment,
   an economic event — all become extra facts, without disturbing the detectors underneath.
5. **Return data, not images.** The eventual web app sends structured JSON (candles + detected
   structure + explanation) and draws the chart interactively. The `mplfinance` PNG stays as
   the CLI output only.

---

## 2. Guiding principles for the forward work

- **Validation-first. You cannot yet tell whether the signals mean anything.** So the backtest
  (Phase 14) is built early and becomes the *instrument that proves or disproves every later
  change*. No analytical upgrade — new indicator, derivative metric, pattern — earns a vote
  until the backtest shows it helps. This resolves the old draft's Part 4-vs-Part 5 tension in
  favor of measuring first.
- **Best ≠ most.** A curated, non-redundant toolkit (a couple of tools per category) beats a
  pile of overlapping indicators. Three momentum indicators agreeing is *one* insight, not
  three — the confluence engine must not double-count.
- **Protect the working core.** Tag it, branch every upgrade, merge only when its "done when"
  passes and (for refactors) a regression check confirms unchanged output.
- **Honest caveats stay in view** (see §5). Richer analysis reduces noise and helps you *see*;
  it is not an edge by itself, and over-optimization (curve-fitting thresholds to history) is
  the main trap.

---

## 3. The linear roadmap (Phases 11–26)

Build in order, each on its own branch, each with tests, merging to `main` only when its
"done when" passes. Phases marked **★** are the three additions folded in from the retired
`PLAN2.md`.

### Phase 11 — Lock in the working core *(protect first)*
Make the current state a fixed point:
```bash
git add -A && git commit -m "Working core advisor (phases 0-10)"
git tag v1-core-advisor
```
Do every upgrade below on its own branch (`git checkout -b feature/<name>`); a bug in a branch
can never break the working core. Also **update `CLAUDE.md`** to describe the built state so
Claude Code's context reflects reality.
**Done when:** the tag exists, and `CLAUDE.md` accurately describes the current detectors,
confluence engine, and reasoning layer.

### ★ Phase 12 — Service core (the JSON seam)
Today `scripts/analyze.py::run_analysis` returns **file paths** (PNG + `.md`) — wrong output
for an API/UI. Lift the orchestration into `src/service/analyze.py::advise(symbol, timeframe,
cfg)` returning a **JSON-serializable `AnalysisResult`** (market, facts, confluence,
explanation). Compute swings **once** and derive everything from it (same consistency guarantee
as Phase 7/8). `scripts/analyze.py` becomes a thin wrapper that calls `advise()` and still
writes the PNG/`.md` for CLI users.
```
src/service/analyze.py     # advise(symbol, timeframe, cfg) -> JSON-able AnalysisResult
```
**Done when:** `advise("BTC/USDT","1h",cfg)` returns a dict that `json.dumps` cleanly, carrying
the same facts + explanation the old script produced, and the CLI still writes its two files.

### Phase 13 — Pluggable data source + data-quality gate
Refactor the data layer so the market is a config choice; the same candle DataFrame comes out
either way, so every detector and Layer 2 stay identical — a candle is a candle.
```
src/data/
├── base.py          # get_candles(symbol, timeframe, limit) -> DataFrame  (common interface)
├── crypto_ccxt.py   # ccxt implementation (rename/refactor of exchange.py) — no keys needed
├── forex_api.py     # slot — raises NotImplementedError until Phase 26
├── registry.py      # the selectable pairs the UI offers (symbol, asset_class, label)
└── quality.py       # ★ data-quality gate: drop dup timestamps, flag gaps, clip/log outliers
```
The rest of the app calls `base.get_candles(...)` and never knows which market it is.
`quality.py` runs on ingest so bad candles can't poison swings. **Forex candidate providers**
(implement later): Twelve Data, Alpha Vantage, or Finnhub (Finnhub also powers the Phase 21
context layer) — each needs a free key; check current free-tier limits before committing.
**Done when:** `advise()` pulls candles through a provider chosen by asset class; crypto works
end-to-end; a deliberately corrupted frame is caught by `quality.py` with a clear report; and
a regression check confirms a known crypto symbol's output is unchanged after the refactor.

### Phase 14 — Backtest / forward-return evaluator *(the instrument — highest leverage)*
For an *advisor* this is not a trade simulator; it's a **forward-return evaluator**: walk
history, run `gather_signals` at each bar, and measure what price did over the next N bars after
each flagged setup. Aggregate by setup type and by threshold so you can tune `min_agreeing`,
`proximity_pct`, and pattern tolerances **with data instead of intuition**.
```
src/backtest/evaluate.py   # walk history, gather_signals per bar, forward-return stats
scripts/backtest.py        # run + print/save a report (win rate, avg/median forward return, N)
tests/test_backtest.py     # incl. an explicit LOOK-AHEAD-BIAS guard test
```
**Build the honesty in from the start:** guard look-ahead bias explicitly (never use a bar's
own future to compute its signal), always report **sample size** (a setup seen 6 times proves
nothing), and remember a good backtest result is *not* proof of a future edge — its early value
is catching signals that are pure noise and comparing later changes fairly.
**Done when:** you can run it on a symbol and get, per setup type, the sample size and the
average/median forward return over the next N bars — and you trust it isn't peeking ahead.

> Every phase from here on is validated by re-running this backtest before it earns its weight.

### Phase 15 — Volume & momentum *(low-risk warm-up, all internal)*
The gap in the core: volume was never built in, and it matters a lot in crypto (a breakout on
high volume means far more than one on thin volume).
- Volume + a volume MA (e.g. 20-period) in `indicators/features.py`.
- A **volume-confirmation vote** in `signals/confluence.py`: a signal firing on above-average
  volume is stronger; a breakout on below-average volume is flagged weak.
- Optional later: **OBV** (volume-momentum) as an extra confluence input.
**Done when:** the report notes whether a signal is volume-confirmed, and the engine treats a
high-volume signal as stronger than a thin-volume one; backtest shows the split is not worse.

### Phase 16 — Multi-timeframe context *(engine-level; largest lift for least code)*
When analyzing 1h, also run trend + S/R on 4h and 1d and feed them in as **weighted context** —
a 1h setup agreeing with the higher-TF trend is categorically stronger than one fighting it.
Context flows **down** only (higher TF informs lower); a lower TF must never vote on a higher-TF
read. Lives in the engine, so it improves every output including the eventual dashboard.
```
src/structure/mtf.py       # higher-timeframe trend + S/R as context for the base timeframe
```
**Done when:** a flagged setup records whether it aligns with or fights the 4h/1d trend, and
that alignment affects its confidence; a 1h oversold-bounce inside a 1d downtrend no longer
flags as a clean bullish setup. Measure backtest hit-rate before/after the gate.

### Phase 17 — Confidence score + category-aware confluence
Replace the equal-weight tally/boolean with a **0–1 confidence**. Two changes:
- **Category-aware voting:** group votes by category (trend / momentum / volatility / volume /
  structure) and require agreement **across different categories**. "Trend + momentum +
  structure align" is real confluence; "RSI + Stochastic + MACD agree" is momentum said three
  times. Collapse correlated signals (S/R-proximity and Fib-proximity both mean "price is at a
  level" — one insight, not two; this is the same overlap that got the trendline vote dropped
  in Phase 6).
- **Magnitude:** weight by reliability (from Phase 14) and strength (how oversold RSI is, how
  many touches a level has, higher-TF alignment from Phase 16), emitting a continuous score.
```yaml
confluence:
  require_categories: 3    # a flagged setup must span at least this many categories
  category_weights: {trend: 1.0, momentum: 1.0, volatility: 0.8, volume: 0.8, structure: 1.2}
```
**Done when:** `gather_signals` emits a 0–1 confidence with weighted reasons; the backtest shows
higher-confidence setups behave differently from lower ones (the proof it's meaningful), and
expectancy is ≥ the unweighted baseline.

### Phase 18 — Technical-analysis toolkit *(curated; each item earns its vote via backtest)*
Add tools that each measure something *different*, incrementally — and promote a tool to a
weighted vote **only when the backtest shows it earns it** (apply the "don't rush patterns" rule
to the whole toolkit).
- **Trend:** **ADX** (trend *strength* — tells you whether trend-following signals even apply;
  one filter that prevents many bad signals). Optional/advanced: Ichimoku.
- **Momentum:** **Stochastic** (second read, big in forex); **RSI divergence** (price higher
  high, RSI lower high = weakening — builds directly on existing swings; high value).
- **Volatility:** **Bollinger Bands** + **ATR** (ATR is the key to calibrating detectors across
  markets — see Phase 19).
- **Structure:** **round-number / psychological levels** (1.1000 in FX, 100,000 in BTC — act as
  magnets; especially strong in forex). Named patterns (Phase 9) stay optional/last.
```
src/indicators/features.py      # + ADX, Stochastic, Bollinger, ATR, OBV
src/structure/divergence.py     # RSI divergence, built on existing swings
src/structure/round_numbers.py  # psychological levels
```
```yaml
indicators:
  adx: {period: 14, trend_threshold: 25}
  stochastic: {k: 14, d: 3}
  bollinger: {period: 20, stddev: 2}
  atr: {period: 14}
  obv: true
structure:
  round_numbers: true
```
**Done when:** each added tool is in the facts and (if promoted) a vote; the backtest shows the
enriched read is coherent and no tool is added on faith.

### Phase 19 — Market adaptation (crypto vs forex)
Same formulas, but a few things genuinely differ — handling them is what makes this "best for
both" rather than crypto-only.
```
src/market/adaptation.py
```
- **Volume means different things.** Crypto = real exchange volume (meaningful). Forex feeds
  usually give only **tick volume** (a proxy) — treat forex volume signals as weaker/contextual
  and have the explanation say so; never present tick-volume like real volume.
- **Sessions & gaps (forex only).** Flag the active Tokyo/London/NY session and weekend gaps
  (Sunday open can jump from Friday close). Crypto is 24/7 — skip entirely.
- **Volatility calibration.** Use **ATR-relative** thresholds ("significant move" = a multiple
  of ATR) so the same detectors behave sensibly in both markets automatically — fixed % moves
  don't transfer between BTC and EUR/USD.
- **Round numbers weigh more in forex** than in crypto.
```yaml
market_adaptation:
  volume_type: auto         # real (crypto) vs tick (forex), inferred from asset class
  use_sessions: auto        # on for forex, off for crypto
  volatility_reference: atr  # calibrate "significant move" by ATR, not a fixed %
```
**Done when:** a crypto pair and a forex pair each produce a coherent read; forex correctly uses
tick-volume caveats and session/gap awareness; "significant move" scales sensibly via ATR.

### Phase 20 — Robustness *(do before trusting the output)*
- **Layer-2 consistency check** (`advisor/verify.py`): confirm the key prices in Claude's
  explanation match the facts dict — a regex or LLM-as-judge pass. This *enforces* the
  never-contradict-Layer-1 rule instead of hoping, and catches the day the model hallucinates a
  number.
- **Snapshot regression test** (`tests/test_snapshot.py`): run `build_facts` on a fixed
  real-data CSV fixture and assert the facts dict — catches silent detector drift when you tune.
- **Structured explanation output**: have `explain()` optionally return JSON
  (`setup` / `why` / `invalidation` fields) via structured outputs — programmatically usable by
  the dashboard and alerts, and it feeds the "return data, not images" API (Phase 24) directly.
**Done when:** a contradicting explanation is caught by `verify.py`; the snapshot test guards
the facts dict; and `explain()` can return structured `setup/why/invalidation`.

### Phase 21 — Context layer (sentiment, calendar, news)
Extra *facts* for Layer 2 — never touches the detectors.
```
src/context/
├── sentiment.py     # crypto Fear & Greed (alternative.me free API)
├── calendar.py      # upcoming high-impact economic events (Finnhub free tier)
└── news.py          # recent relevant headlines; Claude summarizes and factors them in
```
Note: **Forex Factory has no official API** — prefer a provider with a real one. Added to the
facts summary so Claude can say "price at resistance *and* a high-impact USD event in 2 hours —
expect volatility."
```yaml
context:
  fear_greed: true
  economic_calendar: true
  news: true
```
**Done when:** the report shows a small context panel (sentiment / next event / headlines) and
the explanation references it when relevant. *Caveat: context, not prediction — it helps you
avoid being blindsided (trading into a Fed announcement), not foresee price.*

### Phase 22 — Derivatives / positioning engine *(crypto-only; validated after the backtest)*
High-signal because it shows *positioning and leverage* that price-only TA can't see — but it's
context/sentiment, so it feeds **weighted votes** (Phase 17) and **facts** (Layer 2), gated to
crypto and only given weight once the backtest confirms it.
```
src/derivatives/{open_interest,funding,long_short,liquidations}.py
```
- **OI + funding** first — cleanest data, straight from exchange futures APIs via `ccxt`
  (`fetchOpenInterest`, `fetchFundingRate`). Rising OI = conviction; funding extremes are a
  *contrarian* signal.
- **Long/short** next, then **liquidations** last (via an aggregator like CoinGlass; modeled,
  not exchange-confirmed, reliable mainly for BTC/ETH — treat as soft context).
- **The forex catch:** retail forex has no consolidated OI, no perp funding, no public
  liquidation feed. This engine is a **crypto-only bonus** (a real reason to make crypto your
  primary market); the shared TA engine still serves forex, derivatives just stays dark for it.
```yaml
derivatives:
  enabled: auto            # crypto only; ignored for forex
  source_ohlc_funding: ccxt
  source_aggregate: coinglass
  use_liquidations: true   # soft/modeled; least reliable
```
**Done when:** OI/funding feed the score and facts for a crypto perp, gated off for forex, and
the backtest shows funding/OI extremes actually move forward returns before long/short and
liquidations are added.

### Phase 23 — Timeframe policy & multi-timeframe synthesis
Offer `15m, 30m, 1h, 4h, 1d` as selectable (skip 5m — mostly noise, needs real-time alerting
this app isn't). Three rules: context comes from **above, never below**; lower TFs are for
*timing, not direction*; **weight confidence by timeframe** (a daily setup outscores the same
setup on 15m). Add `synthesize()` to `advisor/explain.py`: it takes the **structured facts from
all selected timeframes at once** (never summaries of summaries) and produces one cross-timeframe
read that explicitly states whether the timeframes align or conflict. Drive it from the CLI now
(`analyze.py --symbol BTC/USDT --timeframes 1h,4h,1d`) so Phase 25's checkboxes wire to a
capability that already works.
```yaml
timeframes:
  selectable: [15m, 30m, 1h, 4h, 1d]
  context_from: [4h, 1d]
  weights: {15m: 0.6, 30m: 0.7, 1h: 1.0, 4h: 1.2, 1d: 1.4}
```
**Done when:** one command on several timeframes prints each timeframe's analysis plus a
synthesis that explicitly states alignment or conflict.

### ★ Phase 24 — API backend (FastAPI) + serialize seam
Wrap the engine in a FastAPI backend that **returns JSON, not images**.
```
src/api/app.py             # POST /report + GET /analysis, /pairs, /timeframes; CORS enabled
src/service/serialize.py   # ★ detector objects -> chart series + overlay JSON (single seam)
```
Contract sketch:
```
GET /pairs        -> [{ symbol, asset_class, label }]
GET /timeframes   -> ["15m","30m","1h","4h","1d"]
POST /report  { market, symbol, timeframes[] }
  -> per timeframe: candles[{time,o,h,l,c,volume}], overlays{swings, levels, trendlines, fib,
     markers}, facts, confluence{bias, triggered, confidence, signals[]},
     explanation{setup, why, invalidation}, higher_tf, base_rate, context, (derivatives?)
  + optional cross-timeframe synthesis
```
`serialize.py` is the **single** place detector objects become JSON, mirroring the selection
logic in `viz/chart.py` (nearest-N S/R, r²-gated trendlines, fib band) so the web chart shows
exactly what the facts quote — the Phase 8 consistency guarantee, now over JSON. Short-TTL cache
keyed by `(symbol, timeframe)`. Explanation stays key-gated (facts-only fallback with no API
key). Verify it in FastAPI's auto-generated `/docs` **before** touching Svelte — the JSON
contract is the seam between backend and frontend.
**Done when:** `/report` returns the full payload for BTC/USDT across chosen timeframes, visible
and correct in `/docs`.

### Phase 25 — Web UI: Svelte + TypeScript frontend
A separate SvelteKit + TS app consuming the API. Return-data-not-images makes it professional:
zoom, pan, hover, overlaid levels/markers.
```
frontend/                       # own package.json (SvelteKit + TS, or Svelte+Vite SPA)
└── src/lib/
    ├── api/{client.ts, types.ts}      # typed fetch wrapper + types matching the JSON shape
    └── components/
        ├── ReportForm.svelte          # market / pair / timeframe selectors + Generate
        ├── PriceChart.svelte          # lightweight-charts in onMount: candles + structure
        ├── Explanation.svelte         # Claude's setup / why / invalidation
        ├── ContextPanel.svelte        # sentiment / next event / headlines
        └── TimeframeTabs.svelte
```
- **State:** Svelte 5 runes (`$state`, `$derived`) — no external store lib needed.
- **Charts:** TradingView **`lightweight-charts`** (framework-agnostic; init in `onMount`).
- **Polish:** Tailwind + shadcn-svelte (or Skeleton/Bits+Melt) for a clean, non-templated look.
- Keep `lib/api/types.ts` in tight sync with the backend response model (generate from it so
  they can't drift) — clean typed API boundaries read well in a portfolio.
**Done when:** picking BTC/USDT + 1h and 4h and hitting Generate shows two interactive charts
(levels + signals drawn on) each beside its explanation, plus the context panel and a
cross-timeframe summary.

### Phase 26 — Forex provider *(last — the payoff of the Phase 13 abstraction)*
Implement `data/forex_api.py` against a chosen provider (Twelve Data / Alpha Vantage / Finnhub;
key'd, often rate-limited), register FX pairs, confirm the whole pipeline runs on an FX pair.
No other code changes — that's the point of the abstraction.
```yaml
data:
  forex_provider: twelvedata    # twelvedata / alphavantage / finnhub; key in .env
```
**Done when:** an FX pair (e.g. EUR/USD) flows through the same `/report` endpoint and renders
in the UI like a crypto pair, with tick-volume/session caveats surfaced.

---

## 4. Cross-cutting: DevX, CI, and workflow

Run alongside the phases, not as a single block:
- **CLI args on `analyze.py`** (`--symbol`, `--timeframe(s)`, `--output`) + a watchlist/batch
  mode, so you stop editing `config.yaml` per run. (Pairs naturally with Phase 12/23.)
- **CI**: a GitHub Action running `pytest -m "not network"` on push (the ~85 tests guard the
  repo), plus `ruff` + `mypy`, and pinned `requirements.txt` versions. Clean CI reads well.
- **Per-upgrade workflow with Claude Code:** new branch → give it the specific phase + "add
  tests" → run the "done when" check yourself → ask it to explain the changes in plain language
  → commit; merge to `main` only when the check passes.

---

## 5. Honest caveats (keep these in view the whole way)

- **It won't predict the future.** Confluence, multi-timeframe alignment, volume, context, and
  positioning all reduce some noise and help you *see* — none is a crystal ball. The advisor
  will be "wrong" regularly; that's normal.
- **A good backtest is not proof of an edge.** Report sample size and horizon; never a bare
  "accuracy %". Guard look-ahead bias; the biggest trap is **over-optimization** — tuning
  thresholds until past data looks perfect. Keep parameters sensible and standard.
- **Algorithmic S/R and trendlines won't always match your eye.** Reasonable readers disagree.
  Treat the output as a helpful second opinion.
- **Context and positioning are context, not triggers.** Overcrowded-long funding "can" precede
  a reversal — until price grinds up for weeks. Let the backtest decide every input's weight.
- **Layer 2 only narrates Layer 1.** The UI renders; it never re-reasons. Not financial advice.

---

## 6. Sequencing rationale (one glance)

Protect the core (11) → JSON service seam (12) → pluggable + clean data (13) → **build the
backtest instrument (14)** → validate each analytical upgrade against it: volume (15),
multi-timeframe (16), confidence scoring (17), toolkit (18), market adaptation (19) → robustness
(20) → additive context (21) and crypto derivatives (22) → timeframe synthesis (23) → **front
door**: API (24) then Svelte UI (25) → forex last (26). Measurement precedes tuning; the UI sits
on an engine whose signals you've actually measured; forex is a drop-in, not a rebuild.
