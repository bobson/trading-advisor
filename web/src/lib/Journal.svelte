<script lang="ts">
  // ROADMAP D1: your calls and how well-calibrated they are. Plain numbers — no streaks, no praise.
  // A rate (and a dot on the calibration chart) only with 20+ calls; counts below that.
  import { deleteJournal, getJournal, type JournalGroup, type JournalPage } from './api'

  let { onOpen }: { onOpen?: (symbol: string, timeframe: string) => void } = $props()

  let page = $state<JournalPage | null>(null)
  let error = $state<string | null>(null)
  let loading = $state(false)

  async function load() {
    loading = true; error = null
    try { page = await getJournal() } catch (e: any) { error = e.message } finally { loading = false }
  }
  load()

  async function remove(id: number) {
    try { await deleteJournal(id); await load() } catch (e: any) { error = e.message }
  }

  const pct = (x: number | null | undefined) => (x == null ? '—' : `${Math.round(x * 100)}%`)
  const fmt = (x: number) => (Math.abs(x) >= 100 ? x.toLocaleString(undefined, { maximumFractionDigits: 2 }) : Number(x.toPrecision(6)).toString())
  const when = (t: number) => new Date(t * 1000).toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' })
  const rate = (g: JournalGroup) => (g.n === 0 ? '—' : g.accuracy != null ? `${pct(g.accuracy)} (${g.hits} of ${g.n})` : `${g.hits} of ${g.n}`)
  const over = (g: JournalGroup) => (g.overconfidence == null ? '—' : `${g.overconfidence > 0 ? '+' : ''}${Math.round(g.overconfidence * 100)} pts`)
  const OUT: Record<string, string> = { correct: 'correct', incorrect: 'incorrect', invalidated: 'invalidated' }
  const GROUPS: [string, string][] = [['by_view', 'Blind vs anchored'], ['by_timeframe', 'Timeframe'], ['by_source', 'Where logged'],
                                      ['by_regime', 'Engine regime at the call'], ['by_pattern', 'Patterns on the chart at the call']]
  // calibration chart geometry: x = stated confidence 50..100, y = share correct 0..100
  const W = 300, H = 220, P = 30
  const x = (c: number) => P + ((c - 0.5) / 0.5) * (W - 2 * P)
  const y = (r: number) => H - P - r * (H - 2 * P)
  const canDelete = (e: { outcome: string | null; created_at: number }) =>
    !!page && e.outcome == null && page.now - e.created_at <= page.delete_window_s
</script>

<section class="journal-page">
  <h2>📓 Journal</h2>
  <p class="tag">Your calls, judged by a fixed rule once their time is up. It measures how well <b>you</b> read charts:
    when you say 70%, are you right about 70% of the time?</p>
  {#if error}<p class="error">{error}</p>{/if}
  {#if loading && !page}<p class="muted">Loading…</p>{/if}

  {#if page}
    {@const s = page.stats}
    <div class="cards">
      <div class="card"><span>Calls judged</span><b>{s.overall.n}</b><em>{s.pending} still running</em></div>
      <div class="card"><span>Right</span><b>{rate(s.overall)}</b><em>{s.overall.invalidated} hit the invalidation</em></div>
      <div class="card"><span>Brier score</span><b>{s.overall.brier ?? '—'}</b><em>always saying 50% scores {s.baseline_brier}; lower is better</em></div>
      <div class="card"><span>Overconfidence</span><b>{over(s.overall)}</b><em>average confidence minus share right{s.overall.n ? ` (${s.overall.n} calls)` : ''}</em></div>
    </div>

    <div class="calib">
      <svg viewBox="0 0 {W} {H}" role="img" aria-label="calibration curve">
        <line x1={x(0.5)} y1={y(0.5)} x2={x(1)} y2={y(1)} class="diag" />
        {#each [0.5, 0.6, 0.7, 0.8, 0.9, 1] as c}<text x={x(c)} y={H - 10} class="ax">{Math.round(c * 100)}</text>{/each}
        {#each [0, 0.5, 1] as r}<text x="2" y={y(r) + 3} class="ax left">{Math.round(r * 100)}%</text>{/each}
        {#each s.curve.filter((b) => b.rate != null) as b}
          <circle cx={x(b.mean_confidence ?? 0.5)} cy={y(b.rate ?? 0)} r="5" class="pt" />
        {/each}
        <text x={x(0.75)} y="14" class="ax mid">stated confidence → · ↑ share right · diagonal = perfectly calibrated</text>
      </svg>
      <table>
        <thead><tr><th>you said</th><th>calls</th><th>right</th></tr></thead>
        <tbody>
          {#each s.curve as b}
            <tr><td>{b.bin}%</td><td>{b.n}</td><td>{b.n === 0 ? '—' : b.rate != null ? `${pct(b.rate)} (${b.hits})` : `${b.hits} of ${b.n}`}</td></tr>
          {/each}
        </tbody>
      </table>
    </div>
    <p class="muted small">A dot appears for a confidence band once it has {s.min_n}+ judged calls; below that the table shows counts.</p>

    {#each GROUPS as [key, title]}
      {@const g = (s as any)[key] as Record<string, JournalGroup>}
      {#if Object.keys(g).length}
        <h3>{title}</h3>
        <div class="tablewrap"><table>
          <thead><tr><th></th><th>calls</th><th>right</th><th>Brier</th><th>overconfidence</th></tr></thead>
          <tbody>{#each Object.entries(g) as [k, v]}<tr><td>{k}</td><td>{v.n}</td><td>{rate(v)}</td><td>{v.brier ?? '—'}</td><td>{over(v)}</td></tr>{/each}</tbody>
        </table></div>
      {/if}
    {/each}

    <h3>Calls</h3>
    {#if page.entries.length}
      <div class="tablewrap"><table class="calls">
        <thead><tr><th>logged</th><th>market</th><th>call</th><th>engine then</th><th>result</th><th></th></tr></thead>
        <tbody>
          {#each page.entries as e}
            <tr>
              <td class="muted">{when(e.created_at)}<br /><span class="small">{e.source}{e.verdict_visible || e.explanation_visible ? ' · anchored' : ' · blind'}</span></td>
              <td><button class="link" onclick={() => onOpen?.(e.symbol, e.timeframe)}>{e.symbol} {e.timeframe}</button></td>
              <td><b class={e.direction}>{e.direction === 'up' ? '▲ up' : '▼ down'}</b> {e.confidence}% from {fmt(e.price)}
                <br /><span class="small muted">wrong at {fmt(e.invalidation)} · {e.horizon_value} {e.horizon_unit}</span>
                {#if e.note}<br /><span class="small">“{e.note}”</span>{/if}</td>
              <td class="small muted">{e.engine ? `${e.engine.bias}, ${e.engine.tier.replace('_', ' ')}` : '—'}</td>
              <td>{#if e.outcome}<span class="chip {e.outcome}">{OUT[e.outcome]}</span>
                  <br /><span class="small muted">closed at {e.end_close != null ? fmt(e.end_close) : '—'}</span>
                {:else}<span class="muted small">judged after {when(e.end_time)}</span>{/if}</td>
              <td>{#if canDelete(e)}<button class="small" onclick={() => remove(e.id)}>delete</button>{/if}</td>
            </tr>
          {/each}
        </tbody>
      </table></div>
    {:else}
      <p class="muted">No calls yet. Log one from the Analysis page or the Morning report, ideally with the engine's read hidden.</p>
    {/if}
    <details><summary class="small">How calls are judged — rule v{page.rule.version}</summary><p class="small muted">{page.rule.text}
      Calls can be deleted only within {page.delete_window_s / 60} minutes of logging.</p></details>
  {/if}
</section>

<style>
  .journal-page { max-width: 1000px; }
  .tag { color: #8b949e; margin: 0 0 12px; }
  .muted { color: #8b949e; }
  .small { font-size: 12px; }
  .error { color: #f85149; }
  .cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 10px; margin-bottom: 14px; }
  .card { border: 1px solid #30363d; border-radius: 8px; padding: 10px 12px; display: flex; flex-direction: column; gap: 2px; }
  .card span { font-size: 12px; color: #8b949e; text-transform: uppercase; letter-spacing: .04em; }
  .card b { font-size: 20px; }
  .card em { font-style: normal; font-size: 12px; color: #8b949e; }
  .calib { display: flex; flex-wrap: wrap; gap: 16px; align-items: flex-start; }
  svg { width: 100%; max-width: 360px; background: #0d1117; border: 1px solid #30363d; border-radius: 8px; }
  .diag { stroke: #30363d; stroke-dasharray: 4 3; }
  .pt { fill: #58a6ff; }
  .ax { fill: #6e7681; font-size: 9px; text-anchor: middle; }
  .ax.mid { font-size: 8px; }
  .ax.left { text-anchor: start; }
  h3 { margin: 18px 0 6px; font-size: 15px; }
  .tablewrap { overflow-x: auto; }
  table { border-collapse: collapse; font-size: 13px; }
  .tablewrap table, table.calls { width: 100%; }
  th, td { text-align: left; padding: 5px 8px; border-bottom: 1px solid #161b22; vertical-align: top; }
  th { color: #8b949e; font-weight: 500; }
  b.up { color: #3fb950; }
  b.down { color: #f85149; }
  .chip { border: 1px solid #30363d; border-radius: 10px; padding: 1px 8px; font-size: 12px; }
  .chip.correct { color: #3fb950; border-color: #238636; }
  .chip.incorrect, .chip.invalidated { color: #f85149; border-color: #da3633; }
  button { background: #21262d; color: #c9d1d9; border: 1px solid #30363d; border-radius: 6px; padding: 3px 8px; cursor: pointer; }
  button.link { background: none; border: none; color: #58a6ff; padding: 0; }
  details { margin-top: 12px; }
</style>
