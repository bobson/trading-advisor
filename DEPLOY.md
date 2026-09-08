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
- The Phase-25 Svelte frontend will be a separate static site that calls these endpoints; CORS
  is already open on the API. Tighten `allow_origins` in `app.py` to your domain for production.
