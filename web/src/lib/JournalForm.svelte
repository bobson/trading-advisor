<script lang="ts">
  // ROADMAP D1: log YOUR call on the live chart, ideally before seeing the engine's read. The server
  // picks the bar (latest closed) and price; what was on screen is recorded as it was.
  import { getJournalPrice, postJournal, type JournalEntry } from './api'

  let { symbol, timeframe, lastClose = null, source = 'analysis', verdictVisible, explanationVisible,
        disabledReason = null, onLogged }: {
    symbol: string; timeframe: string; lastClose?: number | null; source?: 'analysis' | 'morning'
    verdictVisible: boolean; explanationVisible: boolean; disabledReason?: string | null
    onLogged?: (e: JournalEntry) => void
  } = $props()

  let direction = $state<'up' | 'down'>('up')
  let confidence = $state(60)
  let invalidation = $state<number | null>(null)
  let horizonValue = $state(2)
  let horizonUnit = $state('weeks')
  let note = $state('')
  let busy = $state(false)
  let error = $state<string | null>(null)
  let logged = $state<JournalEntry | null>(null)
  // The exact candle + price the call will be logged at (the server's latest closed bar, fetched fresh)
  let at = $state<{ bar_time: number; price: number } | null>(null)
  $effect(() => { if (!disabledReason) getJournalPrice(symbol, timeframe).then((r) => (at = r)).catch(() => (at = null)) })

  const fmt = (x: number) => (Math.abs(x) >= 100 ? x.toLocaleString(undefined, { maximumFractionDigits: 2 }) : Number(x.toPrecision(6)).toString())
  const when = (t: number) => new Date(t * 1000).toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' })

  async function submit() {
    if (invalidation == null) { error = 'Set the price that would prove you wrong.'; return }
    busy = true; error = null
    try {
      logged = await postJournal({ symbol, timeframe, direction, confidence, invalidation, horizon_value: horizonValue,
        horizon_unit: horizonUnit, note, source, verdict_visible: verdictVisible, explanation_visible: explanationVisible })
      onLogged?.(logged)
    } catch (e: any) {
      error = String(e.message).replace(/^\d+: /, '').replace(/^\{"detail":"(.*)"\}$/, '$1')
    } finally { busy = false }
  }
</script>

<div class="jform">
  {#if disabledReason}
    <p class="muted small">{disabledReason}</p>
  {:else if logged}
    <p class="ok">📝 Logged: <b>{logged.direction}</b> on {logged.symbol} {logged.timeframe} at {fmt(logged.price)},
      {logged.confidence}% sure, invalidation {fmt(logged.invalidation)}. It's judged after {when(logged.end_time)}
      — see the Journal page.</p>
  {:else}
    <div class="row">
      <span class="lbl">My call</span>
      <button class:on={direction === 'up'} onclick={() => (direction = 'up')}>▲ Up</button>
      <button class:on={direction === 'down'} onclick={() => (direction = 'down')}>▼ Down</button>
      {#if at}<span class="muted small">logged at the close of the last finished {timeframe} candle:
        <b>{fmt(at.price)}</b> (the candle from {when(at.bar_time)})</span>
      {:else if lastClose != null}<span class="muted small">price ~{fmt(lastClose)}</span>{/if}
    </div>
    <div class="row">
      <label>How sure: <b>{confidence}%</b>
        <input type="range" min="50" max="100" step="5" bind:value={confidence} /></label>
    </div>
    <p class="muted small">= how likely you think it is that this call is judged <b>correct</b>: not touching your
      invalidation, and closing on your side at the end.</p>
    <div class="row wrap">
      <label>Wrong if price touches <input type="number" step="any" bind:value={invalidation}
        placeholder={direction === 'up' ? 'below the price' : 'above the price'} /></label>
      <label>Judge after <input class="num" type="number" min="1" bind:value={horizonValue} />
        <select bind:value={horizonUnit}><option>weeks</option><option>days</option><option>bars</option></select></label>
    </div>
    <label class="note">Why (optional) <input type="text" maxlength="2000" bind:value={note} placeholder="what I see" /></label>
    <div class="row">
      <button class="go" onclick={submit} disabled={busy}>{busy ? 'Logging…' : 'Log my call'}</button>
      <span class="muted small">Permanent after 5 minutes. {verdictVisible || explanationVisible ? "The engine's read is on screen — this call counts as anchored." : "The engine's read is hidden — this call counts as blind."}</span>
    </div>
    {#if error}<p class="error">{error}</p>{/if}
  {/if}
</div>

<style>
  .jform { font-size: 14px; }
  .row { display: flex; align-items: center; gap: 10px; margin: 6px 0; }
  .row.wrap { flex-wrap: wrap; }
  .lbl { color: #8b949e; }
  button { background: #21262d; color: #c9d1d9; border: 1px solid #30363d; border-radius: 6px; padding: 5px 12px; cursor: pointer; }
  button.on { border-color: #58a6ff; color: #58a6ff; }
  button.go { border-color: #238636; }
  input, select { background: #0d1117; color: #c9d1d9; border: 1px solid #30363d; border-radius: 6px; padding: 4px 8px; font-size: 14px; }
  input[type='range'] { vertical-align: middle; width: 180px; padding: 0; }
  input.num { width: 64px; }
  .note { display: flex; gap: 8px; align-items: center; }
  .note input { flex: 1; }
  .muted { color: #8b949e; }
  .small { font-size: 12px; }
  .ok { color: #c9d1d9; margin: 4px 0; }
  .error { color: #f85149; margin: 4px 0; }
  @media (max-width: 640px) { input, select { font-size: 16px; } input[type='range'] { width: 140px; } }
</style>
