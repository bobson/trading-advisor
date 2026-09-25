# Deploying Trading Wizard on the droplet

The target is **https://wizard.bosfoot.com**, on the same DigitalOcean droplet as bosfoot, behind the
same **Caddy**, run by the existing **`bobson`** user. Caddy serves the built page and forwards
`/api/*` to the API. The API is uvicorn bound to `127.0.0.1:8010`, never exposed directly, so it
can't collide with bosfoot.

| Piece | Where | Put there by |
|---|---|---|
| Code (the git repo) | `/srv/trading-wizard` | `git clone` once, then every deploy |
| Built page (`web/dist`) | `/srv/trading-wizard/web/dist` | GitHub Actions, every deploy |
| Python + libraries | `/srv/trading-wizard/.venv` | built once on the droplet |
| Keys | `/srv/trading-wizard/.env` | typed by hand, never in git |
| Database + candle cache | `/srv/trading-wizard/data/` | created there (optionally seed `wizard.db` once) |
| API service, morning timer | `/etc/systemd/system/` | copied once from `deploy/` |
| Site block | the existing Caddyfile | added once |

Order: 1 DNS → 2 code → 3 API service → 4 Caddy → 5 automatic deploys → 6 morning report.

## 1. DNS

At your DNS provider for bosfoot.com, add an **A record**: name `wizard`, value = the droplet's
IP. Caddy fetches the HTTPS certificate by itself once the name resolves (`dig +short wizard.bosfoot.com`
should print the IP).

## 2. Code on the droplet (as bobson)

The droplet reads the repo with its own read-only **deploy key**. GitHub won't accept the same key
on two repos, so this key is separate from anything bosfoot uses, with its own host alias:

```bash
ssh-keygen -t ed25519 -N "" -f ~/.ssh/trading_wizard_github -C wizard-droplet
cat >> ~/.ssh/config <<'EOF'
Host github-wizard
    HostName github.com
    User git
    IdentityFile ~/.ssh/trading_wizard_github
    IdentitiesOnly yes
EOF
cat ~/.ssh/trading_wizard_github.pub
```

GitHub → the trading-advisor repo → Settings → **Deploy keys** → Add key: paste that line, leave
"Allow write access" **off**. Then:

```bash
sudo mkdir -p /srv/trading-wizard && sudo chown bobson:bobson /srv/trading-wizard
git clone git@github-wizard:bobson/trading-advisor.git /srv/trading-wizard   # answer "yes" once
cd /srv/trading-wizard
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt           # needs Python 3.11+
cp .env.example .env && nano .env
```

In `.env`: `ANTHROPIC_API_KEY`, `TWELVEDATA_API_KEY`, and `ALLOWED_ORIGINS=https://wizard.bosfoot.com`.

**Optional, saves ~20 min:** copy your local database up once. It carries the encyclopedia and
verdict records and no morning-report data, so the forward record still starts clean. From your
computer:
`scp data/wizard.db bobson@DROPLET_IP:/srv/trading-wizard/data/wizard.db`
(run `mkdir -p /srv/trading-wizard/data` on the droplet first). Otherwise rebuild it there with
`scripts/build_encyclopedia.py` and `scripts/build_verdict_records.py`.

## 3. The API service

First check the port is free: `ss -ltnp | grep 8010` should print nothing.

```bash
sudo cp deploy/trading-wizard.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now trading-wizard
curl -s localhost:8010/health          # -> {"status":"ok"}
```

## 4. Caddy

Add this block to the existing Caddyfile (next to the bosfoot one, which stays untouched):

```caddyfile
wizard.bosfoot.com {
    encode gzip

    # A login prompt in front of everything: the site can spend Claude credit (explanations) and
    # start the morning report ("Run now"). Make the hash with:  caddy hash-password
    basic_auth {
        bobson PASTE_THE_HASH_HERE
    }

    handle_path /api/* {
        reverse_proxy 127.0.0.1:8010
    }
    handle {
        root * /srv/trading-wizard/web/dist
        try_files {path} /index.html
        file_server
    }
}
```

```bash
caddy hash-password                     # type a password; paste the output into the block
sudo caddy validate --config /etc/caddy/Caddyfile
sudo systemctl reload caddy
```

The page appears after the first deploy (step 5) has copied `web/dist`.

## 5. Automatic deploys from GitHub (push to main → droplet)

`.github/workflows/deploy.yml` runs after **CI passes on a push to `main`**. A failing CI never
deploys, and there's also a manual **Run workflow** button. It builds the page on GitHub, SSHes in
as bobson and runs `deploy/deploy.sh <commit>`. That script waits for a running morning report,
moves the code to exactly that commit, installs deps, restarts the API and checks `/health`. Then
the workflow copies the built page to `web/dist`.

**On the droplet:** let bobson restart this one service without a password (nothing else changes):

```bash
echo 'bobson ALL=(root) NOPASSWD: /usr/bin/systemctl restart trading-wizard' | sudo tee /etc/sudoers.d/trading-wizard
sudo chmod 440 /etc/sudoers.d/trading-wizard && sudo visudo -c
```

**On your computer:** a key GitHub Actions uses to log in as bobson:

```bash
ssh-keygen -t ed25519 -N "" -f ~/.ssh/trading_wizard_actions -C github-actions
ssh-copy-id -i ~/.ssh/trading_wizard_actions.pub bobson@DROPLET_IP
ssh-keyscan -t ed25519 DROPLET_IP        # this output -> DEPLOY_KNOWN_HOSTS below
```

**On GitHub** → repo → Settings → **Secrets and variables → Actions**:
- Secrets: `DEPLOY_HOST` = droplet IP, `DEPLOY_USER` = `bobson`, `DEPLOY_SSH_KEY` = the whole
  **private** file `~/.ssh/trading_wizard_actions`, `DEPLOY_KNOWN_HOSTS` = the ssh-keyscan line.
- Variables: `VITE_API_BASE` = `/api`. Leave `VITE_BASE` unset (the page is at the site root).

Test it: Actions tab → **Deploy** → Run workflow. After that, every push to `main` that passes CI
deploys itself.

## 6. Morning report — the forward record (ROADMAP A8)

A daily run at **08:00 Europe/Skopje** that reviews past reads, then freezes today's reads
(`scripts/morning_report.py`). It writes to the same `data/wizard.db` the API reads; the page is
`https://wizard.bosfoot.com/#/morning`. Markets without a key are skipped, and the skip is
recorded. Oil is currently off the watchlist.

```bash
sudo cp deploy/trading-wizard-morning.service deploy/trading-wizard-morning.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now trading-wizard-morning.timer
systemctl list-timers trading-wizard-morning.timer     # NEXT should say 08:00 CEST/CET
```

`Persistent=false`: if the droplet is down at 08:00, that morning is **not** run late. It shows as a
gap.

**Day one:** run it once by hand, read the report, and record the date in PROGRESS.md.

```bash
sudo systemctl start trading-wizard-morning.service
journalctl -u trading-wizard-morning.service -n 30
```

Later manual runs: the same command, or **Run now** on the report page. A second run on the same
day adds nothing new; it only retries markets that failed. Every deploy changes the engine commit
stored on new reads, so the record splits cleanly by engine version.

## Notes

- `/analysis` makes **no Claude call** unless `?explain=true`. Caddy's login prompt guards that.
- The API's own `API_KEY` lockdown (`X-API-Key` header) is not used here: the page doesn't send the
  header, and a key shipped in a public page wouldn't be secret anyway. Caddy's `basic_auth` is the
  lock. Keep `ALLOWED_ORIGINS=https://wizard.bosfoot.com` in `.env`.
