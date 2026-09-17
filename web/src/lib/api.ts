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
export interface Point { time: number; value: number }
export interface Indicators {
  volume_ma: Point[]; rsi: Point[]; adx: Point[]; atr: Point[]
  macd: { line: Point[]; signal: Point[]; hist: Point[] }
}
export interface ChartData {
  candles: Candle[]
  price_precision: number
  min_move: number
  total_bars: number
  indicators: Indicators
  overlays: {
    levels: Level[]; swings: SwingMarker[]; fibonacci: Fib | null; marker: Marker | null
    patterns: Pattern[]; divergence: Divergence | null
    regime?: { time: number; label: string }[]   // TEMP: Feature-6 eyeball strip
  }
}
// Which overlays/sub-panes are drawn (persisted to localStorage; see App.svelte).
export interface PanelToggles {
  levels: boolean; fib: boolean; swings: boolean; patterns: boolean; marker: boolean
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

async function get<T>(path: string): Promise<T> {
  const r = await fetch(API_BASE + path)
  if (!r.ok) throw new Error(`${r.status}: ${await r.text()}`)
  return r.json() as Promise<T>
}

export const getPairs = () => get<Pair[]>('/pairs')
export const getTimeframes = () => get<string[]>('/timeframes')
export const getAnalysis = (
  symbol: string, timeframe: string, explain = false, context = true, asOfBar: number | null = null,
) =>
  get<Analysis>(
    `/analysis?symbol=${encodeURIComponent(symbol)}&timeframe=${timeframe}&explain=${explain}` +
      `&context=${context}` + (asOfBar != null ? `&as_of_bar=${asOfBar}` : ''),
  )
