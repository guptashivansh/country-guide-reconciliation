"""
Pure severity-scoring functions. No database access.

Each rule receives pre-fetched data dicts and the reference datetime,
and returns a DriftRecord or None. Rules are fully independent and
unit-testable without any DB fixtures.

Thresholds are module-level constants — override via subclassing
DriftDetector or monkey-patching in tests.
"""

from datetime import datetime, timezone
from typing import Optional

from app.drift.report import DriftRecord

# ── Tunable thresholds ─────────────────────────────────────────────────────
PENDING_DAYS_CRITICAL = 14   # pending major item → CRITICAL after this many days
PENDING_DAYS_WARNING = 7     # pending minor item → WARNING after this many days
ESCALATED_DAYS_CRITICAL = 7  # escalated item sitting this long → CRITICAL
STALE_DAYS_CRITICAL = 90
STALE_DAYS_WARNING = 30
STALE_DAYS_INFO = 14


def _days_since(iso_timestamp: Optional[str], now: datetime) -> Optional[int]:
    if not iso_timestamp:
        return None
    try:
        ts = datetime.fromisoformat(iso_timestamp)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        return max(0, (now - ts).days)
    except (ValueError, TypeError):
        return None


def _sev(item_severity: Optional[str]) -> str:
    return (item_severity or "minor").lower()


# ── Rule 1: pending change ──────────────────────────────────────────────────

def pending_change_rule(
    section: str,
    current_entry: Optional[dict],
    pending_item: dict,
    now: datetime,
) -> Optional[DriftRecord]:
    """
    A pending review_queue item means the published guide may be out of date.
    Severity escalates with item severity and days unactioned.
    """
    if pending_item.get("status") != "pending":
        return None

    item_sev = _sev(pending_item.get("severity"))
    days = _days_since(pending_item.get("created_at"), now)

    if item_sev == "critical":
        severity = "CRITICAL"
    elif item_sev == "major":
        severity = "CRITICAL" if (days or 0) >= PENDING_DAYS_CRITICAL else "WARNING"
    else:
        severity = "WARNING" if (days or 0) >= PENDING_DAYS_WARNING else "INFO"

    days_label = f"{days}d" if days is not None else "unknown"
    return DriftRecord(
        country=pending_item["country"],
        section=section,
        drift_type="PENDING_CHANGE",
        severity=severity,
        current_value=pending_item.get("old_value"),
        proposed_value=pending_item.get("new_value"),
        pending_item_id=pending_item.get("id"),
        days_pending=days,
        last_verified_at=current_entry.get("last_updated") if current_entry else None,
        evidence=(
            f"Pending {item_sev} change unreviewed for {days_label}. "
            f"Confidence: {round((pending_item.get('confidence') or 0) * 100)}%."
        ),
        recommended_action=(
            "Approve or reject this change immediately."
            if severity == "CRITICAL"
            else "Schedule review of this pending change."
        ),
    )


# ── Rule 2: escalated item ──────────────────────────────────────────────────

def escalated_item_rule(
    section: str,
    current_entry: Optional[dict],
    pending_item: dict,
    now: datetime,
) -> Optional[DriftRecord]:
    """
    An escalated item that has been sitting too long signals a review bottleneck.
    """
    if pending_item.get("status") != "escalated":
        return None

    days = _days_since(pending_item.get("created_at"), now)
    severity = "CRITICAL" if (days or 0) >= ESCALATED_DAYS_CRITICAL else "WARNING"

    days_label = f"{days}d" if days is not None else "unknown"
    return DriftRecord(
        country=pending_item["country"],
        section=section,
        drift_type="ESCALATED_ITEM",
        severity=severity,
        current_value=pending_item.get("old_value"),
        proposed_value=pending_item.get("new_value"),
        pending_item_id=pending_item.get("id"),
        days_pending=days,
        last_verified_at=current_entry.get("last_updated") if current_entry else None,
        evidence=f"Escalated item unresolved for {days_label}.",
        recommended_action="Assign a compliance owner and resolve the escalation.",
    )


# ── Rule 3: missing section ─────────────────────────────────────────────────

def missing_section_rule(
    section: str,
    current_entry: Optional[dict],
    pending_item: dict,
    now: datetime,
) -> Optional[DriftRecord]:
    """
    A section exists in the review queue but has no entry in the live guide.
    This is a gap — a newly discovered regulatory requirement not yet published.
    """
    if current_entry is not None:
        return None
    if pending_item.get("status") not in ("pending", "escalated"):
        return None

    confidence = pending_item.get("confidence") or 0
    item_sev = _sev(pending_item.get("severity"))

    if item_sev == "critical" or confidence >= 0.8:
        severity = "CRITICAL"
    elif confidence >= 0.65:
        severity = "WARNING"
    else:
        severity = "INFO"

    return DriftRecord(
        country=pending_item["country"],
        section=section,
        drift_type="MISSING_SECTION",
        severity=severity,
        current_value=None,
        proposed_value=pending_item.get("new_value"),
        pending_item_id=pending_item.get("id"),
        days_pending=_days_since(pending_item.get("created_at"), now),
        last_verified_at=None,
        evidence=(
            f"Section '{section}' extracted from official source "
            f"(confidence {round(confidence * 100)}%) but absent from the live guide."
        ),
        recommended_action="Review and publish this newly detected compliance requirement.",
    )


# ── Rule 4: stale verification ──────────────────────────────────────────────

def stale_verification_rule(
    section: str,
    current_entry: dict,
    provenance: Optional[dict],
    now: datetime,
) -> Optional[DriftRecord]:
    """
    A rule that hasn't been re-verified against a live official source
    for a long time may be drifting from current regulation.
    """
    reference_ts = None
    if provenance:
        reference_ts = provenance.get("reviewed_at")
    if not reference_ts:
        reference_ts = current_entry.get("last_updated")

    days = _days_since(reference_ts, now)
    if days is None:
        return None

    if days >= STALE_DAYS_CRITICAL:
        severity = "CRITICAL"
    elif days >= STALE_DAYS_WARNING:
        severity = "WARNING"
    elif days >= STALE_DAYS_INFO:
        severity = "INFO"
    else:
        return None

    return DriftRecord(
        country=current_entry["country"],
        section=section,
        drift_type="STALE_VERIFICATION",
        severity=severity,
        current_value=current_entry.get("value"),
        proposed_value=None,
        pending_item_id=None,
        days_pending=None,
        last_verified_at=reference_ts,
        evidence=f"Section '{section}' last verified {days} days ago (threshold: {STALE_DAYS_INFO}d).",
        recommended_action="Trigger a fresh sync and re-verify this section against official sources.",
    )


# ── Rule 5: no provenance ───────────────────────────────────────────────────

def no_provenance_rule(
    section: str,
    current_entry: dict,
    provenance: Optional[dict],
    now: datetime,
) -> Optional[DriftRecord]:
    """
    A rule with no provenance record cannot be traced to a source.
    Typically seeded initial data that has never been reconciled.
    """
    if provenance is not None:
        return None

    return DriftRecord(
        country=current_entry["country"],
        section=section,
        drift_type="NO_PROVENANCE",
        severity="WARNING",
        current_value=current_entry.get("value"),
        proposed_value=None,
        pending_item_id=None,
        days_pending=None,
        last_verified_at=None,
        evidence=f"Section '{section}' has no provenance record — source traceability unavailable.",
        recommended_action="Trigger a sync to establish source-verified provenance for this section.",
    )


# ── Default rule set ────────────────────────────────────────────────────────

DEFAULT_PENDING_RULES = [pending_change_rule, escalated_item_rule, missing_section_rule]
DEFAULT_CANONICAL_RULES = [stale_verification_rule, no_provenance_rule]
