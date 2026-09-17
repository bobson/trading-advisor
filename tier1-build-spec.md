# Trading Wizard — Tier 1 Build Spec

Implementation detail for `final-roadmap.md` Tier 1. Written so Claude Code doesn't have to
invent architecture. **One feature per branch.** Each section ends with a ready prompt.

## Conventions (apply to every feature)
- Branch: `feature/<name>`; merge only when its **Done when** passes.
- Tests alongside code, runnable under `pytest -m "not network"`.
- After each: ask Claude Code to walk you through it in plain language, **max ~15 lines** —
  file-by-file, one or two sentences each. Not an essay.
- Reuse existing ATR-scaled tolerances and look-ahead guards. Never introduce fixed-% thresholds.

## Decisions already made (don't let Claude Code re-open these)
- **Storage: SQLite**, one file at `data/wizard.db`, via stdlib `sqlite3`. No Postgres, no ORM.
  Personal-scale, zero setup, easy to inspect. Tables: `journal_entries`, `encyclopedia_stats`,
  `regime_cache`.
- **Encyclopedia is precomputed**, not computed per request — a script writes stats to SQLite;
  the API reads them.
- **Regime is a column** on the candle DataFrame, computed like any other indicator.
- **Explanation output is structured JSON** (`read` / `why` / `invalidation` / `watch`), not prose.

## Revised order
1 → 2 → **6 (regime)** → 3 (encyclopedia) → 4 → 5 → 7.
Regime moves ahead of the encyclopedia because the encyclopedia segments by it; building it
after would mean recomputing everything.

---

## Feature 1 — Pattern visualization + research view

**Goal:** see every detected pattern and the indicator panels together, and step back through
history to any past bar.

**Backend** — extend the `/report` response with, per pattern: `type`, `state`, `points[]`
(bar index + price for each defining swing), `lines[]` (slope/intercept or two endpoints for
each boundary), `breakout_level`, `invalidation_level`, `target`, `quality`. Add a
`?as_of_bar=N` query param: the engine recomputes using **only bars ≤ N**. This is the
scrubbing primitive — no separate code path, same pipeline with a truncated frame.

**Frontend (Svelte + lightweight-charts)**
- Main pane: patterns drawn as line series + price lines. Style by state — `forming` dashed
  and muted, `confirmed` solid and coloured by direction, `failed` greyed.
- Sub-panes, all visible at once: volume + volume MA (histogram), RSI with divergence segments
  marked, MACD (line/signal/histogram), ADX, ATR. Use synchronised time scales.
- A toggle panel for every overlay and sub-pane; persist choices in `localStorage`.
- Scrub control: a slider/stepper over bar index that refetches with `as_of_bar`, plus
  keyboard left/right for single-bar steps. Debounce refetches.

**Tests:** `as_of_bar=N` output is byte-identical to running the engine on a frame truncated at
N (the look-ahead guard for scrubbing); pattern serialization round-trips; each state serializes
distinctly.

**Done when:** you can scrub to any past bar and see exactly what the engine saw then, with all
panels drawn, and the guard test passes.

> **Prompt:** "On branch `feature/pattern-viz`, implement Feature 1 of BUILD-SPEC.md: extend the
> `/report` response with full pattern geometry and add an `as_of_bar` param that recomputes on
> a truncated frame; then in the Svelte app draw patterns on the main chart styled by state, add
> synchronised sub-panes for volume+MA, RSI with divergences, MACD, ADX and ATR, per-overlay
> toggles persisted to localStorage, and a bar-scrub control with keyboard stepping. Include the
> look-ahead guard test comparing `as_of_bar=N` against a truncated-frame run. Then summarise the
> changes in under 15 lines."

---

## Feature 2 — Pattern confirmation states

**Goal:** every pattern carries state, levels, quality, and a multi-category confirmation profile.

**Key point:** confirmation is **not just volume**. Build a `ConfirmationProfile` with one field
per category — `price` (close beyond level; retest seen), `volume` (expansion vs MA; contraction
inside), `momentum` (RSI/MACD/Stochastic agreement; divergence present), `volatility` (ATR rising;
Bollinger squeeze resolving), `candlestick` (a reversal candle at the level), `higher_tf`
(agrees / neutral / opposes), `structure` (level coincides with S/R, Fib, or round number).
Each: `supports` / `neutral` / `contradicts` / `unavailable`.

Add `src/patterns/base.py` (Pattern dataclass), refactor existing detectors to emit it, add
`src/patterns/dedupe.py` (overlapping detections over the same bar range → keep highest quality).
Keep patterns **out of the confidence score** in this branch — facts and chart only.

**Look-ahead:** state at bar N uses bars ≤ N only; a pattern is never retroactively confirmed.
Extend the existing mutate-future-bars guard to cover the state machine.

**Done when:** each pattern reports state, breakout, invalidation, quality and a full
confirmation profile; overlaps are deduplicated; the guard test passes.

> **Prompt:** "On branch `feature/pattern-confirmation`, implement Feature 2 of BUILD-SPEC.md:
> add `src/patterns/base.py` with the Pattern dataclass and ConfirmationProfile (price, volume,
> momentum, volatility, candlestick, higher_tf, structure — each supports/neutral/contradicts/
> unavailable), refactor the existing double top/bottom, H&S and triangle detectors to emit it
> with ATR-scaled tolerances, and add `dedupe.py`. Keep patterns out of the confluence score.
> Extend the look-ahead guard to the state machine. Tests with synthetic fixtures for each state.
> Summarise in under 15 lines."

---

## Feature 6 — Market regime (build before the encyclopedia)

**Goal:** label every bar's regime so everything else can segment by it.

`src/market/regime.py` → a `regime` column: `trending_up` / `trending_down` / `ranging` /
`volatile` / `quiet`, from ADX (trend presence), MA slope (direction), and ATR percentile over a
rolling window (volatility). Rolling percentiles only — never whole-series statistics, which leak
the future. Cache per symbol/timeframe in SQLite.

**Done when:** every bar has a regime, the classification is stable (not flickering bar to bar),
and a look-ahead test confirms no future data is used.

> **Prompt:** "On branch `feature/regime`, implement Feature 6 of BUILD-SPEC.md: `src/market/
> regime.py` classifying each bar as trending_up/trending_down/ranging/volatile/quiet from ADX,
> MA slope, and rolling ATR percentile (rolling windows only — no whole-series stats). Cache to
> SQLite. Add hysteresis so labels don't flicker. Include a look-ahead test. Summarise in under
> 15 lines."

---

## Feature 3 — Empirical Pattern Encyclopedia

**Goal:** replace textbook claims with what actually happened in your data.

`scripts/build_encyclopedia.py` walks history per **pattern type × timeframe × symbol × regime**
and records: occurrences, confirmation rate, follow-through rate (reached target before
invalidation), median and IQR of move size in ATR units, failure rate, median bars to resolution,
and **the same broken down by each confirmation category** (e.g. follow-through with volume
supporting vs not). Write to `encyclopedia_stats` in SQLite.

**Non-negotiable:** every row stores `sample_size`; anything under a threshold (suggest 20) is
flagged `insufficient_data` and must render as such, not as a percentage. Reuse the existing
backtest's look-ahead-safe walk — do not write a second history walker.

Serve at `/encyclopedia` and `/encyclopedia/{pattern_type}`; render a page per pattern with your
statistics, the conventional claim beside them (source: `docs/patterns-research.md`), sample
sizes, and links to 3–5 real historical examples that open in the scrub view from Feature 1.

**Done when:** every pattern type has a page showing real numbers with sample sizes, insufficient
data is labelled honestly, and examples open at the right bar in the chart.

> **Prompt:** "On branch `feature/encyclopedia`, implement Feature 3 of BUILD-SPEC.md: a
> `scripts/build_encyclopedia.py` that reuses the existing look-ahead-safe backtest walk to
> compute per pattern type × timeframe × symbol × regime — occurrences, confirmation rate,
> follow-through rate, median/IQR move in ATR units, failure rate, bars to resolution, and the
> same split by each confirmation category — into a SQLite `encyclopedia_stats` table with
> sample_size on every row. Flag n<20 as insufficient_data. Add `/encyclopedia` endpoints and
> Svelte pages showing my stats beside the conventional claim from docs/patterns-research.md,
> with links that open examples in the scrub view. Summarise in under 15 lines."

---

## Feature 4 — Prediction journal + calibration

**Goal:** measure how well *you* read charts.

Flow: on an analysis, before revealing Claude's explanation, the user may log a prediction —
direction (`up`/`down`/`neutral`), confidence 0–100, invalidation price, horizon in bars, free-text
note. Stored in `journal_entries` with symbol, timeframe, bar index, timestamp, and a facts
snapshot hash. A resolver (`src/journal/resolve.py`) marks entries resolved once the horizon has
elapsed: correct / incorrect / invalidated.

**Calibration** (`src/journal/calibration.py`): Brier score; a calibration curve bucketed by
stated confidence (10% bins) showing predicted vs actual; breakdown by pattern type and regime;
overconfidence delta (mean confidence − accuracy). Render as a stats page.

**Do not gamify.** No streaks, no scores-as-points, no encouraging copy. Report the numbers
plainly — the value is an uncomfortable accurate mirror.

**Done when:** you can log a prediction, it resolves automatically, and the stats page shows a
calibration curve with sample sizes.

> **Prompt:** "On branch `feature/journal`, implement Feature 4 of BUILD-SPEC.md: a SQLite
> `journal_entries` table and Svelte flow to log direction/confidence/invalidation/horizon before
> revealing the AI explanation; `src/journal/resolve.py` to resolve entries after the horizon; and
> `src/journal/calibration.py` computing Brier score, a 10%-bin calibration curve, per-pattern and
> per-regime breakdowns, and overconfidence delta. Plain reporting, no gamification. Tests for
> resolution logic and calibration maths. Summarise in under 15 lines."

---

## Feature 5 — Blind training mode

**Goal:** deliberate practice. Cheap once 1 and 4 exist — same machinery, future hidden.

Pick a random historical bar where a pattern reached `confirmed` (filterable by type/regime),
render the scrub view at that bar with everything after it hidden, take the user's call via the
Feature 4 journal flow, then reveal: what happened next, what the engine's analysis said at that
moment, and the encyclopedia stats for that pattern type. Log every attempt to the journal so
practice feeds the same calibration numbers.

**Done when:** you can run a session of 10 setups and see your calibration afterwards.

> **Prompt:** "On branch `feature/blind-mode`, implement Feature 5 of BUILD-SPEC.md: a training
> mode that selects a random historical confirmed-pattern bar (filterable by type and regime),
> renders the Feature 1 scrub view with all later bars hidden, collects a call through the Feature
> 4 journal flow, then reveals the outcome, the engine's analysis at that bar, and the relevant
> encyclopedia stats. Session of N setups with calibration summary at the end. Summarise in under
> 15 lines."

---

## Feature 7 — Explanation integrity guard

**Goal:** enforce "Layer 2 never contradicts Layer 1" mechanically.

`src/advisor/verify.py` — after each explanation, extract all numbers and pattern names from the
output and assert each appears in the facts dict (numeric tolerance for rounding). Flag: numbers
not in facts, pattern types not detected, and **output exceeding its word budget** (see the
analyst guide's Section 8). Log violations; surface a warning badge in the UI rather than hiding
the explanation.

**Done when:** a deliberately corrupted explanation is flagged by tests, and real explanations
pass cleanly.

> **Prompt:** "On branch `feature/integrity-guard`, implement Feature 7 of BUILD-SPEC.md:
> `src/advisor/verify.py` checking every number and pattern name in the explanation against the
> facts dict, plus a word-budget check per the analyst guide's Section 8. Log violations and show
> a warning badge in the UI. Tests using deliberately corrupted explanations. Summarise in under
> 15 lines."
