// Verifies the ACTUAL built Svelte app (not a harness): serves web/dist + a canned backend on
// :8123 (same origin, no CORS), drives it in real Chromium, and checks the real PriceChart's
// pan/zoom/edge behavior via the ?__verify chart hook. Screenshots the rendered page.
import http from 'http'
import fs from 'fs'
import path from 'path'
import { fileURLToPath } from 'url'
import puppeteer from 'puppeteer-core'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const dist = path.join(__dirname, '..', 'dist')
const canned = JSON.parse(fs.readFileSync(path.join(__dirname, 'canned.json'), 'utf8'))
const TYPES = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.svg': 'image/svg+xml' }

const server = http.createServer((req, res) => {
  const url = req.url.split('?')[0]
  const json = (o) => { res.writeHead(200, { 'content-type': 'application/json' }); res.end(JSON.stringify(o)) }
  if (url === '/pairs') return json([{ symbol: 'BTC/USDT', asset_class: 'crypto', label: 'Bitcoin' }])
  if (url === '/timeframes') return json(['1d', '1h'])
  if (url === '/analysis') return json(canned)
  const file = path.join(dist, url === '/' ? 'index.html' : url)
  fs.readFile(file, (err, buf) => {
    if (err) { res.writeHead(404); return res.end('nf') }
    res.writeHead(200, { 'content-type': TYPES[path.extname(file)] || 'application/octet-stream' })
    res.end(buf)
  })
})
await new Promise((r) => server.listen(8123, r))

const browser = await puppeteer.launch({ executablePath: '/usr/bin/chromium', headless: true, args: ['--no-sandbox', '--disable-gpu'] })
const page = await browser.newPage()
await page.setViewport({ width: 1100, height: 1500 })
let consoleErrors = 0
const errorTexts = []
page.on('console', (m) => { if (m.type() === 'error') { consoleErrors++; errorTexts.push(m.text()) } })
const pageErrors = []
page.on('pageerror', (e) => pageErrors.push(e.message))

await page.goto('http://127.0.0.1:8123/?__verify=1', { waitUntil: 'networkidle0' })
// click Analyze, then wait for the real chart to mount and expose its hook
await page.evaluate(() => { const b = [...document.querySelectorAll('button')].find((x) => /analy/i.test(x.textContent)); b && b.click() })
await page.waitForFunction('window.__mainChart != null', { timeout: 8123 })
await new Promise((r) => setTimeout(r, 400))

const range = () => page.evaluate(() => { const r = window.__mainChart.timeScale().getVisibleLogicalRange(); return { from: r.from, to: r.to } })
const total = canned.chart.total_bars
const OFF = 25
const box = await page.evaluate(() => { const el = document.querySelector('.chart-root .pane'); const r = el.getBoundingClientRect(); return { x: r.x, y: r.y, w: r.width, h: r.height } })
const yMid = Math.round(box.y + Math.min(160, box.h * 0.4))
const drag = async (x1, x2) => { await page.mouse.move(x1, yMid); await page.mouse.down(); for (let i = 1; i <= 20; i++) await page.mouse.move(x1 + ((x2 - x1) * i) / 20, yMid); await page.mouse.up(); await new Promise((r) => setTimeout(r, 50)) }
const XR = Math.round(box.x + box.w * 0.72), XL = Math.round(box.x + box.w * 0.28)

const setView = (from, to) => page.evaluate((a) => window.__mainChart.timeScale().setVisibleLogicalRange({ from: a.from, to: a.to }), { from, to })
const settle = () => new Promise((r) => setTimeout(r, 120))

const out = {}
const rInit = await range()
out.rawInitialRange = { from: +rInit.from.toFixed(1), to: +rInit.to.toFixed(1) }
out.initial_gap_bars = +(rInit.to - (total - 1)).toFixed(1)     // expect ~25
await page.screenshot({ path: path.join(__dirname, 'app-initial.png') })

// LEFT hard stop (programmatic): overshoot into negative; fixLeftEdge must pin `from` at ~0.
await setView(-40, 120); await settle()
out.leftClamp_from = +(await range()).from.toFixed(1)           // expect ~0

// PAN + no-zoom via a real drag (XL->XR drags content right => reveals OLDER bars).
await setView(total - 200, total - 80); await settle()
const r0 = await range(); const w0 = r0.to - r0.from
await drag(XL, XR); const r1 = await range()
out.panWorks = Math.abs(r1.from - r0.from) > 3
out.panNoZoom_widthDelta = +((r1.to - r1.from) - w0).toFixed(2)  // expect ~0

// RIGHT-edge DRAG: reveal NEWER bars (drag content LEFT, XR->XL) into the edge; the clamp must
// bound the gap (~OFFSET) and width must not change (no zoom).
await setView(total - 130, total - 10); await settle()
const wR = (await range()).to - (await range()).from
for (let k = 0; k < 18; k++) await drag(XR, XL)
await settle(); await settle()
const rR = await range()
out.rightDrag_gap_bars = +(rR.to - (total - 1)).toFixed(1)       // expect ~25 (bounded)
out.rightDrag_noZoom_widthDelta = +((rR.to - rR.from) - wR).toFixed(2)
await page.screenshot({ path: path.join(__dirname, 'app-right-edge.png') })

// LEFT-edge DRAG: reveal OLDER bars (drag content RIGHT, XL->XR) into bar 0.
await setView(60, 180); await settle()
const wL = (await range()).to - (await range()).from
for (let k = 0; k < 18; k++) await drag(XL, XR)
const rL = await range()
out.leftDrag_from = +rL.from.toFixed(1)                          // expect ~0
out.leftDrag_noZoom_widthDelta = +((rL.to - rL.from) - wL).toFixed(2)

out.consoleErrors_nonFavicon = errorTexts.filter((t) => !/404/.test(t)).length
out.pageErrors = pageErrors
const near = (v, t, tol) => Math.abs(v - t) <= tol
const pass =
  near(out.initial_gap_bars, OFF, 3) && near(out.leftClamp_from, 0, 2) &&
  out.panWorks && near(out.panNoZoom_widthDelta, 0, 1.5) &&
  near(out.rightDrag_gap_bars, OFF, 3) && near(out.rightDrag_noZoom_widthDelta, 0, 1.5) &&
  near(out.leftDrag_from, 0, 2) && near(out.leftDrag_noZoom_widthDelta, 0, 1.5) &&
  out.consoleErrors_nonFavicon === 0 && pageErrors.length === 0
console.log(JSON.stringify(out, null, 2))
console.log(pass ? 'PASS' : 'FAIL')

await browser.close()
server.close()
