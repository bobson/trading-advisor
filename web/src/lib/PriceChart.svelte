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
  const RIGHT_OFFSET = 25   // permanent empty bars after the last candle (clear of the price labels)

  const GRID = { vertLines: { color: '#1c2128' }, horzLines: { color: '#1c2128' } }
  const LAYOUT = { background: { color: '#0e1117' }, textColor: '#c9d1d9' }
  // Fixed price-scale width so every pane's left edge lines up under the candles.
  const baseOpts = (h: number, isMain = false) => ({
    height: h, layout: LAYOUT, grid: GRID,
    // Edge behavior (verified in a real headless browser — see verify/). Drag never zooms
    // (axisPressedMouseMove off). Left edge is a hard stop (fixLeftEdge). The right edge is a
    // BOUNDED hard stop applied manually below — fixRightEdge:true would jam the last candle
    // against the price-axis labels (it ignores rightOffset AND trailing whitespace), while
    // fixRightEdge:false alone lets the chart overscroll into empty space (reads as a zoom-out).
    // Only the MAIN pane fixes its left edge; sub-panes are passive followers, otherwise their
    // warm-up-trimmed data clamps the left edge and pushes it back onto the main through the sync.
    timeScale: {
      timeVisible: true, borderColor: '#30363d',
      fixLeftEdge: isMain, fixRightEdge: false, rightOffset: RIGHT_OFFSET,
    },
    rightPriceScale: { borderColor: '#30363d', minimumWidth: 68 },
    // Horizontal DRAG pans the time axis; ZOOM is wheel/pinch only. Axis-drag scaling is off, so
    // dragging (incl. on the time axis) never zooms — that was the "drag = zoom" bug.
    handleScroll: { mouseWheel: true, pressedMouseMove: true, horzTouchDrag: true, vertTouchDrag: false },
    handleScale: {
      mouseWheel: true, pinch: true,
      axisPressedMouseMove: { time: false, price: false },
      axisDoubleClickReset: { time: true, price: true },
    },
  })

  function newPane(label: string, h: number, isMain = false): IChartApi {
    const wrap = document.createElement('div')
    wrap.className = 'pane'
    const tag = document.createElement('span')
    tag.className = 'pane-label'; tag.textContent = label
    wrap.appendChild(tag)
    root.appendChild(wrap)
    const c = createChart(wrap, { ...baseOpts(h, isMain), width: root.clientWidth } as any)
    charts.push(c)
    return c
  }

  function teardown() {
    for (const c of charts) c.remove()
    charts = []; mainSeries = null
    // Also remove the .pane wrapper DIVS (each holds a label span). Removing only the chart
    // instances left stale, empty panes to accumulate across re-renders — their labels stacked
    // into garbled text at the top-left.
    if (root) root.replaceChildren()
  }

  // Sync by LOGICAL (bar-index) range, not time. Every pane is set on the SAME shared index axis
  // (see `axis` in render), so logical sync is exact and can't drift — time-range sync across
  // differing-length series was what made a drag creep into a zoom. A guard stops A->B->A loops.
  function syncTimeScales() {
    for (const src of charts) {
      src.timeScale().subscribeVisibleLogicalRangeChange((range) => {
        if (syncing || !range) return
        syncing = true
        for (const dst of charts) if (dst !== src) dst.timeScale().setVisibleLogicalRange(range as any)
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

    // ONE shared time axis for every pane: the candle times, then RIGHT_OFFSET future bars as
    // whitespace (the right-hand gap, now real index space). Every series is mapped onto this axis
    // — warm-up holes and the trailing gap become whitespace — so all charts share identical
    // logical indices. That makes logical-range sync exact (no drift -> no zoom) AND lets the view
    // include the gap (setVisibleLogicalRange to the last whitespace index isn't clamped away).
    const cTimes = data.candles.map((k) => k.time)
    const step = cTimes.length > 1 ? cTimes[cTimes.length - 1] - cTimes[cTimes.length - 2] : 86400
    const axis: number[] = cTimes.slice()
    for (let k = 1; k <= RIGHT_OFFSET; k++) axis.push(cTimes[cTimes.length - 1] + k * step)
    const whitespace = axis.slice(cTimes.length).map((t) => ({ time: t }))
    const align = (s: { time: number; value: number }[]) => {
      const m = new Map(s.map((p) => [p.time, p.value]))
      return axis.map((t) => (m.has(t) ? { time: t, value: m.get(t) } : { time: t }))
    }

    // ---- main price pane ----
    const main = newPane('price', MAIN_H(), true)
    const series = main.addCandlestickSeries({
      upColor: '#26a641', downColor: '#f85149',
      borderVisible: false, wickUpColor: '#26a641', wickDownColor: '#f85149',
      priceFormat: { type: 'price', precision: prec, minMove: data.min_move ?? 0.01 },
    })
    series.setData((data.candles as any[]).concat(whitespace))
    mainSeries = series

    // Moving averages overlaid on the price pane (50 = blue, 200 = gold), aligned to the axis.
    if (toggles.ma) for (const ma of data.mas ?? []) {
      const maLine = main.addLineSeries({
        color: ma.key === 'long' ? '#e3b341' : '#58a6ff', lineWidth: 2,
        priceLineVisible: false, lastValueVisible: true, title: `MA${ma.period}`,
        crosshairMarkerVisible: false,
      })
      maLine.setData(align(ma.values) as any)
    }

    if (toggles.levels) for (const lv of ov.levels)
      series.createPriceLine({
        price: lv.price, color: lv.role === 'support' ? '#26a641' : '#f85149',
        lineWidth: 1, lineStyle: 0, axisLabelVisible: true, title: `${lv.role} (${lv.touches})`,
      } as any)

    if (toggles.fib && ov.fibonacci)
      for (const [ratio, price] of Object.entries(ov.fibonacci.levels)) {
        if (![0.382, 0.5, 0.618].includes(Number(ratio))) continue   // key retracements only, less clutter
        series.createPriceLine({
          price, color: '#8b949e', lineWidth: 1, lineStyle: 2,
          axisLabelVisible: true, title: `fib ${(Number(ratio) * 100).toFixed(1)}%`,
        } as any)
      }

    // Patterns: draw each ACTUAL boundary (channel/triangle boundaries, neckline, rectangle edges)
    // as a line series, styled by state. The boundaries ARE the breakout/invalidation levels, so we
    // don't also draw horizontal lines for those (that was redundant clutter) — only the projected
    // target gets a single tag.
    if (toggles.patterns) for (const p of ov.patterns) {
      const st = patternStyle(p)
      for (const ln of p.lines ?? []) {
        if (ln.length < 2) continue
        const bl = main.addLineSeries({
          color: st.color, lineWidth: st.width as any, lineStyle: st.dashed ? 2 : 0,
          lastValueVisible: false, priceLineVisible: false, crosshairMarkerVisible: false,
        })
        bl.setData(dedupeByTime(ln.map((pt) => ({ time: pt.time, value: pt.price }))) as any)
      }
      if (p.target != null)
        series.createPriceLine({ price: p.target, color: st.color, lineWidth: 1, lineStyle: 1,
          axisLabelVisible: true, title: `${p.type} target` } as any)
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
      const regMap = new Map(ov.regime.map((r) => [r.time, r.label]))
      strip.setData(axis.map((t) => (regMap.has(t)
        ? { time: t, value: 1, color: regimeColor(regMap.get(t) as string) } : { time: t })) as any)
    }

    // ---- sub-panes (all mapped onto `axis`, so their indices match the price pane) ----
    if (toggles.volume) {
      const c = newPane('volume', SUB_H)
      const vol = c.addHistogramSeries({ priceFormat: { type: 'volume' }, priceLineVisible: false })
      const volMap = new Map(data.candles.filter((k) => k.volume != null)
        .map((k) => [k.time, { v: k.volume as number, up: k.close >= k.open }]))
      vol.setData(axis.map((t) => (volMap.has(t)
        ? { time: t, value: volMap.get(t)!.v, color: volMap.get(t)!.up ? '#26a64155' : '#f8514955' }
        : { time: t })) as any)
      const ma = c.addLineSeries({ color: '#58a6ff', lineWidth: 1, priceLineVisible: false, lastValueVisible: false })
      ma.setData(align(ind.volume_ma) as any)
    }

    if (toggles.rsi) {
      const c = newPane('RSI', SUB_H)
      const rsi = c.addLineSeries({ color: '#d29922', lineWidth: 2, priceLineVisible: false })
      rsi.setData(align(ind.rsi) as any)
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
      const histMap = new Map(ind.macd.hist.map((p) => [p.time, p.value]))
      hist.setData(axis.map((t) => (histMap.has(t)
        ? { time: t, value: histMap.get(t)!, color: histMap.get(t)! >= 0 ? '#26a64188' : '#f8514988' }
        : { time: t })) as any)
      c.addLineSeries({ color: '#58a6ff', lineWidth: 1, priceLineVisible: false, lastValueVisible: false })
        .setData(align(ind.macd.line) as any)
      c.addLineSeries({ color: '#d29922', lineWidth: 1, priceLineVisible: false, lastValueVisible: false })
        .setData(align(ind.macd.signal) as any)
    }

    if (toggles.adx) {
      const c = newPane('ADX', SUB_H)
      const adx = c.addLineSeries({ color: '#a371f7', lineWidth: 2, priceLineVisible: false })
      adx.setData(align(ind.adx) as any)
      adx.createPriceLine({ price: 25, color: '#30363d', lineWidth: 1, lineStyle: 2,
        axisLabelVisible: true, title: 'trend' } as any)
    }

    if (toggles.atr) {
      const c = newPane('ATR', SUB_H)
      c.addLineSeries({ color: '#ec8e2c', lineWidth: 2, priceLineVisible: false })
        .setData(align(ind.atr) as any)
    }

    syncTimeScales()
    // Bounded right stop (snap-back). While you actively drag, the right edge can rubber-band into
    // empty space — lightweight-charts overrides an in-scroll correction, so a hard stop mid-drag
    // isn't possible — but crucially the WIDTH is preserved, so it never becomes a zoom. Once the
    // scroll settles we snap the last candle back to RIGHT_OFFSET bars from the edge (the gap).
    // Debounced so the correction lands after the drag stops, not fighting it. Clamping the MAIN
    // pane propagates to the sub-panes via the logical-range sync.
    const maxRight = data.candles.length - 1 + RIGHT_OFFSET
    let clamping = false
    let clampTimer: any
    main.timeScale().subscribeVisibleLogicalRangeChange((r) => {
      if (!r || clamping || r.to <= maxRight) return
      clearTimeout(clampTimer)
      clampTimer = setTimeout(() => {
        const cur = main.timeScale().getVisibleLogicalRange()
        if (!cur || cur.to <= maxRight) return
        clamping = true
        main.timeScale().setVisibleLogicalRange({ from: maxRight - (cur.to - cur.from), to: maxRight })
        clamping = false
      }, 60)
    })
    // Initial view: the most recent ~200 bars with the trailing gap (like a trading chart). NOT
    // the whole history — thousands of bars hit lightweight-charts' minimum bar-spacing and the
    // view collapses/loses the gap. You can still pan all the way back to bar 0 (fixLeftEdge).
    const view = Math.min(data.candles.length, 200)
    main.timeScale().setVisibleLogicalRange({ from: data.candles.length - view, to: maxRight })

    // Opt-in test hook (only when the URL carries ?__verify) so a headless browser can read the
    // real chart's range. No-op in normal use.
    if (typeof location !== 'undefined' && location.search.includes('__verify')) (window as any).__mainChart = main
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
