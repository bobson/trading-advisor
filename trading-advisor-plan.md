# Trading Advisor — Build Plan (from scratch, Python)

A step-by-step plan for a **visual trading advisor**: it analyzes a chart, draws the
structure it finds (trend, support/resistance, trendlines, Fibonacci), flags
higher-confidence setups when several signals agree, and **explains its reasoning in
plain trading language** — so you decide and trade, and you learn as you go.

Built for a beginner, structured so it can be handed to Claude Code one phase at a time.

**What this is NOT:** it does not place trades, and it does not "learn to become
profitable." It knows trading concepts and applies them consistently to what it sees.
Its value is clarity and education — seeing the market better and understanding *why* —
not predicting the future. Nothing predicts the future reliably. None of this is
financial advice.

---

## 1. The core design: two layers

Everything below is built on one idea — separate the **facts** from the **explanation**.

**Layer 1 — The eyes (deterministic, reliable).**
Pure math and rules computed exactly from the price data: indicators, candlestick
patterns, swing points, support/resistance, trendlines, trend direction, Fibonacci.
No guessing. This layer outputs plain structured facts (numbers and labels).

**Layer 2 — The brain/voice (reasoning & teaching).**
A Claude model that receives Layer 1's facts and reasons about them in trading language:
*"Uptrend making higher highs, pulling back to support near 61,200, RSI oversold —
a classic buy-the-dip setup, but volume is weak, so caution."* This is where trading
knowledge lives — as the vocabulary and framework for the explanation. It reasons over
the **computed facts**, not raw pixels, which is what makes it reliable.

> The single most important building block for Layer 1 is **swing-point detection**
> (the local highs and lows, a.k.a. pivots). Support/resistance, trendlines, trend
> direction, and later named patterns are all built on top of swing points. Get that
> one thing solid and the rest follows.

---

## 2. Tools & accounts to set up first

**On your machine**
- Python 3.11+
- VS Code (or similar) + Claude Code
- Git

**Accounts**
- An **Anthropic API key** (for Layer 2). See current models & pricing at
  https://docs.claude.com/en/docs/about-claude/models — a **Sonnet-class model** is a
  good balance of quality, speed, and cost for explanations.
- **Exchange data access:** you can pull candles through `ccxt` with **no account or
  keys needed** for public market data. (If you later want a specific exchange's private
  data, use read-only keys — this app never needs trade or withdrawal permissions.)

**Python libraries** (install into a virtual environment)
- `ccxt` — fetch OHLCV candle data (read-only use here)
- `pandas` — the core data structure for all price data
- `pandas-ta-classic` — indicators + candlestick patterns (**use this fork**, not the
  original `pandas-ta`, which is now flagged as at risk of discontinuation)
- `scipy` — peak/valley detection, the basis for finding swing points
- `numpy` — numeric helpers (line fitting for trendlines, clustering levels)
- `mplfinance` — candlestick charts you can annotate with lines, levels, and markers
- `anthropic` — official SDK to call Claude for the reasoning layer
- `python-dotenv` — load the API key from a `.env` file
- `pydantic` — validate config so a typo can't silently break things
- `pytest` — tests, especially for the detector logic

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install ccxt pandas scipy numpy mplfinance anthropic python-dotenv pydantic pytest
pip install "git+https://github.com/xgboosted/pandas-ta-classic"
```

---

## 3. Project folder structure

```
trading-advisor/
├── .env                      # ANTHROPIC_API_KEY — NEVER commit this
├── .env.example
├── .gitignore                # include .env, .venv, __pycache__, data/, outputs/
├── README.md
├── requirements.txt
├── config.yaml               # symbol, timeframe, detector sensitivity, model choice
│
├── src/
│   ├── __init__.py
│   ├── config.py             # loads + validates config.yaml and .env (pydantic)
│   │
│   ├── data/
│   │   ├── exchange.py       # ccxt: fetch OHLCV candles (read-only)
│   │   └── cache.py          # save/load candles locally to avoid re-downloading
│   │
│   ├── indicators/           # LAYER 1 — reliable tier
│   │   └── features.py       # moving averages, RSI, MACD, candlestick patterns
│   │
│   ├── structure/            # LAYER 1 — the part you care about most
│   │   ├── swings.py         # swing/pivot detection — THE foundation (scipy)
│   │   ├── support_resistance.py  # cluster swing points into price levels
│   │   ├── trendlines.py     # connect swing lows/highs into sloped lines
│   │   ├── trend.py          # higher-highs/lower-lows + moving-average slope
│   │   └── fibonacci.py      # retracement levels from a chosen swing high/low
│   │
│   ├── patterns/             # LAYER 1 — OPTIONAL, hardest, added late
│   │   └── chart_patterns.py # head & shoulders, double top/bottom (geometry on swings)
│   │
│   ├── signals/
│   │   └── confluence.py     # collect votes from detectors -> flag when N agree, with reasons
│   │
│   ├── advisor/              # LAYER 2 — the brain/voice
│   │   ├── facts.py          # assemble all computed facts into a structured summary (dict/JSON)
│   │   └── explain.py        # send facts to Claude, get a plain-language explanation
│   │
│   ├── viz/
│   │   └── chart.py          # mplfinance: draw candles + levels + trendlines + signal markers
│   │
│   └── advisor_run.py        # orchestrates: data -> detectors -> confluence -> facts -> explain -> chart
│
├── scripts/
│   ├── download_data.py      # one-off: pull history for a symbol
│   └── analyze.py            # run the advisor: prints explanation + saves an annotated chart
│
├── data/                     # cached candles (gitignored)
├── outputs/                  # saved annotated charts + written explanations (gitignored)
└── tests/
    ├── test_swings.py        # most important early test — the foundation must be correct
    ├── test_structure.py     # support/resistance, trendlines, trend direction
    └── test_confluence.py    # the voting logic
```

Why this shape: Layer 1 detectors are each isolated and independently testable; the
confluence engine combines them; Layer 2 only ever consumes their structured output.
You can build and verify one detector at a time, and later add named patterns or a web
dashboard without touching the core.

---

## 4. Build roadmap (phases)

Build in order. Each phase has a clear "done when" check. Do the reliable tier and the
structure detection *before* the reasoning layer, so Claude always has correct facts to
reason about.

### Phase 0 — Skeleton
Repo, virtualenv, `.gitignore`, `config.yaml`, `.env.example`, install libs.
**Done when:** a fresh `pip install -r requirements.txt` works and the repo imports cleanly.

### Phase 1 — Data in
`data/exchange.py` (fetch OHLCV via ccxt) + `data/cache.py` + `scripts/download_data.py`.
**Done when:** you can download ~6 months of BTC/USDT 1h candles into a clean pandas
DataFrame and save it locally.

### Phase 2 — Indicators & candlestick patterns (reliable tier)
`indicators/features.py`: add moving averages, RSI, MACD, and a few candlestick patterns
as columns on the DataFrame.
**Done when:** values match a chart you trust (e.g. TradingView) for the same symbol/period.

### Phase 3 — Swing-point detection (THE foundation)
`structure/swings.py`: find local highs and lows (pivots) using `scipy`, with a
sensitivity setting so you can control how major a swing must be to count.
**Done when:** plotting the detected swings on the chart marks the highs and lows your
eye would pick, and `tests/test_swings.py` passes on known inputs.

### Phase 4 — Structure detection (the stuff you care about)
Built on Phase 3's swings:
- `structure/support_resistance.py` — cluster nearby swing points into price levels
- `structure/trendlines.py` — fit lines through consecutive swing lows / swing highs
- `structure/trend.py` — classify up / down / sideways from higher-highs-higher-lows vs
  lower-highs-lower-lows, confirmed by moving-average slope
**Done when:** the annotated chart shows levels, trendlines, and a trend label that look
reasonable against your own read of the chart.

### Phase 5 — Fibonacci
`structure/fibonacci.py`: retracement levels from a chosen swing high and low (auto-pick
the most recent major swing, or let it be configurable).
**Done when:** the Fib levels plot correctly between the chosen swing points.

### Phase 6 — Confluence engine
`signals/confluence.py`: each detector emits a vote (bullish / bearish / neutral) with a
short reason. The engine flags a setup only when a configurable number (e.g. 2–3) agree,
and records *why*.
**Done when:** given a candle where you can reason out the answer by hand, the engine
produces the expected flag and lists the contributing reasons.

### Phase 7 — The reasoning layer (Claude explains)
`advisor/facts.py` gathers all computed facts into one structured summary;
`advisor/explain.py` sends it to a Claude model and returns a plain-language explanation
that teaches as it describes ("here's the setup, here's why, here's what would invalidate it").
**Done when:** running the advisor on a symbol prints a clear, accurate explanation that
matches the computed facts (it should never contradict Layer 1).

### Phase 8 — Visualization
`viz/chart.py` with `mplfinance`: candles + support/resistance levels + trendlines + Fib +
markers where confluence fired. `scripts/analyze.py` saves the annotated chart and the
written explanation to `outputs/`.
**Done when:** one command on a symbol gives you an annotated chart image plus the
explanation, side by side.
> Optional later: a web dashboard using TradingView's free `lightweight-charts` for an
> interactive, live-updating version. Not needed to be useful.

### Phase 9 — Named chart patterns (OPTIONAL, hardest — add last)
`patterns/chart_patterns.py`: head & shoulders, double top/bottom, triangles, via
geometric rules on swing points. Expect this to be approximate — it will miss some and
over-call others, and needs tuning. That's why it comes last.
**Done when:** it labels clear textbook examples correctly; treat fuzzy cases as best-effort.

### Phase 10 — Chart-image analysis (OPTIONAL bonus)
Let the advisor also explain an uploaded chart *screenshot* using Claude's vision. Useful,
but remember pixels are a worse data source than the real numbers — keep this secondary to
the data-driven pipeline.

---

## 5. Config

- **`.env`** holds `ANTHROPIC_API_KEY` and is never committed. Commit `.env.example` with
  the name only.
- **`config.yaml`** holds everything else. Starting point:

```yaml
market:
  exchange: binance
  symbol: BTC/USDT
  timeframe: 1h              # switch to 4h later by changing this one line
  history_candles: 4320      # ~6 months of 1h candles

structure:
  swing_sensitivity: 5       # how many bars each side define a pivot (higher = only major swings)
  sr_cluster_tolerance_pct: 0.5  # how close levels must be to merge into one S/R zone

indicators:
  rsi_period: 14
  rsi_oversold: 30
  rsi_overbought: 70
  fast_ma: 20
  slow_ma: 50

confluence:
  min_agreeing_signals: 2    # flag a setup only when at least this many agree

advisor:
  model: claude-sonnet        # see docs.claude.com for exact current model names
  explanation_style: teaching # verbose, teaches the concepts as it explains
```

> To try 4h later, change `timeframe` to `4h` and lower `history_candles`. Everything
> else stays the same.

---

## 6. Honest caveats (keep these in mind the whole way)

- **It won't predict the future.** Confluence reduces some noise; it does not create a
  crystal ball. The advisor will be "wrong" regularly — that's normal and expected.
- **Algorithmic trendlines and S/R won't always match your eye.** Reasonable readers
  disagree on which swings to connect. Treat the output as a helpful second opinion.
- **Layer 2 must never override Layer 1.** Claude explains the computed facts; if it ever
  contradicts them, that's a bug in how you're feeding it the facts. Keep the facts
  authoritative.
- **This is a learning and clarity tool, not investment advice.** You make the decisions.

---

## 7. Learning to read the code (do this alongside the build)

You don't need to write Python from scratch, but you committed to *reading* it — good, and
this project is a great way to learn. Practical approach:
- After Claude Code writes each phase, ask it to walk you through the file line by line in
  plain language before moving on.
- The detector files (`swings.py`, `support_resistance.py`) are the best ones to actually
  understand, because they encode the trading logic you care about.
- You'll be able to read a file long before you could write one — that's the goal, and it's
  enough to supervise the project safely.

---

## 8. How to drive this with Claude Code

- Put this file in the repo root as `PLAN.md` and point Claude Code at it.
- Work **one phase per session**. Run each phase's "done when" check yourself before moving on.
- Ask for tests alongside code, especially for `structure/` and `signals/`.
- After each phase, ask Claude Code to explain the new code to you, then commit to git so
  you always have a working checkpoint.

Suggested first prompt to Claude Code:
> "Implement Phase 0 and Phase 1 from PLAN.md: repo skeleton, config loading, and
> `data/exchange.py` + `scripts/download_data.py` using ccxt to fetch BTC/USDT 1h candles
> (public data, no keys). Include a test that downloads and validates a small candle
> DataFrame. Then walk me through each file in plain language."

---

# Part 2 — Interactivity & multi-market (extends the phases above)

Everything here sits *on top of* the working command-line advisor. Build it only
after Phases 0–8 work. The detectors, confluence engine, and Claude explanation
do not change — you're adding a new front door and extra context, not rebuilding.

## Pluggable data source (crypto + forex)

Refactor the data layer so the market is just a config choice. The same candle
DataFrame comes out either way, so every detector and the reasoning layer stay
identical — a candle is a candle, whether it's BTC/USDT or EUR/USD.

- **Crypto** → `ccxt` (already built), no keys needed for public data.
- **Forex** → a provider with a free tier. Good current options: **Twelve Data**
  and **Alpha Vantage** (both cover FX OHLC on free tiers), or **Finnhub** (covers
  forex + crypto + economic calendar + news in one API — attractive because it can
  also power the context layer below). Each needs a free API key. Check each one's
  current free-tier limits before committing — they change.

New files:
```
src/data/
├── base.py          # common interface: get_candles(symbol, timeframe, limit) -> DataFrame
├── crypto_ccxt.py   # ccxt implementation (rename of exchange.py)
└── forex_api.py     # forex provider (Twelve Data / Alpha Vantage / Finnhub)
```
The rest of the app calls `base.get_candles(...)` and never knows which market it is.

## Phase 11 — Web UI: Svelte + TypeScript frontend (polished, portfolio-grade)

Wrap the advisor in a web app with a **FastAPI backend** and a **Svelte + TypeScript
(SvelteKit)** frontend. Svelte is the nicer solo-build experience — less boilerplate,
and Svelte 5's runes handle state without an external library — and it's a well-regarded
skill that can make a portfolio stand out. (If you ever need to target React-only job
postings, the component concepts port over directly; the backend below wouldn't change.)

**Key architecture decision — return data, not images.** The backend sends
*structured JSON* (candles + detected levels, trendlines, swing points, signals,
plus the explanation text and context), and the Svelte app draws the chart
**interactively**. This is what makes it look professional (zoom, pan, hover,
overlaid levels/markers) rather than a flat picture. The `mplfinance` PNG from
Phase 8 stays as your command-line output; the web app gets the interactive version.

**Backend (FastAPI)**
- Endpoint `POST /report` takes `{market, symbol, timeframes[]}`, runs the existing
  advisor per timeframe, and returns JSON: for each timeframe the candles, the
  detected structure (S/R levels, trendlines, swings, Fib), the confluence signals,
  and Claude's explanation — plus the shared context panel (sentiment / calendar / news).
- Enable CORS so the Svelte dev server can call it.

**Frontend (Svelte + TypeScript)**
- **Framework: SvelteKit** — scaffold with the official Svelte CLI (`npx sv create`),
  choose the **TypeScript** option. It's the standard Svelte meta-framework; you can run
  it as a simple single-page app pointed at the FastAPI backend (a plain Svelte + Vite
  SPA via `npm create vite@latest -- --template svelte-ts` is a lighter alternative if
  you'd rather skip SvelteKit's routing).
- **State: Svelte 5 runes** (`$state`, `$derived`) — built in, no Redux/Zustand
  equivalent needed. This is one of Svelte's real advantages.
- **Charts: TradingView `lightweight-charts`** — framework-agnostic; initialize it in a
  component's `onMount`. Industry-standard candlestick look, and it supports overlaying
  your levels, trendlines, and signal markers.
- **Styling/polish: Tailwind CSS + shadcn-svelte** (or Skeleton UI / Bits UI + Melt UI) —
  the fastest route to a clean, modern, non-templated look that reads well to reviewers.
- **Data fetching:** a small typed `fetch` wrapper is enough given runes; add
  `@tanstack/svelte-query` if you want polished loading/error/caching states (a nice
  portfolio touch).
- **Multi-timeframe UI:** market dropdown, pair selector, timeframe checkboxes
  (1h / 4h / 1d), a Generate button, then tabbed or stacked results — one interactive
  chart + explanation per timeframe, with an optional Claude cross-timeframe summary
  at the top ("daily up, 1h pulling back into support").

New structure:
```
src/web/
└── app.py                     # FastAPI: POST /report returns JSON, CORS enabled

frontend/                      # separate SvelteKit + TS app (its own package.json)
├── package.json
├── svelte.config.js
├── tsconfig.json
├── vite.config.ts
└── src/
    ├── app.html
    ├── app.css
    ├── routes/
    │   └── +page.svelte       # the main advisor page
    └── lib/
        ├── api/
        │   ├── client.ts      # typed fetch wrapper for the FastAPI endpoint
        │   └── types.ts       # TypeScript types matching the backend's JSON shape
        └── components/
            ├── ReportForm.svelte    # market / pair / timeframe selectors + Generate
            ├── PriceChart.svelte    # lightweight-charts in onMount: candles + structure
            ├── Explanation.svelte   # Claude's write-up
            ├── ContextPanel.svelte  # sentiment / next event / headlines
            └── TimeframeTabs.svelte
```

**Tip for the portfolio angle:** keep `lib/api/types.ts` in tight sync with the
backend's JSON — clean, well-typed API boundaries are exactly what a reviewer looks for.
Ask Claude Code to generate the TypeScript types from the FastAPI response model so
they can't drift.

**Done when:** you run the FastAPI backend and the SvelteKit dev server, open the page,
pick BTC/USDT + 1h and 4h, hit Generate, and see two interactive charts (with levels and
signals drawn on) each beside its explanation, plus the context panel.

## Phase 12 — Context layer (sentiment, calendar, news)

Extra *facts* that feed into Claude's explanation (Layer 2). This never touches the
technical detectors — it just gives the brain more to reason about.

- **Crypto sentiment:** the **Crypto Fear & Greed Index** has a free API
  (alternative.me) — a single number + label, easy to add.
- **Economic calendar:** high-impact events (rate decisions, CPI, jobs) — matters for
  both markets, especially forex. **Finnhub** offers an economic calendar on its free
  tier. Note: **Forex Factory has no official API**; community scrapers exist but can
  violate terms of service and break without warning — prefer a provider with a real API.
- **News headlines:** a finance/crypto news API; Claude summarizes and factors them in.

New files:
```
src/context/
├── sentiment.py     # Fear & Greed (crypto)
├── calendar.py      # upcoming high-impact economic events
└── news.py          # recent relevant headlines
```
These get added to the facts summary in `advisor/facts.py`, so Claude can say things
like "price at resistance *and* a high-impact USD event in 2 hours — expect volatility."

**Done when:** the report shows a small context panel (sentiment / next event /
headlines) and Claude's explanation references it when relevant.

> Honest caveat: sentiment, calendar, and news add *context, not prediction*. They help
> you avoid being blindsided (e.g. trading into a Fed announcement), but they don't tell
> you what price will do.

## Config additions
```yaml
data:
  market_type: crypto          # 'crypto' or 'forex'
  forex_provider: twelvedata   # twelvedata / alphavantage / finnhub (forex only)
  # API keys go in .env, never here

web:
  timeframes: [1h, 4h, 1d]     # offered in the UI; a report can run several at once

context:
  fear_greed: true             # crypto sentiment
  economic_calendar: true
  news: true
```
Add provider keys (e.g. `TWELVEDATA_API_KEY`, `FINNHUB_API_KEY`) to `.env` and
`.env.example`.

## Build order reminder
Command-line advisor working (Phases 0–8) → pluggable data source → Phase 11 web UI
→ Phase 12 context layer. A form in front of detectors that don't work yet just hides
the real work.

---

# Part 3 — Upgrading the already-built core

The core advisor (Phases 0–10) is done and working. Everything below is *additive* —
it extends the working system without rewriting it. Treat the finished core as
something to protect.

## First: lock in the working core

Before adding anything, make the current working state a fixed point you can always
return to:
```bash
git add -A && git commit -m "Working core advisor (phases 0-10)"
git tag v1-core-advisor
```
Then do every upgrade on its own branch (`git checkout -b feature/volume`), and only
merge back to `main` once that upgrade's "done when" passes. A bug in a new branch can
never break your working core this way.

**Also update `CLAUDE.md`** so Claude Code's context reflects reality now that the core
exists: ask it to "update CLAUDE.md to describe the current built state — the detectors,
confluence engine, and reasoning layer that already exist." Accurate context makes every
upgrade prompt land better.

## Enhancement A — Volume & momentum (important for crypto)

This is the gap: the core lists RSI/MACD/MAs and candlesticks, but volume was never built
in, and volume matters a lot in crypto (a breakout on high volume means far more than one
on thin volume). Add:
- **Volume + a volume moving average** in `indicators/features.py` (e.g. 20-period
  average volume), so you can tell "above/below average volume" at a glance.
- **A volume-confirmation vote** in `signals/confluence.py`: when another signal fires
  *and* volume is above its average, that signal's confidence is boosted; a breakout on
  below-average volume is flagged as weak. This makes the confluence output smarter
  without changing its structure.
- Optional: **OBV (On-Balance Volume)** as a momentum-of-volume indicator (`pandas-ta-classic`
  has it) — a nice extra confluence input, add later.
- Momentum itself is already covered by RSI and MACD from Phase 2 — no new work there.

**Done when:** the report notes whether a signal is volume-confirmed, and the confluence
engine treats a high-volume signal as stronger than a thin-volume one.

This is the ideal **first** upgrade: low risk, extends code you already have, fully
testable, and no new external services.

## Recommended upgrade order

1. **Volume & momentum (Enhancement A)** — low risk warm-up, all internal.
2. **Pluggable data source** (crypto + forex) — a *refactor*, so do it carefully: after
   it, run the advisor on a known crypto symbol and confirm the output is unchanged
   (a regression check), since you've moved the data layer the whole app stands on.
3. **Phase 11 — Svelte web UI** — the biggest new surface. Build the FastAPI JSON
   endpoint first and verify it in FastAPI's auto-generated `/docs` page *before*
   touching Svelte; the JSON contract is the seam between backend and your frontend.
4. **Phase 12 — Context layer** (sentiment / calendar / news) — additive, just new fields
   in the facts summary that Layer 2 reads; low risk to the core.

## Per-upgrade workflow with Claude Code

For each item above, one focused session:
1. New branch.
2. Give Claude Code the specific enhancement from this plan + "add tests for it."
3. Run that enhancement's "done when" check yourself.
4. Ask Claude Code to explain the changes in plain language (keeps you able to read it).
5. Commit; merge to `main` only when the check passes.

The clean extension point throughout: most upgrades just **add new fields to the facts
summary** (`advisor/facts.py`) that Claude reads in Layer 2. Volume confirmation, a
Fear & Greed reading, an upcoming calendar event — all become extra facts the explanation
can reason about, without disturbing the detectors underneath.

Suggested first upgrade prompt to Claude Code:
> "On a new branch, implement Enhancement A (Volume & momentum) from Part 3 of PLAN.md:
> add volume and a volume moving average to indicators/features.py, and a volume-confirmation
> vote to signals/confluence.py so signals on above-average volume are treated as stronger.
> Add tests, then walk me through the changes."

---

# Part 4 — The technical-analysis toolkit (crypto + forex), before the frontend

Build this out *before* Phase 11. Goal: a strong, market-aware analytical engine for
**both** crypto and forex. Guiding principle — **best ≠ most.** A curated, non-redundant
set (a couple of tools per category) beats a pile of overlapping indicators. Each tool
below measures something *different*; confluence combines them.

## The curated toolkit, by category

**Trend** *(what direction, and is there even a trend?)*
- Moving averages + MA crossover — *already built.*
- **ADX (Average Directional Index)** — measures trend *strength*. Crucial: it tells you
  whether the market is trending (trend-following signals apply) or ranging (they don't).
  This one filter prevents a lot of bad signals. **Add it.**
- Optional/advanced: **Ichimoku Cloud** — a complete trend system, popular in crypto/forex.

**Momentum** *(is the move accelerating or tiring?)*
- RSI + MACD — *already built.*
- **Stochastic oscillator** — a second momentum read, widely used especially in forex.
- **RSI divergence** — price makes a higher high but RSI makes a lower high = momentum
  weakening, a classic early reversal warning. High value, and it builds directly on the
  **swing points you already have.** **Add it.**

**Volatility** *(how big is this move relative to normal?)*
- **Bollinger Bands** — volatility envelope + mean-reversion signals.
- **ATR (Average True Range)** — the size of a "normal" move. Even though the advisor
  doesn't place stops, ATR is what lets you say "this move is large *for this market*,"
  and it's the key to calibrating detectors across crypto and forex (below). **Add both.**

**Volume** *(is the move backed by participation?)*
- Volume + volume MA + confirmation — *added in Part 3.*
- **OBV (On-Balance Volume)** — volume-momentum; a useful extra confluence input.

**Structure** *(the map: where are the important prices?)*
- Swings → support/resistance, trendlines, trend classification, Fibonacci — *already built.*
- **Round-number / psychological levels** — prices like 1.1000 (forex) or 100,000 (BTC)
  act as magnets and barriers. Cheap to detect, and especially strong in forex. **Add it.**
- Named chart patterns (Phase 9) — optional, still last.

## Same math, different market: the adaptation layer

The indicators are the *same formulas* for crypto and forex — but a few things genuinely
differ, and handling them is what makes this "best for both" rather than crypto-only.
New module `src/market/adaptation.py`:

- **Volume means different things.** Crypto gives *real* exchange volume — volume analysis
  is meaningful. Forex is decentralized, so most feeds give only **tick volume** (number of
  price updates) as a *proxy*. So for forex, treat volume signals as weaker/contextual and
  have the explanation say so — don't present tick-volume like real volume.
- **Sessions & gaps (forex only).** Forex has Tokyo/London/New York sessions with very
  different volatility, and **weekend gaps** (Sunday open can jump from Friday close).
  Flag the active session and any gap. Crypto is 24/7, so skip this entirely.
- **Volatility calibration.** Crypto is far more volatile than most FX pairs, so *fixed*
  thresholds (e.g. "a 2% move") don't transfer. Use **ATR-relative** thresholds instead —
  define a "significant move" as a multiple of ATR — so the same detectors behave sensibly
  in both markets automatically.
- **Round numbers weigh more in forex** — give psychological levels a bigger confluence
  weight there than in crypto.

## Smarter confluence: category-aware voting

Upgrade `signals/confluence.py` so it doesn't double-count correlated signals (three
momentum indicators all saying the same thing is *one* insight, not three). Group votes
by category (trend / momentum / volatility / volume / structure) and require agreement
**across different categories** — e.g. "trend + momentum + structure align" is a real
confluence; "RSI + Stochastic + MACD agree" is just momentum said three ways. This is the
single biggest quality upgrade, and it's what separates a disciplined read from noise.

## New / updated files
```
src/indicators/features.py      # + ADX, Stochastic, Bollinger, ATR, OBV
src/structure/divergence.py     # RSI divergence, built on existing swings
src/structure/round_numbers.py  # psychological levels
src/market/adaptation.py        # volume type, sessions/gaps, ATR-based calibration
src/signals/confluence.py       # upgraded to category-aware, cross-category agreement
```

## Config additions
```yaml
indicators:
  adx: {period: 14, trend_threshold: 25}   # ADX above ~25 = trending
  stochastic: {k: 14, d: 3}
  bollinger: {period: 20, stddev: 2}
  atr: {period: 14}
  obv: true

structure:
  round_numbers: true

market_adaptation:
  volume_type: auto        # real (crypto) vs tick (forex), inferred from market_type
  use_sessions: auto       # on for forex, off for crypto
  volatility_reference: atr # calibrate "significant move" by ATR, not a fixed %

confluence:
  require_categories: 3    # a flagged setup must span at least this many categories
  category_weights: {trend: 1.0, momentum: 1.0, volatility: 0.8, volume: 0.8, structure: 1.2}
```

## Done when
Running the advisor on a **crypto** pair and a **forex** pair each produces a coherent,
multi-category read; forex correctly uses tick-volume caveats and session/gap awareness;
"significant move" scales sensibly between the two via ATR; and confluence only flags
setups that agree across *different* categories.

## Honest caveats
- None of this predicts price. A richer, disciplined read reduces some noise and helps you
  *see* clearly — it is not an edge by itself.
- The real trap here is **over-optimization**: tuning thresholds until past data looks
  perfect. Keep parameters sensible and standard; don't curve-fit them to history.

## Suggested prompt to Claude Code
> "On a new branch, implement Part 4 of PLAN.md in this order: (1) add ADX, Stochastic,
> Bollinger Bands, ATR, and OBV to indicators/features.py with tests; (2) add
> structure/divergence.py (RSI divergence using existing swings) and
> structure/round_numbers.py; (3) add market/adaptation.py for volume-type, forex
> sessions/gaps, and ATR-based volatility calibration; (4) upgrade signals/confluence.py
> to category-aware, cross-category agreement. After each step, run its tests and walk me
> through the changes."

---

# Part 5 — Final pre-frontend plan (validation-first)

Synthesis of a code review of the built app. The organizing insight: **you cannot yet
tell whether the signals mean anything.** So the sequence below is validation-first —
build the measuring instrument, then use it to prove (or disprove) every other change.
Do this whole part *before* the frontend.

Overlap note — already in this plan, don't rebuild: volume (Part 3/4), ATR (Part 4),
category-aware confluence (Part 4). The items below are the *new* work, plus upgrades to
those.

## Priority 1 (foundation) — Backtest / evaluation harness

The biggest gap. For an *advisor*, this is not a trade simulator — it's a **forward-return
evaluator**: walk the history, run `gather_signals` at each bar, and measure what price did
in the next N bars after each flagged setup. Aggregate by setup type and by threshold.
This is what lets you tune `min_agreeing`, `proximity_pct`, and pattern tolerances **with
data instead of intuition** — and it's the instrument that proves whether Priorities 2–5
actually help.

**Honest caveat (build this in from the start):** a backtest can mislead via look-ahead
bias, overfitting, too-few signals, and regime change. A *good* result is not proof of a
future edge. Its early value is catching signals that are **noise**, and comparing changes
fairly. Guard against look-ahead bias explicitly (never use a bar's own future to compute
its signal), and always report the **sample size** (a setup seen 6 times proves nothing).

```
src/backtest/evaluate.py   # walk history, gather_signals per bar, forward-return stats
scripts/backtest.py        # run + print/save a report (win rate, avg forward return, N)
tests/test_backtest.py     # incl. an explicit look-ahead-bias guard test
```
**Done when:** you can run it on a symbol and get, per setup type, the sample size and the
average/median forward return over the next N bars — and you trust it isn't peeking ahead.

## Priority 2 — Multi-timeframe context (engine-level)

The largest analytical lift for the least code, since the detectors already exist. When
analyzing 1h, also run trend + S/R on 4h and 1d and feed them in as **weighted context/votes**:
a 1h setup agreeing with the higher-timeframe trend is categorically stronger than one
fighting it. This lives in the engine (not the UI), so it improves every output including
the eventual dashboard.
```
src/structure/mtf.py       # higher-timeframe trend + S/R as context for the base timeframe
```
**Done when:** a flagged setup records whether it aligns with or fights the 4h/1d trend, and
that alignment affects its confidence.

## Priority 3 — Confidence score, not a count (upgrades Part 4 confluence)

Replace the equal-weight tally/boolean with a **0–1 confidence**: weight signals (trend / S/R
> a single candle), factor in *strength* (how oversold RSI is, how many touches a level has,
higher-TF alignment from Priority 2), and emit a continuous score. Keeps category-awareness
from Part 4; adds magnitude. The confluence result already carries the raw votes, so this is
contained.
**Done when:** `gather_signals` emits a 0–1 confidence with the contributing weighted reasons,
and the backtest shows higher-confidence setups behave differently from lower ones (that's the
proof it's meaningful).

## Robustness — do before trusting output

- **Layer 2 consistency check** (`advisor/verify.py`): confirm the key prices in Claude's
  explanation match the facts dict — a cheap regex or an LLM-as-judge pass. This *enforces*
  the "never contradict Layer 1" invariant instead of just hoping. Catches the day the model
  hallucinates a number.
- **Snapshot regression test** (`tests/test_snapshot.py`): run `build_facts` on a fixed
  real-data CSV fixture and assert the facts dict. Catches silent detector drift when you
  tune something — your current tests use synthetic fixtures, so this covers integration.
- **Structured explanation output**: have `explain()` optionally return JSON
  (`setup` / `why` / `invalidation` fields) via structured outputs. Makes the explanation
  programmatically usable by the dashboard and alerts instead of a text blob — and it feeds
  the "return data, not images" design in Phase 11 directly.

## DevX (also strengthens the job-portfolio angle)

- **CLI args on `analyze.py`** (`--symbol`, `--timeframe`, `--output`) + a watchlist/batch
  mode, so you stop editing `config.yaml` per run.
- **CI**: a GitHub Action running `pytest -m "not network"` on push (you have ~85 tests —
  let them guard the repo), plus `ruff` + `mypy`, and pin `requirements.txt` versions. Clean
  CI reads well to a reviewer.

## Hold — do NOT rush

Don't make the chart-pattern detector more aggressive (wedges, flags, etc.). It over-calls by
design; without the backtest to keep it honest, more pattern types mostly add noise. Revisit
only after Priority 1 can validate them, and only promote a pattern to a (low-weight) vote
once the backtest shows it earns it.

## Sequence & how to instruct Claude Code

Build in priority order, each on its own branch, each with tests, merging to `main` only when
its "done when" passes:
1. Backtest harness → 2. Multi-timeframe context → 3. Confidence scoring → robustness checks
(consistency / snapshot / structured output) → DevX (CLI, CI). Then, and only then, Phase 11
frontend — now sitting on an engine whose signals you've actually measured.

Suggested next prompt to Claude Code:
> "On a new branch, implement Part 5 Priority 1 (the backtest/evaluation harness) from PLAN.md:
> src/backtest/evaluate.py walks historical candles, runs gather_signals at each bar, and
> measures forward returns over the next N bars per setup type, reporting sample size. Add
> scripts/backtest.py to run and print a report. Include tests, especially an explicit
> look-ahead-bias guard. Then walk me through it, and run it on BTC/USDT 1h so we can see
> whether the current signals show any forward-return difference."

---

# Part 6 — Derivatives / positioning engine (crypto-only)

This is ChatGPT's "Step 5," evaluated and scoped honestly. It's genuinely high-signal —
it shows *positioning and leverage*, which price-only TA can't see — but it is
**crypto-only**, and it's *context/sentiment*, not price structure. So it behaves like the
Part 2 context layer: it feeds **weighted votes into the score** (Part 5 Priority 3) and
**facts into Layer 2**. Build it **after the backtest** so you can verify it earns its weight.

## The four metrics and how to read them
- **Open interest (OI):** total outstanding contracts. Rising OI on a price move = fresh
  capital / conviction; a move on *falling* OI = existing positions unwinding (weaker).
- **Funding rate (perps):** payments between longs and shorts that tether perp to spot.
  Persistently high positive = overcrowded longs; deeply negative = overcrowded shorts.
  Extremes are a *contrarian* signal — they've historically preceded sharp reversals.
- **Long/short ratio:** how traders are positioned; another contrarian sentiment read.
- **Liquidations:** forced closes of leveraged positions; clusters show where leverage
  sits, cascades drive violent moves. **Caveat: liquidation heatmaps are modeled, not
  exchange-confirmed, and reliable mainly for BTC/ETH — treat as soft context, not fact.**

## The forex catch (this answers your crypto-vs-forex question)
Retail forex is decentralized spot/OTC: **no** consolidated open interest, **no** perpetual
funding, **no** public liquidation feed, **no** market-wide long/short. Only weak analogues
exist (CFTC Commitments of Traders — weekly, delayed, futures not spot; and broker-specific
client sentiment — one broker's book). So this engine is a **crypto-only bonus**. Keep the
pluggable data source: forex still works with the shared TA engine (Parts 4–5); derivatives
simply stays dark for it. **If these metrics excite you, that's a real reason to make crypto
your primary market.**

## Sourcing
- **OI + funding:** straight from exchange futures APIs via `ccxt`
  (`fetchOpenInterest`, `fetchFundingRate` / history) — Binance, Bybit, OKX, etc. Start here;
  cleanest data.
- **Long/short + liquidations:** via an aggregator — **CoinGlass** (API v4, 30+ exchanges;
  Python wrappers exist). Paid tiers — check current pricing/limits. (CoinGlass also publishes
  a 0–100 derivatives risk index — a real-world parallel to your own scoring engine.)

## Files (gated to `market_type == crypto`)
```
src/derivatives/
├── open_interest.py
├── funding.py
├── long_short.py
└── liquidations.py     # aggregator; modeled/soft context, least reliable
```
Feed into `signals/confluence.py` (weighted votes) and `advisor/facts.py` (Layer 2 narration).

## Config
```yaml
derivatives:
  enabled: auto            # crypto only; ignored when market_type is forex
  source_ohlc_funding: ccxt        # OI + funding direct from the exchange
  source_aggregate: coinglass      # long/short + liquidations
  use_liquidations: true           # soft/modeled context; the least reliable input
```

## Build order & validation
After Part 5 Priority 1 (backtest). Sequence: **OI + funding first** (cleanest data, highest
signal, ccxt-direct) → **long/short** → **liquidations last** (aggregator + modeled). Validate
each against forward returns in the backtest *before* giving it weight.

## Honest caveat
Positioning data is *context, not prediction*. Overcrowded-long funding "can" precede a
reversal — until it doesn't and price grinds up for weeks. Use it to add nuance to the read,
never as a standalone trigger, and let the backtest decide its weight.

## Prompt to Claude Code
> "After the backtest exists, on a new branch implement Part 6 (crypto-only derivatives
> engine) from PLAN.md, starting with src/derivatives/open_interest.py and funding.py using
> ccxt's fetchOpenInterest and fetchFundingRate for BTC/USDT perps, gated to run only when
> market_type is crypto. Add them as weighted votes to the confluence score and as facts for
> Layer 2. Include tests. Then use the backtest to check whether funding/OI extremes actually
> show a forward-return difference before we add long/short and liquidations."

---

# Part 7 — Timeframe policy & multi-timeframe synthesis

Closes two open decisions. Small, but they shape the engine.

## Selectable timeframes: add 15m and 30m, skip 5m
Offer `15m, 30m, 1h, 4h, 1d` as user-selectable. Adding them costs nothing — the same
detectors run on any candles. Skip **5m**: it's mostly noise and would need near-real-time
alerting to be useful, which this app isn't.

Three rules that keep lower timeframes from degrading the analysis:

1. **Context comes from above, never below.** Engine-level MTF (Part 5 Priority 2) looks
   *up* only: analyzing 1h pulls context from 4h/1d. A lower timeframe must never vote on a
   higher-timeframe read — that just injects noise.
2. **Lower timeframes are for timing, not direction.** The classic stack is higher TF for
   *direction*, lower for *entry timing*. 15m/30m refine where to act once 1d→4h→1h already
   agree; they are not standalone analysis.
3. **Weight confidence by timeframe.** Signal quality rises with timeframe, so the same
   setup on the daily should score higher than on 15m. Add a timeframe weight to the Part 5
   Priority 3 confidence score.

```yaml
timeframes:
  selectable: [15m, 30m, 1h, 4h, 1d]
  context_from: [4h, 1d]        # higher-TF context; never lower
  weights: {15m: 0.6, 30m: 0.7, 1h: 1.0, 4h: 1.2, 1d: 1.4}
```

## Multi-timeframe synthesis (build in the engine, before any UI)
Add `synthesize()` to `advisor/explain.py`: it takes the **computed facts from all selected
timeframes at once** and produces one cross-timeframe read — e.g. *"Daily uptrend with higher
highs; 4h pulled back to support at 61,200; 1h shows a bullish engulfing with RSI oversold at
that level — lower-TF entry aligned with higher-TF trend. Invalidation: 4h close below 60,800."*

**Critical:** synthesize over the **structured facts**, not by summarizing three separate
write-ups. Summarizing summaries loses precision and breaks the never-contradict-Layer-1
rule; raw facts let it catch real conflicts ("daily up but 4h making lower highs — mixed").

Drive it from the CLI now: `analyze.py --symbol BTC/USDT --timeframes 1h,4h,1d`, which
outputs a per-timeframe report plus the synthesis. Phase 11's checkboxes then wire to a
capability that already works — far easier than building both at once.

**Done when:** one command on several timeframes prints each timeframe's analysis plus a
synthesis that explicitly states whether the timeframes align or conflict.

---

# Part 8 — Advanced pattern engine (channels, rectangles, triangles, double tops)

All of these are **geometry on the swing points you already have**. No new foundation
needed. But read the two framing rules first — they decide whether this adds signal or noise.

## Framing rule 1: the shape is the setup, the breakout is the signal
A detected triangle is nearly worthless alone. A triangle that **breaks out, on expanding
volume, in the direction of the higher-timeframe trend** is a real event. So every pattern
must carry four things, not one:
- **Detection** — the geometry matches
- **Validation** — quality score (touch count, symmetry, duration, ATR-relative size)
- **Confirmation** — the breakout level, and whether it has actually broken *with* volume
- **Invalidation** — the price that kills the pattern

Emit patterns in three states: `forming` → `confirmed` → `failed`. Only `confirmed`
patterns get meaningful confluence weight. `forming` is context for the narration only.

## Framing rule 2: gate everything behind the backtest
Do **not** add these as weighted votes until Part 5's harness measures them. Per pattern
type, measure forward returns after *confirmation*, and always report **sample size** — a
pattern seen 7 times proves nothing. Patterns that don't beat baseline stay narration-only.

## Tier 1 — Build these (precise geometry, testable)

All built from consecutive swing highs/lows + line fitting (`numpy.polyfit`), with
**ATR-relative tolerances** (Part 4), never fixed percentages.

- **Channels (ascending / descending / horizontal).** Fit a line through ≥2–3 swing highs
  and another through ≥2–3 swing lows. Require: similar slopes (parallel within tolerance),
  price contained between them, ≥4 total touches. Direction from the slope sign.
- **Rectangle (range).** Horizontal S/R: swing highs cluster near one level, swing lows near
  another, both slopes ≈ 0. You largely have this from S/R clustering — the addition is
  treating it as a bounded *pattern* with a defined breakout level.
- **Ascending triangle.** Flat resistance (highs at ~one level) + rising support (higher
  lows). **Descending triangle.** Flat support + lower highs. **Symmetrical triangle.** Both
  lines converge (lower highs *and* higher lows). Require convergence, ≥4 touches, and that
  the apex is still ahead of the current bar.
- **Double top / bottom.** Two swing highs within ATR-scaled tolerance, separated by a
  meaningful trough; **neckline break confirms it.** (Triple variants: same code, three peaks.)
- **Flags / pennants** (optional): a sharp move ("pole") followed by a small counter-trend
  channel or tiny triangle. Easy once channels and triangles exist.

## The volume layer (this is what you were right about)
Textbook behavior, and it's what separates a real pattern from a drawn line:
- **Inside** a triangle, channel, or flag: volume typically **contracts** — participation
  drying up into the apex.
- **On breakout:** volume should **expand** sharply (e.g. > 1.5–2× the volume MA). A breakout
  on *below*-average volume is the classic false-breakout profile.
- **Double top/bottom:** lower volume on the second peak, expansion on the neckline break.

So each pattern gets a `volume_profile` field: `contracting` / `flat` / `expanding`, and the
confirmation carries a `volume_confirmed` boolean. **Crypto only for real volume** — in forex
this is tick volume, so downgrade its weight and say so (Part 4 adaptation).

## Tier 2 — Elliott Wave (optional, last, heavily caveated)
Different in kind from Tier 1. Wave counting is **subjective**: multiple valid counts coexist,
and counts are routinely revised after the fact, which makes it hard to falsify and hard to
automate honestly. If you build it:
- Lock it to **mechanical rules only** — wave 2 never retraces >100% of wave 1; wave 3 is never
  the shortest of 1/3/5; wave 4 doesn't overlap wave 1's territory. Reject any count violating these.
- Return **multiple candidate counts with confidence**, never one "the count."
- Keep it **narration-only**. Do not give it confluence weight.
- Honest expectation: this will be the least reliable module in the app. Build it for
  interest, not for signal — and consider skipping it in favour of polishing Tier 1.

## Anti-patterns to avoid (these are how pattern engines go wrong)
- **Hindsight/repainting bias:** a pattern that only appears once you can see the future is
  useless. Detect using bars up to the current bar *only*; the backtest's look-ahead guard
  must cover the pattern detector too.
- **Over-calling:** loose tolerances find patterns everywhere. Prefer fewer, higher-quality
  detections; require minimum touch counts and minimum duration in bars.
- **Double-counting:** a rectangle is also two double-tops; a channel contains flags. Deduplicate
  overlapping detections and keep the highest-quality one, or confluence inflates artificially.
- **Fixed percentages:** always scale tolerances by ATR so the same code works on BTC and EUR/USD.

## Files
```
src/patterns/
├── base.py            # Pattern dataclass: type, state, points, breakout, invalidation,
│                      #   quality, volume_profile, volume_confirmed
├── lines.py           # shared: fit/score a trendline through swings, touch counting
├── channels.py        # ascending / descending / horizontal
├── rectangles.py
├── triangles.py       # ascending / descending / symmetrical
├── double_tops.py     # double/triple top & bottom + neckline
├── flags.py           # optional
├── elliott.py         # optional, narration-only
└── dedupe.py          # resolve overlapping detections
```
Feeds `signals/confluence.py` (confirmed patterns only, weighted), `advisor/facts.py`
(all states, for narration), and `viz/chart.py` (draw the lines, neckline, breakout level).

## Config
```yaml
patterns:
  min_touches: 4
  min_duration_bars: 15
  tolerance_atr_mult: 0.5      # ATR-scaled, not fixed %
  require_confirmation: true   # only confirmed patterns get confluence weight
  volume_breakout_mult: 1.5    # breakout volume vs volume MA
  enable: [channels, rectangles, triangles, double_tops]
  elliott: false               # narration-only if enabled
```

## Build order
`base.py` + `lines.py` → rectangles (simplest) → channels → triangles → double tops →
dedupe → volume layer → **backtest each type** → only then assign confluence weights →
draw them on the chart → (optional) flags → (optional) Elliott.

## Done when
Each pattern type is detected with a state, quality score, breakout and invalidation levels;
volume profile is attached; overlapping detections are deduplicated; the backtest reports
per-type forward returns **with sample size**; and only types that earn it carry weight.

## Prompt to Claude Code
> "On a new branch, implement Part 8 Tier 1 from PLAN.md, starting with `src/patterns/base.py`
> (the Pattern dataclass with state/breakout/invalidation/quality/volume fields) and
> `src/patterns/lines.py` (trendline fitting and touch counting over existing swing points),
> then `rectangles.py` and `channels.py`. Use ATR-scaled tolerances, detect using only bars up
> to the current bar (no look-ahead), and emit forming/confirmed/failed states. Add tests with
> synthetic fixtures for each shape plus a look-ahead guard test. Keep them out of confluence
> for now — facts and chart only. Then walk me through the code."
