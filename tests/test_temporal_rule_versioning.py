import os
import tempfile
import unittest

from app.repositories.country_guide_repository import CountryGuideRepository
from app.services.temporal_rule_service import TemporalRuleService


class TemporalRuleVersioningTest(unittest.TestCase):
    def setUp(self):
        handle = tempfile.NamedTemporaryFile(delete=False)
        handle.close()
        self.db_path = handle.name
        self.repository = CountryGuideRepository(self.db_path)
        self.repository.initialize_schema()
        self.service = TemporalRuleService(self.repository)

    def tearDown(self):
        os.unlink(self.db_path)

    def test_time_based_lookup_returns_rule_effective_on_date(self):
        self.repository.upsert_guide_entry(
            "India",
            "termination_notice",
            "30 days notice or pay in lieu",
            "https://labour.gov.in/",
            effective_date="2024-01-01",
            approval_reference="initial-import",
        )
        self.repository.upsert_guide_entry(
            "India",
            "termination_notice",
            "45 days notice or pay in lieu",
            "https://labour.gov.in/",
            effective_date="2024-06-01",
            approval_reference="review_queue:12",
        )

        may_rule = self.service.get_rule_at_date("India", "termination_notice", "2024-05-15")
        june_rule = self.service.get_rule_at_date("India", "termination_notice", "2024-06-01")
        history = self.service.list_version_history("India", "termination_notice")

        self.assertEqual(may_rule["value"], "30 days notice or pay in lieu")
        self.assertEqual(june_rule["value"], "45 days notice or pay in lieu")
        self.assertEqual(june_rule["version_number"], 2)
        self.assertEqual(len(history), 2)
        self.assertEqual(history[0]["superseded_at"], "2024-06-01T00:00:00")

    def test_review_approval_publishes_version_metadata(self):
        self.repository.upsert_guide_entry(
            "Singapore",
            "social_security",
            "Employers must contribute CPF at 17 percent.",
            "https://www.cpf.gov.sg/",
            effective_date="2025-01-01",
            approval_reference="initial-import",
        )
        self.repository.enqueue_review_item(
            "Singapore",
            "social_security",
            "Employers must contribute CPF at 17 percent.",
            "Employers must contribute CPF at 18 percent.",
            "major",
            0.94,
            "https://www.cpf.gov.sg/",
            "Employer contribution rate changed to 18 percent.",
            "hash-123",
            44,
            effective_date="2025-07-01",
        )

        result = self.repository.approve_pending_review_item(1, "Approved", "Priya", "Threshold update")
        july_rule = self.service.get_rule_at_date("Singapore", "social_security", "2025-07-15")

        self.assertEqual(result["effective_date"], "2025-07-01")
        self.assertEqual(result["version_number"], 2)
        self.assertEqual(result["approval_reference"], "review_queue:1")
        self.assertEqual(july_rule["approval_reference"], "review_queue:1")

    def test_current_rule_is_separate_from_version_history(self):
        self.repository.upsert_guide_entry(
            "Australia",
            "annual_leave",
            "Employees are entitled to four weeks of paid annual leave.",
            "https://www.fairwork.gov.au/",
            effective_date="2024-01-01",
            approval_reference="initial-import",
        )

        current = self.service.get_current_rule("Australia", "annual_leave")
        history = self.service.list_version_history("Australia", "annual_leave")

        self.assertEqual(current["value"], history[-1]["value"])
        self.assertIsNone(history[-1]["superseded_at"])
        self.assertEqual(current["version_number"], 1)


if __name__ == "__main__":
    unittest.main()
