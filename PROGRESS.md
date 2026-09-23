# PROGRESS

A state file for the Tier-1 "learning instrument" build. Planning docs: `final-roadmap.md`
(strategy) + `tier1-build-spec.md` (implementation). See `CLAUDE.md` for conventions.

## Current state

**Built (all merged to `main`):** Feature 1 (pattern visualization + research view), Feature 6
(market regime), the hardening pass (`fix/explanation-and-chart`: chart panning fixes, analyst
guide wired in as the real system prompt with brief/teaching modes, signal classification moved
into the facts payload), Feature 9 (risk of ruin, `41232b4`), Feature 10 (honest cost model,
`53e37df`), and Feature 2 (pattern confirmation states, `6b8dfd5`). **256 tests green, ruff +
svelte-check clean.** Regime is still standalone infrastructure (not in any vote/facts);
patterns now carry state/quality/confirmation but stay OUT of the confluence score.

**Explanation layer:** driven by `src/advisor/analyst-guide-system-prompt.md` (loaded at startup,
cached prompt prefix). Default mode `brief` (enforces the guide's §8 word budgets); `teaching`
for long-form; toggle in the UI.

**Next (SURVIVAL-SPEC.md revised order — 1 ✓, 6 ✓, 9 ✓, 10 ✓, 2 ✓):** **Feature 8 (exit-rule
laboratory)** → Feature 3 (empirical pattern encyclopedia) → Feature 4 (prediction journal +
calibration) → 11 (pre-registration) → 12 (behavioural circuit breaker) → 5 (blind mode) →
7 (integrity guard).

**Default config:** symbol `BTC/USDT`, timeframe `1h`, exchange `binance`, history 4320 bars.
Selectable timeframes: `15m, 30m, 1h, 4h, 1d`. Registered pairs: BTC/ETH/SOL/XRP (USDT) +
EUR/USD, GBP/USD (forex via Twelve Data). **Feature 10** adds a `costs:` block (`CostsConfig`);
**Feature 2** adds `patterns.equal_atr_mult` / `depth_atr_mult` (ATR-scaled tolerances; the old
percent fields are kept for `config.yaml` compat). Defaults apply if `config.yaml` omits them.

---

## Log (newest first)

### Three-candle candlestick patterns — morning/evening star, three soldiers/crows (facts-only)
- **Built:** 2026-09-23 · **branch:** `feature/three-candle-patterns`
- **Why:** on BTC/USDT 1h the user spotted a doji-in-the-middle 3-candle shape the app couldn't
  name — we only detected 1- and 2-candle patterns (doji/hammer/shooting-star/engulfing).
- **Done-when:** each pattern fires on its textbook fixture; the last closed bar's read shows in the
  facts + a UI panel row; 3-candle markers draw on the chart; and the exact real bars the user was
  looking at detect **nothing** (all up, doji middle → read stays "doji"). All verified.
- **Design (advisor-reviewed): FACTS-ONLY, not a vote.** Making the existing candlestick vote fire
  in new situations would change confluence → the backtest → an unvalidated vote-path change (the
  Phase 9/18/22 facts-first ethos). Proof it's untouched: snapshot diff is the **single new
  `candlestick` key**, `confluence.signals` is **byte-identical**, `len(signals)==7`.
- **Build:** `features.py` — 4 boolean columns (`morning_star`/`evening_star`/
  `three_white_soldiers`/`three_black_crows`) via shift(1)/shift(2) (causal → look-ahead-safe),
  module-constant thresholds (`STRONG_BODY_MIN_FRACTION`/`STAR_BODY_MAX_RATIO`/
  `SOLDIER_WICK_MAX_FRACTION`), gaps NOT required (24/7 crypto) — reversal proven by close beyond
  candle-A's body midpoint. `candlestick_read()` names the strongest pattern (3-candle first, then
  2- then 1-candle) and labels a doji-middle star a "doji star". Wired into `facts.py`
  (`candlestick` block + prompt render), `serialize.py` (`candle_patterns` overlay — 3-candle set
  ONLY, too-frequent singles excluded), `api.ts` + `PriceChart.svelte` (labelled squares, green
  below/red above, under the `patterns` toggle), and an App.svelte panel row.
- **Tests:** `tests/test_candlesticks.py` — 8 (each pattern fires, doji-star naming, 3-candle
  precedence, causality guard, and the real-BTC no-false-positive tied to the user's exact bars).
  **284 green, ruff + svelte-check clean.** Browser-verified markers on a mock; real BTC 1h → 11
  markers / last 500 bars (~2%), current bar reads doji.
- **Deferred:** promoting any 3-candle pattern to a *vote* is a separate, backtested step — not done
  on faith. Density is fine now; if stars ever feel noisy, tighten to "close beyond candle-A open".

### Paper-trading simulator — Buy/Sell, position + PnL, chart markers
- **Built:** 2026-09-22 · **branch:** `feature/paper-trading` (spec: `paper-trading-spec.md`)
- **Done-when:** enter a `$` amount, click Buy/Sell, see it recorded (time/price/amount + on-screen
  verdict snapshot), an open position + unrealized PnL, a trades log, and green ▲ / red ▼ markers
  on the entry candle — only for the pair you're viewing. **Browser-verified** (headless Chromium +
  stateful mock): Flat → Buy opens LONG (badge, disabled same-side, relabeled close button, log
  row, green ▲ marker) → Sell closes it (Flat badge, realized-PnL record line, red ▼ close marker).
- **Locked decisions:** `$` notional (`units = amount/fill`); one position at a time per symbol
  (opposite side closes + books realized PnL, same side → 400); snapshot = whatever's on screen
  (**never a Claude call**); **live spot fill** server-side (ccxt `fetch_ticker`, graceful fallback
  to `last_close`, source tagged `live`|`last_close`); SQLite `trades` table.
- **Build:** `src/store/db.py` (+`trades` table), `src/trading/paper.py` (`live_price` w/ 5s TTL
  cache, `open_or_close`, `record`, `list_trades`, `position`, `pnl_summary`, `delete_trade`),
  API `POST/GET /trades`, `GET /trades/position`, `DELETE /trades/{id}` (guarded like the rest;
  `_TRADES_DB` tmp-path seam for tests). Frontend: typed client in `api.ts`, trade panel + badge +
  log in `App.svelte`, entry/exit markers in `PriceChart.svelte` (snap trade time → entry candle).
- **Tests:** `tests/test_paper.py` — 7 offline unit (long/short PnL signs, one-at-a-time guard,
  reopen, `live_price` ticker→fallback, injected-fetch record, summary) + 1 `TestClient` API flow
  (monkeypatched `live_price`, tmp DB). **276 green, ruff + svelte-check clean.**
- **Honest framing:** labeled "Paper trading — simulated, not advice"; live fills but no
  slippage/fees/liquidity — PnL measures discipline & read, not a real account.
- **Distinct from Feature 4** (journal/calibration): own `trades` table, shares only
  `src/store/db.py`; extract common resolve-logic later if a 2nd consumer appears.

### Feature 2 — Pattern confirmation states
- **Merged:** 2026-09-20 · **branch:** `feature/pattern-confirmation` → **`main`** (commit `6b8dfd5`, fast-forward)
- **Done-when:** every pattern reports state, breakout, invalidation, quality, and a full 7-category
  confirmation profile; overlaps are deduplicated; the guard passes. Confirmed on real data —
  BTC 1h: one *confirmed bullish ascending triangle* (4 supports / 0 contradicts); BTC 1d: one
  *forming bearish double top* (quality 0.68). No over-calling (dedupe collapses to one each).
  Snapshot diff confined to `chart_patterns`, and `confluence.signals` stays length-7 — proving
  patterns stayed OUT of the score. 24 new tests; **256 green**.
- **Build:** `src/patterns/base.py` (`Pattern` + `ConfirmationProfile`: price/volume/momentum/
  volatility/candlestick/higher_tf/structure, each supports/contradicts/neutral/unavailable;
  look-ahead-safe `classify_state`). Detectors refactored to emit `Pattern` with ATR-scaled
  tolerances; added **rectangle + channel** (continuation). `dedupe.py` keeps highest quality,
  ties preferring continuation. Wired into facts + serialize (additive chart contract → no
  `PriceChart.svelte` edit).
- **Deviations:** **flags deferred** (fuzziest, most over-call-prone geometry) — a note, not a
  gap; triangles + rectangle + channel already cover continuation. Old percent config fields kept
  (config.yaml sets them; `extra="forbid"`). Triangle quality uses flatness × linearity, not the
  degenerate flat-side r2.
- **Learned:** on the same swings a rectangle/triangle also reads as a double top/bottom — the old
  code returned all; dedupe now collapses them, and a continuation-first tie-break resolves it
  (matches the trend-riding use case). Keeping the serialize contract additive meant no chart edit
  and no browser re-verification loop.

### Feature 10 — Honest cost model
- **Merged:** 2026-09-19 · **branch:** `feature/cost-model` → **`main`** (commit `53e37df`)
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
