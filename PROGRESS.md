# PROGRESS

A state file for the Tier-1 "learning instrument" build. Planning docs: `final-roadmap.md`
(strategy) + `tier1-build-spec.md` (implementation). See `CLAUDE.md` for conventions.

## Current state

**Built:** Feature 1 (pattern visualization + multi-panel research view + history scrubber),
Feature 6 (market regime classifier), a hardening pass (`fix/explanation-and-chart`: chart
panning/right-edge fixes, analyst guide wired in as the real system prompt with brief/teaching
modes, signal classification moved into the facts payload), and **Feature 9 (risk of ruin &
position sizing)** — all merged to `main` (Feature 9 = commit `41232b4`). Plus **Feature 10
(honest cost model)** — implemented on `feature/cost-model`, **not yet committed/merged**. **247
tests green, ruff clean.** Regime is still standalone infrastructure (a committed strip overlay
eyeballs it) — not in any vote/facts; the encyclopedia consumes it next.

**Explanation layer:** driven by `src/advisor/analyst-guide-system-prompt.md` (loaded at startup,
cached prompt prefix). Default mode `brief` (enforces the guide's §8 word budgets); `teaching`
for long-form; toggle in the UI.

**Next (SURVIVAL-SPEC.md revised order — 1 ✓, 6 ✓, 9 ✓, 10 ✓):** Feature 2 (pattern confirmation
states) → Feature 8 (exit-rule laboratory) → Feature 3 (empirical pattern encyclopedia) →
Feature 4 (prediction journal + calibration) → 11 (pre-registration) → 12 (behavioural circuit
breaker) → 5 (blind mode) → 7 (integrity guard).

**Default config:** symbol `BTC/USDT`, timeframe `1h`, exchange `binance`, history 4320 bars.
Selectable timeframes: `15m, 30m, 1h, 4h, 1d`. Registered pairs: BTC/ETH/SOL/XRP (USDT) +
EUR/USD, GBP/USD (forex via Twelve Data). Feature 9 added no config; **Feature 10 adds a `costs:`
block** (`CostsConfig`: `enabled` default true + spread/fee/slippage/funding/financing/tax rates;
defaults apply if `config.yaml` omits it).

---

## Log (newest first)

### Feature 10 — Honest cost model
- **Status:** implemented 2026-09-19 · **branch:** `feature/cost-model` (**not yet committed/merged**)
- **Done-when:** every backtest reports net-of-everything by default, and you can see what fraction
  of the gross edge costs consume. Confirmed live (BTC 1d, 506 setups): **gross +0.45%/trade →
  net −0.14%** (win 50%→48%) — a gross-positive setup flips **net-negative after costs**. Costs
  consume **~133% of the gross edge**; breakeven needs a **51% win-rate vs the current 50%** (at
  payoff 1.10), or a 1.13 payoff at the current win-rate. Slippage dominates (~48 bps of ~60).
- **Build:** `src/backtest/costs.py` — per-trade round-trip cost as a fraction of notional:
  spread (crypto bps; forex pip-spread per pair, session-aware), taker fees (both sides),
  volatility-scaled slippage (`mult × ATR/price`), signed perp funding over the holding period,
  forex overnight financing, configurable tax on realised gains. `evaluate()` applies it by
  default (`costs.enabled`); `BacktestReport.costs` + `summary()` show gross vs net, per-component
  bps, cost-share-of-edge, and a breakeven win-rate/payoff. 8 new tests.
- **Deviations:** funding & crypto spread come from CONFIG defaults, not per-bar live data — the
  historical backtest doesn't carry live order-book spread or funding, so a universal config rate
  is used (funding still signed by direction: longs pay positive). Tax defaults to 0 (jurisdiction-
  specific, opt-in); the transaction costs apply regardless. Session spread multipliers are module
  constants (base spread is config). Gross stats are unchanged, so base_rate/suite/snapshot are
  untouched — costs are purely additive.
- **Learned:** volatility-scaled **slippage dominates** (~48 bps vs ~12 for spread+fees on daily
  crypto) — "fixed slippage is a lie" is the load-bearing choice; it's what flips gross-positive to
  net-negative. "Cost as % of gross profit" is ambiguous: against gross WINNINGS it read a
  reassuring 13% next to a net-NEGATIVE result; against the gross EDGE (total pre-cost P&L) it
  reads 133% — the honest denominator, consistent with net-negative.

### Feature 9 — Risk of ruin & position sizing
- **Status:** implemented 2026-09-19 · **branch:** `feature/risk-of-ruin` → **merged to `main`** (commit `41232b4`)
- **Done-when:** enter your own measured stats → see probability of ruin, expected worst drawdown,
  and a sized position, and the numbers *sober* rather than reassure. Confirmed live: 45% win at
  1:1 payoff → ~100% chance of a 50% drawdown before doubling at any risk level; full-Kelly median
  drawdown ~86% vs quarter-Kelly ~32%; the risk×win-rate table renders as a green→red cliff. 18
  new maths tests + a real headless-browser check of the calculator page. **239 tests green.**
- **Build:** `src/risk/ruin.py` — analytic ruin (diffusion two-barrier hitting probability) +
  vectorised Monte Carlo (Wilson CI + an `unresolved`-fraction bias check); bootstrap drawdown
  distribution from real trade returns; Kelly/half/quarter with drawdown pain; position-size
  calculator; ruin table. `GET /risk` + `/risk/measured`; `RiskCalculator.svelte` + a nav toggle.
- **Deviations / how win rate & payoff are handled:** win rate is pulled from the backtest
  (`base_rates.json`) with a Wilson CI and a `thin` flag when n is small. **Payoff ratio is left
  `None`** — it is NOT stored by the backtest and CANNOT be reconstructed from win rate + avg
  return (underdetermined), and the journal (Feature 4) that would supply it **doesn't exist yet**.
  So the calculator takes payoff as a user input for now; `gather_measured_stats` queries a
  `journal_entries` table defensively so it auto-populates payoff once Feature 4 lands.
- **Learned:** monotonicity of ruin (↑ with risk) only holds for a POSITIVE edge — a losing
  system's ruin can *fall* with more risk, because higher variance gives a small chance to hit the
  double first (a real result, not a bug). The i.i.d. bootstrap destroys loss clustering and so
  *understates* the longest losing streak — flagged in the output; a block-bootstrap option
  retains some clustering.

### Hardening — chart panning, analyst-guide wiring, explanation modes, Layer-1 classification
- **Merged:** 2026-09-18 · **branch:** `fix/explanation-and-chart` (commit `17f7bd1`, merge `8442a87`)
- **Chart (frontend):** fixed drag-to-pan (it was zooming) and the right edge. All panes now share
  ONE index axis (warm-up + trailing gap as whitespace) and sync by *logical* range, not time —
  no drift, so a drag can't creep into a zoom. Left edge is a hard stop; the right edge is a
  debounced snap-back to a permanent ~25-bar gap so the newest candles clear the price-axis
  labels. Verified in real headless Chromium (puppeteer), not just a build.
- **Analyst guide wired in:** `analyst-guide-system-prompt.md` is now loaded at startup (fails
  loudly if missing) and IS the system prompt for `explain`/`synthesize`/`explain_structured` —
  one source of truth, behind a cache breakpoint. **FINDING: the guide had been ORPHANED for
  several sessions** — never loaded by any code; the real prompt was a hardcoded string in
  `explain.py`, so its §8 word budgets never applied and explanations ran 1000+ words.
- **Two explanation modes, default `brief`:** brief enforces the guide's §8 budgets (`max_tokens`
  ~400 → structural, not just requested); teaching is the fuller breakdown, exempt from the
  budgets *only* (every other rule binds), `max_tokens` 2048. UI toggle added (browser-verified).
  Live check: **43 words (brief) vs 1162 (teaching)** on the same analysis.
- **Classification moved to Layer 1:** every confluence signal now carries a pre-computed vote +
  category in the facts payload; context items (Fear & Greed, funding, distance-from-ATH) are
  marked explicitly non-directional (F&G gets an extreme-vs-mid-range read per the guide's bands).
  Fixes Layer 2 classifying the same fact differently across runs. Snapshot regenerated (only the
  `category` keys added). New `tests/test_facts_classification.py`.
- **Learned:** a prompt file living next to the code is not the same as being *used* — verify the
  wiring, not the file's existence. The guide (§5) already forbade directional context reads, so
  the classification bug was the facts render not surfacing that framing, letting Layer 2 fill the
  gap.

### Feature 6 — Market regime detection
- **Merged:** 2026-09-18 · **branch:** `feature/regime` (commit `dce3906`)
- **Done-when:** every bar labeled trending_up/down / ranging / volatile / quiet; stable, not
  flickering; look-ahead test passes. On real BTC data: daily 5.5% switch rate (~2.5-week
  regimes), weekly 4.3% (~23 weeks), all five labels present. Look-ahead guard proven to *bite*
  (fails when a whole-series percentile is injected). 8 new tests.
- **Decisions/deviations:** ADX + slow-MA slope + rolling ATR percentile; persistence hysteresis
  (a new regime must hold N bars). First use of SQLite (`data/wizard.db`, `regime_cache`).
  Standalone — wired into no vote/facts by design.
- **Learned:** trend must take priority over volatility, else trending-but-volatile markets
  mislabel. ATR percentile is *relative*, so a permanently-flat series reads `ranging`, not
  `quiet` — quiet needs contrast.

### Feature 1 — Pattern visualization + multi-panel research view
- **Merged:** 2026-09-18 · **branch:** `feature/pattern-viz` (commit `d7c0dc9`)
- **Done-when:** scrub to any past bar and see what the engine saw then, all panels drawn, guard
  test passes. Backend + guard test green (201 tests); `as_of_bar=N` proven equal to a
  truncated-frame run, future-mutation leaves bar N unchanged. Frontend built + type-checked
  clean; **browser-unverified** (no `npm run` this session).
- **Decisions/deviations:** endpoint is `/analysis` (spec said `/report`). Pattern `state` is a
  lightweight look-ahead-safe read; `quality` and per-boundary lines are deferred to Feature 2.
  Patterns stay out of the confidence score until measured.
- **Learned:** the look-ahead leak vector is `find_swings` (confirmed-interior filter), not
  `add_features` (causal); the guard must assert boundary activity *before* invariance or it
  passes vacuously.
