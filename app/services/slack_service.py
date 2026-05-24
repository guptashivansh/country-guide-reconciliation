import json
import logging
import urllib.request
import urllib.error
from datetime import datetime, timezone

from app.utils.config import app_base_url

logger = logging.getLogger(__name__)


REGION_OWNERS = {
    "APAC": "Divya",
    "EMEA": "Shweta",
    "Americas": "Kathryn",
}

# Region assignments for every country tracked in country_guide.
# Unmapped countries fall through to EMEA (where most uncategorised guides
# currently sit); add to this map rather than relying on the fallback.
COUNTRY_REGION = {
    # APAC
    "Australia": "APAC", "Bangladesh": "APAC", "China": "APAC", "Hong Kong": "APAC",
    "India": "APAC", "Indonesia": "APAC", "Japan": "APAC", "Malaysia": "APAC",
    "Nepal": "APAC", "New Zealand": "APAC", "Pakistan": "APAC", "Philippines": "APAC",
    "Singapore": "APAC", "South Korea": "APAC", "Sri Lanka": "APAC", "Taiwan": "APAC",
    "Thailand": "APAC", "Vietnam": "APAC",
    # EMEA
    "Austria": "EMEA", "Azerbaijan": "EMEA", "Bahrain": "EMEA", "Belgium": "EMEA",
    "Bosnia And Herzegovina": "EMEA", "Botswana": "EMEA", "Bulgaria": "EMEA",
    "Cameroon": "EMEA", "Congo (Republic of Congo)": "EMEA", "Croatia": "EMEA",
    "Cyprus": "EMEA", "Czech Republic": "EMEA", "Denmark": "EMEA", "Egypt": "EMEA",
    "Estonia": "EMEA", "France": "EMEA", "Georgia": "EMEA", "Germany": "EMEA",
    "Ghana": "EMEA", "Greece": "EMEA", "Hungary": "EMEA", "Israel": "EMEA",
    "Jordan": "EMEA", "Kenya": "EMEA", "Kuwait": "EMEA", "Lebanon": "EMEA",
    "Lithuania": "EMEA", "Luxembourg": "EMEA", "Madagascar": "EMEA", "Malawi": "EMEA",
    "Malta": "EMEA", "Mauritius": "EMEA", "Morocco": "EMEA", "Netherlands": "EMEA",
    "Nigeria": "EMEA", "Norway": "EMEA", "Oman": "EMEA", "Poland": "EMEA",
    "Portugal": "EMEA", "Qatar": "EMEA", "Romania": "EMEA", "Rwanda": "EMEA",
    "Saudi Arabia": "EMEA", "Serbia": "EMEA", "Slovakia": "EMEA", "South Africa": "EMEA",
    "Spain": "EMEA", "Switzerland": "EMEA", "Turkey": "EMEA", "UAE": "EMEA",
    "Uganda": "EMEA", "Ukraine": "EMEA", "United Kingdom": "EMEA",
    # Americas
    "Argentina": "Americas", "Belize": "Americas", "Bolivia": "Americas",
    "Brazil": "Americas", "Chile": "Americas", "Colombia": "Americas",
    "Costa Rica": "Americas", "Dominican Republic": "Americas",
    "Guatemala": "Americas", "Jamaica": "Americas", "Mexico": "Americas",
    "Nicaragua": "Americas", "Panama": "Americas", "Paraguay": "Americas",
    "Peru": "Americas", "Puerto Rico": "Americas",
}


def region_for(country):
    return COUNTRY_REGION.get(country, "EMEA")


def send_sync_alert(webhook_url, sync_result, triggered_by="scheduler"):
    """Post one Slack message per region (APAC / EMEA / Americas)."""
    if not webhook_url:
        return

    per_country = sync_result.get("per_country", {})
    sync_error = sync_result.get("sync_error")
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    # Bucket per-country activity by region.
    buckets = {region: {} for region in REGION_OWNERS}
    for country, stats in per_country.items():
        buckets.setdefault(region_for(country), {})[country] = stats

    for region, owner in REGION_OWNERS.items():
        region_stats = buckets.get(region, {})
        _post_region_alert(
            webhook_url=webhook_url,
            region=region,
            owner=owner,
            region_stats=region_stats,
            timestamp=timestamp,
            triggered_by=triggered_by,
            sync_error=sync_error,
        )


def _post_region_alert(webhook_url, region, owner, region_stats, timestamp, triggered_by, sync_error=None):
    total_changes = sum(s.get("changes", 0) for s in region_stats.values())
    failures = sum(1 for s in region_stats.values() if s.get("failed"))
    countries_with_changes = sorted(
        (c for c, s in region_stats.items() if s.get("changes", 0) > 0),
        key=lambda c: region_stats[c].get("changes", 0),
        reverse=True,
    )
    failed_countries = sorted(c for c, s in region_stats.items() if s.get("failed"))

    if sync_error:
        status_emoji = ":red_circle:"
        color = "#d72b3f"
    elif failures > 0:
        status_emoji = ":warning:"
        color = "#e8a838"
    elif total_changes > 0:
        status_emoji = ":large_green_circle:"
        color = "#2eb67d"
    else:
        status_emoji = ":white_circle:"
        color = "#aaaaaa"

    lines = [f"{status_emoji} *{region} Country Guide Sync* — owner: *{owner}*"]

    if sync_error:
        lines.append(f"• Sync run crashed before processing endpoints: `{sync_error}`")
    else:
        lines.append(f"• Changes queued for review: *{total_changes}*")
        lines.append(f"• Countries processed: {len(region_stats)}")
        lines.append(f"• Failures: {failures}")

        if countries_with_changes:
            breakdown = ", ".join(
                f"{c} ({region_stats[c]['changes']})" for c in countries_with_changes[:8]
            )
            more = len(countries_with_changes) - 8
            if more > 0:
                breakdown += f", +{more} more"
            lines.append(f"• Top countries: {breakdown}")

        if failed_countries:
            lines.append(f"• Failed sources: {', '.join(failed_countries[:8])}")

    lines.append(f"• Triggered by: {triggered_by}  ·  {timestamp}")

    base = app_base_url()
    actions = [
        {
            "type": "button",
            "text": "Review Queue",
            "url": f"{base}/api/review-queue",
        },
        {
            "type": "button",
            "text": "Open Dashboard",
            "url": f"{base}/compliance/dashboard",
        },
    ]

    payload = {
        "attachments": [
            {
                "color": color,
                "text": "\n".join(lines),
                "mrkdwn_in": ["text"],
                "actions": actions,
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
        logger.info(
            "Slack sync alert sent",
            extra={"stage": "slack", "region": region, "changes": total_changes, "failures": failures},
        )
    except urllib.error.URLError as e:
        logger.warning(
            "Slack alert failed",
            extra={"stage": "slack", "region": region, "failure": str(e)},
        )
