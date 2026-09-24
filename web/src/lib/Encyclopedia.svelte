<script lang="ts">
  // ROADMAP B3 — the Empirical Pattern Encyclopedia. The textbook claim on one side, what the
  // pattern ACTUALLY did in this app's history on the other. Any rate with fewer than 20 cases is
  // shown as counts only ("7 of 12 — too few to rate"), never as a percentage.
  import { onMount } from 'svelte'
  import { getEncyclopedia, getEncyclopediaPage, type EncIndex, type EncPage, type EncRow } from './api'

  let { onOpenExample }: { onOpenExample?: (symbol: string, timeframe: string, bar: number) => void } = $props()

  const MIN_N = 20
  let index = $state<EncIndex | null>(null)
  let page = $state<EncPage | null>(null)
  let selected = $state<string | null>(null)
  let tf = $state('')
  let sym = $state('all')
  let reg = $state('all')
  let error = $state<string | null>(null)

  onMount(async () => {
    try { index = await getEncyclopedia() } catch (e: any) { error = e.message }
    const m = location.hash.match(/^#\/encyclopedia\/(.+)$/)
    if (m) open(decodeURIComponent(m[1]))
  })

  async function open(t: string) {
    selected = t
    location.hash = `#/encyclopedia/${encodeURIComponent(t)}`
    page = null
    try {
      page = await getEncyclopediaPage(t)
      const tfs = [...new Set(page.rows.map((r) => r.timeframe))]
      if (!tfs.includes(tf)) tf = tfs[0] ?? ''
      sym = 'all'; reg = 'all'
    } catch (e: any) { error = e.message }
  }
  function back() { selected = null; page = null; location.hash = '#/encyclopedia' }

  const types = $derived([...new Set((index?.types ?? []).map((r) => r.pattern_type))].sort())
  const summary = (t: string) => (index?.types ?? []).filter((r) => r.pattern_type === t)
  const pageTfs = $derived([...new Set((page?.rows ?? []).map((r) => r.timeframe))].sort())
  const symbols = $derived([...new Set((page?.rows ?? []).filter((r) => r.timeframe === tf).map((r) => r.symbol))]
    .sort((a, b) => (a === 'all' ? -1 : b === 'all' ? 1 : a.localeCompare(b))))
  const regimes = $derived([...new Set((page?.rows ?? []).filter((r) => r.timeframe === tf && r.symbol === sym).map((r) => r.regime))]
    .sort((a, b) => (a === 'all' ? -1 : b === 'all' ? 1 : a.localeCompare(b))))
  const row = (split: string) => page?.rows.find((r) => r.timeframe === tf && r.symbol === sym && r.regime === reg && r.split === split)
  const main = $derived(row('all'))
  const examples = $derived(page?.rows.find((r) => r.timeframe === tf && r.symbol === sym && r.regime === 'all' && r.split === 'all')?.examples ?? [])
  const precision = $derived(page?.detector_precision?.[tf])

  // A rate is a percentage ONLY with 20+ cases; otherwise the raw counts.
  function rate(r: number | null, num: number, den: number) {
    if (den === 0) return { text: 'no cases', thin: true }
    if (r == null || den < MIN_N) return { text: `${num} of ${den} — too few to rate`, thin: true }
    return { text: `${(r * 100).toFixed(0)}%  (${num} of ${den})`, thin: false }
  }
  function moveText(r: EncRow | undefined) {
    if (!r || r.move_n === 0) return { text: 'no cases', thin: true }
    if (r.move_atr_median == null) return { text: `${r.move_n} cases — too few to summarise`, thin: true }
    const s = (x: number | null) => (x == null ? '—' : `${x > 0 ? '+' : ''}${x.toFixed(2)}`)
    return { text: `median ${s(r.move_atr_median)} ATR  (middle half ${s(r.move_atr_q1)} to ${s(r.move_atr_q3)}; ${r.move_n} cases)`, thin: false }
  }
  const nice = (s: string) => s.replace(/_/g, ' ')
  const fmtDate = (t: number | null) => (t ? new Date(t * 1000).toISOString().slice(0, 10) : '—')
  const CATS = ['volume', 'momentum', 'volatility', 'candlestick']
</script>

<section class="enc">
  <h2>📚 Pattern encyclopedia</h2>
  <p class="tag">What each chart pattern <b>actually did</b> in this app's own history, beside what the
    textbooks claim. Past outcomes, not odds for the next one; any rate with fewer than {MIN_N} cases
    is shown as counts only.</p>
  {#if error}<p class="error">{error}</p>{/if}

  {#if !selected}
    {#if index && !index.types.length}
      <p class="hint">Not built yet. Run <code>python scripts/build_encyclopedia.py</code> (about a minute per daily market), then reload.</p>
    {:else if index}
      <p class="muted small">Built {fmtDate(index.built_at)} · outcomes measured over {index.params.horizon} bars after the breakout;
        a forming pattern gets {index.params.max_wait} bars to break out.</p>
      <table class="list">
        <thead><tr><th>pattern</th><th>tf</th><th>seen</th><th>broke out</th><th>reached target</th><th>failed</th></tr></thead>
        <tbody>
          {#each types as t}
            {#each summary(t) as r, k}
              <tr>
                <td>{#if k === 0}<button class="link" onclick={() => open(t)}>{t}</button>{/if}</td>
                <td>{r.timeframe}</td>
                <td>{r.sample_size}</td>
                <td class:thin={rate(r.confirmation_rate, r.confirmed_n, r.decided_n).thin}>{rate(r.confirmation_rate, r.confirmed_n, r.decided_n).text}</td>
                <td class:thin={rate(r.follow_through_rate, r.target_hit_n, r.target_n).thin}>{rate(r.follow_through_rate, r.target_hit_n, r.target_n).text}</td>
                <td class:thin={rate(r.failure_rate, r.failed_n, r.judged_n).thin}>{rate(r.failure_rate, r.failed_n, r.judged_n).text}</td>
              </tr>
            {/each}
          {/each}
        </tbody>
      </table>
    {:else}
      <p class="muted">Loading…</p>
    {/if}
  {:else}
    <button class="link" onclick={back}>← all patterns</button>
    <h3 class="title">{selected}</h3>
    {#if page}
      <div class="filters">
        <label>timeframe <select bind:value={tf}>{#each pageTfs as t}<option>{t}</option>{/each}</select></label>
        <label>market <select bind:value={sym}>{#each symbols as s}<option value={s}>{s === 'all' ? 'all markets' : s}</option>{/each}</select></label>
        <label>regime <select bind:value={reg}>{#each regimes as g}<option value={g}>{g === 'all' ? 'all regimes' : nice(g)}</option>{/each}</select></label>
      </div>

      <div class="two">
        <div class="panel textbook">
          <h4>Textbook claim <span class="muted small">(convention — "hypotheses to test")</span></h4>
          {#if page.textbook}
            {#if page.textbook.shape}<p><b>Shape:</b> {page.textbook.shape}</p>{/if}
            {#if page.textbook.trigger}<p><b>Trigger:</b> {page.textbook.trigger}</p>{/if}
            <ul>{#each page.textbook.claims as c}<li>{c}</li>{/each}</ul>
            <p class="muted small">Source: {page.textbook.source}</p>
          {:else}<p class="muted">No textbook entry for this type.</p>{/if}
        </div>

        <div class="panel measured">
          <h4>What actually happened here</h4>
          {#if main}
            <div class="stat"><span>Times seen</span><b>{main.sample_size}</b>
              <span class="muted small">({main.seen_forming} first seen while still forming — the rates below use only these)</span></div>
            {#each [
              ['Broke out', rate(main.confirmation_rate, main.confirmed_n, main.decided_n)],
              ['Invalidated before breaking out', rate(main.decided_n ? main.invalidated_n / main.decided_n : null, main.invalidated_n, main.decided_n)],
              ['Reached its target (after breaking out)', rate(main.follow_through_rate, main.target_hit_n, main.target_n)],
              ['Failed (fell back through the breakout)', rate(main.failure_rate, main.failed_n, main.judged_n)],
            ] as [label, v]}
              <div class="stat"><span>{label}</span><b class:thin={(v as any).thin}>{(v as any).text}</b></div>
            {/each}
            {#if main.pending_breakout_n || main.pending_outcome_n}
              <div class="stat"><span>Too recent to judge (left out of the rates)</span>
                <b class="thin">{main.pending_breakout_n} still forming · {main.pending_outcome_n} broke out recently</b></div>
            {/if}
            <div class="stat"><span>Move after the breakout</span>
              <b class:thin={moveText(main).thin}>{moveText(main).text}</b></div>
            <div class="stat"><span>Bars to target or failure</span>
              <b class:thin={main.bars_to_resolution_median == null}>{main.bars_to_resolution_median == null
                ? `${main.resolved_n} resolved — too few to summarise` : `median ${main.bars_to_resolution_median} (${main.resolved_n} resolved)`}</b></div>
            <div class="stat"><span>Detector precision</span>
              <b class:thin={precision?.precision == null}>{precision?.precision == null ? 'unmeasured (needs gold labels, ROADMAP B2)'
                : `${(precision.precision * 100).toFixed(0)}% of ${precision.n} detections matched a label (${precision.status})`}</b></div>
          {:else}<p class="muted">No cases for this selection.</p>{/if}
        </div>
      </div>

      <div class="panel">
        <h4>Split by what confirmed the breakout <span class="muted small">(did each category support it at the breakout candle?)</span></h4>
        <table class="split">
          <thead><tr><th>category</th><th></th><th>judged breakouts</th><th>reached target</th><th>failed</th><th>move after</th></tr></thead>
          <tbody>
            {#each CATS as cat}
              {#each ['supports', 'not'] as val}
                {@const r = row(`${cat}=${val}`)}
                {#if r}
                  <tr>
                    <td>{val === 'supports' ? cat : ''}</td>
                    <td class="muted">{val === 'supports' ? 'supported' : 'did not'}</td>
                    <td>{r.judged_n}</td>
                    <td class:thin={rate(r.follow_through_rate, r.target_hit_n, r.target_n).thin}>{rate(r.follow_through_rate, r.target_hit_n, r.target_n).text}</td>
                    <td class:thin={rate(r.failure_rate, r.failed_n, r.judged_n).thin}>{rate(r.failure_rate, r.failed_n, r.judged_n).text}</td>
                    <td class:thin={moveText(r).thin}>{moveText(r).text}</td>
                  </tr>
                {/if}
              {/each}
            {/each}
          </tbody>
        </table>
      </div>

      <div class="panel">
        <h4>Examples <span class="muted small">(opens the chart at the breakout candle — history to the right stays hidden)</span></h4>
        {#if examples.length}
          <div class="examples">
            {#each examples as ex}
              <button class="ex" onclick={() => onOpenExample?.(ex.symbol, ex.timeframe, ex.bar)}>
                {ex.symbol} {ex.timeframe} · bar {ex.bar} · {ex.direction} · <b class={ex.outcome}>{ex.outcome === 'target' ? 'reached target' : ex.outcome === 'failed' ? 'failed'
                  : ex.outcome === 'pending' ? 'too recent to judge' : 'neither, within the horizon'}</b>
                {#if ex.move_atr != null}· {ex.move_atr > 0 ? '+' : ''}{ex.move_atr} ATR{/if} ▶</button>
            {/each}
          </div>
        {:else}<p class="muted">No confirmed examples for this selection.</p>{/if}
      </div>
    {:else}<p class="muted">Loading…</p>{/if}
  {/if}
</section>

<style>
  .enc { max-width: 1000px; }
  .tag { color: #8b949e; margin: 0 0 12px; }
  .muted { color: #8b949e; }
  .small { font-size: 12px; }
  .hint { color: #8b949e; }
  .error { color: #f85149; }
  code { background: #161b22; padding: 1px 5px; border-radius: 4px; }
  .list, .split { width: 100%; border-collapse: collapse; font-size: 13px; }
  .list th, .list td, .split th, .split td { text-align: left; padding: 5px 8px; border-bottom: 1px solid #161b22; }
  .list th, .split th { color: #8b949e; font-weight: 500; }
  .thin { color: #8b949e; font-weight: 400; }
  button.link { background: none; border: none; color: #58a6ff; padding: 0; cursor: pointer; text-decoration: underline; font-size: 14px; }
  .title { margin: 8px 0; text-transform: capitalize; }
  .filters { display: flex; flex-wrap: wrap; gap: 12px; margin: 8px 0 12px; }
  .filters label { color: #8b949e; font-size: 13px; display: flex; gap: 6px; align-items: center; }
  select { background: #161b22; color: #c9d1d9; border: 1px solid #30363d; border-radius: 6px; padding: 5px 8px; }
  .two { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
  .panel { border: 1px solid #30363d; border-radius: 8px; padding: 12px 14px; margin-bottom: 12px; }
  .panel h4 { margin: 0 0 8px; font-size: 14px; }
  .textbook ul { margin: 6px 0; padding-left: 18px; font-size: 13px; line-height: 1.5; }
  .textbook p { margin: 4px 0; font-size: 13px; }
  .stat { display: flex; flex-wrap: wrap; gap: 4px 10px; justify-content: space-between; padding: 5px 0; border-bottom: 1px solid #161b22; font-size: 13px; }
  .stat > span:first-child { color: #8b949e; }
  .examples { display: flex; flex-direction: column; gap: 6px; }
  .ex { text-align: left; background: #161b22; color: #c9d1d9; border: 1px solid #30363d; border-radius: 6px; padding: 6px 10px; cursor: pointer; font-size: 13px; }
  .ex:hover { border-color: #58a6ff; }
  .ex b.target { color: #c9d1d9; } .ex b.failed { color: #c9d1d9; } .ex b.open { color: #8b949e; }
  @media (max-width: 640px) { .two { grid-template-columns: 1fr; } }
</style>
