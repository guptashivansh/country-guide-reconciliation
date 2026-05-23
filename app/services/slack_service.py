import json
import logging
import urllib.request
import urllib.error
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def send_sync_alert(webhook_url, sync_result, triggered_by="scheduler"):
    """Post a sync summary to Slack via incoming webhook."""
    if not webhook_url:
        return

    total_changes = sync_result.get("total_changes", 0)
    endpoints_processed = sync_result.get("endpoints_processed", 0)
    failures = sync_result.get("failures", 0)
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    if failures > 0:
        status_emoji = ":warning:"
        color = "#e8a838"
    elif total_changes > 0:
        status_emoji = ":large_green_circle:"
        color = "#2eb67d"
    else:
        status_emoji = ":white_circle:"
        color = "#aaaaaa"

    lines = [
        f"{status_emoji} *Country Guide Sync Complete*",
        f"• Changes queued for review: *{total_changes}*",
        f"• Endpoints processed: {endpoints_processed}",
        f"• Failures: {failures}",
        f"• Triggered by: {triggered_by}",
        f"• {timestamp}",
    ]

    payload = {
        "attachments": [
            {
                "color": color,
                "text": "\n".join(lines),
                "mrkdwn_in": ["text"],
            }
        ]
    }

    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            webhook_url,
            data=data,
            headers={"Content-Type": "application/json"},
        )
        urllib.request.urlopen(req, timeout=10)
        logger.info("Slack sync alert sent", extra={"stage": "slack", "changes": total_changes})
    except urllib.error.URLError as e:
        logger.warning("Slack alert failed", extra={"stage": "slack", "failure": str(e)})
