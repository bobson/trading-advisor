# Feature 13 — Geopolitical context & event study

Two halves. The first gives you macro context for trends you're already riding. The second
**measures** what markets actually did after events, instead of assuming.

**Framing, before anything else:** this is not a prediction feature. You cannot beat the market
to public news, and even perfect foreknowledge of an event doesn't determine the price reaction
— Russia invaded Ukraine in February 2022, oil spiked toward $130, and by year-end it traded
below its pre-invasion level. Markets price expectations and react only to surprises relative
to them. The value here is (a) knowing when technical levels are about to become unreliable,
(b) understanding *why* a trend exists, which predicts its persistence better than its shape,
and (c) finding out empirically whether event reactions are consistent at all.

Same conventions: one branch per half, tests alongside code, SQLite at `data/wizard.db`,
walkthrough summaries under 15 lines.

---

## 13a — News & macro context panel

### Data sources
- **Economic calendar** — Finnhub (already integrated). Extend to: event name, country, impact
  rating, scheduled time, consensus forecast, previous value, and actual once released.
- **News headlines** — a finance/crypto news API with categories and timestamps. Store
  headline, source, timestamp, instruments/regions tagged, and URL. Do not store article bodies
  (licensing); headline + link only.
- **Central bank calendar** — scheduled policy meetings for the Fed, ECB, BoJ, BoE, plus any
  central bank relevant to a traded pair.
- **Commodity-specific** (for when you add oil/gold): OPEC+ meeting dates, EIA inventory release
  schedule.

### What it surfaces
- **Event risk warning** — the defensive one, and the most useful day to day. Flag high-impact
  events within a configurable window (default 24h) for any instrument's relevant regions.
  Message is a *warning*, not a direction: elevated volatility, technical levels less reliable,
  stops may gap. For a trend follower this informs whether to add to a position now or wait.
- **Driver attribution for the current trend** ★ *the part worth building*
  Given the active regime and trend direction (Feature 6), assemble the macro facts that plausibly
  explain it: real rate direction, dollar index trend, relevant policy stance, recent high-impact
  events in that instrument's drivers. Pass to Layer 2, which names the likely driver **and how
  durable that class of driver tends to be**.
  Why this matters more than a chart pattern: a trend driven by a structural policy shift has
  different persistence than one driven by a single headline. Persistence is the whole question
  for a trend rider.
- **Correlation / driver-exposure warning** ★ *original, genuinely useful*
  Compute rolling correlations between the instruments you follow, and flag when apparently
  separate positions are one macro bet. Long gold + short dollar + long BTC is a single bet on
  real rates and liquidity held three ways. This is the most valuable non-signal feature in the
  app for a multi-instrument trend follower — it converts hidden concentration into a visible number.

### Instrument → driver map (`src/context/drivers.py`)
Static reference, used to decide which events are relevant to which instrument:
- **Gold** — real rates, dollar, central bank buying, crisis/geopolitical demand, ETF flows.
  Supply is nearly irrelevant (almost all gold ever mined still exists).
- **Oil** — OPEC+ decisions, shale economics, spare capacity, inventories, global growth
  (China), geopolitical supply disruption. Supply-dominated; both sides price-inelastic short
  term, so small imbalances move price violently; storage constraints matter.
- **FX** — *relative* by construction: interest rate differentials and, more precisely, changes
  in rate *expectations*; relative growth; trade balances; safe-haven flows (JPY, CHF, USD);
  political risk. Commodity currencies partly track their commodity (CAD/oil, AUD/metals).
- **BTC** — liquidity and risk appetite (behaves as high-beta risk asset), real rates,
  ETF/institutional flows, halving supply schedule, regulation, derivatives leverage positioning.
  Weakest fundamental anchor of the four; more reflexive and narrative-driven.
- **Shared across all four** — dollar strength and real rates move all of them at once. This is
  what makes the correlation warning necessary.

### Layer 2 rules (add to the analyst guide)
- Context explains **conditions**, never direction. Never say an event will push price a way.
- Event warnings are about **reliability of the read**, not about a trade.
- Driver attribution is **hypothesis, not fact** — "consistent with", never "because of".
- Headlines: paraphrase, never reproduce more than a short fragment; always link the source.
- Stays inside the existing word budgets; context earns a sentence only when it changes the read.

### Done when
The report shows upcoming high-impact events for the instrument, a plausible driver attribution
for the current trend with a note on that driver's typical persistence, and a warning when your
followed instruments are highly correlated.

> **Prompt:** "On branch `feature/news-context`, implement Feature 13a of FEATURE-13-SPEC.md:
> extend the Finnhub calendar integration with consensus/previous/actual, add a news-headline
> source (headlines and links only, no article bodies), add central bank and commodity event
> calendars, and `src/context/drivers.py` mapping instruments to their macro drivers. Surface:
> a high-impact event warning within a configurable window; a driver attribution for the current
> trend built from regime plus macro facts and narrated by Layer 2 as a hypothesis; and a rolling
> correlation matrix across followed instruments that flags when positions are effectively one
> macro bet. Add the Layer 2 context rules to the analyst guide. Tests with injected HTTP.
> Summarise in under 15 lines."

---

## 13b — Event study module ★ the empirically interesting half

**The question:** do markets actually react consistently to event types? Most traders assume yes.
Almost nobody tests it. You have the machinery to.

### Build (`src/research/event_study.py`)
1. **Event database** (SQLite `events`): type, instrument/region, timestamp, magnitude where
   applicable (surprise vs consensus for data releases), source. Seed from the calendar history
   plus a curated list of major geopolitical events.
2. **Event study engine** — for each event type × instrument, compute the distribution of forward
   returns at multiple horizons (1 bar, 1 day, 1 week, 1 month, 3 months): median, IQR, direction
   consistency (% of occurrences moving the same way), and how long any reaction persisted before
   mean-reverting. **Sample size on every row, always.**
3. **Surprise conditioning** — for data releases, split by whether actual beat, met, or missed
   consensus. This is the real test: markets should react to surprises, not to events. If reactions
   don't differ by surprise direction, that's a strong finding.
4. **Regime conditioning** — segment by the Feature 6 regime. Reactions may differ in trending vs
   ranging conditions; if they do, that's more actionable than the aggregate.
5. **Pre-registration integration** — route every event study through Feature 11. Write down your
   expected reaction *before* running it. Your hit rate at predicting your own results is itself
   a finding.

### Reuse, don't rebuild
Use the existing look-ahead-safe backtest walk and the forward-return machinery from the
encyclopedia. This is the same computation with a different trigger — an event instead of a
pattern. Do not write a second history walker.

### Presentation
A page per event type: the distribution of reactions, split by surprise and regime, with sample
sizes, and a plain verdict — *consistent*, *inconsistent*, or *insufficient data*. Link to
example charts that open in the Feature 1 scrub view at the event bar.

### Expect this
My strong prior is you'll find reactions are wildly inconsistent, with direction consistency near
coin-flip for most event types. **That would be one of the most valuable outputs of this app** —
it's the belief most retail traders hold and almost never test, and you'd be turning it from
assumption into measurement on your own data. Same move that made the no-edge finding worth
publishing.

If a few event types *do* show consistency with adequate sample size, that's worth knowing too —
and pre-registration is what stops you from finding it by accident across fifty comparisons.

### Done when
You can pick an event type and instrument and see measured reaction distributions with sample
sizes, split by surprise and regime, with an honest verdict on consistency.

> **Prompt:** "On branch `feature/event-study`, implement Feature 13b of FEATURE-13-SPEC.md:
> a SQLite `events` table seeded from calendar history plus major geopolitical events, and
> `src/research/event_study.py` computing forward-return distributions per event type × instrument
> at 1-bar/1-day/1-week/1-month/3-month horizons — median, IQR, direction consistency, persistence
> before mean reversion, sample size on every row. Condition on surprise vs consensus and on
> Feature 6 regime. Reuse the existing look-ahead-safe backtest walk and encyclopedia forward-return
> code; do not write a second history walker. Route studies through the Feature 11 pre-registration
> flow. Add a Svelte page per event type with an honest consistent/inconsistent/insufficient-data
> verdict and links into the scrub view. Tests included. Summarise in under 15 lines."

---

## Where this sits in the order
After Feature 11 (pre-registration), because 13b depends on it to stay honest. 13a can be built
earlier if you want the event warnings sooner — it's independent.

## Honest caveat
Neither half gives you an information edge. 13a makes you harder to surprise and tells you why a
trend exists; 13b tells you whether the "news moves price predictably" belief survives contact
with your data. Both are worth having. Neither is a crystal ball, and any feature that starts to
feel like one should be treated as a bug.
