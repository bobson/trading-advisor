# Trading Wizard — Master Roadmap & Status

**The single source of truth for what the app is, what's built, and what's left.**
Supersedes `PLAN.md`, `trading-advisor-plan.md`, `final-roadmap.md`, `tier1-build-spec.md`,
`survival-spec.md`, `feature-13-spec.md` (kept in `docs/archive/` as reference for deeper rationale).
Build history lives in `PROGRESS.md`; engineering conventions in `CLAUDE.md`; the ready-to-paste
prompt for every step below is in `PROMPTS.md`.

*Last updated: 2026-09-23 — revised after an external design review of the two-layer architecture
and the Analyst Guide.*

---

## 1. What the app is

Trading Wizard reads market price candles, measures the chart's structure with deterministic code,
and has Claude explain it in plain language — to help you **see a chart clearly and learn.**
It does **not** place trades and does **not** predict prices.

**Two layers (never blur them):**
- **Layer 1 — the eyes (pure math).** Trend, swings, support/resistance, trendlines, Fibonacci,
  chart patterns, candlestick patterns, indicators, regime. Outputs facts (numbers + labels).
- **Layer 2 — the voice (Claude).** Receives those facts and explains them under the Analyst Guide
  (`src/advisor/analyst-guide-system-prompt.md`). Never sees raw candles, **never contradicts Layer 1.**

## 2. Strategic direction

The engine was tested honestly — a look-ahead-safe backtest **and** a machine-learning walk-forward
evaluation. Both found **no predictive edge.** The project pivoted: stop chasing edge, build the
honest learning instrument. Every remaining feature either **shows you what actually happened**
or **shows you how well you read it.** Nothing may imply prediction.

**What "more precise" means here.** Precision of *reading*, never of forecasting: patterns and levels
identified accurately (measured against your own hand-labelled charts), stated exactly, and shown
with their known reliability. Forecast precision is what the testing ruled out; nothing in this
roadmap tries to recover it.

## 3. What the design review found (why the order changed)

- **The biggest honesty leak is deterministic UI, not the AI.** "Bias: bullish · confidence 55% ·
  SETUP FLAGGED" in green reads as odds to a beginner — and since explanation defaults off, most
  sessions see only that badge.
- **Layer 1 and the guide disagree about what a setup is.** A *forming* SOL channel produced a flagged
  setup; the guide says forming is not a setup. Claude also picks its own situation tier, which
  sets its own word budget.
- **Verification checks numbers, not claims.** The main failure mode — *which* facts get mentioned —
  is unchecked. A correct number attached to the wrong meaning passes.
- **The anti-prediction rules ban words, not implications.** "Conventionally read as continuation"
  and "structure favours upside" are compliant forecasts. A more fluent model makes this worse.
- **§7 "own observations"** lets Claude build unverified structure out of verified numbers.
- **The guide contradicts itself** in several places (quoted in the review).

**The lesson:** every fix that has worked removed a decision from the model; none worked by
instructing it better. So **the guide shrinks as Layer 1 grows.**

---

## 4. Status at a glance

| Layer | State |
|---|---|
| Core engine + web app + API (original Phases 0–26) | ✅ Done |
| ML "is there an edge?" harness | ✅ Done → **no edge** |
| Features 1, 2, 6, 8, 9, 10 + paper trading + 3-candle patterns | ✅ Done |
| A1 Human verification pass | ✅ Done (merged `645231c`, 2026-09-23) |
| A2 Verdict reframe + no-edge disclosure | ✅ Done (merged `800e12a`, 2026-09-23) |
| A3 Situation tier in Layer 1 | ✅ Done (merged, 2026-09-23) |
| A4 Support/resistance as zones + level freshness | ✅ Done (merged, 2026-09-23) |
| A5 Facts payload hardening | ✅ Done (merged, 2026-09-24) |
| A6 Analyst guide revision | ✅ Done (merged, 2026-09-24) |
| A7 Honest baselines | ✅ Done (merged, 2026-09-24) |
| B1 Detector gold set — labelling mode | ✅ Tooling merged (2026-09-24); ≥30 labelled charts pending (user) |
| Tests | 382 green, ruff + svelte-check clean |

**Remaining, in order:**

~~`A1`~~ ✅ `→` ~~`A2`~~ ✅ `→` ~~`A3`~~ ✅ `→` ~~`A4`~~ ✅ `→` ~~`A5`~~ ✅ `→` ~~`A6`~~ ✅ `→` ~~`A7`~~ ✅ `→ A8 → A5 → A6 → A7 → A8` *(honesty & precision hardening, then start the forward record)*
`→ B1 → B2 → B3 → B4 → B5` *(measure the detectors, then the patterns)*
`→ C1` *(integrity, enforced)*
`→ D1 → D2 → D3 → D4 → D5 → D6` *(the learning loop)*

---

## 5. Done

**Foundation:** candles via ccxt (crypto) and Twelve Data (forex); RSI, MACD, MAs, ADX, Stochastic,
Bollinger, ATR, OBV, volume; swings, S/R, trendlines, trend, Fibonacci, round numbers, RSI divergence;
double top/bottom, head & shoulders, triangles, channels, rectangles; 1-, 2-, 3-candle patterns;
category-aware confluence with multi-timeframe gating; Claude explanation (brief + teaching modes,
guide wired in, classification in Layer 1); Svelte + lightweight-charts app with scrubbing;
FastAPI with auth + rate limiting; look-ahead-safe backtester, out-of-sample suite, track-record
base rates, crypto/forex adaptation, derivatives context.

| # | Feature | Summary |
|---|---|---|
| 1 | Pattern visualization + research view | multi-panel chart, look-ahead-safe scrubbing |
| 2 | Pattern confirmation states | forming/confirmed/failed + 7-way confirmation profile |
| 6 | Market regime | per-bar trending/ranging/volatile/quiet |
| 8 | Exit-rule laboratory | entries fixed, exit rules compared |
| 9 | Risk of ruin & position sizing | survival maths + calculator |
| 10 | Honest cost model | fees/slippage/funding netted by default |
| — | Paper-trading simulator | simulated trades, fills, P&L, chart markers |
| — | Three-candle patterns | facts-only, drawn on chart |

Standing rules these respected: patterns and 3-candle candlesticks stay **out of the confidence
score** until measured; regime is standalone (not a vote).

---

## 6. Remaining — in build order

One step per branch, tests alongside, SQLite at `data/wizard.db`, ATR-scaled tolerances,
look-ahead-safe, merged only when **Done when** passes. Prompts for each are in `PROMPTS.md`.

### Phase A — Honesty & precision hardening *(do first; mostly small)*

**A1 — Human verification pass.** Things only your eyes can check, plus the rendering bugs that block
them. Fix: pattern boundary lines not drawn (SOL/USDT daily showed an ascending-channel badge but only
the swing zigzag); overlapping labels in the top-left of the main pane. Then check by eye: regime labels
on daily match periods you remember (clear trend → trending, clear chop → ranging, no flicker); the old
BTC double top (neckline ~76,264) now reads `failed`; the SOL "ascending channel" looks like a channel
to you (record yes/no — it feeds B1).
**Done when:** boundaries and labels render correctly in the browser, and each eye-check is recorded
pass/fail in `PROGRESS.md`.

**A2 — Verdict reframe + no-edge disclosure.** Replace "confidence 55%" with a count ("2 of 5
categories agree") — keep the 0–1 score internally. Remove directional colour coding on the verdict.
Rename "SETUP FLAGGED" to a non-actionable label ("categories aligned"). Add a persistent, quiet UI
line: *"Tested: no predictive edge. This tool is for reading charts, not forecasting them,"* linking to
the backtest/ML evidence. Delete the guide's "if asked whether it works" rule — the UI carries it now.
**Done when:** no percentage labelled "confidence" anywhere in the UI, no green/red verdict styling,
disclosure visible — verified in the browser.

**A3 — Situation tier in Layer 1.** Layer 1 computes `situation_tier` —
`no_setup / notable / confirmed` (plus `mtf_synthesis` for multi-timeframe) — from deterministic rules
that mirror the guide's §2 criteria. **Forming patterns cannot make categories "aligned"**; they appear
as context only. The tier selects the explanation template and word budget; Claude receives it and
cannot escalate it. Show the tier in the UI.
**Done when:** identical facts always yield the same tier (test); the SOL forming channel no longer
produces an aligned verdict; each §2 criterion has a test.

**A4 — Support/resistance as zones + level freshness.** S/R becomes a band: centre, ATR-scaled width,
touch count, first/last touch, bars since last touch. Recency-weighted strength; levels untouched for a
long time are marked **stale**. Draw zones as shaded bands. Fibonacci and round numbers stay as exact
lines (they're exact by definition).
**Done when:** zones render in the browser; stale levels are marked; snapshot regenerated with a
reviewed diff; tests for width scaling and staleness.

**A5 — Facts payload hardening.** In `facts.py`:
- **Explicit absences** — "no divergence detected", "no confirmed pattern", never silent omission.
- **Distances** from price to every level in ATR units and %, computed by Layer 1 — Claude never does
  arithmetic.
- **Nearest structural level above and below** price — enables symmetric conditional reads.
- **Bars since confirmation** for every pattern (staleness).
- **Detector reliability as a field**, not prose (populated properly in B2).
- **Multi-timeframe alignment per signal** — e.g. trend: 1d bullish / 1w neutral.
- **`strongest_opposing_fact`** — when any category votes against the read, Layer 1 names the strongest one.
- Facts **rendered in the guide's §3 priority order.**

**Done when:** every field is present; tests assert absences are explicit and distances exist;
snapshot regenerated with a reviewed diff.

**A6 — Analyst Guide revision.** Fix the contradictions and gameable rules the review quoted:
- §1.4: drop "what it conventionally suggests." Treat *suggests / favours / leans / path of least
  resistance / buyers or sellers in control* as **directional claims** — allowed only where the Layer 1
  vote agrees (and, from B4, alongside the measured record).
- §4: "conventionally read as" labels a convention; it does not license a direction.
- §5: extremes describe **crowded positioning**, with no implied direction; remove the guide's own
  uncounted historical claims ("historically coincided with turning points", "many false breaks").
- §1.1 vs "≈": one stated rounding rule, matching the verifier's tolerance; fix the example.
- §8 vs §10: one fact-naming style.
- §2 conditional reads: **symmetric** — use Layer 1's nearest level above *and* below; no directional
  "so"; fix "worth revisiting near…".
- §7: cut to a single allowed relation — higher-timeframe trend vs pattern-implied direction. Everything
  else belongs in Layer 1.
- Use the tier supplied by A3; never escalate it.
- Always include `strongest_opposing_fact` when supplied; it doesn't count toward the word budget.
- **Teaching mode lifts only the word cap** — tier, opposing fact, and every rule still apply.
- §11 self-check: keep, but note enforcement moves to C1.

**Done when:** guide updated; prompt tests pass; three charts spot-checked in brief and teaching modes —
no directional wording without an agreeing vote, opposing fact present, conditionals symmetric.

**A7 — Honest baselines.** Paper trading: a **random-entry baseline band** beside the P&L (same
instrument, similar holding periods, many random entries) showing where luck alone lands. Risk
calculator: default win rate is a cost-adjusted coin flip; backtest numbers only when explicitly chosen,
labelled "backtest — no edge found".
**Done when:** baseline band visible; calculator defaults changed; browser-verified.

**A8 — Morning report: the forward record ★** A scheduled daily analysis that builds the one kind of
evidence a backtest can't: the engine's live record on data that didn't exist when it spoke. It can't
be look-ahead-biased, and it can't be backfilled — so it goes at the end of Phase A, once the verdict,
tier, and levels are stable, and then runs every day from there.

- **When:** every day at **08:00 Europe/Skopje** (daylight-saving aware). Must run on an always-on
  machine — a sleeping laptop records nothing.
- **What:** a configurable watchlist — default a few crypto pairs (BTC, SOL…), **EUR/USD, gold
  (XAU/USD), oil (WTI)** — on **30m, 1h, 4h, 1d**. Gold and oil need a data source (check Twelve Data
  coverage first). **Closed candles only** — never analyse a half-formed candle.
- **Order of each run — review first, then read:**
  1. **Review:** resolve every past read whose horizon has ended, and show the outcomes.
  2. **Read:** run the engine on every symbol × timeframe and **freeze** each read.
  3. **Explain (optional):** one multi-timeframe synthesis per symbol (≈6 Claude calls, not 24).
- **The review never feeds the new read.** Outcomes are shown *beside* today's analysis, never used
  as an input — otherwise the engine starts chasing its own misses and the record is no longer clean.
- **Horizons match the timeframe, counted in bars** (so forex weekends skip naturally):
  30m → 48 bars (≈1 day), 1h → 24 bars (≈1 day), 4h → 42 bars (≈1 week), 1d → 21 bars (≈1 month).
  Configurable.
- **Frozen read** (SQLite `forward_reads`): timestamp, symbol, timeframe, last closed bar, price,
  situation tier, categories aligned + direction, invalidation level, next level in the read's
  direction, nearest level above/below, a hash of the facts, and the **engine version (git commit)** —
  so any later change to the engine splits the record cleanly instead of silently mixing versions.
- **Outcome rule — fixed and versioned before the first run:**
  - *Directional read:* first touch wins, using bar highs/lows — invalidation first = **invalidated**;
    next level first = **followed through**; neither within the horizon = **expired**; both inside the
    same bar = **ambiguous** (OHLC can't tell the order — never guess).
  - *No-setup read:* **correct** if price stayed between the nearest levels above and below for the
    horizon; **missed move** if it broke out. No-setup reads are scored too — otherwise only signals
    get graded and the record is skewed.
  - Changing the rule creates a new rule version; old reads keep their original rule.
- **Missed mornings are recorded as gaps, never backfilled.** Backfilling with historical candles
  would turn the forward record back into a backtest.
- **Weekends:** forex, gold, oil produce no new read when there's no new closed candle; crypto runs daily.
- **Report page:** review section first (resolved reads and outcomes), then today's reads as a
  symbol × timeframe grid, then the per-symbol synthesis. A running scoreboard per timeframe and tier —
  followed / invalidated / expired / ambiguous, with counts — beside a **coin-flip baseline** using the
  same outcome rule with random direction.

**Done when:** the scheduler fires at 08:00 Skopje (timezone test, including a DST change) and via a
manual trigger; reads are frozen with engine version; expired reads resolve under the fixed rule;
running twice in one day doesn't duplicate; a missed day shows as a gap; weekend handling is tested;
the report page shows review first, then today — verified in the browser.

*Honest note: 30m and 1h resolve fastest, so they'll dominate the early record — but they're the
timeframes least relevant to multi-week trend riding. Weigh the 4h and 1d record more, even though
it builds slowly.*

### Phase B — Measure the detectors, then the patterns

**B1 — Detector gold set (labelling mode).** In the scrub view, a labelling mode where you mark, at a
chosen bar, the patterns (type + key points) and S/R zones **your eye** sees. **Detector overlays are
hidden while labelling** so you don't anchor on them. Saved to SQLite `gold_labels`
(symbol, timeframe, bar, labels, timestamp). Start with ~30 charts — BTC, SOL, one forex pair, daily,
a mix of trend and chop, including the SOL channel case — and grow to 50+.
*Honest note: the labelling is your work, a few hours. That's the point — your eye becomes the reference.*
**Done when:** labelling mode works with overlays hidden; ≥30 charts labelled.

**B2 — Detector precision/recall + tuning.** `scripts/eval_detectors.py` compares detections with your
gold labels at the same bars (ATR-scaled matching): **precision** (when it fires, is it right?) and
**recall** (does it find what you marked?), with counts, per detector per timeframe. Tune weak detectors
(e.g. channel over-calling). **Hold out ~30% of labels** — tune on the rest, report on the held-out set,
so you don't just overfit to your own labels. Populate the reliability field from A5 with measured precision.
**Done when:** a precision/recall table per detector with counts, before and after tuning, on held-out
labels — recorded in `PROGRESS.md`.

**B3 — Feature 3: Empirical Pattern Encyclopedia ★** Per pattern type × timeframe × symbol × regime:
occurrences, confirmation rate, follow-through, median/IQR move in ATR units, failure rate, bars to
resolution, split by confirmation category. `encyclopedia_stats` in SQLite, **sample size on every row**,
n<20 flagged `insufficient_data`. Reuse the existing look-ahead-safe backtest walk. `/encyclopedia` pages
show your numbers beside the textbook claim (`docs/patterns-research.md`), with examples opening in the
scrub view. **New:** each row also shows that detector's measured precision from B2, so you know how
much to trust it.
**Done when:** every pattern type has a page of real numbers with sample sizes and detector precision;
thin data labelled honestly; examples open at the right bar.

**B4 — Data adjacency.** Beside the verdict: the measured record of that verdict type ("categories
aligned bullish, 2 of 5 — 212 of 430 resolved that way", or "insufficient data"). Beside any measured
target: how often that pattern type reached its target. **Rendered by the UI from Layer 1 data**, not
written by Claude. Guide: any directional read references its record.
**Done when:** every directional verdict and every measured target carries an adjacent count, or
"insufficient data".

**B5 — Calibrate quality + re-rank the guide.** Map raw pattern quality to observed follow-through per
pattern type; show quality as a calibrated band (low/medium/high) with counts. Re-order the guide's §3
priority list using measured detector precision (B2) and encyclopedia results — least reliable moves down.
**Done when:** quality displays its calibrated meaning; the new §3 order is justified by a table in
`PROGRESS.md`.

### Phase C — Integrity, enforced

**C1 — Feature 7 rebuilt: the integrity guard.** Not just number-matching.
- `explain()` returns **structured claims** — `{text, fact_id, role, direction}` with roles
  `read / why / invalidation / watch / opposing / conditional`. Prose is rendered from claims.
- Mechanical checks: `fact_id` exists; role fits the fact type (a neckline can't be "support");
  direction matches the Layer 1 vote; no state upgrades (forming → confirmed); numbers match within the
  stated rounding rule; opposing slot present when supplied; tier respected; word budget (brief mode).
- **Directional-language check:** suggests/favours/likely/path-of-least-resistance flagged unless tied
  to a claim with a matching vote.
- **Hard failures gate:** one retry with the violation list; if it still fails, show a deterministic
  facts-only fallback with a notice. Soft issues get a warning badge.
- The guide's §11 self-check becomes this verification pass.

**Done when:** a deliberately corrupted output for each check is caught by a test; real explanations
pass; the fallback path works; teaching mode is checked too (minus the word budget).

### Phase D — The learning loop

**D1 — Feature 4: Prediction journal + calibration ★** Log direction, confidence 0–100, invalidation,
horizon (**default in weeks** — you trade trends), and a note, before the explanation is revealed.
**Option to hide the verdict badge until you've logged**, so you don't anchor on it. Auto-resolution,
Brier score, 10%-bin calibration curve, per-pattern and per-regime breakdowns, overconfidence delta.
No gamification. **Pairs with A8:** the morning report is the natural moment to log your own read
*before* viewing the engine's, so your record and the engine's accumulate side by side.
**Done when:** you can log, it resolves, and a calibration curve with sample sizes appears.

**D2 — Feature 11: Pre-registration.** Append-only `experiments` table; hypothesis, parameters,
metric, threshold, and predicted result recorded before any backtest; multiple-comparison correction;
dashboard listing every experiment including failures, plus your hit rate at predicting your own results.
**Done when:** a backtest can't run unregistered, and the dashboard shows every miss.

**D3 — Feature 13a: News & macro context.** Calendar with consensus/previous/actual; headlines (link
only); central-bank and commodity calendars; `src/context/drivers.py`. Surfaces an event-risk warning,
a driver attribution for the current trend (as a *hypothesis*), and a **correlation warning** when your
instruments are secretly one macro bet.
**Done when:** events, driver hypothesis, and correlation warning appear for a followed instrument.

**D4 — Feature 13b: Event study ★** `events` table + `src/research/event_study.py`: forward-return
distributions per event type × instrument at several horizons, conditioned on surprise vs consensus
and on regime, routed through D2. Reuses the backtest walk.
**Done when:** you can pick an event type + instrument and see measured reactions with sample sizes and
an honest consistent / inconsistent / insufficient-data verdict.

**D5 — Feature 12: Behavioural circuit breaker.** Versioned declared rules; every logged trade checked;
violations recorded, not blocked; rule-following vs rule-breaking outcomes with sample sizes; tilt
detection; weekly review. Neutral tone.
**Done when:** you can see, with counts, how your rule-breaking trades did vs your disciplined ones.

**D6 — Feature 5: Blind training mode ★** Random historical bar where a pattern confirmed (filter by
type/regime), future hidden, your call through the journal, then the reveal: outcome, what the engine
said then, and the encyclopedia stats.
**Done when:** a 10-setup session ends with your calibration.

---

## 7. Maybe later / deprioritized

**Maybe later:** watchlist scan (not real-time); flags & pennants (once B1/B2 can measure them);
analysis permalinks.

**Skip:** Elliott Wave; exotic patterns (diamonds, broadening); chasing edge with more indicators;
live alerting / real-time; anything that implies prediction.

## 8. Conventions (every step)

- One step per branch; merge only when **Done when** passes.
- Tests alongside code, runnable under `pytest -m "not network"`.
- SQLite at `data/wizard.db` via stdlib `sqlite3` — no Postgres, no ORM.
- **Never fixed-% thresholds** — ATR-scaled tolerances.
- **Look-ahead safety is sacred** — guard tests mutate future bars and assert the past is unchanged.
- Frontend changes are **verified in a real browser**, not just a build.
- **Facts-first:** new detectors surface as facts before they may become votes, and only when a
  backtest shows they earn it.
- **The guide shrinks as Layer 1 grows:** new judgement goes into code, not into the prompt.
- **Precision of reading, never forecasting.**
- **Any number that could read as a probability carries its count.**
- **Snapshot regenerations require a reviewed diff.**
- **Forward records are never backfilled** — a missed day is a gap, not a reconstruction.
- Every ~3 steps, ask Claude Code for a user-level tour of what the app now does.

## 9. Old planning files

`PLAN.md`, `trading-advisor-plan.md`, `final-roadmap.md`, `tier1-build-spec.md`, `survival-spec.md`,
and `feature-13-spec.md` are superseded. Move them to `docs/archive/` as reference.
