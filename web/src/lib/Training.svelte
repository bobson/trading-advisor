<script lang="ts">
  // ROADMAP D6: blind training. A random PAST candle where a chart pattern broke out — or, training on
  // entry types, a textbook entry point (support bounce, zone breakout, trendline touch, MA pullback, RSI
  // divergence); the chart ends there and the engine's drawings are hidden. You make your call (it goes to
  // the journal as "blind"), it's judged at once — the future is known — and then everything is revealed.
  // The scorecard sets your calls per type beside how the textbook side and its mirror did.
  import PriceChart from './PriceChart.svelte'
  import {
    getAnalysis, getTrainingNext, getTrainingOptions, getTrainingScorecard, postTrainingAnswer, recordText,
    type Analysis, type PanelToggles, type TrainingOptions, type TrainingReveal, type TrainingScoreRow, type TrainingSetup,
  } from './api'

  const SESSION = 10
  const BLIND: PanelToggles = { trendlines: false, candles_all: false, levels: false, fib: false, swings: false,
    patterns: false, marker: false, ma: true, volume: true, rsi: true, macd: true, adx: false, atr: false }
  // The reveal shows what happened next, with the TESTED pattern's own levels (as at the breakout
  // candle) — not the engine's drawings at the end of the window, which may be a different pattern.
  const REVEALED: PanelToggles = { ...BLIND }

  let opts = $state<TrainingOptions | null>(null)
  // what to practise: "" any · "family:entry" / "family:pattern" · a single type
  let fType = $state('family:entry'), fRegime = $state(''), fTf = $state('')
  let card = $state<TrainingScoreRow[]>([])
  const typesOf = (fam: string) => Object.entries(opts?.types ?? {}).filter(([t]) => (opts?.families?.[t] ?? 'pattern') === fam)
  const loadCard = () => getTrainingScorecard().then((c) => (card = c.rows)).catch(() => {})
  loadCard()
  let running = $state(false)
  let setup = $state<TrainingSetup | null>(null)
  let chart = $state<Analysis | null>(null)
  let reveal = $state<TrainingReveal | null>(null)
  let revealChart = $state<Analysis | null>(null)
  let results = $state<TrainingReveal[]>([])
  let error = $state<string | null>(null)
  let busy = $state(false)
  // the call
  let direction = $state<'up' | 'down'>('up')
  let confidence = $state(60)
  let invalidation = $state<number | null>(null)
  let note = $state('')

  getTrainingOptions().then((o) => {
    opts = o
    if (!Object.values(o.families ?? {}).includes('entry')) fType = ''      // no entry points in this pool yet
  }).catch((e) => (error = e.message))

  async function next() {
    busy = true; error = null; reveal = null; revealChart = null; chart = null
    direction = 'up'; confidence = 60; invalidation = null; note = ''
    try {
      const fam = fType.startsWith('family:') ? fType.slice(7) : undefined
      const r = await getTrainingNext({ type: fType && !fam ? fType : undefined, family: fam,
                                        regime: fRegime || undefined, timeframe: fTf || undefined })
      setup = r.setup
      if (!setup) { error = 'No unanswered setup matches these filters.'; running = false; return }
      chart = await getAnalysis(setup.symbol, setup.timeframe, false, false, setup.as_of_bar, 400)
    } catch (e: any) { error = e.message } finally { busy = false }
  }
  function start() { results = []; running = true; next() }

  async function answer() {
    if (!setup || invalidation == null) { error = 'Set the price that would prove you wrong.'; return }
    busy = true; error = null
    try {
      reveal = await postTrainingAnswer({ setup_id: setup.id, direction, confidence, invalidation, note })
      results = [...results, reveal]
      loadCard()
      revealChart = await getAnalysis(setup.symbol, setup.timeframe, false, false, reveal.reveal_bar, 400)
    } catch (e: any) {
      error = String(e.message).replace(/^\d+: /, '').replace(/^\{"detail":"(.*)"\}$/, '$1')
    } finally { busy = false }
  }

  const fmt = (x: number | null | undefined) => (x == null ? '—' : Math.abs(x) >= 100 ? x.toLocaleString(undefined, { maximumFractionDigits: 2 }) : Number(x.toPrecision(6)).toString())
  const hits = $derived(results.filter((r) => r.entry.outcome === 'correct').length)
  const brier = $derived(results.length ? results.reduce((a, r) => a + (r.entry.confidence / 100 - (r.entry.outcome === 'correct' ? 1 : 0)) ** 2, 0) / results.length : null)
  const meanConf = $derived(results.length ? results.reduce((a, r) => a + r.entry.confidence, 0) / results.length / 100 : null)
  const done = $derived(results.length >= SESSION && !!reveal)
  const OUT: Record<string, string> = { target: 'reached its target', failed: 'failed (closed back through the breakout)', open: 'neither reached its target nor failed within the horizon' }
  const ENTRY_OUT: Record<string, string> = { target: 'reached its next level first', failed: 'hit its invalidation first', open: 'touched neither within the horizon' }
  const WHAT: Record<string, string> = {
    'support bounce': 'the candle dipped into a support zone and closed back above it',
    'resistance rejection': 'the candle poked into a resistance zone and closed back below it',
    'zone breakout': 'the candle closed through the far edge of a zone',
    'trendline touch': 'the candle reached an unbroken trendline and closed on its right side',
    'MA pullback': 'in a trend, the candle pulled back to the 50-MA and closed on the trend side of it',
    'RSI divergence': 'price and RSI disagreed on the last two swings',
  }
  const isEntry = (t: string) => (opts?.families?.[t] ?? 'pattern') === 'entry'
  const pct = (k: number, n: number, rate: number | null) => `${k} of ${n}${rate != null ? ` (${Math.round(rate * 100)}%)` : ''}`
</script>

<section class="training">
  <h2>🎯 Blind training</h2>
  <p class="tag">A random past candle at a textbook entry point (a bounce, a breakout, a trendline touch…) or where a
    chart pattern broke out. The future is hidden and so are the engine's drawings. Make your call; it's judged at once and goes to your Journal as <b>blind</b>. {SESSION} setups per session.</p>

  {#if !running}
    <div class="filters">
      <label>practise <select bind:value={fType}>
        <option value="family:entry">entry points — any</option>
        {#if typesOf('entry').length}<optgroup label="Entry points">{#each typesOf('entry') as [k, n]}<option value={k}>{k} ({n})</option>{/each}</optgroup>{/if}
        <option value="family:pattern">chart patterns — any</option>
        {#if typesOf('pattern').length}<optgroup label="Chart patterns">{#each typesOf('pattern') as [k, n]}<option value={k}>{k} ({n})</option>{/each}</optgroup>{/if}
        <option value="">everything</option>
      </select></label>
      <label>regime <select bind:value={fRegime}><option value="">any</option>{#each Object.entries(opts?.regimes ?? {}) as [k, n]}<option value={k}>{k} ({n})</option>{/each}</select></label>
      <label>timeframe <select bind:value={fTf}><option value="">any</option>{#each Object.entries(opts?.timeframes ?? {}) as [k, n]}<option value={k}>{k} ({n})</option>{/each}</select></label>
      <button class="go" onclick={start} disabled={!opts?.total}>Start a session</button>
    </div>
    {#if opts && !opts.total}<p class="muted">The setup pool is empty — run <code>scripts/build_training_setups.py</code>.</p>{/if}
    <p class="muted small">Picking one type tells you what to look for; "any" is the harder, blinder test.</p>
  {/if}
  {#if error}<p class="error">{error}</p>{/if}

  {#if running && setup}
    <p class="progress">Setup {Math.min(results.length + (reveal ? 0 : 1), SESSION)} of {SESSION} · {setup.symbol} {setup.timeframe}
      · the chart ends at the candle you're calling from</p>
    {#if !reveal && chart}
      <PriceChart data={chart.chart} toggles={BLIND} />
      <div class="callbox">
        <div class="row"><span class="lbl">My call</span>
          <button class:on={direction === 'up'} onclick={() => (direction = 'up')}>▲ Up</button>
          <button class:on={direction === 'down'} onclick={() => (direction = 'down')}>▼ Down</button>
          <span class="muted small">from the last close: <b>{fmt(setup.price)}</b>, judged after {setup.horizon_bars} {setup.timeframe} candles</span></div>
        <div class="row"><label>How sure: <b>{confidence}%</b> <input type="range" min="50" max="100" step="5" bind:value={confidence} /></label></div>
        <div class="row wrap"><label>Wrong if price touches <input type="number" step="any" bind:value={invalidation}
          placeholder={direction === 'up' ? 'below the price' : 'above the price'} /></label>
          <label class="grow">Why (optional) <input type="text" bind:value={note} /></label></div>
        <button class="go" onclick={answer} disabled={busy}>{busy ? 'Judging…' : 'Make the call'}</button>
      </div>
    {/if}

    {#if reveal}
      {@const e = reveal.entry}
      <div class="reveal {e.outcome}">
        <h3>Your call: {e.direction} at {e.confidence}% — <span class="res">{e.outcome}</span></h3>
        <p>Closed at {fmt(e.end_close)} after {setup.horizon_bars} candles (from {fmt(e.price)}; wrong at {fmt(e.invalidation)}).</p>
        {#if isEntry(reveal.setup.type)}
          <p><b>The entry:</b> a {reveal.setup.type} ({reveal.setup.direction}) — {WHAT[reveal.setup.type] ?? ''} — at
            {fmt(reveal.setup.breakout)}, in a {reveal.setup.regime} regime. The textbook {reveal.setup.direction} trade (next level
            {fmt(reveal.setup.target)}, wrong at {fmt(reveal.setup.invalidation)}) {ENTRY_OUT[reveal.setup.outcome] ?? reveal.setup.outcome};
            {reveal.setup.move_atr != null ? ` the close ${setup.horizon_bars} candles later was ${reveal.setup.move_atr > 0 ? '+' : ''}${reveal.setup.move_atr} ATR in its direction.` : ''}</p>
        {:else}
          <p><b>The pattern:</b> a {reveal.setup.type} ({reveal.setup.direction}) broke out on this candle in a {reveal.setup.regime} regime.
            It {OUT[reveal.setup.outcome] ?? reveal.setup.outcome}{reveal.setup.move_atr != null ? `; ${reveal.setup.move_atr > 0 ? '+' : ''}${reveal.setup.move_atr} ATR in its direction` : ''}.</p>
        {/if}
        <p><b>The engine then:</b> {reveal.engine.bias}, {reveal.engine.tier.replace('_', ' ')} ({reveal.engine.agreeing} of {reveal.engine.total} categories agree){reveal.engine.cautions.length ? ` · cautions: ${reveal.engine.cautions.join(', ').toLowerCase()}` : ''}.</p>
        {#if isEntry(reveal.setup.type) && reveal.pool}
          {@const p = reveal.pool}
          <p><b>Every {reveal.setup.type} in the pool:</b> the textbook side reached its next level first in {pct(p.target, p.n, p.target_rate)};
            the mirror — same distances, other direction — in {pct(p.opposite_target ?? 0, p.n, p.opposite_rate)}.</p>
        {:else}
          <p><b>History of {reveal.setup.type}s on {setup.timeframe}:</b> {recordText(reveal.record)}.</p>
        {/if}
      </div>
      {#if revealChart}
        <PriceChart data={revealChart.chart} toggles={REVEALED}
          call={{ time: e.bar_time, direction: e.direction, invalidation: e.invalidation, endTime: e.end_time - 1,
                  lines: [
                    ...(reveal.setup.breakout != null ? [{ price: reveal.setup.breakout, text: isEntry(reveal.setup.type) ? reveal.setup.type : `${reveal.setup.type} breakout`, color: '#8b949e' }] : []),
                    ...(reveal.setup.target != null ? [{ price: reveal.setup.target, text: isEntry(reveal.setup.type) ? 'next level' : `${reveal.setup.type} target`, color: '#d29922' }] : []),
                  ] }} />
      {/if}
      {#if !done}<button class="go" onclick={next} disabled={busy}>Next setup ▶</button>{/if}
    {/if}
  {/if}

  {#if done}
    <div class="summary">
      <h3>Session done</h3>
      <p>{hits} of {results.length} calls right · your average confidence {Math.round((meanConf ?? 0) * 100)}% ·
        Brier {brier?.toFixed(3)} (always saying 50% scores 0.250; lower is better).</p>
      <p class="muted small">Ten calls are far too few to judge yourself — every session adds to the Journal's calibration,
        where the numbers get meaningful with 20+ calls per confidence band.</p>
      <button class="go" onclick={() => { running = false; setup = null; reveal = null }}>New session</button>
    </div>
  {/if}

  {#if !running && card.length}
    <h3 class="sch">Scorecard <span class="muted small">— your blind calls per type, beside how the setup itself did</span></h3>
    <div class="tablewrap"><table>
      <thead><tr><th>type</th><th>your calls (right)</th><th>Brier</th><th>textbook side · mirror (whole pool)</th></tr></thead>
      <tbody>
        {#each card as r}
          <tr>
            <td>{r.type}{#if r.family === 'pattern'} <span class="muted small">pattern</span>{/if}</td>
            <td>{r.you ? pct(r.you.correct, r.you.n, r.you.rate) : '—'}</td>
            <td class="muted">{r.you ? r.you.brier.toFixed(3) : '—'}</td>
            <td class="muted">{#if r.pool && r.family === 'entry'}{pct(r.pool.target, r.pool.n, r.pool.target_rate)} · {pct(r.pool.opposite_target ?? 0, r.pool.n, r.pool.opposite_rate)}
              {:else if r.pool}{pct(r.pool.target, r.pool.n, r.pool.target_rate)} reached target{:else}—{/if}</td>
          </tr>
        {/each}
      </tbody>
    </table></div>
    <p class="muted small">A % only with 20+ cases. "Right" = your call closed on your side without touching your
      invalidation (Brier: 0.250 = always saying 50%; lower is better). Textbook side · mirror: how often the setup's own
      direction reached its next level first, and how often the same distances the other way did — on the same candles.
      An entry only means something when its side clearly beats its mirror; where you beat both, that's your edge to test.</p>
  {/if}
</section>

<style>
  .training { max-width: 1100px; }
  .tag { color: #8b949e; margin: 0 0 12px; }
  .muted { color: #8b949e; }
  .small { font-size: 12px; }
  .error { color: #f85149; }
  .filters { display: flex; flex-wrap: wrap; gap: 12px; align-items: center; margin-bottom: 8px; }
  .filters label, .row label { color: #c9d1d9; font-size: 14px; display: inline-flex; gap: 6px; align-items: center; }
  select, input { background: #0d1117; color: #c9d1d9; border: 1px solid #30363d; border-radius: 6px; padding: 4px 8px; font-size: 14px; }
  input[type='range'] { width: 180px; padding: 0; }
  button { background: #21262d; color: #c9d1d9; border: 1px solid #30363d; border-radius: 6px; padding: 6px 12px; cursor: pointer; }
  button.on { border-color: #58a6ff; color: #58a6ff; }
  button.go { border-color: #238636; margin-top: 8px; }
  .progress { color: #8b949e; font-size: 13px; }
  .sch { margin: 24px 0 6px; font-size: 15px; }
  .tablewrap { overflow-x: auto; }
  table { border-collapse: collapse; width: 100%; font-size: 13px; }
  th, td { text-align: left; padding: 6px 8px; border-bottom: 1px solid #161b22; vertical-align: top; }
  th { color: #8b949e; font-weight: 500; }
  .callbox, .reveal, .summary { border: 1px solid #30363d; border-radius: 8px; padding: 10px 12px; margin: 10px 0; font-size: 14px; }
  .row { display: flex; align-items: center; gap: 10px; margin: 6px 0; }
  .row.wrap { flex-wrap: wrap; }
  .grow { flex: 1; }
  .grow input { flex: 1; }
  .lbl { color: #8b949e; }
  .reveal h3 { margin: 0 0 6px; font-size: 15px; }
  .reveal.correct .res { color: #3fb950; }
  .reveal.incorrect .res, .reveal.invalidated .res { color: #f85149; }
  .reveal p { margin: 4px 0; }
  @media (max-width: 640px) { select, input { font-size: 16px; } input[type='range'] { width: 140px; } }
</style>
