// Typed client for the Phase-24 API. Keep these types in step with src/service/serialize.py.
const API_BASE = (import.meta as any).env?.VITE_API_BASE ?? 'http://127.0.0.1:8000'

export interface Pair { symbol: string; asset_class: string; label: string }
export interface Candle { time: number; open: number; high: number; low: number; close: number; volume: number | null }
export interface Level { price: number; role: string; touches: number }
export interface SwingMarker { time: number; price: number; kind: string }
export interface Fib { direction: string; levels: Record<string, number> }
export interface Marker { time: number; bias: string }
export interface PatternPoint { time: number; price: number }
export interface Pattern {
  type: string; direction: string; state: string; quality: number | null
  points: PatternPoint[]; lines: PatternPoint[][]
  breakout_level: number | null; invalidation_level: number | null; target: number | null
}
export interface Divergence { kind: string; reason: string; times: number[] }
export interface CandlePattern { time: number; direction: string; label: string }
export interface Point { time: number; value: number }
export interface Indicators {
  volume_ma: Point[]; rsi: Point[]; adx: Point[]; atr: Point[]
  macd: { line: Point[]; signal: Point[]; hist: Point[] }
}
export interface MovingAverage { key: string; period: number; values: Point[] }
export interface ChartData {
  candles: Candle[]
  price_precision: number
  min_move: number
  total_bars: number
  indicators: Indicators
  mas: MovingAverage[]
  overlays: {
    levels: Level[]; swings: SwingMarker[]; fibonacci: Fib | null; marker: Marker | null
    patterns: Pattern[]; divergence: Divergence | null; candle_patterns: CandlePattern[]
    trendlines?: TrendLine[]
    regime?: { time: number; label: string }[]   // TEMP: Feature-6 eyeball strip
  }
}
// Which overlays/sub-panes are drawn (persisted to localStorage; see App.svelte).
export interface TrendLine {
  kind: 'support' | 'resistance'; direction: 'rising' | 'falling' | 'flat'
  anchors: { time: number; price: number }[]; points: { time: number; price: number }[]
}

export interface PanelToggles {
  trendlines: boolean; levels: boolean; fib: boolean; swings: boolean; patterns: boolean; marker: boolean; ma: boolean
  volume: boolean; rsi: boolean; macd: boolean; adx: boolean; atr: boolean
}
export interface Confluence {
  bias: string; triggered: boolean; confidence: number; agreeing_categories: number
  categories?: Record<string, string>
}
export interface BaseRate { bias: string; win_rate: number; n: number; horizon: number }
export interface Analysis {
  market: { symbol: string; timeframe: string; last_close: number }
  confluence: Confluence
  base_rate: BaseRate | null
  explanation: string | null
  chart: ChartData
  as_of_bar: number | null
  [k: string]: any
}

// --- Feature 9: risk of ruin & position sizing ---
export interface RiskResult {
  inputs: Record<string, number>
  ruin: {
    analytic: number
    monte_carlo: { prob: number; ci_low: number; ci_high: number; unresolved: number; n_paths: number }
  }
  kelly: { edge: number; full: number; half: number; quarter: number; has_edge: boolean }
  kelly_drawdowns: Record<string, { fraction: number; median_drawdown: number; p90_drawdown: number }>
  table: { payoff_ratio: number; win_rates: number[]; drawdown: number; target: number; rows: { risk_fraction: number; ruin: number[] }[] }
  position?: { risk_amount: number; stop_distance: number; stop_distance_pct: number; units: number; position_value: number; leverage: number }
  position_error?: string
}
export interface MeasuredStats {
  win_rate: number | null; win_rate_ci: [number, number] | null
  payoff_ratio: number | null; n: number; source: string; thin: boolean
}

async function get<T>(path: string): Promise<T> {
  const r = await fetch(API_BASE + path)
  if (!r.ok) throw new Error(`${r.status}: ${await r.text()}`)
  return r.json() as Promise<T>
}

async function send<T>(method: string, path: string, body?: unknown): Promise<T> {
  const r = await fetch(API_BASE + path, {
    method,
    headers: body !== undefined ? { 'content-type': 'application/json' } : undefined,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  })
  if (!r.ok) throw new Error(`${r.status}: ${await r.text()}`)
  return r.json() as Promise<T>
}

export const getRisk = (p: {
  win_rate: number; payoff_ratio: number; risk_fraction: number; account: number; entry?: number; stop?: number
}) => {
  const q = new URLSearchParams({
    win_rate: String(p.win_rate), payoff_ratio: String(p.payoff_ratio),
    risk_fraction: String(p.risk_fraction), account: String(p.account),
  })
  if (p.entry != null) q.set('entry', String(p.entry))
  if (p.stop != null) q.set('stop', String(p.stop))
  return get<RiskResult>('/risk?' + q.toString())
}
export const getMeasured = (symbol: string, timeframe: string) =>
  get<MeasuredStats>(`/risk/measured?symbol=${encodeURIComponent(symbol)}&timeframe=${timeframe}`)

// --- Paper-trading simulator ---
export interface Trade {
  id: number; symbol: string; timeframe: string | null; side: string
  amount_usd: number; price: number; entry_source: string | null; units: number
  opened_at: number; status: string; closed_at: number | null; exit_price: number | null
  exit_source: string | null; realized_pnl: number | null
  snapshot: Record<string, any>; note: string | null
}
export interface TradePnl { closed: number; wins: number; realized_total: number; win_rate: number | null }
export interface TradeState { trades: Trade[]; pnl: TradePnl }
export interface Position {
  flat: boolean; id?: number; side?: string; amount_usd?: number; entry?: number
  units?: number; price?: number; unrealized_pnl?: number; unrealized_pct?: number; price_source?: string
}

export const getTrades = (symbol: string) =>
  get<TradeState>(`/trades?symbol=${encodeURIComponent(symbol)}`)
export const getPosition = (symbol: string, lastClose?: number | null) =>
  get<Position>(`/trades/position?symbol=${encodeURIComponent(symbol)}` +
    (lastClose != null ? `&last_close=${lastClose}` : ''))
export const postTrade = (body: {
  symbol: string; side: string; amount_usd: number
  timeframe?: string; last_close?: number | null; snapshot?: Record<string, any> | null
}) => send<{ result: any } & TradeState>('POST', '/trades', body)
export const deleteTrade = (id: number) => send<{ deleted: number }>('DELETE', `/trades/${id}`)

export const getPairs = () => get<Pair[]>('/pairs')
export const getTimeframes = () => get<string[]>('/timeframes')
// limit = candles returned. Default 5000 (the API cap) so the chart holds the FULL history and
// you can pan all the way back, not just the last 500 bars.
export const getAnalysis = (
  symbol: string, timeframe: string, explain = false, context = true,
  asOfBar: number | null = null, limit = 5000, explanationStyle = 'brief',
) =>
  get<Analysis>(
    `/analysis?symbol=${encodeURIComponent(symbol)}&timeframe=${timeframe}&explain=${explain}` +
      `&context=${context}&limit=${limit}&explanation_style=${explanationStyle}` +
      (asOfBar != null ? `&as_of_bar=${asOfBar}` : ''),
  )
