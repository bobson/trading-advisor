#!/usr/bin/env python3
"""#7 alerts — scan the watchlist once and notify on flagged setups.

Run it on a schedule with cron, e.g. every 30 minutes on the droplet:

    */30 * * * * cd /srv/trading-wizard && .venv/bin/python scripts/watch.py >> /var/log/tw-watch.log 2>&1

Set WEBHOOK_URL in .env (a Discord/Slack incoming webhook) to get pinged; otherwise it just
prints. It makes NO Claude calls (free) — it only checks whether setups are flagged.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.alerts import format_alert, scan, send_webhook  # noqa: E402
from src.config import load_config  # noqa: E402


def main() -> None:
    cfg = load_config()
    alerts = scan(cfg)
    if not alerts:
        print("No setups flagged.")
        return

    message = "Trading Wizard alerts:\n" + "\n".join(format_alert(a) for a in alerts)
    print(message)
    if cfg.webhook_url:
        print("Sent to webhook." if send_webhook(message, cfg.webhook_url) else "Webhook send FAILED.")
    else:
        print("\n(set WEBHOOK_URL in .env to get pinged — e.g. a Discord webhook)")


if __name__ == "__main__":
    main()
