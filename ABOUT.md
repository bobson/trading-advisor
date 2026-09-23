# Trading Wizard — what it is and how it thinks

*A plain-language overview. Written to be shared with someone who hasn't seen the code.*

---

## What it is, in one line

**Trading Wizard reads a price chart, points out the structure a trained eye would notice, and
explains it in plain language — so a person can see the market more clearly and learn. It does not
place trades and it does not predict prices.**

Think of it as a patient teacher looking over your shoulder at a chart, not a signal service
promising you the next move.

---

## The one idea that makes it honest: two separate layers

Most "AI trading" tools blur two very different things — *measuring* the chart and *talking about*
the chart — into one black box that sounds confident. Trading Wizard keeps them strictly apart:

- **Layer 1 — the eyes (pure math).** Deterministic code measures the chart: trend direction,
  support and resistance levels, swing highs/lows, trendlines, Fibonacci levels, chart patterns
  (double tops, triangles, head-and-shoulders…), candlestick patterns, and momentum/volatility
  indicators (RSI, MACD, ADX, ATR, Bollinger Bands, volume). These are **facts** — numbers and
  labels, no opinion.

- **Layer 2 — the voice (Claude).** The Claude API receives *those facts* and explains what they
  mean in trading language. **It never sees the raw chart pixels or invents numbers** — it reasons
  only over what Layer 1 measured.

The unbreakable rule: **Layer 2 may never contradict Layer 1.** If the explanation ever disagreed
with the measured facts, that would be a bug, not an opinion. This is what stops the AI from making
things up — the classic failure of chatbots. It can only talk about numbers it was actually handed.

The flow, end to end:

```
market data → Layer 1 measures facts → facts handed to Claude → plain-language explanation
                       ↘ same facts also drawn on an interactive chart
```

Because the chart and the explanation are built from the *same* measured facts, the level the
explanation quotes is exactly the line you see drawn on the chart. They can't drift apart.

---

## What guides the Claude analysis (the important part)

Claude is not left to "be a trading guru." It is given a strict written **Analyst Guide** as its
system prompt — a rulebook it must follow on every single explanation. (In the codebase this lives
at `src/advisor/analyst-guide-system-prompt.md`.) Here is what that guide tells it, in plain terms:

### The hard rules it may never break
1. **The facts are the only truth.** Every price, level, indicator, and pattern it mentions must
   come from the supplied facts. If a number isn't in the facts, it doesn't exist. No estimating,
   no rounding differently, no inferring.
2. **Never invent a pattern.** If the detectors didn't find a head-and-shoulders, there isn't one —
   no matter how much the chart "feels like" one.
3. **Never force a signal** (see below — this is the rule most tools get wrong).
4. **No prediction.** It may never say price "will" do anything. It describes what's present, what
   that conventionally suggests, and what would prove the reading wrong.
5. **No financial advice.** It never tells you to buy, sell, or size a position. It describes; you
   decide.
6. **No confidence theatre.** It must not pretend the tool can predict the market. (More on this
   below — this system was honestly tested and found to have *no* predictive edge, and the guide
   makes Claude say so plainly if asked.)

### Permission — and obligation — to find nothing
This is the heart of it. Most charts, most of the time, show **nothing worth acting on.** The guide
explicitly tells Claude that saying *"there's no clear setup here"* is a correct, valuable answer —
not a failure. It's forbidden from manufacturing a story out of neutral, mid-range noise just to
sound useful. When there's nothing, it says so in a sentence or two, names what *would* make the
chart interesting (e.g. "if price reaches the 59,800 support with RSI oversold, a bounce setup
forms"), and stops. This single instruction is what separates it from hype machines.

### How it weighs the facts
It reads them in a deliberate order: **trend & regime first** (the big-picture context), then
**where price is** (structure: support/resistance, Fibonacci, round numbers), then **patterns**,
then **momentum**, then **volatility**, then **volume**, and finally **background context**
(sentiment, fundamentals, economic calendar). The principle: *where* price is matters more than
what any single indicator says.

### The reasoning framework it must use
- **A candlestick pattern only matters at a location.** A hammer at a support level is meaningful;
  the same hammer in the middle of nowhere is noise — and it's told to say *where* the candle
  occurred or not mention it at all.
- **Real confluence means different kinds of evidence agreeing** (trend + structure + momentum).
  Three momentum indicators agreeing is *one* signal said three times, not three confirmations — and
  it's forbidden from dressing correlated signals up as independent proof.
- **A pattern's state changes its meaning:** *forming* (developing, not a setup yet), *confirmed*
  (the breakout actually happened), or *failed* (broke down — often the most informative state).

### How it talks about odds and history
- **It may never state a probability for the current setup** — no "70% chance", no "likely to."
  Invented precision reads as rigour and is worse than saying nothing.
- **But it does use real historical base rates** when the facts include them, always phrased in the
  past tense with the raw count: *"Historically, 19 of 41 such breakouts on BTC resolved upward"* —
  never *"there's a 46% chance."* Same number, but the honest version doesn't claim the past
  predicts this exact instance. If the sample is too small, it says so instead of quoting a rate.

### Brevity is a hard rule
The guide sets strict word ceilings — roughly **30 words for "no setup," up to ~130 for a fully
confirmed setup** — with no preamble, no "Looking at the chart…", no reciting every indicator, no
padding. It names the 2–3 facts that carry the read and stops. A short, dense answer is the goal.

### Its voice
Plain trading language, defines a term the first time it matters (because teaching is the point),
concrete over vague ("RSI at 28, below the 30 threshold" — not "momentum is weak"), calm, no hype,
no emoji, no urgency. And before answering it runs a self-check: *Did every number come from the
facts? Did I invent a pattern? Am I forcing a signal? Did I state the invalidation level?*

**The short version:** Claude is boxed in on purpose. It can only speak about measured facts, it's
rewarded for finding nothing, it's banned from predicting, and it's forced to be brief and honest.

---

## The honesty stance (why this tool is different)

The engine was rigorously tested — both a rule-based backtest and a machine-learning evaluation —
to answer one question: *does it actually predict the market?* The honest, documented answer is
**no — no predictive edge was found.** Rather than hide that, the whole product is built around it.
Trading Wizard is positioned as a **learning and research instrument**, not a signal generator. Its
value is *clarity* (seeing the chart's structure cleanly) and *honesty* (never implying it can tell
the future). That honesty is the differentiator.

---

## What's been built so far

The app is a working system with a Python backend and an interactive web chart (Svelte). What
exists today:

**The measuring engine (Layer 1)** — a full deterministic toolkit: trend, support/resistance,
trendlines, swing detection, Fibonacci, chart patterns (double tops/bottoms, head-and-shoulders,
triangles, channels), candlestick patterns (including single-, two-, and now **three-candle**
patterns like morning/evening stars and three soldiers/crows), and a wide indicator set
(RSI, MACD, ADX, Stochastic, Bollinger, ATR, OBV, volume).

**The explanation engine (Layer 2)** — Claude, driven by the Analyst Guide described above, with a
brief mode and a longer "teaching" mode.

**An interactive web app** — pick a market and timeframe, see candlesticks with all the detected
structure drawn on top (levels, Fibonacci, patterns, swing points), scroll back through history to
see exactly what the engine saw at any past bar, read the verdict and the plain-language
explanation, and view supporting panels (momentum, volatility, key levels, market context).

**Honesty & research tooling** — a look-ahead-safe backtester, out-of-sample testing, honest
base-rate ("track record") numbers, a risk-of-ruin calculator, and a realistic cost model
(fees/slippage) so nothing looks better than it really is.

**A paper-trading simulator** — log simulated Buy/Sell decisions with a live fill price, track an
open position and profit/loss, and see your entries marked on the chart — clearly labelled
"simulated, not advice," with no fees fantasy. It's a practice-and-journaling loop, not a broker.

**Roadmap progress:** the build is planned as 12 numbered features across two spec files. **Six are
done** (pattern visualization + research view, pattern confirmation states, market regime detection,
the exit-rule laboratory, the risk-of-ruin calculator, and the cost model), plus the two extras
above (paper trading and three-candle patterns).

**What's next:** an **Empirical Pattern Encyclopedia** — instead of repeating textbook claims like
"double tops are bearish," it will compute and show what each pattern has *actually* done in the
historical data (how often it confirmed, followed through, or failed), sliced by market and
conditions, with sample sizes. After that: a prediction journal that scores how well-calibrated
*your own* reads are over time, and a blind training mode. Every one of these reinforces the same
theme — measure honestly, teach, and never pretend to predict.

---

## In one paragraph, to hand to someone

*Trading Wizard is a visual trading-education tool. Deterministic code measures everything on a
price chart — trend, support/resistance, patterns, momentum — and hands those hard facts to the
Claude API, which explains them in plain English under a strict rulebook: use only the measured
numbers, never invent a pattern, never predict price, never give financial advice, and be willing
to say "there's nothing here." The chart you see and the words you read are built from the same
measurements, so they can never contradict each other. It was honestly tested and found to have no
predictive edge — so it's deliberately built as a learning instrument, not a signal service. Its
value is clarity and honesty about what a chart does and doesn't show.*
