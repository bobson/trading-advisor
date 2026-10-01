<script lang="ts">
  // ROADMAP D6: blind training. A random PAST candle where a chart pattern broke out; the chart ends
  // there and the engine's drawings are hidden. You make your call (it goes to the journal as "blind"),
  // it's judged at once — the future is known — and then everything is revealed.
  import PriceChart from './PriceChart.svelte'
  import {
    getAnalysis, getTrainingNext, getTrainingOptions, postTrainingAnswer, recordText,
    type Analysis, type PanelToggles, type TrainingOptions, type TrainingReveal, type TrainingSetup,
  } from './api'

  const SESSION = 10
  const BLIND: PanelToggles = { trendlines: false, candles_all: false, levels: false, fib: false, swings: false,
    patterns: false, marker: false, ma: true, volume: true, rsi: true, macd: true, adx: false, atr: false }
  // The reveal shows what happened next, with the TESTED pattern's own levels (as at the breakout
  // candle) — not the engine's drawings at the end of the window, which may be a different pattern.
  const REVEALED: PanelToggles = { ...BLIND }

  let opts = $state<TrainingOptions | null>(null)
  let fType = $state(''), fRegime = $state(''), fTf = $state('')
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

  getTrainingOptions().then((o) => (opts = o)).catch((e) => (error = e.message))

  async function next() {
    busy = true; error = null; reveal = null; revealChart = null; chart = null
    direction = 'up'; confidence = 60; invalidation = null; note = ''
    try {
      const r = await getTrainingNext({ type: fType || undefined, regime: fRegime || undefined, timeframe: fTf || undefined })
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
</script>

<section class="training">
  <h2>🎯 Blind training</h2>
  <p class="tag">A random past candle where a chart pattern broke out. The future is hidden and so are the engine's
    drawings. Make your call; it's judged at once and goes to your Journal as <b>blind</b>. {SESSION} setups per session.</p>

  {#if !running}
    <div class="filters">
      <label>pattern <select bind:value={fType}><option value="">any</option>{#each Object.entries(opts?.types ?? {}) as [k, n]}<option value={k}>{k} ({n})</option>{/each}</select></label>
      <label>regime <select bind:value={fRegime}><option value="">any</option>{#each Object.entries(opts?.regimes ?? {}) as [k, n]}<option value={k}>{k} ({n})</option>{/each}</select></label>
      <label>timeframe <select bind:value={fTf}><option value="">any</option>{#each Object.entries(opts?.timeframes ?? {}) as [k, n]}<option value={k}>{k} ({n})</option>{/each}</select></label>
      <button class="go" onclick={start} disabled={!opts?.total}>Start a session</button>
    </div>
    {#if opts && !opts.total}<p class="muted">The setup pool is empty — run <code>scripts/build_training_setups.py</code>.</p>{/if}
    <p class="muted small">Filtering by pattern tells you what to look for; "any" is the harder, blinder test.</p>
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
        <p><b>The pattern:</b> a {reveal.setup.type} ({reveal.setup.direction}) broke out on this candle in a {reveal.setup.regime} regime.
          It {OUT[reveal.setup.outcome] ?? reveal.setup.outcome}{reveal.setup.move_atr != null ? `; ${reveal.setup.move_atr > 0 ? '+' : ''}${reveal.setup.move_atr} ATR in its direction` : ''}.</p>
        <p><b>The engine then:</b> {reveal.engine.bias}, {reveal.engine.tier.replace('_', ' ')} ({reveal.engine.agreeing} of {reveal.engine.total} categories agree){reveal.engine.cautions.length ? ` · cautions: ${reveal.engine.cautions.join(', ').toLowerCase()}` : ''}.</p>
        <p><b>History of {reveal.setup.type}s on {setup.timeframe}:</b> {recordText(reveal.record)}.</p>
      </div>
      {#if revealChart}
        <PriceChart data={revealChart.chart} toggles={REVEALED}
          call={{ time: e.bar_time, direction: e.direction, invalidation: e.invalidation, endTime: e.end_time - 1,
                  lines: [
                    ...(reveal.setup.breakout != null ? [{ price: reveal.setup.breakout, text: `${reveal.setup.type} breakout`, color: '#8b949e' }] : []),
                    ...(reveal.setup.target != null ? [{ price: reveal.setup.target, text: `${reveal.setup.type} target`, color: '#d29922' }] : []),
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
