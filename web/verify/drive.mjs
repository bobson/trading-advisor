// Headless browser check of chart pan/zoom + edge behavior. Drives real Chromium against
// harness.html for each config (A/B/C) and reads the chart's visible logical range around drags.
// "No zoom" == visible width (to-from) stays constant through every drag, incl. slamming edges.
// "Gap" == after slamming the right edge, `to` sits ~RIGHT_OFFSET past the last candle index.
import puppeteer from 'puppeteer-core'
import { fileURLToPath } from 'url'
import path from 'path'

const __dirname = path.dirname(fileURLToPath(import.meta.url))

const browser = await puppeteer.launch({
  executablePath: '/usr/bin/chromium', headless: true, args: ['--no-sandbox', '--disable-gpu'],
})

async function run(mode) {
  const page = await browser.newPage()
  await page.setViewport({ width: 1000, height: 600 })
  const errs = []
  page.on('pageerror', (e) => errs.push(e.message))
  await page.goto('file://' + path.join(__dirname, 'harness.html') + '?mode=' + mode)
  await page.waitForFunction('window.__ready === true', { timeout: 8000 })

  const range = () => page.evaluate(() => {
    const r = window.__chart.timeScale().getVisibleLogicalRange(); return { from: r.from, to: r.to }
  })
  const N = await page.evaluate(() => window.__N)
  const OFF = await page.evaluate(() => window.__RIGHT_OFFSET)
  const drag = async (x1, y, x2) => {
    await page.mouse.move(x1, y); await page.mouse.down()
    for (let i = 1; i <= 20; i++) await page.mouse.move(x1 + ((x2 - x1) * i) / 20, y)
    await page.mouse.up(); await new Promise((r) => setTimeout(r, 40))
  }

  // zoom to ~60 bars so panning is testable (mirrors real use: wheel-zoom then drag)
  await page.evaluate(() => window.__chart.timeScale().setVisibleLogicalRange({ from: 120, to: 180 }))
  await new Promise((r) => setTimeout(r, 60))
  const r0 = await range(); const w0 = r0.to - r0.from

  await drag(520, 200, 300); const r1 = await range()
  const panned = Math.abs(r1.from - r0.from) > 1
  const panZoom = +((r1.to - r1.from) - w0).toFixed(2)

  for (let k = 0; k < 8; k++) await drag(720, 200, 150)          // slam RIGHT edge
  const rR = await range(); const rightZoom = +((rR.to - rR.from) - w0).toFixed(2)

  for (let k = 0; k < 14; k++) await drag(150, 200, 850)         // slam LEFT edge
  const rL = await range(); const leftZoom = +((rL.to - rL.from) - w0).toFixed(2)

  // screenshot the rested view for the layout check
  await page.evaluate(() => (window.__mode === 'A' ? window.__chart.timeScale().scrollToRealTime() : window.__chart.timeScale().fitContent()))
  await new Promise((r) => setTimeout(r, 200))
  await page.screenshot({ path: path.join(__dirname, 'chart-' + mode + '.png') })

  const noZoom = Math.abs(panZoom) < 1 && Math.abs(rightZoom) < 1 && Math.abs(leftZoom) < 1
  const rightGap = +(rR.to - (N - 1)).toFixed(1)          // bars of gap after last candle at right stop
  const leftStop = +rL.from.toFixed(1)
  await page.close()
  return { mode, panned, noZoom, panZoom, rightZoom, leftZoom, rightGap_bars: rightGap, leftStop_from: leftStop,
           gapOK: rightGap > 10, lastCandleVisible: rR.to >= N - 1, errs }
}

for (const m of ['A', 'B', 'C', 'D']) console.log(JSON.stringify(await run(m)))
await browser.close()
