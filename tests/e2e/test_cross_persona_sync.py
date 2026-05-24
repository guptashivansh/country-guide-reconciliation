"""
Playwright E2E tests: cross-persona data synchronization.

Verifies that a data change made by one persona is immediately and
simultaneously visible to all other personas (Reviewer, Admin, Publisher,
Employee) without requiring independent refreshes or cache invalidation.
"""

import pytest

from tests.e2e.conftest import TEST_COUNTRY, TEST_RULES

pytestmark = [pytest.mark.e2e, pytest.mark.sync]


# ── Helpers ───────────────────────────────────────────────────────────────────


def _api_get_json(page, base_url, path):
    resp = page.request.get(f"{base_url}{path}")
    assert resp.ok, f"GET {path} failed: {resp.status}"
    return resp.json()


def _api_post_json(page, base_url, path, data=None):
    resp = page.request.post(f"{base_url}{path}", data=data)
    assert resp.ok, f"POST {path} failed: {resp.status}"
    return resp.json()


def _api_put_json(page, base_url, path, data=None):
    resp = page.request.put(f"{base_url}{path}", data=data)
    assert resp.ok, f"PUT {path} failed: {resp.status}"
    return resp.json()


def _get_guide_value(page, base_url, country, section):
    guide = _api_get_json(page, base_url, f"/api/employee/guide/{country}")
    for group in guide["groups"]:
        for rule in group["rules"]:
            if rule["id"] == section:
                return rule["value"]
    return None


def _get_pending_queue(page, base_url):
    return _api_get_json(page, base_url, "/api/queue")


def _get_metrics(page, base_url):
    return _api_get_json(page, base_url, "/api/metrics")


def _get_audit(page, base_url, country=None):
    path = "/api/audit"
    if country:
        path += f"?country={country}"
    return _api_get_json(page, base_url, path)


def _get_guide_entries(page, base_url):
    return _api_get_json(page, base_url, "/api/guide")


# ── Tests ─────────────────────────────────────────────────────────────────────


class TestCrossPersonaSync:
    """Verify that data changes propagate simultaneously across all personas."""

    def test_seeded_data_visible_to_all_personas(
        self, reviewer_page, publisher_page, employee_page, seeded_app
    ):
        """Baseline: all personas see the same seeded data before any changes."""
        base = seeded_app["base_url"]

        guide_entries = _get_guide_entries(reviewer_page, base)
        germany_entries = [e for e in guide_entries if e["country"] == TEST_COUNTRY]
        assert len(germany_entries) >= len(TEST_RULES)

        for section, expected_value in TEST_RULES.items():
            pub_value = _get_guide_value(publisher_page, base, TEST_COUNTRY, section)
            assert pub_value is not None, f"Publisher missing {section}"

            emp_value = _get_guide_value(employee_page, base, TEST_COUNTRY, section)
            assert emp_value is not None, f"Employee missing {section}"

            assert pub_value == emp_value, (
                f"Publisher/Employee mismatch for {section}: {pub_value!r} vs {emp_value!r}"
            )

    def test_pending_review_items_visible_to_reviewer_and_admin(
        self, reviewer_page, admin_page, seeded_app
    ):
        """Review queue items are visible to both reviewer and admin personas."""
        base = seeded_app["base_url"]

        queue_reviewer = _get_pending_queue(reviewer_page, base)
        queue_admin = _get_pending_queue(admin_page, base)

        assert len(queue_reviewer) == len(queue_admin)

        pending_sections = {item["section"] for item in queue_reviewer}
        assert "annual_leave" in pending_sections
        assert "minimum_wage" in pending_sections

        metrics_reviewer = _get_metrics(reviewer_page, base)
        metrics_admin = _get_metrics(admin_page, base)
        assert metrics_reviewer["pending_reviews"] == metrics_admin["pending_reviews"]
        assert metrics_reviewer["pending_reviews"] >= 2

    def test_approval_propagates_to_all_personas(
        self, reviewer_page, publisher_page, employee_page, admin_page, seeded_app
    ):
        """
        When the reviewer approves a change, the new value appears
        simultaneously in the guide (publisher), employee view, and
        metrics (admin) without separate refresh or sync.
        """
        base = seeded_app["base_url"]

        old_value = _get_guide_value(publisher_page, base, TEST_COUNTRY, "annual_leave")
        assert old_value == "20 working days minimum"

        queue = _get_pending_queue(reviewer_page, base)
        leave_item = next(i for i in queue if i["section"] == "annual_leave")
        item_id = leave_item["id"]

        metrics_before = _get_metrics(admin_page, base)
        pending_before = metrics_before["pending_reviews"]

        result = _api_post_json(reviewer_page, base, f"/api/approve/{item_id}", {
            "notes": "E2E test approval",
            "assignee": "e2e-tester",
            "rationale": "Verified against government gazette",
            "effective_date": "2026-01-01",
        })
        assert result["success"] is True
        assert result["status"] == "approved"

        pub_value = _get_guide_value(publisher_page, base, TEST_COUNTRY, "annual_leave")
        assert pub_value == "24 working days minimum (updated 2026)"

        emp_value = _get_guide_value(employee_page, base, TEST_COUNTRY, "annual_leave")
        assert emp_value == "24 working days minimum (updated 2026)"

        metrics_after = _get_metrics(admin_page, base)
        assert metrics_after["pending_reviews"] == pending_before - 1

        audit = _get_audit(reviewer_page, base, country=TEST_COUNTRY)
        approval_entries = [
            e for e in audit
            if e.get("section") == "annual_leave"
            and e.get("decision") == "approved"
        ]
        assert len(approval_entries) >= 1

    def test_rejection_preserves_original_value_across_personas(
        self, reviewer_page, publisher_page, employee_page, seeded_app
    ):
        """
        When the reviewer rejects a change, the original value is
        retained for both publisher and employee personas.
        """
        base = seeded_app["base_url"]

        queue = _get_pending_queue(reviewer_page, base)
        wage_item = next(
            (i for i in queue if i["section"] == "minimum_wage" and i["status"] == "pending"),
            None,
        )
        if wage_item is None:
            pytest.skip("No pending minimum_wage item to reject")

        item_id = wage_item["id"]
        result = _api_post_json(reviewer_page, base, f"/api/reject/{item_id}", {
            "notes": "Source not authoritative",
            "assignee": "e2e-tester",
            "rationale": "Document is draft, not final",
        })
        assert result["success"] is True
        assert result["status"] == "rejected"

        pub_value = _get_guide_value(publisher_page, base, TEST_COUNTRY, "minimum_wage")
        assert pub_value == TEST_RULES["minimum_wage"]

        emp_value = _get_guide_value(employee_page, base, TEST_COUNTRY, "minimum_wage")
        assert emp_value == TEST_RULES["minimum_wage"]

    def test_manual_edit_propagates_to_all_personas(
        self, reviewer_page, publisher_page, employee_page, admin_page, seeded_app
    ):
        """
        A publisher's manual edit is immediately visible to the employee
        and shows up in the audit trail for the reviewer.
        """
        base = seeded_app["base_url"]
        new_value = "10 hours/day, 50 hours/week maximum (amended 2026)"

        result = _api_put_json(publisher_page, base, f"/api/guide/{TEST_COUNTRY}/working_hours", {
            "value": new_value,
        })
        assert result["success"] is True

        emp_value = _get_guide_value(employee_page, base, TEST_COUNTRY, "working_hours")
        assert emp_value == new_value

        pub_value = _get_guide_value(publisher_page, base, TEST_COUNTRY, "working_hours")
        assert pub_value == new_value

        audit = _get_audit(reviewer_page, base, country=TEST_COUNTRY)
        manual_edits = [
            e for e in audit
            if e.get("action") == "MANUAL_EDIT" and e.get("section") == "working_hours"
        ]
        assert len(manual_edits) >= 1
        assert manual_edits[0]["new_value"] == new_value

    def test_version_history_reflects_all_changes(
        self, reviewer_page, publisher_page, seeded_app
    ):
        """
        After seeding + manual edit, the version history API returns
        a consistent timeline visible to any persona.
        """
        base = seeded_app["base_url"]

        _api_put_json(publisher_page, base, f"/api/guide/{TEST_COUNTRY}/sick_leave", {
            "value": "8 weeks full pay (amended 2026)",
        })

        history_from_reviewer = _api_get_json(
            reviewer_page, base,
            f"/api/guide/{TEST_COUNTRY}/sick_leave/history",
        )
        history_from_publisher = _api_get_json(
            publisher_page, base,
            f"/api/guide/{TEST_COUNTRY}/sick_leave/history",
        )

        assert len(history_from_reviewer) == len(history_from_publisher)
        assert len(history_from_reviewer) >= 2

        latest = history_from_reviewer[-1] if isinstance(history_from_reviewer, list) else None
        if latest and "value" in latest:
            assert latest["value"] == "8 weeks full pay (amended 2026)"


class TestMetricsSyncConsistency:
    """Verify that dashboard metrics stay consistent across personas."""

    def test_metrics_match_queue_state(self, reviewer_page, admin_page, seeded_app):
        """Metrics pending count matches actual queue length across personas."""
        base = seeded_app["base_url"]

        queue = _get_pending_queue(reviewer_page, base)
        pending_count = len([i for i in queue if i.get("status") == "pending"])

        metrics_reviewer = _get_metrics(reviewer_page, base)
        metrics_admin = _get_metrics(admin_page, base)

        assert metrics_reviewer["pending_reviews"] == pending_count
        assert metrics_admin["pending_reviews"] == pending_count

    def test_critical_count_matches_across_personas(
        self, reviewer_page, admin_page, seeded_app
    ):
        """Critical change count is consistent between reviewer and admin."""
        base = seeded_app["base_url"]

        queue = _get_pending_queue(reviewer_page, base)
        critical_count = len([
            i for i in queue
            if i.get("status") == "pending" and (i.get("severity") or "").lower() == "critical"
        ])

        metrics_reviewer = _get_metrics(reviewer_page, base)
        metrics_admin = _get_metrics(admin_page, base)

        assert metrics_reviewer["critical_changes"] == critical_count
        assert metrics_admin["critical_changes"] == critical_count


class TestBulkApprovalSync:
    """Verify bulk operations propagate consistently."""

    def test_bulk_approve_updates_all_persona_views(
        self, reviewer_page, publisher_page, employee_page, admin_page, seeded_app
    ):
        """
        Bulk approval of non-critical items updates guide, employee view,
        and metrics simultaneously.
        """
        base = seeded_app["base_url"]

        queue_before = _get_pending_queue(reviewer_page, base)
        non_critical_pending = [
            i for i in queue_before
            if i.get("status") == "pending"
            and (i.get("severity") or "").lower() != "critical"
        ]

        if not non_critical_pending:
            pytest.skip("No non-critical pending items for bulk approval test")

        result = _api_post_json(reviewer_page, base, "/api/bulk-approve", {
            "country": TEST_COUNTRY,
            "comment": "E2E bulk approval test",
            "rationale": "All verified via government sources",
        })
        assert result["success"] is True
        approved_count = result["approved"]
        assert approved_count >= 1

        for item in non_critical_pending:
            section = item["section"]
            expected_new_value = item["new_value"]

            pub_value = _get_guide_value(publisher_page, base, TEST_COUNTRY, section)
            emp_value = _get_guide_value(employee_page, base, TEST_COUNTRY, section)
            assert pub_value == expected_new_value, f"Publisher not updated for {section}"
            assert emp_value == expected_new_value, f"Employee not updated for {section}"

        metrics = _get_metrics(admin_page, base)
        queue_after = _get_pending_queue(reviewer_page, base)
        remaining_pending = len([i for i in queue_after if i.get("status") == "pending"])
        assert metrics["pending_reviews"] == remaining_pending


class TestEscalationSync:
    """Verify escalation state is visible across personas."""

    def test_escalation_visible_in_queue_and_drift(
        self, reviewer_page, admin_page, seeded_app
    ):
        """Escalated items appear in the queue for both reviewer and admin."""
        base = seeded_app["base_url"]

        queue = _get_pending_queue(reviewer_page, base)
        pending_items = [i for i in queue if i.get("status") == "pending"]
        if not pending_items:
            pytest.skip("No pending items to escalate")

        item_id = pending_items[0]["id"]
        result = _api_post_json(reviewer_page, base, f"/api/escalate/{item_id}", {
            "notes": "Needs compliance team review",
            "assignee": "compliance-lead",
            "rationale": "Potential regulatory impact",
        })
        assert result["success"] is True
        assert result["status"] == "escalated"

        queue_reviewer = _api_get_json(reviewer_page, base, "/api/queue")
        queue_admin = _api_get_json(admin_page, base, "/api/queue")

        escalated_reviewer = [i for i in queue_reviewer if i["id"] == item_id]
        escalated_admin = [i for i in queue_admin if i["id"] == item_id]

        assert len(escalated_reviewer) == 1
        assert escalated_reviewer[0]["status"] == "escalated"
        assert len(escalated_admin) == 1
        assert escalated_admin[0]["status"] == "escalated"


class TestNotesSync:
    """Verify country notes propagate across personas."""

    def test_notes_saved_by_publisher_visible_to_reviewer(
        self, reviewer_page, publisher_page, seeded_app
    ):
        """Notes saved on the guide page are retrievable by the reviewer."""
        base = seeded_app["base_url"]
        note_content = "Germany compliance verified Q2 2026. Next review due Q4."

        result = _api_put_json(publisher_page, base, f"/api/notes/{TEST_COUNTRY}", {
            "content": note_content,
        })
        assert result["success"] is True

        notes_from_reviewer = _api_get_json(reviewer_page, base, f"/api/notes/{TEST_COUNTRY}")
        assert notes_from_reviewer["content"] == note_content

        notes_from_publisher = _api_get_json(publisher_page, base, f"/api/notes/{TEST_COUNTRY}")
        assert notes_from_publisher["content"] == note_content


