from dataclasses import dataclass, asdict, field
from typing import Optional, List

SEVERITY_ORDER = {"CRITICAL": 3, "WARNING": 2, "INFO": 1, "NONE": 0}


@dataclass
class DriftRecord:
    country: str
    section: str
    drift_type: str          # PENDING_CHANGE | ESCALATED_ITEM | MISSING_SECTION | STALE_VERIFICATION | NO_PROVENANCE
    severity: str            # CRITICAL | WARNING | INFO
    current_value: Optional[str]
    proposed_value: Optional[str]
    pending_item_id: Optional[int]
    days_pending: Optional[int]
    last_verified_at: Optional[str]
    evidence: str
    recommended_action: str


@dataclass
class DriftReport:
    country: str
    generated_at: str
    drift_detected: bool
    severity: str            # CRITICAL | WARNING | INFO | NONE
    affected_sections: List[DriftRecord] = field(default_factory=list)
    summary: str = ""
    recommended_action: str = ""

    def to_dict(self):
        d = asdict(self)
        d["affected_sections"] = [asdict(r) for r in self.affected_sections]
        return d


def aggregate_severity(records: List[DriftRecord]) -> str:
    if not records:
        return "NONE"
    return max((r.severity for r in records), key=lambda s: SEVERITY_ORDER.get(s, 0))


def build_summary(records: List[DriftRecord], country: str) -> str:
    if not records:
        return f"No drift detected for {country}."
    counts = {}
    for r in records:
        counts[r.severity] = counts.get(r.severity, 0) + 1
    parts = [f"{v} {k.lower()}" for k, v in sorted(counts.items(), key=lambda x: -SEVERITY_ORDER[x[0]])]
    types = sorted({r.drift_type for r in records})
    return f"{country}: {len(records)} drift issue(s) — {', '.join(parts)}. Types: {', '.join(types)}."


def build_recommended_action(records: List[DriftRecord]) -> str:
    severity = aggregate_severity(records)
    types = {r.drift_type for r in records}
    if severity == "NONE":
        return "No action required."
    if severity == "CRITICAL":
        if "MISSING_SECTION" in types:
            return "Immediately review and publish missing compliance sections. Critical regulatory gaps detected."
        if "PENDING_CHANGE" in types or "ESCALATED_ITEM" in types:
            return "Urgent: approve or escalate critical pending changes. Unreviewed changes may expose compliance risk."
        return "Investigate critical drift signals and verify guide accuracy against official sources."
    if severity == "WARNING":
        if "STALE_VERIFICATION" in types:
            return "Trigger a fresh sync for affected countries and review stale sections."
        return "Review pending changes and re-verify affected sections against current official sources."
    return "Schedule routine review of pending minor changes and stale sections."
