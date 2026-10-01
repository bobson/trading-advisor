<script lang="ts">
  // ROADMAP D2: every pre-registered experiment, failures included, and how well you predict your own
  // results. Read-only: experiments are registered (and run) from the scripts, and can't be edited.
  import { getExperiments, type Experiment, type ExperimentsPage } from './api'

  let page = $state<ExperimentsPage | null>(null)
  let error = $state<string | null>(null)
  getExperiments().then((p) => (page = p)).catch((e) => (error = e.message))

  const when = (t: number) => new Date(t * 1000).toLocaleDateString()
  const num = (x: number | null) => (x == null ? '—' : Math.abs(x) < 1 ? Number(x.toPrecision(3)).toString() : x.toLocaleString(undefined, { maximumFractionDigits: 3 }))
  const result = (e: Experiment) => e.ran_at == null ? 'not run yet'
    : `${num(e.value)}${e.n ? ` (n=${e.n})` : ''} — ${e.passed ? 'passed' : 'did not pass'}`
  const corrected = (e: Experiment) => e.ran_at == null ? '' : e.passed_corrected == null
    ? `not correctable (not a rate) · ${e.variations} variation${e.variations === 1 ? '' : 's'}`
    : `${e.passed_corrected ? 'passes' : 'does not pass'} at α ${num(e.corrected_alpha)} (p ${num(e.p_value)}, ${e.variations} variation${e.variations === 1 ? '' : 's'})`
</script>

<section class="exp">
  <h2>🧪 Experiments</h2>
  <p class="tag">Every backtest is registered before it runs: the hypothesis, the exact parameters, the success
    threshold and your prediction, hashed and never editable. Failures stay on the record.</p>
  {#if error}<p class="error">{error}</p>{/if}
  {#if page}
    {@const s = page.summary}
    <div class="cards">
      <div class="card"><span>Registered</span><b>{s.registered}</b><em>{s.never_ran} never run</em></div>
      <div class="card"><span>Results</span><b>{s.passed} passed · {s.misses} missed</b><em>of {s.ran} run</em></div>
      <div class="card"><span>Your predictions</span><b>{s.prediction_n ? `${s.prediction_hits} of ${s.prediction_n}` : '—'}</b><em>times you called pass/fail right</em></div>
    </div>
    {#if Object.keys(page.questions).length}
      <h3>Questions</h3>
      <div class="tablewrap"><table>
        <thead><tr><th>question</th><th>variations</th><th>run</th><th>passed</th><th>passed after correction</th></tr></thead>
        <tbody>{#each Object.entries(page.questions) as [q, v]}<tr><td>{q}</td><td>{v.registered}</td><td>{v.ran}</td><td>{v.passed}</td><td>{v.passed_corrected}</td></tr>{/each}</tbody>
      </table></div>
    {/if}
    <h3>All experiments</h3>
    {#if page.experiments.length}
      <div class="list">
        {#each page.experiments as e}
          <div class="item" class:miss={e.ran_at != null && !e.passed} class:old={e.superseded}>
            <div><b>#{e.id}</b> <span class="muted">{when(e.created_at)} · {e.script} · hash {e.hash}{e.supersedes ? ` · supersedes #${e.supersedes}` : ''}{e.superseded ? ' · superseded' : ''}</span></div>
            <div class="q">{e.question}</div>
            <div>{e.hypothesis}</div>
            <div class="muted small">success: {e.metric} {e.direction} {e.threshold}{e.baseline != null ? ` (no effect = ${e.baseline})` : ''} · you predicted
              {e.predicted_pass ? 'pass' : 'fail'}{e.predicted_value != null ? ` (${e.predicted_value})` : ''}</div>
            <div class="res">{result(e)}{#if e.ran_at != null}{' · '}<span class="muted">prediction {!!e.passed === !!e.predicted_pass ? 'right' : 'wrong'}</span>{/if}</div>
            {#if corrected(e)}<div class="muted small">{corrected(e)}</div>{/if}
            <details><summary class="small">parameters</summary><pre>{JSON.stringify(e.params, null, 1)}</pre></details>
          </div>
        {/each}
      </div>
    {:else}
      <p class="muted">No experiments yet. Register one from a script, e.g.<br />
        <code>python scripts/backtest.py --symbol BTC/USDT --timeframe 1d --register --question "…" --hypothesis "…"
        --metric win_rate --threshold 0.55 --baseline 0.5 --predict fail</code></p>
    {/if}
  {/if}
</section>

<style>
  .exp { max-width: 1000px; }
  .tag { color: #8b949e; margin: 0 0 12px; }
  .muted { color: #8b949e; }
  .small { font-size: 12px; }
  .error { color: #f85149; }
  .cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 10px; margin-bottom: 12px; }
  .card { border: 1px solid #30363d; border-radius: 8px; padding: 10px 12px; display: flex; flex-direction: column; gap: 2px; }
  .card span { font-size: 12px; color: #8b949e; text-transform: uppercase; letter-spacing: .04em; }
  .card b { font-size: 18px; }
  .card em { font-style: normal; font-size: 12px; color: #8b949e; }
  h3 { margin: 16px 0 6px; font-size: 15px; }
  .tablewrap { overflow-x: auto; }
  table { border-collapse: collapse; width: 100%; font-size: 13px; }
  th, td { text-align: left; padding: 5px 8px; border-bottom: 1px solid #161b22; }
  th { color: #8b949e; font-weight: 500; }
  .list { display: flex; flex-direction: column; gap: 8px; }
  .item { border: 1px solid #30363d; border-radius: 8px; padding: 10px 12px; font-size: 14px; }
  .item.miss { border-left: 3px solid #da3633; }
  .item.old { opacity: .7; }
  .q { color: #c9d1d9; font-weight: 600; margin: 2px 0; }
  .res { margin-top: 4px; }
  pre { font-size: 12px; color: #8b949e; white-space: pre-wrap; }
  code { font-size: 12px; }
</style>
