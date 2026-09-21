// Screenshot SOL/USDT daily to diagnose/verify pattern boundary lines + label stacking.
import http from 'http'
import fs from 'fs'
import path from 'path'
import { fileURLToPath } from 'url'
import puppeteer from 'puppeteer-core'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const dist = path.join(__dirname, '..', 'dist')
const canned = JSON.parse(fs.readFileSync(path.join(__dirname, 'canned_btc.json'), 'utf8'))
const TYPES = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css' }
const out = process.argv[2] || 'sol-before.png'

const server = http.createServer((req, res) => {
  const url = req.url.split('?')[0]
  const json = (o) => { res.writeHead(200, { 'content-type': 'application/json' }); res.end(JSON.stringify(o)) }
  if (url === '/pairs') return json([{ symbol: 'SOL/USDT', asset_class: 'crypto', label: 'Solana' }])
  if (url === '/timeframes') return json(['1d'])
  if (url === '/analysis') return json(canned)
  const file = path.join(dist, url === '/' ? 'index.html' : url)
  fs.readFile(file, (e, b) => {
    if (e) { res.writeHead(404); return res.end('nf') }
    res.writeHead(200, { 'content-type': TYPES[path.extname(file)] || 'application/octet-stream' }); res.end(b)
  })
})
await new Promise((r) => server.listen(8155, r))

const browser = await puppeteer.launch({ executablePath: '/usr/bin/chromium', headless: true, args: ['--no-sandbox', '--disable-gpu'] })
const page = await browser.newPage()
await page.setViewport({ width: 1200, height: 1400 })
const errs = []
page.on('pageerror', (e) => errs.push('PAGEERR ' + e.message))
page.on('console', (m) => { if (m.type() === 'error') errs.push('CONSOLE ' + m.text()) })
await page.goto('http://127.0.0.1:8155/', { waitUntil: 'networkidle0' })
await new Promise((r) => setTimeout(r, 300))
const clicked = await page.evaluate(() => {
  const b = [...document.querySelectorAll('button')].find((x) => /^analyz/i.test(x.textContent))
  if (b) { b.click(); return b.textContent } return 'NO ANALYZE BUTTON'
})
await new Promise((r) => setTimeout(r, 2500))
const dom = await page.evaluate(() => ({
  panes: document.querySelectorAll('.chart-root .pane').length,
  canvases: document.querySelectorAll('.chart-root canvas').length,
  hasError: !!document.querySelector('.error') && document.querySelector('.error').textContent,
}))
console.log('clicked:', clicked, '| dom:', JSON.stringify(dom), '| errs:', errs.slice(0, 3))

// count how many pattern boundary line-series got drawn (exposed by the component if it wants)
await page.screenshot({ path: path.join(__dirname, out), clip: { x: 0, y: 120, width: 1200, height: 640 } })
await browser.close(); server.close()
