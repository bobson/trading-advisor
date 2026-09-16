"""#7 alerts — format a flagged setup and (optionally) POST it to a webhook.

Webhook payload uses `{"content": ...}` (Discord incoming-webhook format; Slack uses "text",
so we send both keys to be friendly). Graceful: no URL or any error -> returns False, never
raises, so a scheduled scan can't crash on a flaky webhook.
"""

from __future__ import annotations


def format_alert(a: dict) -> str:
    return (f"{a['symbol']} {a['timeframe']}: {a['bias'].upper()} setup — "
            f"confidence {a['confidence'] * 100:.0f}% ({a['agreeing']} categories agree)")


def _post(url: str, payload: dict) -> None:
    import requests

    requests.post(url, json=payload, timeout=5).raise_for_status()


def send_webhook(message: str, url: str | None, post=None) -> bool:
    """POST `message` to `url`; True on success, False if no URL / any failure."""
    if not url:
        return False
    post = post or _post
    try:
        post(url, {"content": message, "text": message})
        return True
    except Exception:
        return False
