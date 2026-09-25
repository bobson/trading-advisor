# Deploying the API on your DigitalOcean droplet

The API is a small ASGI app (`src/api/app.py`) run by uvicorn. Your droplet already runs
another server, so this one **binds to localhost on its own port** and you reverse-proxy to it
with nginx — it never competes for port 80/443 or collides with the other service.

## 1. Put the code at /srv/trading-wizard

```bash
sudo mkdir -p /srv/trading-wizard && sudo chown $USER /srv/trading-wizard
git clone <your-repo-url> /srv/trading-wizard      # or rsync your working copy up
cd /srv/trading-wizard
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env      # then add ANTHROPIC_API_KEY (and FINNHUB_API_KEY if you have one)
python scripts/download_data.py   # cache candles for the configured pair(s)
```

## 2. Run it under systemd (pick an unused port, e.g. 8010)

`/etc/systemd/system/trading-wizard.service`:

```ini
[Unit]
Description=Trading Advisor API
After=network.target

[Service]
User=YOUR_USER
WorkingDirectory=/srv/trading-wizard
Environment=API_HOST=127.0.0.1
Environment=API_PORT=8010
ExecStart=/srv/trading-wizard/.venv/bin/python scripts/serve.py
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now trading-wizard
sudo systemctl status trading-wizard          # confirm it's listening on 127.0.0.1:8010
curl -s localhost:8010/health                 # -> {"status":"ok"}
```

## 3. Reverse-proxy with nginx (alongside your existing server)

Add a `location` on an existing server block, or a new subdomain — point it at 127.0.0.1:8010:

```nginx
location /trading/ {
    proxy_pass http://127.0.0.1:8010/;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
}
```

```bash
sudo nginx -t && sudo systemctl reload nginx
```

Then `https://your-domain/trading/health`, `/trading/pairs`, `/trading/docs` (FastAPI's
auto-generated API explorer), and `/trading/analysis?symbol=BTC/USDT&timeframe=1h`.

## Notes

- `/analysis` defaults to **no Claude call and no extra network** (fast, free). Add
  `?explain=true` for Claude's write-up (uses API credit) and `?context=true` for
  sentiment/positioning.
- Keep the port (`API_PORT`) different from whatever your other server uses.
- **Before exposing publicly, set these in `.env`** (the #8 lockdown): `API_KEY` (then every
  data endpoint requires header `X-API-Key: <it>` — this also protects the credit-spending
  `explain` path), `ALLOWED_ORIGINS` (your frontend URL, comma-separated — CORS default is only
  localhost), and optionally `RATE_LIMIT_PER_MIN` (default 60). The API logs a warning at startup
  if no `API_KEY` is set. The Svelte frontend then sends the key as the `X-API-Key` header.

## Morning report — the forward record (ROADMAP A8)

A daily run at **08:00 Europe/Skopje** that reviews past reads, then freezes today's reads
(`scripts/morning_report.py`). It needs an always-on machine, which is why it lives here and not on a
laptop. It writes to the same `data/wizard.db` the API reads, so the report page is at `#/morning`.

1. **Keys in `.env`:** `TWELVEDATA_API_KEY` (EUR/USD and gold) and `OANDA_API_TOKEN` (WTI oil, from a
   free OANDA practice account: My Account → Manage API Access). A missing key just skips that
   market, and the skip is recorded.
2. **Install the timer** (copy both files, set `User=` in the service to the user that owns
   `/srv/trading-wizard`):

   ```bash
   sudo cp deploy/trading-wizard-morning.service deploy/trading-wizard-morning.timer /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo systemctl enable --now trading-wizard-morning.timer
   systemctl list-timers trading-wizard-morning.timer     # NEXT should say 08:00 CEST/CET
   ```

   `Persistent=false`: if the droplet is down at 08:00, that morning is **not** run late. It shows
   as a gap.
3. **Day one:** run it once by hand and read the report. Record that date in PROGRESS.md; it's day
   one of the forward record.

   ```bash
   sudo systemctl start trading-wizard-morning.service     # or: .venv/bin/python scripts/morning_report.py
   journalctl -u trading-wizard-morning.service -n 30
   ```

Manual trigger later: the same command, or the **Run now** button on the report page. A second run
on the same day adds nothing new; it only retries markets that failed. Every deploy (`git pull`)
changes the engine commit stored on new reads, so the record splits cleanly by engine version.
