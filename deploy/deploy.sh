#!/usr/bin/env bash
# Runs ON THE DROPLET, called by .github/workflows/deploy.yml over SSH:  deploy.sh <commit-sha>
#
# 1. waits for a running morning report to finish (same lock file the report takes), so the
#    code never changes under a run in progress;
# 2. moves the checkout to exactly that commit (the morning report stores it as the engine version);
# 3. installs Python dependencies; 4. restarts the API and checks it answers.
set -euo pipefail

# Everything is inside main() so bash reads the WHOLE script before running it — `git reset`
# below rewrites this very file.
main() {
  SHA="${1:?usage: deploy.sh <commit-sha>}"
  APP="${APP_DIR:-/srv/trading-wizard}"
  PORT="${API_PORT:-8010}"
  cd "$APP"

  mkdir -p "$APP/data"
  exec 9>"$APP/data/wizard.db.morning.lock"
  echo "waiting for any running morning report…"
  flock -w 3600 9

  git fetch --quiet origin main
  git reset --hard "$SHA"
  echo "code at $(git rev-parse --short HEAD)"

  .venv/bin/pip install --quiet -r requirements.txt

  sudo systemctl restart trading-wizard      # the only sudo this user may run (see DEPLOY.md)
  for _ in $(seq 1 20); do
    if curl -fsS "http://127.0.0.1:${PORT}/health" >/dev/null; then
      echo "API healthy on :${PORT}"
      exit 0
    fi
    sleep 1
  done
  echo "API did not come back on :${PORT}" >&2
  systemctl status trading-wizard --no-pager -n 20 >&2 || true
  exit 1
}
main "$@"
