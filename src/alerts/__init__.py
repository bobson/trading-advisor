"""#7 alerts — scan a watchlist and notify when a setup fires."""

from src.alerts.notify import format_alert, send_webhook
from src.alerts.watch import scan

__all__ = ["scan", "format_alert", "send_webhook"]
