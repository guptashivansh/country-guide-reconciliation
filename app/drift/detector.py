"""
DriftDetector: orchestrates data fetching + rule evaluation into DriftReport.

Usage:
    detector = DriftDetector(drift_repository)
    report   = detector.detect(country)
    reports  = detector.detect_all()
"""

from datetime import datetime, timezone
from typing import List, Optional

from app.drift.report import (
    DriftRecord,
    DriftReport,
    aggregate_severity,
    build_recommended_action,
    build_summary,
)
from app.drift.repository import DriftRepository
from app.drift.rules import DEFAULT_CANONICAL_RULES, DEFAULT_PENDING_RULES


class DriftDetector:
    def __init__(
        self,
        repository: DriftRepository,
        pending_rules=None,
        canonical_rules=None,
    ):
        self.repository = repository
        self.pending_rules = pending_rules if pending_rules is not None else DEFAULT_PENDING_RULES
        self.canonical_rules = canonical_rules if canonical_rules is not None else DEFAULT_CANONICAL_RULES

    # ── public API ─────────────────────────────────────────────────────────────

    def detect(self, country: str, now: Optional[datetime] = None) -> DriftReport:
        now = now or datetime.now(tz=timezone.utc)
        records = self._run_pending_rules(country, now) + self._run_canonical_rules(country, now)
        # De-duplicate: keep highest severity per (section, drift_type)
        records = _deduplicate(records)
        severity = aggregate_severity(records)
        return DriftReport(
            country=country,
            generated_at=now.isoformat(),
            drift_detected=bool(records),
            severity=severity,
            affected_sections=records,
            summary=build_summary(records, country),
            recommended_action=build_recommended_action(records),
        )

    def detect_all(self, now: Optional[datetime] = None) -> List[DriftReport]:
        now = now or datetime.now(tz=timezone.utc)
        countries = self.repository.list_countries()
        return [self.detect(c, now) for c in countries]

    # ── internal ───────────────────────────────────────────────────────────────

    def _run_pending_rules(self, country: str, now: datetime) -> List[DriftRecord]:
        pending_items = self.repository.get_pending_items(country)
        if not pending_items:
            return []

        # Build canonical lookup by section
        entries = {e["section"]: e for e in self.repository.get_canonical_entries(country)}

        records = []
        for item in pending_items:
            section = item.get("section", "")
            current_entry = entries.get(section)
            for rule in self.pending_rules:
                result = rule(section, current_entry, item, now)
                if result is not None:
                    records.append(result)
        return records

    def _run_canonical_rules(self, country: str, now: datetime) -> List[DriftRecord]:
        entries = self.repository.get_canonical_entries(country)
        if not entries:
            return []

        provenances = self.repository.get_all_provenances(country)

        records = []
        for entry in entries:
            section = entry["section"]
            prov = provenances.get(section)
            for rule in self.canonical_rules:
                result = rule(section, entry, prov, now)
                if result is not None:
                    records.append(result)
        return records


# ── helpers ────────────────────────────────────────────────────────────────────

_SEVERITY_RANK = {"CRITICAL": 3, "WARNING": 2, "INFO": 1}


def _deduplicate(records: List[DriftRecord]) -> List[DriftRecord]:
    """When the same (section, drift_type) appears multiple times, keep the highest severity."""
    best: dict = {}
    for rec in records:
        key = (rec.section, rec.drift_type)
        existing = best.get(key)
        if existing is None or _SEVERITY_RANK.get(rec.severity, 0) > _SEVERITY_RANK.get(existing.severity, 0):
            best[key] = rec
    return list(best.values())
