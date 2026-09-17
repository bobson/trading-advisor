<script lang="ts">
  import { onMount } from 'svelte'
  import { createChart, type IChartApi, type ISeriesApi } from 'lightweight-charts'
  import type { ChartData, PanelToggles, Pattern } from './api'

  let { data, toggles }: { data: ChartData | null; toggles: PanelToggles } = $props()

  let root: HTMLDivElement
  let charts: IChartApi[] = []
  let mainSeries: ISeriesApi<'Candlestick'> | null = null
  let syncing = false

  const isMobile = () => window.innerWidth < 640
  const MAIN_H = () => (isMobile() ? 300 : 380)
  const SUB_H = 110

  const GRID = { vertLines: { color: '#1c2128' }, horzLines: { color: '#1c2128' } }
  const LAYOUT = { background: { color: '#0e1117' }, textColor: '#c9d1d9' }
  // Fixed price-scale width so every pane's left edge lines up under the candles.
  const baseOpts = (h: number) => ({
    height: h, layout: LAYOUT, grid: GRID,
    timeScale: { timeVisible: true, borderColor: '#30363d' },
    rightPriceScale: { borderColor: '#30363d', minimumWidth: 68 },
    handleScroll: true, handleScale: true,
  })

  function newPane(label: string, h: number): IChartApi {
    const wrap = document.createElement('div')
    wrap.className = 'pane'
    const tag = document.createElement('span')
    tag.className = 'pane-label'; tag.textContent = label
    wrap.appendChild(tag)
    root.appendChild(wrap)
    const c = createChart(wrap, { ...baseOpts(h), width: root.clientWidth } as any)
    charts.push(c)
    return c
  }

  function teardown() {
    for (const c of charts) c.remove()
    charts = []; mainSeries = null
  }

  // Sync every pane's VISIBLE TIME RANGE (time-based, so it aligns across panes even when the
  // sub-series have different lengths from warm-up NaNs). A reentrancy guard stops A->B->A loops.
  function syncTimeScales() {
    for (const src of charts) {
      src.timeScale().subscribeVisibleTimeRangeChange((range) => {
        if (syncing || !range) return
        syncing = true
        for (const dst of charts) if (dst !== src) dst.timeScale().setVisibleRange(range as any)
        syncing = false
      })
    }
  }

  // TEMP (Feature 6 eyeball): regime -> strip color.
  const REGIME_COLORS: Record<string, string> = {
    trending_up: '#26a641', trending_down: '#f85149', ranging: '#8b949e',
    volatile: '#d29922', quiet: '#3b6ea5',
  }
  const regimeColor = (label: string) => REGIME_COLORS[label] ?? '#484f58'

  const patternStyle = (p: Pattern) => {
    if (p.state === 'failed') return { color: '#6e7681', width: 1, dashed: true }
    if (p.state === 'confirmed')
      return { color: p.direction === 'bearish' ? '#f85149' : '#26a641', width: 2, dashed: false }
    return { color: '#d29922', width: 2, dashed: true } // forming
  }

  onMount(() => {
    render()
    const ro = new ResizeObserver(() => {
      for (const c of charts) c.applyOptions({ width: root.clientWidth })
    })
    ro.observe(root)
    return () => { ro.disconnect(); teardown() }
  })

  // Rebuild whenever the data or the toggles change (simple + robust vs incremental updates).
  $effect(() => { data; toggles; render() })

  function render() {
    if (!root) return
    teardown()
    if (!data) return
    const prec = data.price_precision ?? 2
    const ov = data.overlays
    const ind = data.indicators

    // ---- main price pane ----
    const main = newPane('price', MAIN_H())
    const series = main.addCandlestickSeries({
      upColor: '#26a641', downColor: '#f85149',
      borderVisible: false, wickUpColor: '#26a641', wickDownColor: '#f85149',
      priceFormat: { type: 'price', precision: prec, minMove: data.min_move ?? 0.01 },
    })
    series.setData(data.candles as any)
    mainSeries = series

    if (toggles.levels) for (const lv of ov.levels)
      series.createPriceLine({
        price: lv.price, color: lv.role === 'support' ? '#26a641' : '#f85149',
        lineWidth: 1, lineStyle: 0, axisLabelVisible: true, title: `${lv.role} (${lv.touches})`,
      } as any)

    if (toggles.fib && ov.fibonacci)
      for (const [ratio, price] of Object.entries(ov.fibonacci.levels))
        series.createPriceLine({
          price, color: '#8b949e', lineWidth: 1, lineStyle: 2,
          axisLabelVisible: true, title: `fib ${(Number(ratio) * 100).toFixed(1)}%`,
        } as any)

    // Patterns: each as a line through its defining swings, styled by state, plus level lines.
    if (toggles.patterns) for (const p of ov.patterns) {
      const st = patternStyle(p)
      const line = main.addLineSeries({
        color: st.color, lineWidth: st.width as any, lineStyle: st.dashed ? 2 : 0,
        pointMarkersVisible: true, lastValueVisible: false, priceLineVisible: false,
      })
      const pts = dedupeByTime(p.points.map((pt) => ({ time: pt.time, value: pt.price })))
      line.setData(pts as any)
      const levelLine = (price: number | null, style: number, title: string) => {
        if (price == null) return
        series.createPriceLine({ price, color: st.color, lineWidth: 1, lineStyle: style,
          axisLabelVisible: true, title } as any)
      }
      levelLine(p.breakout_level, 0, `${p.type} neckline`)
      levelLine(p.target, 1, `${p.type} target`)
      levelLine(p.invalidation_level, 3, `${p.type} invalid`)
    }

    const markers: any[] = []
    if (toggles.swings) for (const s of ov.swings)
      markers.push({ time: s.time, position: s.kind === 'high' ? 'aboveBar' : 'belowBar',
        color: '#8b949e', shape: 'circle' })
    if (toggles.marker && ov.marker)
      markers.push({ time: ov.marker.time,
        position: ov.marker.bias === 'bullish' ? 'belowBar' : 'aboveBar',
        color: ov.marker.bias === 'bullish' ? '#26a641' : '#f85149',
        shape: ov.marker.bias === 'bullish' ? 'arrowUp' : 'arrowDown' })
    markers.sort((a, b) => a.time - b.time)
    series.setMarkers(markers as any)

    // ---- TEMP regime strip (Feature 6 eyeball): a full-height colored bar per candle ----
    if (ov.regime && ov.regime.length) {
      const c = newPane('regime', 40)
      const strip = c.addHistogramSeries({ priceLineVisible: false, lastValueVisible: false })
      strip.setData(ov.regime.map((r) => ({ time: r.time, value: 1, color: regimeColor(r.label) })) as any)
    }

    // ---- sub-panes ----
    if (toggles.volume) {
      const c = newPane('volume', SUB_H)
      const vol = c.addHistogramSeries({ priceFormat: { type: 'volume' }, priceLineVisible: false })
      vol.setData(data.candles.filter((k) => k.volume != null).map((k) => ({
        time: k.time, value: k.volume as number,
        color: k.close >= k.open ? '#26a64155' : '#f8514955',
      })) as any)
      const ma = c.addLineSeries({ color: '#58a6ff', lineWidth: 1, priceLineVisible: false, lastValueVisible: false })
      ma.setData(ind.volume_ma as any)
    }

    if (toggles.rsi) {
      const c = newPane('RSI', SUB_H)
      const rsi = c.addLineSeries({ color: '#d29922', lineWidth: 2, priceLineVisible: false })
      rsi.setData(ind.rsi as any)
      for (const [lvl, style] of [[70, 2], [30, 2]] as [number, number][])
        rsi.createPriceLine({ price: lvl, color: '#30363d', lineWidth: 1, lineStyle: style,
          axisLabelVisible: true } as any)
      const d = ov.divergence
      if (d && d.times.length) {
        const byTime = new Map(ind.rsi.map((p) => [p.time, p.value]))
        rsi.setMarkers(d.times.map((t) => ({
          time: t, position: d.kind === 'bearish' ? 'aboveBar' : 'belowBar',
          color: d.kind === 'bearish' ? '#f85149' : '#26a641', shape: 'circle',
          text: `${d.kind} div`,
        })).filter((m) => byTime.has(m.time)) as any)
      }
    }

    if (toggles.macd) {
      const c = newPane('MACD', SUB_H)
      const hist = c.addHistogramSeries({ priceLineVisible: false })
      hist.setData(ind.macd.hist.map((p) => ({
        time: p.time, value: p.value, color: p.value >= 0 ? '#26a64188' : '#f8514988',
      })) as any)
      c.addLineSeries({ color: '#58a6ff', lineWidth: 1, priceLineVisible: false, lastValueVisible: false })
        .setData(ind.macd.line as any)
      c.addLineSeries({ color: '#d29922', lineWidth: 1, priceLineVisible: false, lastValueVisible: false })
        .setData(ind.macd.signal as any)
    }

    if (toggles.adx) {
      const c = newPane('ADX', SUB_H)
      const adx = c.addLineSeries({ color: '#a371f7', lineWidth: 2, priceLineVisible: false })
      adx.setData(ind.adx as any)
      adx.createPriceLine({ price: 25, color: '#30363d', lineWidth: 1, lineStyle: 2,
        axisLabelVisible: true, title: 'trend' } as any)
    }

    if (toggles.atr) {
      const c = newPane('ATR', SUB_H)
      c.addLineSeries({ color: '#ec8e2c', lineWidth: 2, priceLineVisible: false })
        .setData(ind.atr as any)
    }

    syncTimeScales()
    main.timeScale().fitContent()   // propagates to the sub-panes via the sync subscription
  }

  // lightweight-charts requires strictly-increasing unique times.
  function dedupeByTime<T extends { time: number }>(rows: T[]): T[] {
    const seen = new Set<number>()
    return rows.filter((r) => (seen.has(r.time) ? false : (seen.add(r.time), true)))
      .sort((a, b) => a.time - b.time)
  }
</script>

<div bind:this={root} class="chart-root"></div>

<style>
  .chart-root { width: 100%; }
  .chart-root :global(.pane) { position: relative; margin-bottom: 2px; }
  .chart-root :global(.pane-label) {
    position: absolute; top: 4px; left: 8px; z-index: 3;
    font-size: 11px; letter-spacing: .04em; text-transform: uppercase;
    color: #8b949e; pointer-events: none;
  }
</style>
