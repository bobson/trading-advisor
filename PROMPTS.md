# Trading Wizard — Step-by-Step Prompts

Work top to bottom. Each step: create the branch, paste the prompt, do **your check**, then run the
standard cycle below. Full specs for every step are in `ROADMAP.md §6`.

---

## The standard cycle (after every step)

**1. Merge and push**
```bash
git checkout main
git merge <branch-name>
git push origin main
```

**2. Update PROGRESS.md** — paste, filling in the step:
> Step [ID] ([name]) is merged. Update PROGRESS.md: date, branch, what the "done when" check showed,
> any deviations from ROADMAP.md and why, and any finding worth remembering. Update the current-state
> section and mark the step done in ROADMAP.md §4.

**3. Every ~3 steps**, ask for a tour:
> Walk me through what the app can do now from a user's point of view — how to run it, what I see,
> what I can click, what each part shows. Under 30 lines, no implementation detail.

---

## Step 0 — Install the roadmap (once, on main)

> I've added a new ROADMAP.md (replacing the old one) and PROMPTS.md. Read ROADMAP.md fully. Then:
> 1. Move PLAN.md, trading-advisor-plan.md, final-roadmap.md, tier1-build-spec.md, survival-spec.md
>    and feature-13-spec.md into docs/archive/.
> 2. Update CLAUDE.md so these standing rules apply to every future task: ROADMAP.md is the source of
>    truth; if a spec doesn't match the real code, adapt it and tell me what differed; verify every
>    frontend change in a real browser before calling it done; snapshot regenerations need a diff I
>    review; the analyst guide shrinks as Layer 1 grows — new judgement goes into code, not the prompt;
>    summaries stay under 15 lines.
>
> Don't write feature code. Tell me what you changed.

**Your check:** the old files are in `docs/archive/`; CLAUDE.md contains the standing rules. Commit on main.

---

# Phase A — Honesty & precision hardening

## A1 — Human verification pass
**Branch:** `fix/verification-pass`

> ROADMAP step A1. Before I do the visual checks, fix what blocks them:
> 1. On SOL/USDT daily an "ascending channel · forming" badge appears, but only the swing-point zigzag
>    is drawn — not the channel's two boundary lines. Check whether pattern geometry (channel rails,
>    triangle sides, necklines) is rendered at all; if not, wire it up for every pattern type.
> 2. Fix the overlapping, garbled labels in the top-left of the main chart pane.
> 3. Make sure the regime strip is visible and legible on the daily timeframe.
> 4. Tell me the current state of the BTC/USDT daily double top with neckline ~76,264. Price has since
>    broken above it, so it should be `failed` — confirm, or explain why not.
>
> Verify 1–3 in the browser. Summarise in under 15 lines.

**Your check (by eye):**
- Pattern boundaries now draw where you'd draw them.
- Scroll the daily chart: a clear multi-month rise is labelled trending, a clear sideways chop is
  labelled ranging, and labels don't flip every few bars.
- Does the SOL "ascending channel" look like a channel to you? **Write down yes or no** — it feeds B1.
- Record every check as pass/fail when you update PROGRESS.md.

---

## A2 — Verdict reframe + no-edge disclosure
**Branch:** `feature/verdict-reframe`

> ROADMAP step A2. The verdict header ("Bias: bullish · confidence 55% · SETUP FLAGGED" in green) reads
> as odds to a beginner, and it's what most sessions see. Change it:
> - Replace "confidence NN%" with a count, e.g. "2 of 5 categories agree". Keep the 0–1 score
>   internally; just never display it as a percentage labelled confidence.
> - Remove directional colour coding (green/red) from the verdict; neutral styling.
> - Rename "SETUP FLAGGED" to a non-actionable label such as "categories aligned".
> - Add a persistent, quiet line in the UI: "Tested: no predictive edge. This tool is for reading
>   charts, not forecasting them." Link it to a short page or panel summarising the backtest and ML results.
> - Remove the "if asked whether it works, say so plainly" rule from the analyst guide — the UI carries
>   the disclosure now.
>
> Search the whole frontend for any other place a percentage is labelled confidence. Verify in the
> browser. Summarise in under 15 lines.

**Your check:** no "confidence %" anywhere; verdict isn't green or red; the disclosure line is visible.

---

## A3 — Situation tier in Layer 1
**Branch:** `feature/situation-tier`

> ROADMAP step A3. Right now Claude decides whether a chart is "no setup", "notable" or "confirmed", and
> that choice sets its own word budget. Move it into Layer 1:
> - Compute `situation_tier` (no_setup / notable / confirmed, plus mtf_synthesis for multi-timeframe)
>   deterministically, using rules that mirror the analyst guide's §2 "no clear setup" criteria.
> - Forming patterns must not make categories count as aligned — they're context only. On SOL/USDT
>   daily, a forming ascending channel currently produced a flagged setup; that must stop.
> - Pass the tier in the facts; it selects the explanation template and word budget. Claude receives it
>   and must not change it.
> - Show the tier in the UI next to the verdict.
>
> Tests: identical facts always give the same tier; each §2 criterion has a test; a forming-only chart
> can't be "confirmed". Verify the UI in the browser. Summarise in under 15 lines.

**Your check:** reload SOL daily — the forming channel no longer produces an aligned verdict. Try a few
charts and see whether the tier matches your own sense of "nothing here" vs "something here".

---

## A4 — Support/resistance as zones + freshness
**Branch:** `feature/sr-zones`

> ROADMAP step A4. A single S/R line at 76,132 implies false precision. Change S/R to zones:
> - Each level becomes a band: centre, ATR-scaled width, touch count, first and last touch bar,
>   bars since last touch.
> - Add recency-weighted strength; mark levels untouched for a long time as stale (define "long" in
>   ATR/bar terms, not a fixed date).
> - Draw zones as shaded bands on the chart. Fibonacci and round numbers stay as exact lines.
> - Update confluence and facts to use zones (price "at support" means inside or near the band).
>
> The snapshot test will change — show me the diff before regenerating it. Tests for width scaling and
> staleness. Verify in the browser. Summarise in under 15 lines.

**Your check:** zones look like the areas where price actually reacted; old levels are visibly marked stale.

---

## A5 — Facts payload hardening
**Branch:** `feature/facts-hardening`

> ROADMAP step A5. Make the facts sent to Claude complete enough that it never has to guess or calculate:
> - Explicit absences: "no divergence detected", "no confirmed pattern", etc. — never silent omission.
> - Distance from price to every level, in ATR units and %, computed here. Claude must never do arithmetic.
> - The nearest structural level above price and below price.
> - Bars since confirmation for every pattern.
> - A detector reliability field (placeholder for now; B2 fills it with measured precision).
> - Multi-timeframe alignment per signal, e.g. trend: 1d bullish / 1w neutral.
> - `strongest_opposing_fact`: when any category votes against the read, name the strongest one.
> - Render the facts in the analyst guide's §3 priority order.
>
> Show me the snapshot diff before regenerating. Tests that absences are explicit and distances are
> present. Summarise in under 15 lines.

**Your check:** ask Claude Code to print the facts for BTC/USDT daily and read them yourself — could you
explain the chart from that text alone, without doing any maths?

---

## A6 — Analyst Guide revision
**Branch:** `feature/guide-revision`

> ROADMAP step A6. Revise `src/advisor/analyst-guide-system-prompt.md` to fix these contradictions and
> gameable rules:
> 1. §1.4: remove "what it conventionally suggests". State that suggests / favours / leans / path of
>    least resistance / buyers or sellers in control are directional claims, allowed only where the
>    Layer 1 vote agrees.
> 2. §4: "conventionally read as" labels a convention; it doesn't license a directional claim.
> 3. §5: extremes describe crowded positioning with no implied direction. Remove the guide's own uncounted
>    historical claims ("historically coincided with turning points", "many false breaks").
> 4. §1.1 vs the "≈" in examples: write one rounding rule that matches the verifier's tolerance; fix examples.
> 5. §8 vs §10: pick one fact-naming style and use it in both.
> 6. §2 conditional reads: must be symmetric, using the nearest level above and below from the facts;
>    no directional "so"; replace "worth revisiting near…".
> 7. §7: cut to one allowed observation — higher-timeframe trend conflicting with a pattern's implied
>    direction. Everything else belongs in Layer 1.
> 8. Use the `situation_tier` supplied in the facts; never escalate it.
> 9. Always include `strongest_opposing_fact` when supplied; it doesn't count toward the word budget.
> 10. Teaching mode lifts only the word cap — tier, opposing fact, and every other rule still apply.
> 11. §11: keep the self-check, noting that mechanical enforcement comes in step C1.
>
> Keep the prompt tests passing. Then run brief and teaching on three charts (BTC daily, SOL daily, one
> forex pair) and show me the outputs.

**Your check:** read the six outputs. Any directional wording without an agreeing vote? Is the opposing
fact there? Are the conditional reads symmetric (a level above *and* below)?

---

## A7 — Honest baselines
**Branch:** `feature/honest-baselines`

> ROADMAP step A7. Two baselines so luck is visible:
> 1. Paper trading: beside the P&L, add a random-entry baseline band — many random entries on the same
>    instrument with similar holding periods, showing the range luck alone produces.
> 2. Risk calculator: default the win rate to a cost-adjusted coin flip. Only use backtest numbers when I
>    explicitly choose them, and label that option "backtest — no edge found".
>
> Tests for the baseline simulation. Verify in the browser. Summarise in under 15 lines.

**Your check:** is your paper-trading result inside or outside the luck band? Write that down in PROGRESS.md.

---

## A8 — Morning report: the forward record
**Branch:** `feature/morning-report`

> ROADMAP step A8 — read the full spec there first. Build a daily morning report that creates a
> forward record of the engine's reads:
>
> 1. **Before writing code**, tell me: where will the scheduler run? It must fire at 08:00
>    Europe/Skopje every day, so it needs an always-on machine. Also check whether Twelve Data covers
>    gold (XAU/USD) and oil (WTI); if not, propose an alternative source. Wait for my answer on both.
> 2. Schedule a job at 08:00 Europe/Skopje, daylight-saving aware, plus a manual trigger.
> 3. Watchlist (configurable): a few crypto pairs, EUR/USD, gold, oil — on 30m, 1h, 4h, 1d.
>    Closed candles only.
> 4. Each run, in this order: (a) review — resolve every past read whose horizon has ended;
>    (b) read — run the engine on every symbol × timeframe and freeze each read; (c) optionally, one
>    multi-timeframe Claude synthesis per symbol. The review must never be an input to the new read.
> 5. Horizons in bars: 30m → 48, 1h → 24, 4h → 42, 1d → 21 (configurable).
> 6. SQLite `forward_reads`: timestamp, symbol, timeframe, last closed bar, price, situation tier,
>    categories aligned + direction, invalidation level, next level in the read's direction, nearest
>    level above/below, facts hash, and the engine's git commit.
> 7. Outcome rule, versioned and written down before the first run: for directional reads, first touch
>    using bar highs/lows — invalidation first = invalidated, next level first = followed through,
>    neither = expired, both in the same bar = ambiguous. For no-setup reads: correct if price stayed
>    between the nearest levels above and below for the horizon, otherwise missed move. Changing the rule
>    creates a new version; old reads keep theirs.
> 8. Never backfill missed mornings — record them as gaps. Running twice in a day must not duplicate.
>    Forex, gold and oil skip when there's no new closed candle.
> 9. A report page: review section first, then today's symbol × timeframe grid, then the per-symbol
>    synthesis; a running scoreboard per timeframe and tier with counts, beside a coin-flip baseline using
>    the same outcome rule with random direction.
>
> Tests: timezone including a DST change, outcome rule for every case including ambiguous, no-setup
> scoring, idempotency, gap recording, weekend handling. Verify the page in the browser. Summarise in
> under 15 lines.

**Your check:** trigger it manually once and read the report. Then leave it running — check back after
a week to see the first 4h reviews, and after a month for the first 1d reviews. Record the start date in
PROGRESS.md; that's day one of the forward record.

---

# Phase B — Measure the detectors, then the patterns

## B1 — Detector gold set (labelling mode)
**Branch:** `feature/gold-set`

> ROADMAP step B1. Build a labelling mode in the scrub view so I can mark what my eye sees:
> - At a chosen bar, I can mark patterns (type + key points) and S/R zones.
> - Detector overlays are hidden while labelling, so I don't anchor on them.
> - Save to a SQLite `gold_labels` table: symbol, timeframe, bar, labels, timestamp.
> - A simple list of what I've labelled so far, with counts by pattern type.
>
> Tests for saving and loading. Verify in the browser. Summarise in under 15 lines, then tell me exactly
> how to label a chart.

**Your work (a few hours, can be spread over days):** label about 30 charts to start — BTC, SOL, and
one forex pair, on daily, mixing trend and chop periods. Include the SOL channel case. Aim for 50+
eventually. Mark only what you genuinely see; "nothing here" is a valid label.

---

## B2 — Detector precision/recall + tuning
**Branch:** `feature/detector-eval`

> ROADMAP step B2. Create `scripts/eval_detectors.py`:
> - Compare detector outputs to my gold labels at the same bars, with ATR-scaled matching.
> - Report per detector per timeframe: precision (when it fires, is it right?) and recall (does it find
>   what I marked?), always with counts.
> - Hold out ~30% of labels. Tune only on the rest; report final numbers on the held-out set.
> - Tune the weakest detectors (start with channels, which appear to over-call on post-impulse ranges).
>   Show before/after on held-out labels.
> - Fill the reliability field from A5 with the measured precision.
>
> Summarise in under 15 lines, including the precision/recall table.

**Your check:** which detectors are trustworthy and which aren't? Record the table in PROGRESS.md —
it's one of the most important findings of the project.

---

## B3 — Feature 3: Empirical Pattern Encyclopedia
**Branch:** `feature/encyclopedia`

> ROADMAP step B3. Build the encyclopedia:
> - `scripts/build_encyclopedia.py` reusing the existing look-ahead-safe backtest walk (no second walker).
> - Per pattern type × timeframe × symbol × regime: occurrences, confirmation rate, follow-through rate,
>   median/IQR move in ATR units, failure rate, bars to resolution, and the same split by confirmation
>   category.
> - SQLite `encyclopedia_stats`, sample_size on every row; n<20 flagged insufficient_data and never shown
>   as a percentage.
> - `/encyclopedia` pages: my numbers beside the textbook claim from docs/patterns-research.md, plus each
>   detector's measured precision from B2, plus example charts that open in the scrub view at the right bar.
>
> Tests included. Verify the pages in the browser. Summarise in under 15 lines.

**Your check:** open three pattern pages. Where does your data disagree with the textbook? Record that.

---

## B4 — Data adjacency
**Branch:** `feature/data-adjacency`

> ROADMAP step B4. Put measured records next to anything directional:
> - Beside the verdict: how that verdict type actually resolved historically, e.g. "categories aligned
>   bullish, 2 of 5 — 212 of 430 resolved that way", or "insufficient data".
> - Beside any measured target: how often that pattern type reached its target.
> - Rendered by the UI from Layer 1 data — not written by Claude.
> - Update the analyst guide: any directional read references its record.
>
> Tests included. Verify in the browser. Summarise in under 15 lines.

**Your check:** every directional verdict and target now has a count beside it. Does seeing them change
how much you trust the verdict?

---

## B5 — Calibrate quality + re-rank the guide
**Branch:** `feature/calibration`

> ROADMAP step B5.
> 1. Map raw pattern quality scores to observed follow-through per pattern type, using the encyclopedia.
>    Display quality as a calibrated band (low / medium / high) with counts, not a raw 0.62.
> 2. Re-order the analyst guide's §3 priority list using measured detector precision (B2) and encyclopedia
>    results — the least reliable detectors move down. Show me a table justifying the new order.
>
> Tests included. Summarise in under 15 lines.

**Your check:** the justification table goes into PROGRESS.md.

---

# Phase C — Integrity, enforced

## C1 — Feature 7 rebuilt: the integrity guard
**Branch:** `feature/integrity-guard`

> ROADMAP step C1. Replace the advisory number-checker with real enforcement:
> - `explain()` returns structured claims: {text, fact_id, role, direction}, with roles read / why /
>   invalidation / watch / opposing / conditional. Render the prose from the claims.
> - Mechanical checks: fact_id exists; role fits the fact type (a neckline can't be "support"); direction
>   matches the Layer 1 vote; no state upgrades (forming → confirmed); numbers match within the stated
>   rounding rule; opposing slot present when supplied; tier respected; word budget in brief mode.
> - Directional-language check: suggests / favours / likely / path of least resistance flagged unless tied
>   to a claim with a matching vote.
> - Hard failures: one retry with the violation list; if it still fails, show a deterministic facts-only
>   fallback with a notice. Soft issues: a warning badge.
> - This replaces the guide's §11 self-check as the real enforcement.
>
> Tests: one deliberately corrupted output per check, each caught. Teaching mode checked too (minus word
> budget). Verify in the browser. Summarise in under 15 lines.

**Your check:** run ten analyses across symbols and modes. How many passed first time, retried, or fell
back? Record the counts — they measure how often Claude drifts from the facts.

---

# Phase D — The learning loop

## D1 — Feature 4: Prediction journal + calibration
**Branch:** `feature/journal`

> ROADMAP step D1. Build the prediction journal:
> - Before the explanation is revealed, I log: direction, confidence 0–100, invalidation price, horizon
>   (default in weeks — I trade multi-week trends), and a note. SQLite `journal_entries`.
> - An option to hide the verdict badge until I've logged, so I don't anchor on it.
> - Integrate with the A8 morning report: let me log my read for a symbol there before its engine read
>   is revealed, so my record and the engine's forward record build side by side.
> - `src/journal/resolve.py` resolves entries when the horizon elapses: correct / incorrect / invalidated.
> - `src/journal/calibration.py`: Brier score, 10%-bin calibration curve, per-pattern and per-regime
>   breakdowns, overconfidence delta.
> - A stats page. Plain numbers, no streaks, no gamification.
>
> Tests for resolution and calibration maths. Verify in the browser. Summarise in under 15 lines.

**Your check:** log your first few real reads, with the verdict hidden. Then just keep logging —
this feature pays off over months, not days.

---

## D2 — Feature 11: Pre-registration
**Branch:** `feature/prereg`

> ROADMAP step D2. Build pre-registration:
> - `src/research/prereg.py` and an append-only SQLite `experiments` table.
> - Before any backtest: hypothesis, exact parameters, success metric and threshold, predicted result —
>   timestamped and hashed. The result is stored linked to its registration.
> - Count variations tested per question and apply a multiple-comparison correction.
> - A dashboard of every experiment including failures, with my hit rate at predicting my own results.
> - Registrations can't be deleted — supersede, don't edit. A backtest can't run unregistered.
>
> Tests included. Summarise in under 15 lines.

**Your check:** try running a backtest without registering — it should refuse.

---

## D3 — Feature 13a: News & macro context
**Branch:** `feature/news-context`

> ROADMAP step D3. Build the context panel:
> - Extend the calendar with consensus / previous / actual; add a headline source (headline + link only,
>   no article bodies); central-bank and commodity calendars.
> - `src/context/drivers.py` mapping each instrument to its macro drivers.
> - Surface: a high-impact event warning within a configurable window; a driver attribution for the
>   current trend, narrated as a hypothesis; a rolling correlation matrix of my followed instruments that
>   warns when they're effectively one macro bet.
> - Add the context rules to the analyst guide (context describes conditions, never direction).
>
> Tests with injected HTTP. Verify in the browser. Summarise in under 15 lines.

**Your check:** follow BTC plus one forex pair — does the correlation warning show when they move together?

---

## D4 — Feature 13b: Event study
**Branch:** `feature/event-study`

> ROADMAP step D4. Build the event study:
> - SQLite `events` table seeded from calendar history plus major geopolitical events.
> - `src/research/event_study.py`: forward-return distributions per event type × instrument at 1-bar,
>   1-day, 1-week, 1-month and 3-month horizons — median, IQR, direction consistency, persistence —
>   sample size on every row.
> - Condition on surprise vs consensus and on regime.
> - Reuse the look-ahead-safe backtest walk; route every study through pre-registration (D2).
> - A page per event type with an honest consistent / inconsistent / insufficient-data verdict and
>   links into the scrub view.
>
> Tests included. Verify in the browser. Summarise in under 15 lines.

**Your check:** before looking, pre-register what you expect for Fed rate decisions. Then look. Record both.

---

## D5 — Feature 12: Behavioural circuit breaker
**Branch:** `feature/circuit-breaker`

> ROADMAP step D5. Extend the journal with declared rules:
> - `src/journal/rules.py`: a versioned rule set (max risk per trade, max open positions, required regime,
>   minimum categories aligned, allowed instruments, max trades per week, post-loss cooling-off).
> - Check every logged trade; record violations, never block.
> - Compare outcomes of rule-following vs rule-breaking trades, with sample sizes.
> - Tilt detection as after-the-fact observations: post-loss clusters, oversized positions, off-regime
>   trades, frequency spikes.
> - A weekly review page. Neutral tone, no scolding.
>
> Tests included. Verify in the browser. Summarise in under 15 lines.

**Your check:** declare your rules honestly, then leave it running alongside the journal.

---

## D6 — Feature 5: Blind training mode
**Branch:** `feature/blind-mode`

> ROADMAP step D6. Build blind training:
> - Pick a random historical bar where a pattern reached confirmed (filter by type and regime).
> - Render the scrub view with everything after that bar hidden.
> - Take my call through the journal flow.
> - Reveal: what happened next, what the engine said at that moment, and the encyclopedia stats for that
>   pattern.
> - Sessions of N setups, with a calibration summary at the end; every attempt logs to the journal.
>
> Tests included. Verify in the browser. Summarise in under 15 lines.

**Your check:** run a 10-setup session. Compare your blind calibration with your live-journal calibration.

---

*When D6 is merged, the roadmap is complete. Update ROADMAP.md with a final status, and decide from
your journal and calibration data what — if anything — comes next.*
