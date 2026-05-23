"""
Tests for the Compliance Drift Detection module.

Pure-function tests (rules.py) need no fixtures.
Integration tests (detector.py) use an in-memory SQLite DB.
"""

import sqlite3
import unittest
from datetime import datetime, timedelta, timezone

from app.drift.report import (
    DriftRecord,
    aggregate_severity,
    build_recommended_action,
    build_summary,
)
from app.drift.rules import (
    ESCALATED_DAYS_CRITICAL,
    PENDING_DAYS_CRITICAL,
    PENDING_DAYS_WARNING,
    STALE_DAYS_CRITICAL,
    STALE_DAYS_INFO,
    STALE_DAYS_WARNING,
    escalated_item_rule,
    missing_section_rule,
    no_provenance_rule,
    pending_change_rule,
    stale_verification_rule,
)
from app.drift.detector import DriftDetector
from app.drift.repository import DriftRepository


# ── helpers ────────────────────────────────────────────────────────────────────

NOW = datetime(2026, 5, 23, 12, 0, 0, tzinfo=timezone.utc)


def _days_ago(n: int) -> str:
    return (NOW - timedelta(days=n)).isoformat()


def _pending_item(status="pending", severity="minor", days_old=0, **kwargs):
    base = {
        "id": 1,
        "country": "TestLand",
        "section": "annual_leave",
        "status": status,
        "severity": severity,
        "old_value": "20 days",
        "new_value": "22 days",
        "confidence": 0.9,
        "created_at": _days_ago(days_old),
    }
    base.update(kwargs)
    return base


def _current_entry(**kwargs):
    base = {
        "country": "TestLand",
        "section": "annual_leave",
        "value": "20 days",
        "last_updated": _days_ago(5),
        "current_provenance_id": None,
    }
    base.update(kwargs)
    return base


def _provenance(**kwargs):
    base = {
        "id": 1,
        "source_url": "https://example.gov/law",
        "reviewed_at": _days_ago(10),
        "crawled_at": _days_ago(10),
        "extraction_confidence": 0.95,
        "parser_version": "v1",
        "reviewer_action": "approved",
    }
    base.update(kwargs)
    return base


# ── Rule 1: pending_change_rule ────────────────────────────────────────────────

class TestPendingChangeRule(unittest.TestCase):

    def test_ignores_non_pending_status(self):
        item = _pending_item(status="approved")
        self.assertIsNone(pending_change_rule("annual_leave", _current_entry(), item, NOW))

    def test_critical_item_always_critical(self):
        item = _pending_item(severity="critical", days_old=0)
        rec = pending_change_rule("annual_leave", _current_entry(), item, NOW)
        self.assertIsNotNone(rec)
        self.assertEqual(rec.severity, "CRITICAL")
        self.assertEqual(rec.drift_type, "PENDING_CHANGE")

    def test_major_item_warning_before_threshold(self):
        item = _pending_item(severity="major", days_old=PENDING_DAYS_CRITICAL - 1)
        rec = pending_change_rule("annual_leave", _current_entry(), item, NOW)
        self.assertEqual(rec.severity, "WARNING")

    def test_major_item_critical_at_threshold(self):
        item = _pending_item(severity="major", days_old=PENDING_DAYS_CRITICAL)
        rec = pending_change_rule("annual_leave", _current_entry(), item, NOW)
        self.assertEqual(rec.severity, "CRITICAL")

    def test_minor_item_info_before_threshold(self):
        item = _pending_item(severity="minor", days_old=PENDING_DAYS_WARNING - 1)
        rec = pending_change_rule("annual_leave", _current_entry(), item, NOW)
        self.assertEqual(rec.severity, "INFO")

    def test_minor_item_warning_at_threshold(self):
        item = _pending_item(severity="minor", days_old=PENDING_DAYS_WARNING)
        rec = pending_change_rule("annual_leave", _current_entry(), item, NOW)
        self.assertEqual(rec.severity, "WARNING")

    def test_fields_populated(self):
        item = _pending_item(severity="major", days_old=3)
        rec = pending_change_rule("annual_leave", _current_entry(), item, NOW)
        self.assertEqual(rec.country, "TestLand")
        self.assertEqual(rec.section, "annual_leave")
        self.assertEqual(rec.current_value, "20 days")
        self.assertEqual(rec.proposed_value, "22 days")
        self.assertEqual(rec.days_pending, 3)

    def test_missing_current_entry(self):
        item = _pending_item(severity="critical")
        rec = pending_change_rule("annual_leave", None, item, NOW)
        self.assertIsNotNone(rec)
        self.assertIsNone(rec.last_verified_at)


# ── Rule 2: escalated_item_rule ────────────────────────────────────────────────

class TestEscalatedItemRule(unittest.TestCase):

    def test_ignores_pending_status(self):
        item = _pending_item(status="pending")
        self.assertIsNone(escalated_item_rule("annual_leave", _current_entry(), item, NOW))

    def test_warning_before_threshold(self):
        item = _pending_item(status="escalated", days_old=ESCALATED_DAYS_CRITICAL - 1)
        rec = escalated_item_rule("annual_leave", _current_entry(), item, NOW)
        self.assertEqual(rec.severity, "WARNING")

    def test_critical_at_threshold(self):
        item = _pending_item(status="escalated", days_old=ESCALATED_DAYS_CRITICAL)
        rec = escalated_item_rule("annual_leave", _current_entry(), item, NOW)
        self.assertEqual(rec.severity, "CRITICAL")
        self.assertEqual(rec.drift_type, "ESCALATED_ITEM")


# ── Rule 3: missing_section_rule ───────────────────────────────────────────────

class TestMissingSectionRule(unittest.TestCase):

    def test_ignores_when_entry_exists(self):
        item = _pending_item(status="pending")
        self.assertIsNone(missing_section_rule("annual_leave", _current_entry(), item, NOW))

    def test_ignores_non_actionable_status(self):
        item = _pending_item(status="approved")
        self.assertIsNone(missing_section_rule("annual_leave", None, item, NOW))

    def test_critical_for_critical_severity(self):
        item = _pending_item(status="pending", severity="critical", confidence=0.5)
        rec = missing_section_rule("annual_leave", None, item, NOW)
        self.assertEqual(rec.severity, "CRITICAL")
        self.assertEqual(rec.drift_type, "MISSING_SECTION")

    def test_critical_for_high_confidence(self):
        item = _pending_item(status="pending", severity="minor", confidence=0.85)
        rec = missing_section_rule("annual_leave", None, item, NOW)
        self.assertEqual(rec.severity, "CRITICAL")

    def test_warning_for_medium_confidence(self):
        item = _pending_item(status="pending", severity="minor", confidence=0.70)
        rec = missing_section_rule("annual_leave", None, item, NOW)
        self.assertEqual(rec.severity, "WARNING")

    def test_info_for_low_confidence(self):
        item = _pending_item(status="pending", severity="minor", confidence=0.50)
        rec = missing_section_rule("annual_leave", None, item, NOW)
        self.assertEqual(rec.severity, "INFO")

    def test_escalated_status_also_triggers(self):
        item = _pending_item(status="escalated", severity="minor", confidence=0.90)
        rec = missing_section_rule("annual_leave", None, item, NOW)
        self.assertIsNotNone(rec)


# ── Rule 4: stale_verification_rule ───────────────────────────────────────────

class TestStaleVerificationRule(unittest.TestCase):

    def test_no_drift_when_recently_verified(self):
        entry = _current_entry(last_updated=_days_ago(STALE_DAYS_INFO - 1))
        self.assertIsNone(stale_verification_rule("annual_leave", entry, None, NOW))

    def test_info_at_info_threshold(self):
        entry = _current_entry(last_updated=_days_ago(STALE_DAYS_INFO))
        rec = stale_verification_rule("annual_leave", entry, None, NOW)
        self.assertEqual(rec.severity, "INFO")
        self.assertEqual(rec.drift_type, "STALE_VERIFICATION")

    def test_warning_at_warning_threshold(self):
        entry = _current_entry(last_updated=_days_ago(STALE_DAYS_WARNING))
        rec = stale_verification_rule("annual_leave", entry, None, NOW)
        self.assertEqual(rec.severity, "WARNING")

    def test_critical_at_critical_threshold(self):
        entry = _current_entry(last_updated=_days_ago(STALE_DAYS_CRITICAL))
        rec = stale_verification_rule("annual_leave", entry, None, NOW)
        self.assertEqual(rec.severity, "CRITICAL")

    def test_provenance_reviewed_at_takes_priority(self):
        # provenance reviewed 5 days ago → no drift even if entry is old
        entry = _current_entry(last_updated=_days_ago(STALE_DAYS_CRITICAL + 10))
        prov = _provenance(reviewed_at=_days_ago(5))
        self.assertIsNone(stale_verification_rule("annual_leave", entry, prov, NOW))

    def test_provenance_stale_triggers_drift(self):
        entry = _current_entry(last_updated=_days_ago(5))
        prov = _provenance(reviewed_at=_days_ago(STALE_DAYS_CRITICAL))
        rec = stale_verification_rule("annual_leave", entry, prov, NOW)
        self.assertEqual(rec.severity, "CRITICAL")

    def test_no_drift_when_no_timestamp_available(self):
        entry = _current_entry(last_updated=None)
        self.assertIsNone(stale_verification_rule("annual_leave", entry, None, NOW))


# ── Rule 5: no_provenance_rule ─────────────────────────────────────────────────

class TestNoProvenanceRule(unittest.TestCase):

    def test_no_drift_when_provenance_exists(self):
        entry = _current_entry()
        prov = _provenance()
        self.assertIsNone(no_provenance_rule("annual_leave", entry, prov, NOW))

    def test_warning_when_no_provenance(self):
        entry = _current_entry()
        rec = no_provenance_rule("annual_leave", entry, None, NOW)
        self.assertIsNotNone(rec)
        self.assertEqual(rec.severity, "WARNING")
        self.assertEqual(rec.drift_type, "NO_PROVENANCE")


# ── report helpers ─────────────────────────────────────────────────────────────

class TestReportHelpers(unittest.TestCase):

    def _record(self, severity, drift_type="PENDING_CHANGE"):
        return DriftRecord(
            country="TestLand", section="annual_leave", drift_type=drift_type,
            severity=severity, current_value=None, proposed_value=None,
            pending_item_id=None, days_pending=None, last_verified_at=None,
            evidence="", recommended_action="",
        )

    def test_aggregate_severity_empty(self):
        self.assertEqual(aggregate_severity([]), "NONE")

    def test_aggregate_severity_picks_highest(self):
        records = [self._record("INFO"), self._record("CRITICAL"), self._record("WARNING")]
        self.assertEqual(aggregate_severity(records), "CRITICAL")

    def test_build_summary_no_drift(self):
        summary = build_summary([], "TestLand")
        self.assertIn("No drift", summary)

    def test_build_summary_counts(self):
        records = [self._record("CRITICAL"), self._record("WARNING"), self._record("INFO")]
        summary = build_summary(records, "TestLand")
        self.assertIn("3 drift issue", summary)
        self.assertIn("1 critical", summary)

    def test_build_recommended_action_critical(self):
        records = [self._record("CRITICAL", "PENDING_CHANGE")]
        action = build_recommended_action(records)
        self.assertIn("critical", action.lower())


# ── integration: DriftDetector with in-memory DB ───────────────────────────────

def _make_in_memory_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE country_guide (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            country TEXT NOT NULL,
            section TEXT NOT NULL,
            value TEXT,
            last_updated TEXT,
            current_provenance_id INTEGER
        );
        CREATE TABLE review_queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            country TEXT NOT NULL,
            section TEXT NOT NULL,
            old_value TEXT,
            new_value TEXT,
            status TEXT NOT NULL DEFAULT 'pending',
            severity TEXT DEFAULT 'minor',
            confidence REAL,
            created_at TEXT
        );
        CREATE TABLE rule_provenance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            country TEXT NOT NULL,
            section TEXT NOT NULL,
            rule_value TEXT,
            review_queue_id INTEGER,
            source_snapshot_id INTEGER,
            ingestion_job_id INTEGER,
            source_url TEXT,
            source_hash TEXT,
            source_fragment TEXT,
            extraction_confidence REAL,
            parser_version TEXT,
            reviewer_action TEXT,
            reviewer_assignee TEXT,
            reviewer_rationale TEXT,
            reviewer_comment TEXT,
            crawled_at TEXT,
            extracted_at TEXT,
            reviewed_at TEXT,
            created_at TEXT NOT NULL
        );
        CREATE TABLE source_snapshots (id INTEGER PRIMARY KEY);
        CREATE TABLE ingestion_jobs (id INTEGER PRIMARY KEY);
    """)
    conn.commit()
    return conn


class InMemoryDriftRepository(DriftRepository):
    """Subclass that shares an in-memory connection."""
    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def _connect(self):
        return self._conn

    def list_countries(self):
        rows = self._conn.execute(
            "SELECT DISTINCT country FROM country_guide ORDER BY country"
        ).fetchall()
        return [r["country"] for r in rows]


class TestDriftDetectorIntegration(unittest.TestCase):

    def setUp(self):
        self.conn = _make_in_memory_db()
        self.repo = InMemoryDriftRepository(self.conn)
        self.detector = DriftDetector(self.repo)

    def _insert_guide(self, country, section, value, days_old=5, provenance_id=None):
        self.conn.execute(
            "INSERT INTO country_guide (country, section, value, last_updated, current_provenance_id) VALUES (?,?,?,?,?)",
            (country, section, value, _days_ago(days_old), provenance_id),
        )
        self.conn.commit()

    def _insert_pending(self, country, section, status="pending", severity="minor",
                        days_old=0, confidence=0.9):
        self.conn.execute(
            "INSERT INTO review_queue (country, section, old_value, new_value, status, severity, confidence, created_at) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (country, section, "old", "new", status, severity, confidence, _days_ago(days_old)),
        )
        self.conn.commit()

    def _insert_provenance(self, country, section, reviewed_days_ago=5):
        self.conn.execute(
            "INSERT INTO rule_provenance "
            "(country, section, rule_value, reviewer_action, reviewed_at, created_at) "
            "VALUES (?,?,?,?,?,?)",
            (country, section, "20 days", "approved",
             _days_ago(reviewed_days_ago), _days_ago(reviewed_days_ago)),
        )
        self.conn.commit()

    def test_no_drift_clean_guide(self):
        self._insert_guide("Australia", "annual_leave", "4 weeks", days_old=5)
        self._insert_provenance("Australia", "annual_leave", reviewed_days_ago=5)
        report = self.detector.detect("Australia", now=NOW)
        self.assertFalse(report.drift_detected)
        self.assertEqual(report.severity, "NONE")

    def test_detects_pending_change(self):
        self._insert_guide("Australia", "annual_leave", "4 weeks")
        self._insert_pending("Australia", "annual_leave", status="pending",
                             severity="major", days_old=PENDING_DAYS_CRITICAL)
        report = self.detector.detect("Australia", now=NOW)
        self.assertTrue(report.drift_detected)
        types = {r.drift_type for r in report.affected_sections}
        self.assertIn("PENDING_CHANGE", types)

    def test_detects_stale_section(self):
        self._insert_guide("Australia", "annual_leave", "4 weeks",
                          days_old=STALE_DAYS_CRITICAL)
        report = self.detector.detect("Australia", now=NOW)
        self.assertTrue(report.drift_detected)
        types = {r.drift_type for r in report.affected_sections}
        self.assertIn("STALE_VERIFICATION", types)

    def test_detects_no_provenance(self):
        self._insert_guide("Australia", "annual_leave", "4 weeks", days_old=5)
        # No provenance inserted → should get NO_PROVENANCE warning
        report = self.detector.detect("Australia", now=NOW)
        types = {r.drift_type for r in report.affected_sections}
        self.assertIn("NO_PROVENANCE", types)

    def test_detects_missing_section(self):
        # Pending item for a section that has no guide entry
        self._insert_pending("India", "maternity_leave", status="pending",
                             severity="critical", confidence=0.9)
        report = self.detector.detect("India", now=NOW)
        types = {r.drift_type for r in report.affected_sections}
        self.assertIn("MISSING_SECTION", types)

    def test_detect_all_covers_all_countries(self):
        self._insert_guide("Australia", "annual_leave", "4 weeks")
        self._insert_guide("India", "annual_leave", "26 days")
        reports = self.detector.detect_all(now=NOW)
        countries = {r.country for r in reports}
        self.assertIn("Australia", countries)
        self.assertIn("India", countries)

    def test_deduplication_keeps_highest_severity(self):
        # Two pending items for the same section — only highest severity should survive
        self._insert_guide("Australia", "annual_leave", "4 weeks")
        self._insert_pending("Australia", "annual_leave", status="pending",
                             severity="minor", days_old=1)
        self._insert_pending("Australia", "annual_leave", status="pending",
                             severity="critical", days_old=1)
        report = self.detector.detect("Australia", now=NOW)
        pending_records = [r for r in report.affected_sections if r.drift_type == "PENDING_CHANGE"]
        # Should be deduplicated to one record
        self.assertEqual(len(pending_records), 1)
        self.assertEqual(pending_records[0].severity, "CRITICAL")

    def test_escalated_item_detected(self):
        self._insert_guide("Australia", "annual_leave", "4 weeks")
        self._insert_pending("Australia", "annual_leave", status="escalated",
                             days_old=ESCALATED_DAYS_CRITICAL)
        report = self.detector.detect("Australia", now=NOW)
        types = {r.drift_type for r in report.affected_sections}
        self.assertIn("ESCALATED_ITEM", types)

    def test_report_to_dict_is_serializable(self):
        self._insert_guide("Australia", "annual_leave", "4 weeks",
                          days_old=STALE_DAYS_WARNING)
        report = self.detector.detect("Australia", now=NOW)
        d = report.to_dict()
        self.assertIn("affected_sections", d)
        self.assertIsInstance(d["affected_sections"], list)


if __name__ == "__main__":
    unittest.main()
