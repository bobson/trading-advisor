<script lang="ts">
  // ROADMAP D5: your declared rules, checked on every paper trade and journal call. Violations are
  // recorded, never blocked. Neutral numbers with counts — a mirror, not a scolding.
  import { getDiscipline, postRules, type DisciplineOutcome, type DisciplinePage, type TradingRules } from './api'

  const REGIMES = ['trending_up', 'trending_down', 'ranging', 'volatile', 'quiet']
  let page = $state<DisciplinePage | null>(null)
  let error = $state<string | null>(null)
  let editing = $state(false)
  let form = $state<TradingRules & { symbols: string; note: string }>({ symbols: '', note: '' })

  async function load() {
    try { page = await getDiscipline() } catch (e: any) { error = e.message }
  }
  load()

  function edit() {
    const r = page?.rules?.rules ?? {}
    form = { ...r, required_regimes: [...(r.required_regimes ?? [])], symbols: (r.allowed_symbols ?? []).join(', '), note: '' }
    editing = true
  }
  async function save() {
    error = null
    const num = (x: any) => (x === '' || x == null ? null : Number(x))
    try {
      await postRules({
        account_size: num(form.account_size) ?? undefined, max_position_pct: num(form.max_position_pct) ?? undefined,
        max_open_positions: num(form.max_open_positions) ?? undefined, min_categories_aligned: num(form.min_categories_aligned) ?? undefined,
        max_per_week: num(form.max_per_week) ?? undefined, cooling_off_hours: num(form.cooling_off_hours) ?? undefined,
        required_regimes: form.required_regimes?.length ? form.required_regimes : undefined,
        allowed_symbols: form.symbols.split(',').map((x) => x.trim()).filter(Boolean),
        note: form.note,
      } as any)
      editing = false
      await load()
    } catch (e: any) { error = String(e.message).replace(/^\d+: /, '').replace(/^\{"detail":"(.*)"\}$/, '$1') }
  }

  const when = (t: number) => new Date(t * 1000).toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' })
  const out = (o: DisciplineOutcome, kind: string) => o.n === 0 ? '—'
    : `${o.n} ${kind === 'trade' ? 'trades' : 'calls'} · ${o.judged ? (o.win_rate != null ? `${Math.round(o.win_rate * 100)}% won (${o.wins} of ${o.judged})` : `${o.wins} of ${o.judged} won`) : 'none judged yet'}`
      + (o.pnl_total != null ? ` · P&L ${o.pnl_total >= 0 ? '+' : ''}${o.pnl_total.toLocaleString()}` : '')
  const ruleText = (r: TradingRules) => [
    r.account_size ? `account ${r.account_size.toLocaleString()}` : '',
    r.max_position_pct ? `max ${r.max_position_pct}% per position` : '',
    r.max_open_positions ? `max ${r.max_open_positions} open` : '',
    r.required_regimes?.length ? `only in ${r.required_regimes.join(' / ')}` : '',
    r.min_categories_aligned ? `≥ ${r.min_categories_aligned} categories agreeing` : '',
    r.allowed_symbols?.length ? `markets: ${r.allowed_symbols.join(', ')}` : '',
    r.max_per_week ? `max ${r.max_per_week} per week` : '',
    r.cooling_off_hours ? `${r.cooling_off_hours} h cooling-off after a loss` : '',
  ].filter(Boolean).join(' · ') || 'no rules declared'
</script>

<section class="disc">
  <h2>🧭 Discipline</h2>
  <p class="tag">Your own rules, checked on every paper trade and journal call. Breaking one is recorded, never
    blocked. Over time this shows, with counts, how your disciplined decisions did against the others.</p>
  {#if error}<p class="error">{error}</p>{/if}

  {#if page}
    <div class="box">
      <h3>My rules {#if page.rules}<span class="muted small">version {page.rules.version}, since {when(page.rules.created_at)}</span>{/if}</h3>
      {#if !editing}
        <p>{page.rules ? ruleText(page.rules.rules) : 'No rules declared yet.'}</p>
        <button onclick={edit}>{page.rules ? 'Declare a new version' : 'Declare my rules'}</button>
        <span class="muted small">Old versions stay; past decisions are checked against the version active then.</span>
      {:else}
        <div class="grid">
          <label>Account size <input type="number" bind:value={form.account_size} /></label>
          <label>Max % of account per position <input type="number" step="0.1" bind:value={form.max_position_pct} /></label>
          <label>Max open positions <input type="number" bind:value={form.max_open_positions} /></label>
          <label>Min categories agreeing <input type="number" bind:value={form.min_categories_aligned} /></label>
          <label>Max decisions per week <input type="number" bind:value={form.max_per_week} /></label>
          <label>Cooling-off after a loss (hours) <input type="number" bind:value={form.cooling_off_hours} /></label>
          <label class="wide">Only these markets (comma-separated) <input type="text" bind:value={form.symbols} placeholder="BTC/USDT, EUR/USD" /></label>
        </div>
        <div class="regimes">Only in these regimes:
          {#each REGIMES as r}<label><input type="checkbox" value={r} bind:group={form.required_regimes} /> {r.replace('_', ' ')}</label>{/each}
        </div>
        <label class="wide">Why this change (optional) <input type="text" bind:value={form.note} /></label>
        <div><button class="go" onclick={save}>Save as a new version</button> <button onclick={() => (editing = false)}>cancel</button>
          <span class="muted small">Leave a field empty to not have that rule.</span></div>
      {/if}
    </div>

    <h3>Following vs breaking your rules</h3>
    <div class="tablewrap"><table>
      <thead><tr><th></th><th>followed every rule</th><th>broke at least one</th></tr></thead>
      <tbody>
        {#each ['trade', 'call'] as kind}
          {@const c = page.compare[kind as 'trade' | 'call']}
          <tr><td>{kind === 'trade' ? 'Paper trades' : 'Journal calls'}</td><td>{out(c.followed, kind)}</td><td>{out(c.broke, kind)}</td></tr>
        {/each}
      </tbody>
    </table></div>
    <p class="muted small">A % only with {page.min_n}+ judged. Decisions made before you declared any rules aren't counted here.</p>
    {#each ['trade', 'call'] as kind}
      {@const br = page.compare[kind as 'trade' | 'call'].by_rule}
      {#if Object.keys(br).length}
        <p class="small"><b>{kind === 'trade' ? 'Trades' : 'Calls'} by rule broken:</b>
          {Object.entries(br).map(([k, v]) => `${page?.labels[k] ?? k}: ${out(v, kind)}`).join(' · ')}</p>
      {/if}
    {/each}

    {#if page.observations.length}
      <h3>Observations <span class="muted small">after the fact — patterns worth noticing, not verdicts</span></h3>
      <ul class="obs">{#each page.observations.slice(0, 20) as o}<li>{o.t ? when(o.t) + ': ' : ''}{o.text}</li>{/each}</ul>
    {/if}

    <h3>Weekly review</h3>
    {#if page.weekly.length}
      <div class="tablewrap"><table>
        <thead><tr><th>week</th><th>trades</th><th>calls</th><th>broke a rule</th><th>judged · won</th><th>noticed</th></tr></thead>
        <tbody>{#each page.weekly as w}
          <tr><td>{w.week}</td><td>{w.trades}</td><td>{w.calls}</td>
            <td>{w.broke}{w.rules_broken.length ? ` (${w.rules_broken.map((r) => page?.labels[r] ?? r).join(', ')})` : ''}</td>
            <td>{w.judged} · {w.wins}</td><td class="small muted">{w.observations.join('; ') || '—'}</td></tr>
        {/each}</tbody>
      </table></div>
    {:else}
      <p class="muted">No paper trades or journal calls yet.</p>
    {/if}

    {#if page.decisions.some((d) => d.violations.length)}
      <h3>Recent decisions that broke a rule</h3>
      <ul class="obs">{#each page.decisions.filter((d) => d.violations.length).slice(0, 20) as d}
        <li>{when(d.t)} · {d.kind === 'trade' ? 'trade' : 'call'} on {d.symbol}: {d.violations.map((v) => v.detail).join('; ')}</li>
      {/each}</ul>
    {/if}
  {/if}
</section>

<style>
  .disc { max-width: 1000px; }
  .tag { color: #8b949e; margin: 0 0 12px; }
  .muted { color: #8b949e; }
  .small { font-size: 12px; }
  .error { color: #f85149; }
  .box { border: 1px solid #30363d; border-radius: 8px; padding: 10px 12px; margin-bottom: 12px; font-size: 14px; }
  h3 { margin: 16px 0 6px; font-size: 15px; }
  .box h3 { margin-top: 0; }
  .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 8px 14px; margin: 8px 0; }
  .grid label, .wide { display: flex; flex-direction: column; gap: 3px; font-size: 13px; color: #8b949e; }
  .wide { margin: 6px 0; }
  .regimes { display: flex; flex-wrap: wrap; gap: 10px; align-items: center; font-size: 13px; color: #8b949e; margin: 6px 0; }
  .regimes label { color: #c9d1d9; }
  input { background: #0d1117; color: #c9d1d9; border: 1px solid #30363d; border-radius: 6px; padding: 4px 8px; font-size: 14px; }
  button { background: #21262d; color: #c9d1d9; border: 1px solid #30363d; border-radius: 6px; padding: 5px 12px; cursor: pointer; }
  button.go { border-color: #238636; }
  .tablewrap { overflow-x: auto; }
  table { border-collapse: collapse; width: 100%; font-size: 13px; }
  th, td { text-align: left; padding: 5px 8px; border-bottom: 1px solid #161b22; vertical-align: top; }
  th { color: #8b949e; font-weight: 500; }
  .obs { margin: 0; padding-left: 18px; font-size: 13px; color: #c9d1d9; }
  @media (max-width: 640px) { input { font-size: 16px; } }
</style>
