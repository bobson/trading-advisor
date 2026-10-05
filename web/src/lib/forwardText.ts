// Simplification pass 1 — the morning record in plain words, shared by the Morning report and the
// box on Analysis. Wording only: every fact comes from the frozen read and the fixed rule.
import { CAUTION_STATUSES, type ForwardRead, type MorningSummary } from './api'

export const fmtPrice = (x: number | null) => (x == null ? '—' : Math.abs(x) >= 100
  ? x.toLocaleString(undefined, { maximumFractionDigits: 2 }) : Number(x.toPrecision(6)).toString())

/** ✓ / ✗ / – for a judged read (expired / ambiguous / unscorable are neither right nor wrong). */
export function mark(r: ForwardRead): '✓' | '✗' | '–' {
  if (r.outcome === 'followed_through' || r.outcome === 'correct') return '✓'
  if (r.outcome === 'invalidated' || r.outcome === 'missed_move') return '✗'
  return '–'
}

/** What the engine said, in one sentence. */
export function readSentence(r: ForwardRead): string {
  if (r.read_kind === 'directional')
    return `${r.direction === 'bullish' ? '▲ Up' : '▼ Down'} read at ${fmtPrice(r.price)}: aiming for ${fmtPrice(r.next_level)}, wrong below/above ${fmtPrice(r.invalidation)}`
      .replace('wrong below/above', r.direction === 'bullish' ? 'wrong below' : 'wrong above')
  return `No setup at ${fmtPrice(r.price)}: expected to stay between ${fmtPrice(r.range_low)} and ${fmtPrice(r.range_high)}`
}

/** What happened, in one sentence. */
export function outcomeSentence(r: ForwardRead): string {
  const bars = `${r.horizon} candles`
  switch (r.outcome) {
    case 'followed_through': return `reached ${fmtPrice(r.next_level)} first — followed through`
    case 'invalidated': return `hit ${fmtPrice(r.invalidation)} first — invalidated`
    case 'expired': return `touched neither level within ${bars} — expired (neither right nor wrong)`
    case 'ambiguous': return 'touched both levels inside one candle — can\'t tell which came first'
    case 'correct': return `stayed inside the range for ${bars} — correct`
    case 'missed_move': return `left the range within ${bars} — missed move`
    case 'unscorable': return 'had no levels to judge it by — unscorable'
    default: return `not judged yet (judged after ${bars})`
  }
}

const COIN: Record<string, string> = {
  followed_through: 'followed through', invalidated: 'invalidated', expired: 'expired', ambiguous: 'ambiguous',
}
export const coinSentence = (r: ForwardRead) =>
  r.baseline_direction ? `A coin flip said ${r.baseline_direction === 'bullish' ? 'up' : 'down'} → ${COIN[r.baseline_outcome ?? ''] ?? '—'}.` : ''

/** The cautions frozen with the read, split into ones history backs (or that are arithmetic) and the rest. */
export function cautionsAt(r: ForwardRead, labels: Record<string, string>, status: Record<string, string>) {
  if (r.caution == null) return null                                        // before cautions were recorded
  const on = Object.entries(r.caution).filter(([, v]) => v).map(([k]) => k)
  const counted = on.filter((k) => !status[k] || CAUTION_STATUSES.includes(status[k]))
  const info = on.filter((k) => !counted.includes(k))
  return { counted: counted.map((k) => labels[k] ?? k), info: info.map((k) => labels[k] ?? k) }
}

/** "Why it may have gone wrong" for a ✗ read; flagged cautions on a ✓ read are said too, so a
 *  caution never reads as "this means a miss". */
export function whySentence(r: ForwardRead, labels: Record<string, string>, status: Record<string, string>): string {
  const c = cautionsAt(r, labels, status)
  const m = mark(r)
  if (c == null) return 'Cautions weren\'t recorded for reads this old.'
  const extra = c.info.length ? ` (also on, but with no measured effect: ${c.info.join(', ').toLowerCase()})` : ''
  if (m === '✗') {
    if (r.read_kind === 'range') return 'No-setup ranges are narrow (about 2 ATR) — over a day or more, price usually leaves them.'
    return c.counted.length
      ? `Flagged at the time: ${c.counted.join(', ').toLowerCase()}${extra}.`
      : `Nothing was flagged${extra} — the read was simply wrong. Reads like this go either way about as often as a coin flip.`
  }
  if (m === '✓' && c.counted.length) return `Right despite: ${c.counted.join(', ').toLowerCase()}.`
  return ''
}

const pct = (n: number, d: number) => (d ? `${Math.round((n / d) * 100)}%` : '—')

/** The record in one line: directional reads that followed through vs a coin flip on the same reads. */
export function summarySentence(s: MorningSummary | undefined, minN = 20): string {
  if (!s) return ''
  const d = s.directional, n = d.engine.n
  const parts: string[] = []
  if (n) {
    const c = d.engine.counts, b = d.baseline?.counts
    const enough = n >= minN
    parts.push(`Directional reads: ${c.followed_through} of ${n} followed through${enough ? ` (${pct(c.followed_through, n)})` : ''} ` +
      `and ${c.invalidated} were invalidated; a coin flip on the same reads: ${b?.followed_through ?? 0} and ${b?.invalidated ?? 0}.` +
      `${enough ? '' : ` Too early to tell — under ${minN} reads.`}`)
  } else parts.push('No directional read judged yet.')
  if (s.range.n) parts.push(`No-setup reads: ${s.range.counts.correct} of ${s.range.n} stayed in their range.`)
  return parts.join(' ')
}
