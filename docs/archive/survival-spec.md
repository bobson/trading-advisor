# Trading Wizard — Features 8–12: The Survival Layer

Specs for the five features that target where outcomes actually come from: risk, costs,
exits, overfitting, and behaviour. None of these improve signal quality. That's deliberate —
signal quality is the variable this app already measured and found wanting, and the research
on the profitable minority points at these five instead.

Same conventions as BUILD-SPEC.md: one feature per branch, tests alongside code, SQLite at
`data/wizard.db`, no fixed-% thresholds (ATR-scaled), walkthrough summaries under 15 lines.

**Priority:** build **9 (risk of ruin)** and **10 (cost model)** before trading anything real.
They're the two that prevent irreversible mistakes. 8 and 11 raise the quality of your
research; 12 measures the variable most likely to undo you.

---

## Feature 8 — Exit rule laboratory

**Why:** in trend following, returns come overwhelmingly from how long you hold winners, not
from entry precision. People optimize entries because that's where the emotion is. Test whether
that's true in *your* data.

**Build:** `src/backtest/exits.py` — hold entries fixed, vary only the exit, and compare.

Exit rules to implement (each parameterised, all ATR-scaled):
- **Fixed target** — take profit at N × ATR
- **Fixed stop only** — ride until stopped out at N × ATR
- **Trailing ATR stop** — trail at N × ATR from the running high (the classic trend-following exit)
- **Chandelier exit** — trail from the highest high since entry, N × ATR below
- **Regime exit** — close when `regime` flips out of trending (needs Feature 6)
- **Structure exit** — close on a close beyond the last swing low (uptrend) / high (downtrend)
- **Time exit** — close after N bars regardless
- **Moving-average exit** — close on a close below the slow MA

**Report per exit rule:** total return, median win, median loss, win rate, largest winner's
share of total profit, average holding period, max drawdown, and — the key comparison —
**variance of outcome across entry rules**. If exit choice dominates entry choice, the spread
across exits will be much wider than the spread across entries with a fixed exit. Run both
directions and report which matters more.

**Guard:** all exits evaluated bar-by-bar forward, never using future bars. Reuse the existing
look-ahead-safe walk. Report sample size on every row.

**Done when:** you can see a table of exit rules × outcomes on your own data, and answer
"does the exit or the entry matter more here?" with evidence.

> **Prompt:** "On branch `feature/exit-lab`, implement Feature 8 of SURVIVAL-SPEC.md:
> `src/backtest/exits.py` that holds entries fixed and compares fixed-target, stop-only,
> trailing-ATR, chandelier, regime-flip, structure, time-based and MA-cross exits, all ATR-scaled.
> Report total return, median win/loss, win rate, largest-winner share, holding period, max
> drawdown and sample size per rule — plus a comparison of outcome spread across exits vs across
> entries. Reuse the existing look-ahead-safe backtest walk. Tests included. Summarise in under
> 15 lines."

---

## Feature 9 — Risk of ruin & position sizing ★ build early

**Why:** the math of survival, which almost nobody runs. Someone risking 5% per trade at a 40%
win rate is mathematically doomed regardless of how good their analysis is. This is the single
most protective thing in the app.

**Build:** `src/risk/ruin.py`

- **Risk of ruin** — given win rate, average win/loss ratio, and fractional risk per trade,
  compute the probability of hitting a given drawdown threshold (say −50%) before doubling.
  Analytic formula plus a Monte Carlo simulation (10k+ paths) for realistic, non-i.i.d. cases.
- **Drawdown distribution** — simulate N paths from your actual historical trade distribution
  (bootstrap, not a normal assumption — trade returns are fat-tailed) and report the median,
  90th percentile, and worst-case drawdown, plus the longest losing streak to expect.
- **Kelly sizing** — full Kelly from your measured win rate and payoff ratio, then display
  half-Kelly and quarter-Kelly, which is what practitioners actually use. Show explicitly how
  much full Kelly's drawdowns hurt: it's growth-optimal and psychologically unbearable.
- **Sizing calculator** — given account size, entry, and stop distance, output position size
  for a chosen fractional risk. This is the everyday-use surface.
- **A table** of risk-per-trade (0.25% → 5%) × win rate → probability of 50% drawdown, so the
  cliff is visible rather than abstract.

**Feed it real inputs** — win rate and payoff ratio come from Feature 8's results and the
journal (Feature 4), not user guesses. Where sample size is thin, say so and widen the
confidence interval rather than presenting a point estimate.

**Done when:** you can enter your own measured statistics and see your probability of ruin,
your expected worst drawdown, and a sized position — and the numbers are sobering rather than
reassuring.

> **Prompt:** "On branch `feature/risk-of-ruin`, implement Feature 9 of SURVIVAL-SPEC.md:
> `src/risk/ruin.py` with analytic and Monte Carlo risk-of-ruin, bootstrap drawdown distribution
> from historical trade returns (fat-tailed, not normal), Kelly / half-Kelly / quarter-Kelly
> sizing, a position-size calculator from account/entry/stop, and a risk-per-trade × win-rate
> table of ruin probabilities. Pull win rate and payoff ratio from backtest and journal data
> where available, with confidence intervals when samples are thin. Svelte page for the
> calculator. Tests for the maths. Summarise in under 15 lines."

---

## Feature 10 — Honest cost model ★ build early

**Why:** transaction costs explain a large share of documented retail underperformance. Many
strategies that look profitable gross are negative net. A backtest without costs is fiction.

**Build:** `src/backtest/costs.py`, applied to every backtest result by default (not opt-in).

- **Spread** — per symbol; for forex use typical pip spreads by pair and session (wider in
  Asian hours, wider around news); for crypto use the actual order book spread where available.
- **Commission/fees** — exchange taker and maker fees; configurable per venue.
- **Slippage** — modelled as a function of volatility (ATR) and, where available, volume.
  Fixed slippage is a lie; it's worst exactly when you most want to exit.
- **Funding costs** — for leveraged/perp positions, funding rate × holding period. This is
  what quietly kills long holds on perps.
- **Overnight/weekend financing** — for forex CFD-style positions.
- **Tax drag** — a configurable rate applied to realised gains. Crude, but its absence
  flatters results badly.

**Report gross vs net side by side**, and a "cost as % of gross profit" figure. Add a
**breakeven analysis**: given these costs, what win rate or payoff ratio does this strategy
need to break even? That single number is often more informative than the backtest itself.

**Done when:** every backtest reports net-of-everything results by default, and you can see
what fraction of gross profit costs consume.

> **Prompt:** "On branch `feature/cost-model`, implement Feature 10 of SURVIVAL-SPEC.md:
> `src/backtest/costs.py` modelling spread (per symbol, session-aware for forex), exchange fees,
> volatility-scaled slippage, perp funding costs over holding period, overnight financing, and a
> configurable tax drag. Apply to all backtest results by default, reporting gross vs net and
> cost as a share of gross profit, plus a breakeven win-rate/payoff analysis. Tests included.
> Summarise in under 15 lines."

---

## Feature 11 — Pre-registration

**Why:** the biggest threat to your research isn't bad code, it's testing twenty variations and
keeping the one that looked good. That manufactures edges that don't exist. Pre-registration is
what scientists use to prevent exactly this, and you already have the honesty infrastructure to
support it.

**Build:** `src/research/prereg.py` + SQLite `experiments` table.

- Before running a backtest, record: the hypothesis in plain words, the exact parameters, the
  metric that decides success, the threshold that counts as success, and the predicted result.
  Timestamp and hash it.
- Run the experiment; store the result linked to the registration.
- **Track the multiple-comparison count.** Display how many variations you've tested on the same
  underlying question, and apply a correction (Bonferroni or similar) to the significance
  threshold. If you've tested 20 variations, one result at p<0.05 is exactly what noise produces.
- A dashboard of all experiments: hypothesis, prediction, outcome, and whether you called it.
  **Show the failures prominently** — the file drawer is where self-deception lives.

**Refuse to hide results.** No deleting an experiment after seeing the outcome. Registrations
are append-only; supersede rather than edit.

**Done when:** you cannot run a backtest without registering a prediction first, and the
dashboard shows your hit rate at predicting your own results — including every miss.

> **Prompt:** "On branch `feature/prereg`, implement Feature 11 of SURVIVAL-SPEC.md:
> `src/research/prereg.py` with an append-only SQLite `experiments` table recording hypothesis,
> parameters, success metric and threshold, and predicted outcome before a backtest runs; link
> results back to registrations; track how many variations have been tested per question and
> apply a multiple-comparison correction to the significance threshold; a Svelte dashboard listing
> all experiments including failures, with my hit rate at predicting my own results. Registrations
> cannot be deleted. Tests included. Summarise in under 15 lines."

---

## Feature 12 — Behavioural circuit breaker

**Why:** the research says the gap between the profitable minority and everyone else is driven
more by risk management and psychology than by strategy. This is the feature that measures that
variable directly, on you.

**Build:** extends the Feature 4 journal. `src/journal/rules.py`

- **Declare rules up front** (stored, versioned): max risk per trade, max concurrent positions,
  required regime conditions, minimum confluence or confidence, instruments allowed, a maximum
  number of trades per week, and a cooling-off period after a loss.
- **Every logged trade is checked against the active rule set**, and any violation is recorded
  with which rule broke — not blocked, just recorded. You're an adult; the point is measurement,
  not a nanny.
- **The comparison that matters:** outcomes of rule-following trades vs rule-breaking trades,
  with sample sizes. For most people this is decisive and uncomfortable.
- **Tilt detection** — flag clusters: trades taken within a short window after a loss, position
  sizes above your own average, trades outside your declared regime conditions, trading frequency
  spikes. Surface these as observations after the fact, not alerts in the moment.
- **A weekly review page:** rules followed, violations, and what each cost or earned.

**Tone: neutral.** No scolding, no gamification, no streaks. Report the numbers and let them
speak — the same standard as the analyst guide.

**Done when:** you can see, with sample sizes, whether your rule-breaking trades did better or
worse than your disciplined ones.

> **Prompt:** "On branch `feature/circuit-breaker`, implement Feature 12 of SURVIVAL-SPEC.md:
> `src/journal/rules.py` extending the journal with a versioned declared rule set (max risk,
> max positions, required regime, min confidence, allowed instruments, max trades/week,
> post-loss cooling-off); check every logged trade against it and record violations without
> blocking; compute outcomes of rule-following vs rule-breaking trades with sample sizes; detect
> tilt clusters (post-loss trades, oversized positions, off-regime trades, frequency spikes) as
> after-the-fact observations; a weekly review page. Neutral tone, no gamification. Tests
> included. Summarise in under 15 lines."

---

## Honest framing

None of these will make you profitable. What they do is make it much harder to be
*unknowingly* unprofitable, and much harder to be ruined while finding out. Given that the
documented failure rate for retail speculation runs from roughly 70% to 97% depending on market
and holding period — and that persistence alone showed no improvement in the largest study —
that's a meaningful thing to build.

If after all this the evidence says you don't have an edge, the app worked. That's the finding,
not a failure of the tool.

## Revised overall order
Feature 1 ✓ → **6** (regime) → **9** (risk of ruin) → **10** (costs) → **2** (patterns) →
**8** (exits) → **3** (encyclopedia) → **4** (journal) → **11** (pre-registration) →
**12** (circuit breaker) → **5** (blind mode) → **7** (integrity guard)
