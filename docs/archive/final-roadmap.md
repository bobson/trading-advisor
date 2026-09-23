# Trading Wizard — Final Roadmap

The strategic call, after building the core and measuring it honestly.

**Priority: this is a tool you use, not a portfolio piece.** A portfolio benefit may follow,
but it never drives a decision here. The test for every feature below is simple — *will you
actually open this next week?* Features you don't use are wasted effort, however impressive
they'd look to a stranger.

---

## The call

Your backtest and ML harness said the app has **no predictive edge**. Everything proposed
since has quietly been an attempt to find that edge anyway — more patterns, more confirmations,
more context. That's the wrong direction, and your own instrument already told you so.

**The right direction: stop building a signal generator and finish building a learning
instrument.** Not as a consolation prize — as the better product. Almost every trading app
claims edge; almost none of them can prove anything, and the ones that can't, lie. You have
rare infrastructure: look-ahead-safe backtesting, walk-forward ML validation, an honesty test
proving the "no edge" verdict is trustworthy, and a reasoning layer bound to computed facts.
That combination makes a genuinely excellent *research and training tool* — the thing that
teaches you to read markets and shows you honestly how often you're wrong.

Three consequences:
1. **Features that teach beat features that signal.** Prioritized below accordingly.
2. **The empirical record replaces convention.** You don't need to trust what the literature
   says about triangles — you can compute what triangles actually did on your data.
3. **Honesty is the differentiator**, in the product and in the job market. Lead with it.

---

## Tier 1 — Build these, in this order

### 1. Pattern visualization + multi-panel research view
*(prerequisite for everything else; nothing below is possible without seeing the chart)*

- All detected patterns drawn: boundaries, neckline, breakout level, invalidation, with
  `forming` / `confirmed` / `failed` visually distinct.
- Sub-panels visible together: volume + volume MA, RSI (divergences marked), MACD, ADX, ATR.
- Per-overlay and per-panel toggles.
- **Historical scrubbing** — step to any past bar and see exactly what the engine saw then.
  Look-ahead-safe: the view at bar N must use only bars ≤ N.

This is the difference between a dashboard and a research tool. Build it first.

### 2. Pattern confirmation states (the retrofit)
Give existing detectors `forming`/`confirmed`/`failed`, breakout and invalidation levels,
quality scores, and a confirmation profile — volume, momentum, volatility, candlestick at the
level, higher-TF agreement. **Not just volume**: a shooting star at a double top's second peak
is as much a confirmation as a volume spike. Keep patterns out of the confidence score until
measured. (Detail: PLAN.md Part 8.)

### 3. The Empirical Pattern Encyclopedia ★ *new*
**The single most valuable thing you can build, and nobody else has it.**

Instead of quoting textbook claims about patterns, compute the truth from your own data:
for every pattern type × timeframe × symbol × market regime, run your backtest and publish
the real numbers — occurrence count, confirmation rate, follow-through rate, median move,
failure rate, and how each confirmation type shifted the outcome.

Then: an in-app encyclopedia page per pattern showing *your* statistics beside the
conventional claim, with sample sizes, and example charts pulled from your own history.
Where the data contradicts the convention, say so.

Why this is the winner: it turns the "no edge" finding from a limitation into the product.
It's an original empirical contribution, it's directly useful to you as a learner, it uses
machinery you already built, and it's the most interesting thing in your README.

### 4. Prediction journal + calibration scoring ★ *new*
**The feature that makes this genuinely educational rather than advisory.**

Before revealing the analysis, let the user record their own read: direction, confidence
(0–100%), and invalidation level. The app stores it, resolves it against what actually
happened, and tracks calibration over time — a Brier score, a calibration curve (when you
said 70%, were you right 70% of the time?), and a breakdown by pattern type and regime.

This inverts the app's premise in the best way: instead of the AI claiming to predict, **it
measures whether *you* can** — and almost certainly shows you're overconfident, which is the
most valuable lesson in trading. It's honest, it's unusual, and it makes the tool's value
unambiguous.

### 5. Blind training mode ★ *new*
Pick a random historical setup, hide everything after it, show the chart and indicator panels,
let the user call it — then reveal what happened and what the engine's analysis said at that
moment. Spaced repetition for chart reading.

Cheap to build once #1 (scrubbing) and #4 (journal) exist, since it's the same machinery with
the future hidden. Turns passive analysis into deliberate practice.

### 6. Market regime layer
Classify each bar's regime — trending / ranging / volatile / quiet — using ADX, ATR percentile,
and Bollinger width. Then segment *everything* by regime: encyclopedia stats, confluence
weights, calibration scores.

Analytically, this is the likeliest place any real signal hides — patterns that look useless
in aggregate sometimes behave differently in specific regimes. And it's honest: report per-regime
sample sizes, and expect most differences to vanish under scrutiny.

### 7. Explanation integrity guard
Automated check that every number in Claude's output appears in the facts dict, plus a flag if
it asserts a pattern that wasn't detected. Enforces the Layer 1 invariant instead of hoping.
Cheap; do it while the reasoning layer is fresh.

---

## Tier 2 — Worthwhile after Tier 1

- **Watchlist scan** — run the engine across your symbols and surface only genuinely notable
  setups. **Promote this if you'd use the app daily** — it's the difference between a tool you
  open deliberately and one that tells you when it's worth opening. Honest version: it should
  often return "nothing across 40 symbols today."
- **Local convenience over polish** — a saved default watchlist, fast startup, results cached
  between runs. Unglamorous, but it decides whether you keep using it.
- **Analysis permalinks** — mainly a sharing feature. Low priority for personal use, unless you
  want to review your own past reads (the journal covers most of that).
- **New pattern shapes** — channels, rectangles, flags/pennants. Easy once #2's machinery exists.
- **Derivatives context** (crypto) — OI and funding via ccxt. Good narration colour; treat as
  context, never trigger. Skip liquidations (modeled, unreliable).
- **Structured explanation output** — JSON (`read` / `why` / `invalidation` / `watch`) so the
  frontend can render sections rather than a text blob.

---

## Tier 3 — Deprioritize or skip

- **Elliott Wave.** Subjective, multiple valid counts, revised after the fact. Would be the
  least defensible module you own. Skip it.
- **More exotic patterns** (diamonds, broadening formations). Diminishing returns; rare enough
  that sample sizes will be useless.
- **Chasing edge with more indicators.** Your ML harness swept a large feature space and found
  noise. Adding features to the same pipeline is unlikely to change that, and each addition
  raises the odds of a false positive.
- **Live alerting / real-time.** Real infrastructure cost, and it pulls the product back toward
  signal-chasing.
- **Anything that implies prediction.** Non-negotiable, product-wide.

---

## The through-line

Each Tier 1 feature does one of two things: **shows you what actually happened** (encyclopedia,
regime stats, scrubbing) or **shows you how well you read it** (journal, calibration, blind
mode). Neither claims prophecy. Together they make a tool that makes you measurably better at
reading charts — which is what you originally asked for, back when you described wanting an AI
that knows trading and teaches you.

## If you later want it as a portfolio piece

Secondary, and it needs almost no extra work — the honest engineering is already the asset.
Lead the README with the "no predictive edge" finding and what you built instead: measuring
honestly, publishing an unwelcome result, and redesigning around it is stronger evidence of
judgment than any feature list. Add the empirical encyclopedia as an original contribution and
a short write-up of data versus textbook claims. Only *then* is deploying publicly worth the
effort. Don't do deployment, polish, or sharing features for a hypothetical reviewer — do them
if they make the tool better for you.

## Suggested build order
1 (visualization) → 2 (confirmation states) → 3 (encyclopedia) → 6 (regimes, feeding 3) →
4 (journal) → 5 (blind mode) → 7 (integrity guard) → Tier 2 as appetite allows.
