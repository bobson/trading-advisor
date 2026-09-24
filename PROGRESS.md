# PROGRESS

A state file for the "learning instrument" build. Source of truth for what's next: `ROADMAP.md`
(steps A1…D6; prompts in `PROMPTS.md`). Older plans are in `docs/archive/`. See `CLAUDE.md` for conventions.

**ROADMAP progress:** A1 ✓ (merged, `645231c`), A2 ✓ (merged, `800e12a`; docs `1003735`), A3 ✓ (merged), A4 ✓ (merged), A5 ✓ (merged), A6 ✓ (merged), A7 ✓ (merged), B1 ✓ (merged — labelling mode
built; the ≥30 labelled charts are the user's ongoing work). **Next: A8** (morning report — the forward
record), with gold-set labelling continuing alongside.

## Current state

**Direction:** honest learning instrument, not a signal generator — the backtest and the ML harness
found no predictive edge. `ROADMAP.md` is the plan (Phase A hardening → B measure detectors →
C integrity → D learning loop); the old Tier-1 feature numbering lives on inside it.

**Built and on `main`:** the core engine + FastAPI + Svelte app (original Phases 0–26); the ML "is
there an edge?" harness (no edge); Features 1 (pattern viz + research view), 2 (pattern confirmation
states), 6 (market regime), 8 (exit-rule lab), 9 (risk of ruin), 10 (honest cost model); the
hardening pass (guide wired in, brief/teaching modes); paper trading; three-candle patterns; and
**ROADMAP A1** (verification pass: chart label/regime fixes, reclaimed-neckline → `failed`,
two-point trendlines). **ROADMAP A2** (verdict as a category count, neutral styling, no-edge
disclosure; `800e12a`). **ROADMAP A3** (situation tier decided in Layer 1) and **ROADMAP A4** (support/resistance as
ATR-scaled zones) and **ROADMAP A5** (facts payload hardening) and **ROADMAP A6** (analyst guide revision +
instrument price precision) and **ROADMAP A7** (honest baselines: luck band + zero-edge calculator
default) and **ROADMAP B1** (gold-set labelling mode — `gold_labels` table), plus the user-requested
**1–2 candle patterns at levels** chart markers. **392 tests green, ruff + svelte-check clean.**

**Standing facts:** patterns and 3-candle candlesticks stay OUT of the confidence score (facts
only); regime is standalone (not a vote); two-point trendlines are chart-only (not in facts); the
0–1 confluence `confidence` is internal — the UI shows "N of M categories agree", never a %. The
situation tier (`facts["situation"]`: no_setup / notable / confirmed, + mtf_synthesis for the
synthesis) is Layer 1's decision; it sets the explanation's format and word budget, and Claude may
not change it. Support/resistance are ZONES (bands with touches, strength, stale flag) built by one
shared `sr_zones()`; "at support" = inside the band or within 0.25×ATR of its edge. The facts
carry pre-computed distances (ATR + %, + above / − below) to every level, the nearest structural
level above/below, pattern ages, per-signal higher-timeframe votes (`mtf.facts_from`, incl. 1w —
information only), the strongest opposing fact, an unmeasured reliability field and an explicit
`absences` list; the prompt follows the guide's §3 order.

**Known open items:** channel detector over-calls (SOL 1d eye-check FAIL → B1/B2); phone-width
right-axis price-label pile-up; the disclosure panel's evidence numbers are hard-coded from past
runs (update by hand if re-run).

**Explanation layer:** driven by `src/advisor/analyst-guide-system-prompt.md` (loaded at startup,
cached prompt prefix). Default mode `brief` (enforces the guide's §8 word budgets); `teaching`
for long-form; toggle in the UI.

**Default config:** symbol `BTC/USDT`, timeframe `1h`, exchange `binance`, history 4320 bars.
Selectable timeframes: `15m, 30m, 1h, 4h, 1d`. Registered pairs: BTC/ETH/SOL/XRP (USDT) +
EUR/USD, GBP/USD (forex via Twelve Data). New in A1: `patterns.reclaim_atr_mult` (0.25),
`structure.trendline_break_atr_mult` (0.25), `structure.trendline_max_anchors` (6). New in A4:
`structure.sr_zone_atr_mult` (0.5), `sr_near_atr_mult` (0.25), `sr_stale_bars` (120),
`sr_strength_halflife_bars` (60). New in A5: `mtf.facts_from` ([4h, 1d, 1w]) — per-signal
higher-timeframe votes shown to Claude; the veto still uses `mtf.context_from` ([4h, 1d]). Defaults
apply if `config.yaml` omits them.

---

## Log (newest first)

### 1–2 candle patterns at levels — chart markers (user request, facts-only)
- **Done:** 2026-09-24 · built on `main`'s working tree (user to branch/commit) · **merged to `main`.**
- **Why:** only the 3-candle patterns were drawn; doji/hammer/shooting star/engulfing were detected
  (and the last one votes) but never shown — ~190 per 500 candles would bury the chart.
- **What's drawn now (browser-verified on BTC 1d and XRP 1d):**
  - by default, a directional 1–2 candle pattern whose **wick tagged a level that favours it, as of
    that candle**: `H@sup`, `BeE@res`, `BuE@fib61.8`, `SS@TL` — bullish needs the nearest non-stale
    support zone below the previous close, a key Fibonacci level (38.2–78.6%) of an up-leg, or an
    unbroken support trendline; bearish the mirror. ~45–65 per 500 candles (BTC/SOL/EUR/USD 1d, BTC 1h).
  - always, the **last closed candle's** 1–2 candle pattern — the one the candlestick vote reads — as
    `CODE (last)`.
  - a study toggle **"1–2 candle patterns (all)"** (off by default) adds every other one, faded.
  - the legend explains the codes and the `@` tags.
- **Build:** `src/patterns/candle_context.py` — `candle_events()` (vectorised pattern lookup, vote
  precedence engulfing > hammer/shooting star > doji), `level_for()` (levels rebuilt as they existed at
  that bar: swings filtered to bars ≤ i − sensitivity — verified equal to recomputing on df[:i+1] up to
  the tie order of outside bars — then zones / Fibonacci / two-point trendlines on that history). An
  in-process cache per (market, bar, direction) makes repeat views and scrubbing cheap (first view of
  a market ~1.6 s, then ~0.04 s); level context covers the last 500 candles. `serialize.py` adds
  `overlays.candles_12 = {all, at_level, last}`. `find_sr_zones` clustering made linear-time (running
  sum; snapshot unchanged). 10 new tests incl. look-ahead guards.
- **How the rule was chosen (measured, not tuned to a count):** every historical zone + a 0.25×ATR "near"
  margin → 85–99% of patterns "at a level" (meaningless); nearest non-stale zone only → 64–86%; wick
  must actually TAG the level → ~50%; doji excluded (no direction for a level to favour) → final.
- **Not changed:** the candlestick VOTE (still any 1–2 candle pattern on the last bar); the facts sent
  to Claude (no "at a level" fact yet — a natural Layer-1 addition, would change the snapshot).
  Stale zones don't count as a level here (a pattern at a long-dormant zone isn't marked).

### ROADMAP B1 — Detector gold set: labelling mode
- **Done:** 2026-09-24 · **branch:** `feature/gold-set` · **merged to `main`.** Tooling done; the
  done-when's second half — **≥30 charts labelled — is the user's work and is still open (0 so far).**
- **Done-when (tooling) → PASS:** labelling mode works with the detector overlays hidden — checked in
  headless Chromium on BTC/USDT 1d at a scrubbed bar: verdict, pattern chips, facts panels, paper
  trade, S/R zones, Fibonacci, patterns, trendlines, swings, candle patterns, the verdict marker and
  the regime strip all hidden; a double top (3 wick-snapped points) + a support zone drawn, saved,
  reloaded when returning to the bar, and the detectors restored on exit. Tested against a SCRATCH
  DB (the real `data/wizard.db` untouched). 15 new tests, **382 green**.
- **Build:** `gold_labels` table (symbol, timeframe, bar, bar_time, labels JSON, created/updated;
  UNIQUE per bar → re-saving updates). `src/labels/gold.py`: `validate` (known type, ≥2 points,
  lower<upper, role; "nothing here" is a real label and can't coexist with patterns), `save` (upsert),
  `load`, `list_all`, `delete`, `summary` (charts, patterns by type, zones, "nothing here",
  per market). Vocabulary = the detector's own type names + a few it doesn't detect yet (wedges,
  flags, other) so recall can be measured on them. API: `GET /labels/types`, `GET /labels`,
  `GET /labels/one`, `PUT /labels`, `DELETE /labels/{id}`. UI: "🏷 Label this bar" in the scrub row →
  `LabelPanel.svelte` (pattern type + clicks on key points with snap-to-wick, "Add pattern"; S/R zone =
  two clicks + role; "nothing here"; note; save/update; the gold-set list with counts by type, and
  click a row to jump to that chart/bar). `PriceChart` label mode draws your labels in purple, keeps
  zoom/scroll across clicks, and ignores clicks after the labelling bar. Labelling never calls Claude.
- **Bugs found and fixed on the way:** (1) **CORS allowed only GET** since Phase 24 — every browser
  write (paper Buy/Sell/undo, label save) failed its preflight ("Failed to fetch"); now GET/POST/PUT/
  DELETE, origins still restricted (test added). (2) **Scrub race:** a request made while one was
  loading was silently dropped, so the chart could show an older bar than the slider — a label would
  have been saved to the wrong bar. Requests now queue; the API returns `bar_index` (the bar actually
  computed) and labels key to that (test added). (3) While scrubbed back, paper trades from the future
  were snapped onto the last candle; they're now skipped, and hidden entirely while labelling.
- **Deviations from ROADMAP.md:** none in substance. Labels are keyed by bar index AND bar_time, so
  B2 can match either way.

### ROADMAP A7 — Honest baselines
- **Done:** 2026-09-24 · **branch:** `feature/honest-baselines` · **merged to `main`.**
- **Done-when → PASS:** baseline band visible beside the paper P&L; calculator defaults to the
  cost-adjusted coin flip, backtest only on an explicit click labelled "Backtest — no edge found";
  checked in headless Chromium at 1400px + 400px (against a SCRATCH trades DB with 5 seeded closed
  BTC trades — the real `data/wizard.db` was never touched). 13 new tests, **367 green**.
- **Paper-trading luck band:** `src/trading/baseline.py` — `random_entry_baseline()` (pure, seeded)
  replays your k closed trades as many "monkey" records: random historical bar, random side, SAME
  holding time (in bars of the trades' timeframe) and SAME size; reports the 5th/50th/95th percentile
  of total P&L and wins, your percentile, and `inside_luck_band`. `GET /trades/baseline` (1000 runs).
  UI: range + median + a bar with your marker + a verdict ("inside the luck band — this record can't
  tell skill from luck, especially with only 5 trades"). No costs on either side (like-for-like with
  paper P&L). Refreshes after a close / undo.
- **Calculator default:** `src/risk/coin_flip.py` + `GET /risk/coin_flip` — round-trip cost from the
  Feature-10 cost model (spread, fees, ATR slippage, funding/financing over a 24-bar hold), in units
  of the risk (entry→stop), then **p = (1 − c)/(1 + R)**: the zero-edge win rate at your payoff, net of
  costs (expectancy exactly −c). Win-rate source buttons: "Coin flip, cost-adjusted (default)" /
  "Backtest — no edge found"; typing your own number is labelled as such. BTC 1h at 1.5:1 → 37.8%
  (ruin 99.7%, Kelly "don't bet").
- **Deviation / correction:** "coin flip" taken literally as 50% is only zero-edge at a 1:1 payoff.
  My first version used 0.5 − c/(1+R), which at 1.5:1 showed 47.8% — a hidden +0.2R edge that made
  ruin read 0.0% in green (caught in the browser). Replaced with the zero-edge rate 1/(1+R) net of
  costs; a test pins "expectancy = −cost at every payoff".
- **Findings:** crypto funding dominates daily holds (24-bar hold on 1d = 24 days of funding → BTC 1d
  cost ~1.1% round trip vs ~0.22% on 1h). Paper trades held minutes are rounded up to 1 bar of their
  timeframe in the luck band (overstates the monkeys' holding time for very short trades).

### ROADMAP A6 — Analyst guide revision (+ forex price-precision fix)
- **Done:** 2026-09-24 · **branch:** `feature/guide-revision` · **merged to `main`.**
- **Done-when → PASS (with findings):** guide updated; prompt tests pass (+2 new guide-rule tests;
  **354 green**); brief + teaching spot-checked on BTC 1d, SOL 1d, EUR/USD 1d — verifier OK on all
  six. Brief mode: within budget, `Opposing:` line present when supplied, conditionals two-sided,
  no directional wording against the Layer 1 bias. Teaching mode still drifts (see findings).
- **Guide changes:** §1.1 one rounding rule (prices exactly as given; other numbers ≥3 significant
  figures; no "≈"; inside the verifier's 1% tolerance). §1.4 "what it conventionally suggests"
  removed; suggests/favours/leans/path of least resistance/buyers-sellers in control are directional
  claims, allowed only in the direction of the Layer 1 bias or when attributing a detector's own vote.
  §2 conditional reads symmetric (nearest level above AND below, no "so"; "worth revisiting" gone).
  §4 "conventionally read as" labels a convention, doesn't license direction; "many false breaks"
  removed. §5 extremes = crowded positioning with no implied direction; "historically coincided with
  turning points" and the contrarian readings removed. §7 cut to one allowed observation (higher-TF
  trend vs a pattern's implied direction). §8 tier supplied/never escalated, `Opposing:` line always
  when supplied and outside the budget, teaching lifts only the word cap; examples rewritten. §8/§10
  one fact-naming style: "RSI 28 (oversold)". §11 self-check kept, noting C1 will enforce it.
- **Code alongside:** brief `max_tokens` gets +60 for the uncounted Opposing line; the teaching note
  restates that tier/format/Opposing still apply. Layer 1's own prompt text aligned with §5 (Fear &
  Greed and funding extremes → "crowded positioning, no implied direction"); two tests that pinned
  the old "contrarian" wording updated.
- **Deviation / scope added:** the forex spot-check exposed a Layer 1 bug — facts AND the pattern
  detectors rounded every price to 2 decimals. EUR/USD zones read "1.15–1.15", ATR became 0.0 (so ATR
  distances vanished), and pattern breakout levels moved ~50 pips BEFORE the state machine compared
  closes to them (wrong forex states). Fixed with `src/market/precision.py` (`price_decimals`: 2 at
  ≥100, 5 at ≥1, 6 below — the chart's existing rule; `round_price`, `fmt_price`) used by facts,
  detectors, `Pattern.to_dict`, zone/fib vote reasons and level labels. Crypto ≥100 is unchanged →
  BTC snapshot byte-identical. Regression test added. My first rounding rule ("3 significant figures
  for everything") also collapsed forex prices and was replaced by "prices exactly as given".
- **Findings:** teaching mode keeps adding things the guide now forbids: uncounted historical claims
  ("follow-through historically requires more confirmation", "often appears at a turning point"),
  invented mechanics ("a stale zone has fewer participants", "the measured target is the minimum
  move"), causal guesses ("which may explain the failure"), extra own observations (the ADX-vs-
  sideways tension, in all three teaching runs), and bold headings. Prompt rules alone don't stop
  it — C1's claim-level checks must. Candidate Layer 1 fact: label "ADX trending but swing structure
  sideways" explicitly so the model stops explaining it. Round-number step for FX is still 0.1
  (nearest 1.1 for 1.1467 — the Phase-18 "FX may want finer steps" note stands). Claude's prompt
  still carries "confidence NN%" (not removed here).

### ROADMAP A5 — Facts payload hardening
- **Done:** 2026-09-24 · **branch:** `feature/facts-hardening` · **merged to `main`.**
- **Done-when → PASS:** every field present (test per field); absences explicit in both the facts
  dict (`absences`) and the prompt ("NOT PRESENT…", "RSI divergence: none detected", "not fetched",
  "not available"); distances present on every level (tests); snapshot regenerated after the user
  reviewed the diff. 18 new tests, **351 green**, ruff + svelte-check clean. No UI change → no
  browser check needed.
- **Build:** new `src/advisor/facts_detail.py` (pure helpers) + `facts._harden()`:
  - **Distances** `{distance_atr, distance_pct}`, signed (+ above / − below): S/R zones (to the nearer
    edge, 0 inside), each key Fibonacci level, the round number, each pattern's breakout /
    invalidation / target, and the 50/200 SMAs (new `moving_averages` block).
  - **`nearest_levels.above/below`**: nearest structural level (zone edges, key Fibonacci, round
    numbers either side, pattern breakout/invalidation) with its source. MAs excluded (dynamic).
  - **Pattern ages**: `bars_since_completion` and `bars_since_state_change` (None while forming).
    `classify_state_history` now also returns where the state began; memoryless (continuation)
    patterns use the start of the current same-state run.
  - **`detector_reliability`**: every detector + pattern type `{precision: None, n: 0, status:
    unmeasured}` until B2.
  - **`mtf_signals`**: each detector's vote on the base TF and each higher TF in `mtf.facts_from`,
    resampled from the base candles, dormant below `slow_ma` bars. Base votes are reused, not recomputed.
  - **`strongest_opposing_fact`**: the opposing category with the highest configured weight, its
    detector and reason; None when nothing opposes or the read is neutral (stated either way).
  - **`absences`**: divergence, confirmed/failed/any pattern, candlestick, support/resistance zone,
    Fibonacci leg, volume, higher timeframe, opposing category, nearest level above/below.
  - **Prompt** rewritten in §3 order: 1 trend & regime (+ MAs, ADX, HTF, per-signal TF votes) →
    2 structure (nearest levels, zones, Fibonacci, round number) → 3 patterns (+ candlestick) →
    4 momentum → 5 volatility → 6 volume → 7 context/derivatives → verdict, opposing fact, track
    record, per-detector votes, reliability, NOT PRESENT. Old labels kept inside the sections.
- **Snapshot diff (approved):** purely additive (179 lines added, no existing value changed; tier
  still notable) — the new keys above plus distance fields.
- **Deviations from ROADMAP.md:** (1) the roadmap's "1d / 1w" example needed a weekly timeframe
  that wasn't configured; with the user's OK, `mtf.facts_from` [4h, 1d, 1w] was added for the
  per-signal votes ONLY — the veto (`context_from` [4h, 1d]) is unchanged, since adding 1w there
  would change daily/4h verdicts and needs a daily backtest first. 1w weeks run Mon–Sun (`W-SUN`).
  (2) Opposing fact is category-based as specified; an opposing CONFIRMED PATTERN (e.g. SOL 1d's
  bullish double bottom vs a bearish read, before A4) is not yet surfaced as the opposing fact.
- **Prompt wording fixes (after reading the real BTC 1d facts):** the verdict count now reads
  "1 of 4 voting categories agree; 2 needed to align" (was "1 of 2", i.e. agreeing-of-required);
  the veto line is labelled "Higher-timeframe veto check" and, when none applies, says so and points
  to the per-timeframe votes (it used to say "no higher timeframe available" right above the 1w
  votes); "1 bar ago" singular. Wording only — snapshot unchanged.
- **Findings:** on 1h, 1w stays dormant (~26 weeks of history < 50); on daily and 4h it is active
  (e.g. BTC 1d: trend 1d neutral / 1w bearish). The prompt still shows the internal "confidence NN%"
  to Claude — A2 removed it from the UI only; A6/C1 should decide whether Claude may see it.

### ROADMAP A4 — Support/resistance as zones + level freshness
- **Done:** 2026-09-23 · **branch:** `feature/sr-zones` · **merged to `main`.**
- **Done-when → PASS:** zones render as shaded bands in the browser (headless Chromium: BTC 1d,
  SOL 1d zoomed); stale zones are marked (fainter band + "stale" axis tag + in facts/prompt);
  snapshot regenerated after the user reviewed and approved the diff; tests for width scaling and
  staleness (13 new; **333 green**, ruff + svelte-check clean).
- **Build:** `support_resistance.py` — `find_sr_zones()` clusters swings within `sr_zone_atr_mult`
  (0.5) × ATR of the running centroid; band = centred on the touches' mean, ≥ 0.5×ATR wide, always
  covering every touch; `touches` / `first_touch` / `last_touch` / `bars_since_touch` (touch =
  a swing REVERSAL in the zone); `strength` = Σ 0.5^(age/60 bars); `stale` = no reversal for 120
  bars. `sr_zones(featured, swings, cfg)` is the ONE builder used by facts, confluence, the service
  and the chart; `zone_distance()` = 0 inside the band. `price` stays the band centre, so every old
  consumer (roles, chart-pattern structure hits, PNG chart) still works.
- **Vote:** `signal_from_support_resistance(zones, close, atr, near_atr_mult)` — at a zone = inside
  or within 0.25×ATR of its edge (was: within 0.5% of a single line). Role from the centre vs price.
  Facts `nearest_support/resistance` now carry lower/upper/touches/bars_since_touch/strength/stale/
  inside; the prompt renders them as bands ("last reversal N bars ago", STALE flag).
- **Chart:** a lightweight-charts series primitive (`ZoneBands`) fills each band under the candles;
  an axis tag at the centre (no line). Fibonacci and round numbers stay exact lines.
- **Backtest (vote-path change, BTC/USDT 1h, h=24, step=4):** **51.6% of 438 → 50.5% of 440** —
  within noise, slightly worse; NOT tuned. Still no edge.
- **Snapshot diff (approved):** the old 7-touch line at 64,166 (0.5% clustering ≈ 1.4×ATR on 1h) split
  under 0.5×ATR clustering; price is now INSIDE a 2-touch support zone 63,829–63,944 → S/R vote
  bearish→bullish → structure nets neutral → 1 agreeing category, not triggered → tier confirmed→notable.
- **Deviations from ROADMAP.md:** clustering itself also moved from a fixed 0.5% to ATR (the roadmap
  asked only for ATR-scaled *width*, but the conventions ban fixed-% thresholds and %-clusters with
  ATR-wide bands would overlap). `sr_cluster_tolerance_pct` is now used only by chart-pattern
  structure hits and the old `find_support_resistance` (kept for `show_structure.py`/tests).
- **Findings:** ATR clustering is TIGHTER than 0.5% on 1h and WIDER on daily — zones fragment on
  intraday charts. "Touch" = reversal, so a zone price is trading in right now can still be stale
  (SOL 1d: inside a zone last reversed ~270 bars ago). Not changed here: the Fibonacci vote still uses
  the percent `proximity_pct`; the PNG chart (`viz/chart.py`) still draws centre lines.

### ROADMAP A3 — Situation tier in Layer 1
- **Done:** 2026-09-23 · **branch:** `feature/situation-tier` · **merged to `main`.**
- **Done-when → PASS:** identical facts always give the same tier (test); each §2 criterion has its
  own isolated test; a forming-only chart can't be `confirmed` (test); the tier shows in the UI —
  checked in headless Chromium at 1400px and 400px (SOL 1d notable, BTC 1h notable, ETH 1h no clear
  setup). 26 new tests, **326 green**, ruff + svelte-check clean.
- **Build:** `src/signals/situation.py` — `classify_situation(facts, cfg)`, a pure function of the
  facts dict, called at the end of `build_facts` → `facts["situation"] = {tier, reasons,
  word_budget, template}`. `confirmed` = a confirmed pattern matching a triggered bias whose
  confirmation profile shows §4's shape (price supports, volume OR volatility supports, momentum and
  higher TF not contradicting). `no_setup` = any §2 criterion, each a reason code
  (`no_pattern_no_confluence`, `away_from_levels`, `conflicting_signals`, `neutral_indicators`,
  `single_weak_signal`). Precedence confirmed > no_setup > notable. Failed patterns count toward
  notable; forming patterns are ignored entirely.
- **Explanation bound by the tier:** `facts_to_prompt` leads with `SITUATION TIER`; `explain` /
  `explain_structured` take `situation=` and the mode note names ONLY that tier's template and
  budget; brief `max_tokens` = budget×3+60 (structural cap). Teaching keeps the tier, lifts only the
  word cap. `synthesize` is always `mtf_synthesis` (150). Guide §8 gained one line: use the supplied
  tier, never change it (small pull-forward from A6).
- **UI:** "Situation: notable (categories aligned; confirmed double bottom; price is at a level)"
  under the verdict, neutral styling.
- **Snapshot:** regenerated — diff is ONE added key, `situation` (fixture reads `confirmed` via its
  double top); nothing else moved. Reviewed and approved by the user with the commit.
- **Deviations from ROADMAP.md:** the premise "a forming SOL channel produced a flagged setup" doesn't
  match the code — chart patterns were never confluence voters. A day-by-day SOL 1d replay showed
  every flag came from MACD / S/R / volume. So SOL still shows "categories aligned" (2 of 4 really
  agree); the change is that its tier is `notable`, not `confirmed` (its confirmed double bottom is
  bullish vs a bearish bias). A test pins that injecting a forming pattern leaves confluence and the
  tier unchanged.
- **Findings / limitations:** §2's "away from levels" taken literally demotes a mid-range
  trend+momentum agreement to no_setup (deliberate — documented in the module). A stale confirmed
  pattern still counts as confirmed until A5 adds bars-since-confirmation. An MTF veto can leave
  "2 of 4 agree" without the "categories aligned" badge (BTC 1h) — the UI doesn't yet say why.

### ROADMAP A2 — Verdict reframe + no-edge disclosure
- **Done:** 2026-09-23 · **branch:** `feature/verdict-reframe` · frontend + one guide sentence.
  **Merged to `main`: `800e12a`** (code) + `1003735` (PROGRESS/ROADMAP updates).
- **Done-when → PASS:** no percentage labelled "confidence" anywhere in the UI, no green/red verdict
  styling, disclosure visible — checked in headless Chromium at 1400px and 400px.
- **Verdict:** "confidence NN%" → a count ("2 of 4 categories agree · 1 opposes · 1 neutral";
  denominator = categories that voted). "SETUP FLAGGED" → "categories aligned". Green/red border and
  badge removed; the chart's verdict arrow is now neutral grey. The 0–1 `confidence` stays in the
  API/facts, never displayed.
- **Other "confidence" displays found:** the paper-trade log showed "NN% conf" per read → replaced
  with "N categories agreed", bias no longer colour-coded. None left in `web/src`.
- **Disclosure:** persistent line under the title on every view — "Tested: no predictive edge. This
  tool is for reading charts, not forecasting them." — expands to a plain-language evidence panel
  (backtest 51.3% of 429, cross-coin 40–61% unstable, ML AUC 0.51 / broken calibration, funding no edge).
  The numbers are hard-coded from the documented runs; update them if the tests are re-run.
- **Guide:** removed "If asked whether it works, say so plainly." (rule 6 keeps "do not imply
  predictive power").
- **Verified in the browser** (desktop + 400px): no percentage labelled confidence, neutral verdict,
  disclosure visible on Analysis and Risk views. 300 green, svelte-check clean.
- **Kept on purpose:** the track-record line ("right NN% of the time") — a base rate shown with its
  count, not a confidence. P&L green/red and per-category vote colours (facts, not the verdict).
- **Deviations from ROADMAP.md:** (1) the count's denominator is the categories that actually voted
  (4 today: trend/momentum/structure/volume — volatility has no voter), so it reads "of 4", not the
  roadmap's "of 5" example; showing a category that can't vote would understate agreement.
  (2) The "link to the evidence" is an expandable panel under the disclosure, not a separate page —
  one click, no routing, visible on every view. (3) Went slightly wider than asked: the chart's
  verdict arrow and the paper-trade log's bias are also neutral now (same verdict, same leak).
- **Findings:** the verdict now also shows how many categories OPPOSE — the old % hid disagreement.
  The evidence figures are historical (backtest 51.3% is the Phase-17 run); no test re-run in A2.

### ROADMAP A1 — Human verification pass (+ rendering fixes, reclaim rule, 2-point trendlines)
- **Done:** 2026-09-23 · **branch:** `feature/a1-verification-fixes` · **merged to `main`: `645231c`**
  (the `fix/verification-pass` branch holds no A1 commits).
- **Done-when → PASS:** boundaries and labels render correctly in the browser (headless Chromium,
  1400px + 400px), and each eye-check is recorded pass/fail below.
- **Rendering fixes (browser-verified, desktop + 400px phone):** pattern boundary lines were already
  drawn since `32da1e5` (the review predated it) — confirmed on SOL 1d. The garbled top-left labels
  were the full-name 3-candle marker texts from `ea0294c` overlapping/clipping → markers now use
  short codes (MS/ES/3WS/3BC) with a legend row. Regime strip rebuilt: solid 22px band, no axis/logo,
  legend row with the latest regime, switches to the hovered bar's regime.
- **Reclaim rule (Layer 1):** reversal patterns (double top/bottom, H&S) now keep state history
  (`classify_state_history`): a neckline break later reclaimed by ≥ `patterns.reclaim_atr_mult`
  (0.25) × that bar's ATR reads `failed` instead of reverting to `forming`. Continuation patterns
  (sloped rails) still use the last close only. Snapshot unchanged.
- **Two-point trendlines (user request):** `find_two_point_trendlines` joins the latest swing
  low/high to an earlier one, kept only while no close crosses it by > `structure.
  trendline_break_atr_mult` (0.25) × ATR; longest valid line wins. Chart-only (teal support / pink
  resistance, `trendlines` toggle) — NOT in facts, so no explanation/snapshot change. SOL 1d: rising
  support Aug 16 → Sep 15, which the user confirmed is the line their eye draws.
- **Eye-checks (user, in the browser):**
  - **Regime labels on daily match remembered periods — PASS.** Trends read trending, chop reads
    ranging, no flicker.
  - **Old BTC 1d double top (neckline 76,264) reads `failed` — PASS.** Replay: forming → confirmed
    Sep 15–16 (closes < 76,264) → `failed` Sep 18 (close 80,884, reclaim beyond the 0.25×ATR margin).
  - **SOL 1d "ascending channel" looks like a channel — FAIL.** User: no channel. Only the lower
    rail is real (rising support Aug 16 → Sep 15, unbroken); the recent highs don't form a valid
    parallel upper rail (Aug 27 110.60 > Sep 6 107.36; Aug 9 → Sep 6 was broken Aug 27). The
    least-squares channel fit doesn't require its rails to be respected → over-calling. **Feeds B1/B2**
    as a labelled channel false positive; candidate fix: require both rails to pass the 2-point
    trendline "unbroken" test.
- **Tests:** +7 reclaim/state-history, +8 two-point trendlines. **300 green, ruff + svelte-check clean.**
- **Not done here:** phone-width right-axis label pile-up (many price-line labels cover the chart).
- **Deviations from ROADMAP.md:** (1) "pattern boundary lines not drawn" was already fixed in
  `32da1e5` — the design review predated it — so A1 verified it instead of rebuilding it. (2) The
  top-left garble had a different cause than the one fixed earlier: the full-name 3-candle markers
  from `ea0294c`. (3) PROMPTS.md expected the double top to be `failed` because price broke *above
  the neckline*; the rule fails it only on a close above the *peaks* (82,300) — or, since A1, on a
  reclaim of the neckline beyond 0.25×ATR. (4) Scope added at the user's request: the reclaim rule
  and two-point trendlines (both Layer 1, tested, snapshot unchanged).
- **Findings worth remembering:** pattern state was MEMORYLESS (last close only), so a confirmed break
  that price later reclaimed silently went back to `forming` — fixed for reversal patterns only;
  continuation patterns still work that way. The channel detector's least-squares rails don't have to
  be respected by price, which is why it over-calls. A running dev backend can be older than the
  code (the user's predated `ea0294c`), so a UI bug may not reproduce until the server restarts.

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
