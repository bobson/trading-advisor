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
