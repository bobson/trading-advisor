<script lang="ts">
  // ROADMAP B1 — labelling mode: mark what YOUR eye sees at the scrub bar, with the detector
  // overlays hidden. Clicks on the chart arrive through `handleClick` (the parent binds this
  // component and forwards chart clicks). The draft is bindable so the chart can draw it.
  import { onMount } from 'svelte'
  import {
    getLabelTypes, getLabels, getLabel, putLabel, deleteLabel,
    type GoldLabels, type GoldRow, type GoldSummary,
  } from './api'

  let {
    symbol, timeframe, bar, barTime, candles = [],
    draft = $bindable(), pending = $bindable(), onJump,
  }: {
    symbol: string; timeframe: string; bar: number; barTime: number | null
    candles?: { time: number; high: number; low: number }[]
    draft: GoldLabels
    pending: { kind: 'pattern' | 'zone'; points: { time: number; price: number }[] } | null
    onJump?: (symbol: string, timeframe: string, bar: number) => void
  } = $props()

  let detectorTypes = $state<string[]>([])
  let extraTypes = $state<string[]>([])
  let tool = $state<'pattern' | 'zone'>('pattern')
  let patternType = $state('double top')
  let zoneRole = $state<'support' | 'resistance'>('support')
  let snap = $state(true)
  let msg = $state<string | null>(null)
  let saved = $state<GoldRow | null>(null)
  let rows = $state<GoldRow[]>([])
  let summary = $state<GoldSummary | null>(null)

  onMount(async () => {
    try {
      const t = await getLabelTypes()
      detectorTypes = t.detector_types; extraTypes = t.extra_types
    } catch (e: any) { msg = e.message }
    refreshList()
  })

  async function refreshList() {
    try { const r = await getLabels(); rows = r.labels; summary = r.summary } catch { /* non-critical */ }
  }

  // Load whatever is already saved for this exact bar whenever the bar/market changes.
  $effect(() => {
    const s = symbol, tf = timeframe, b = bar
    getLabel(s, tf, b).then((r) => {
      saved = r.label
      draft = r.label ? structuredClone(r.label.labels) : { patterns: [], zones: [], nothing: false, note: '' }
      pending = null
      msg = r.label ? `Loaded your saved labels for this bar.` : null
    }).catch(() => {})
  })

  // Snap a click to the candle's wick (high or low, whichever is nearer) — swing points are wicks.
  function snapPrice(time: number, price: number) {
    if (!snap) return price
    const c = candles.find((k) => k.time === time)
    if (!c) return price
    return Math.abs(price - c.high) <= Math.abs(price - c.low) ? c.high : c.low
  }

  /** Called by the parent for every click on the price chart while labelling. */
  export function handleClick(time: number, price: number) {
    if (barTime != null && time > barTime) { msg = 'That is after the labelling bar — only past bars can be marked.'; return }
    if (tool === 'pattern') {
      const p = { time, price: snapPrice(time, price) }
      pending = pending?.kind === 'pattern' ? { kind: 'pattern', points: [...pending.points, p] } : { kind: 'pattern', points: [p] }
      draft.nothing = false
      msg = `${patternType}: ${pending.points.length} point${pending.points.length === 1 ? '' : 's'} — keep clicking key points, then "Add pattern".`
    } else {
      const p = { time, price }
      if (pending?.kind === 'zone' && pending.points.length === 1) {
        const [a, b] = [pending.points[0].price, p.price].sort((x, y) => x - y)
        if (a === b) { msg = 'Zone edges must differ.'; return }
        draft.zones = [...draft.zones, { lower: a, upper: b, role: zoneRole }]
        pending = null
        msg = `Added ${zoneRole} zone ${a.toFixed(5).replace(/0+$/, '')}–${b.toFixed(5).replace(/0+$/, '')}.`
      } else {
        pending = { kind: 'zone', points: [p] }
        msg = 'Zone: click the other edge.'
      }
    }
  }

  function addPattern() {
    if (pending?.kind !== 'pattern' || pending.points.length < 2) { msg = 'Click at least 2 key points first.'; return }
    const pts = [...pending.points].sort((a, b) => a.time - b.time)
    draft.patterns = [...draft.patterns, { type: patternType, points: pts }]
    pending = null
    msg = `Added ${patternType} (${pts.length} points).`
  }
  function cancelPending() { pending = null; msg = null }
  function removePattern(i: number) { draft.patterns = draft.patterns.filter((_, j) => j !== i) }
  function removeZone(i: number) { draft.zones = draft.zones.filter((_, j) => j !== i) }
  function toggleNothing() {
    if (!draft.nothing && draft.patterns.length) { msg = "Remove the pattern labels first — 'nothing here' means no pattern."; return }
    draft.nothing = !draft.nothing
  }

  async function save() {
    try {
      const r = await putLabel({ symbol, timeframe, bar, bar_time: barTime, labels: draft })
      saved = r.label; summary = r.summary
      msg = `Saved: ${symbol} ${timeframe}, bar ${bar}.`
      refreshList()
    } catch (e: any) { msg = e.message.replace(/^\d+: /, '') }
  }
  async function remove(id: number) {
    try { const r = await deleteLabel(id); summary = r.summary; if (saved?.id === id) saved = null; refreshList() }
    catch (e: any) { msg = e.message }
  }

  const fmtTime = (t: number | null) => (t == null ? '—' : new Date(t * 1000).toISOString().slice(0, 16).replace('T', ' '))
  const fmtPx = (x: number) => (Math.abs(x) >= 100 ? x.toFixed(2) : x.toFixed(5))
</script>

<section class="label-panel panel">
  <h3>🏷 Labelling — {symbol} {timeframe}, bar {bar} <span class="muted">({fmtTime(barTime)} UTC)</span></h3>
  <p class="muted small">Detector overlays, the verdict and the facts are hidden so you don't anchor on them.
    The chart only shows candles up to this bar. Mark what <b>your</b> eye sees.</p>

  <div class="tools">
    <label><input type="radio" bind:group={tool} value="pattern" onchange={cancelPending} /> Pattern</label>
    <select bind:value={patternType} disabled={tool !== 'pattern'}>
      <optgroup label="Detector's types">{#each detectorTypes as t}<option value={t}>{t}</option>{/each}</optgroup>
      <optgroup label="Other shapes">{#each extraTypes as t}<option value={t}>{t}</option>{/each}</optgroup>
    </select>
    <label class="small"><input type="checkbox" bind:checked={snap} disabled={tool !== 'pattern'} /> snap to wick</label>
    <span class="sep"></span>
    <label><input type="radio" bind:group={tool} value="zone" onchange={cancelPending} /> S/R zone</label>
    <select bind:value={zoneRole} disabled={tool !== 'zone'}>
      <option value="support">support</option><option value="resistance">resistance</option>
    </select>
  </div>

  <div class="tools">
    {#if tool === 'pattern'}
      <button onclick={addPattern} disabled={pending?.kind !== 'pattern' || pending.points.length < 2}>Add pattern</button>
    {/if}
    {#if pending}<button class="ghost" onclick={cancelPending}>Cancel current</button>{/if}
    <label class="small"><input type="checkbox" checked={draft.nothing} onchange={toggleNothing} /> nothing here (no pattern)</label>
  </div>
  {#if msg}<p class="msg">{msg}</p>{/if}

  <div class="draft">
    {#each draft.patterns as p, i}
      <div class="item">▲ {p.type} — {p.points.length} points
        ({p.points.map((q) => fmtPx(q.price)).join(', ')}) <button class="x" onclick={() => removePattern(i)}>✕</button></div>
    {/each}
    {#each draft.zones as z, i}
      <div class="item">▭ {z.role} zone {fmtPx(z.lower)}–{fmtPx(z.upper)} <button class="x" onclick={() => removeZone(i)}>✕</button></div>
    {/each}
    {#if draft.nothing}<div class="item">∅ nothing here — no pattern at this bar</div>{/if}
    {#if !draft.patterns.length && !draft.zones.length && !draft.nothing}<div class="muted small">No labels yet for this bar.</div>{/if}
  </div>
  <label class="note-in small">Note <input type="text" bind:value={draft.note} placeholder="optional" /></label>
  <div class="tools">
    <button class="save" onclick={save}>{saved ? 'Update labels' : 'Save labels'}</button>
    {#if saved}<span class="muted small">saved {fmtTime(saved.updated_at)}</span>{/if}
  </div>

  <h3 class="list-h">Your gold set</h3>
  {#if summary}
    <p class="small">
      <b>{summary.charts}</b> chart{summary.charts === 1 ? '' : 's'} labelled ·
      <b>{summary.patterns}</b> pattern{summary.patterns === 1 ? '' : 's'} ·
      <b>{summary.zones}</b> zone{summary.zones === 1 ? '' : 's'} ·
      <b>{summary.nothing}</b> "nothing here" <span class="muted">(target: 30+ charts)</span>
    </p>
    {#if summary.patterns}
      <div class="counts">
        {#each Object.entries(summary.by_type) as [t, n]}<span class="count">{t} <b>{n}</b></span>{/each}
      </div>
    {/if}
  {/if}
  {#if rows.length}
    <table class="rows">
      <thead><tr><th>market</th><th>bar</th><th>time (UTC)</th><th>labels</th><th></th></tr></thead>
      <tbody>
        {#each rows as r (r.id)}
          <tr class:current={r.symbol === symbol && r.timeframe === timeframe && r.bar === bar}>
            <td>{r.symbol} {r.timeframe}</td>
            <td><button class="link" onclick={() => onJump?.(r.symbol, r.timeframe, r.bar)}>{r.bar}</button></td>
            <td>{fmtTime(r.bar_time)}</td>
            <td>{r.labels.nothing ? 'nothing here' : [...r.labels.patterns.map((p) => p.type),
              ...(r.labels.zones.length ? [`${r.labels.zones.length} zone${r.labels.zones.length === 1 ? '' : 's'}`] : [])].join(', ')}</td>
            <td><button class="x" title="delete this label" onclick={() => remove(r.id)}>✕</button></td>
          </tr>
        {/each}
      </tbody>
    </table>
  {/if}
</section>

<style>
  .label-panel { margin: 10px 0; }
  .label-panel h3 { margin: 0 0 6px; font-size: 14px; color: #c9d1d9; text-transform: none; letter-spacing: 0; }
  .muted { color: #8b949e; }
  .small { font-size: 12px; }
  .tools { display: flex; flex-wrap: wrap; gap: 8px 12px; align-items: center; margin: 8px 0; }
  .tools label { color: #c9d1d9; font-size: 13px; display: inline-flex; gap: 5px; align-items: center; }
  .sep { width: 1px; height: 20px; background: #30363d; }
  .msg { margin: 4px 0; font-size: 13px; color: #d2a8ff; }
  .draft { margin: 6px 0; font-size: 13px; }
  .item { padding: 3px 0; border-bottom: 1px solid #161b22; }
  .note-in { display: flex; gap: 8px; align-items: center; color: #8b949e; }
  .note-in input { flex: 1; background: #161b22; color: #c9d1d9; border: 1px solid #30363d; border-radius: 6px; padding: 6px; }
  button { background: #21262d; color: #c9d1d9; border: 1px solid #30363d; border-radius: 6px; padding: 6px 10px; cursor: pointer; font-weight: 500; }
  button:disabled { opacity: .5; cursor: default; }
  button.save { background: #6e40c9; border-color: #6e40c9; color: #fff; font-weight: 600; }
  button.ghost { background: transparent; }
  button.x { background: transparent; border: none; color: #8b949e; padding: 0 4px; }
  button.link { background: transparent; border: none; color: #58a6ff; padding: 0; text-decoration: underline; }
  .list-h { margin-top: 14px !important; }
  .counts { display: flex; flex-wrap: wrap; gap: 6px; margin: 6px 0; }
  .count { font-size: 12px; border: 1px solid #30363d; border-radius: 999px; padding: 2px 8px; color: #8b949e; }
  .count b { color: #c9d1d9; }
  .rows { width: 100%; border-collapse: collapse; font-size: 12px; margin-top: 6px; }
  .rows th, .rows td { text-align: left; padding: 4px 6px; border-bottom: 1px solid #161b22; }
  .rows th { color: #8b949e; font-weight: 500; }
  .rows tr.current td { background: #1f1d2e; }
  select { background: #161b22; color: #c9d1d9; border: 1px solid #30363d; border-radius: 6px; padding: 5px 8px; }
</style>
