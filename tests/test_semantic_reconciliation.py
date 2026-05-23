import unittest

from app.reconciliation.schemas import ChangeType, MaterialityLevel, SemanticReconciliationResult
from app.reconciliation.semantic_reconciliation_service import SemanticReconciliationEngine


class StubFallback:
    def __init__(self):
        self.called = False

    def classify(self, old_rule, new_rule):
        self.called = True
        return SemanticReconciliationResult(
            semantic_change_detected=True,
            materiality_level=MaterialityLevel.LOW,
            change_type=ChangeType.REQUIREMENT_ADDED,
            human_readable_summary="Fallback classified ambiguous wording.",
            reasoning=["Fallback invoked after deterministic checks found no structured signal."],
        )


class SemanticReconciliationEngineTest(unittest.TestCase):
    def setUp(self):
        self.engine = SemanticReconciliationEngine()

    def test_detects_numeric_threshold_change(self):
        result = self.engine.reconcile(
            {
                "section": "social_security",
                "text": "Employers must contribute CPF at 17 percent for eligible employees.",
                "numeric_thresholds": [{"label": "cpf", "value": 17, "unit": "percent"}],
                "requirements": ["Employers must contribute CPF for eligible employees."],
            },
            {
                "section": "social_security",
                "text": "Employers must contribute CPF at 18 percent for eligible employees.",
                "numeric_thresholds": [{"label": "cpf", "value": 18, "unit": "percent"}],
                "requirements": ["Employers must contribute CPF for eligible employees."],
            },
        )

        self.assertTrue(result.semantic_change_detected)
        self.assertEqual(result.change_type, ChangeType.NUMERIC_THRESHOLD_CHANGE)
        self.assertEqual(result.materiality_level, MaterialityLevel.HIGH)

    def test_detects_structured_threshold_change_when_text_is_unchanged(self):
        result = self.engine.reconcile(
            {
                "section": "social_security",
                "text": "Employers must contribute CPF for eligible employees.",
                "numeric_thresholds": [{"label": "cpf", "value": 17, "unit": "percent"}],
            },
            {
                "section": "social_security",
                "text": "Employers must contribute CPF for eligible employees.",
                "numeric_thresholds": [{"label": "cpf", "value": 18, "unit": "percent"}],
            },
        )

        self.assertTrue(result.semantic_change_detected)
        self.assertEqual(result.change_type, ChangeType.NUMERIC_THRESHOLD_CHANGE)

    def test_detects_eligibility_change(self):
        result = self.engine.reconcile(
            {
                "section": "social_security",
                "text": "CPF applies to Singapore Citizens.",
                "eligibility": ["Singapore Citizens"],
            },
            {
                "section": "social_security",
                "text": "CPF applies to Singapore Citizens and Singapore Permanent Residents.",
                "eligibility": ["Singapore Citizens", "Singapore Permanent Residents"],
            },
        )

        self.assertTrue(result.semantic_change_detected)
        self.assertEqual(result.change_type, ChangeType.ELIGIBILITY_CHANGE)
        self.assertEqual(result.materiality_level, MaterialityLevel.HIGH)

    def test_detects_requirement_added(self):
        result = self.engine.reconcile(
            {
                "section": "payroll_tax",
                "text": "Employers should keep payroll records.",
                "requirements": ["Employers should keep payroll records."],
            },
            {
                "section": "payroll_tax",
                "text": "Employers should keep payroll records. Employers must submit payroll tax filings monthly.",
                "requirements": [
                    "Employers should keep payroll records.",
                    "Employers must submit payroll tax filings monthly.",
                ],
            },
        )

        self.assertTrue(result.semantic_change_detected)
        self.assertEqual(result.change_type, ChangeType.REQUIREMENT_ADDED)
        self.assertIn(result.materiality_level, {MaterialityLevel.MODERATE, MaterialityLevel.HIGH})

    def test_detects_requirement_removed(self):
        result = self.engine.reconcile(
            {
                "section": "workplace_safety",
                "text": "Employers must report workplace safety incidents. Employers must keep incident records.",
                "requirements": [
                    "Employers must report workplace safety incidents.",
                    "Employers must keep incident records.",
                ],
            },
            {
                "section": "workplace_safety",
                "text": "Employers must keep incident records.",
                "requirements": ["Employers must keep incident records."],
            },
        )

        self.assertTrue(result.semantic_change_detected)
        self.assertEqual(result.change_type, ChangeType.REQUIREMENT_REMOVED)

    def test_detects_timeline_change(self):
        result = self.engine.reconcile(
            {
                "section": "termination_notice",
                "text": "Employer must provide notice within 30 days before termination.",
            },
            {
                "section": "termination_notice",
                "text": "Employer must provide notice within 45 days before termination.",
            },
        )

        self.assertTrue(result.semantic_change_detected)
        self.assertEqual(result.change_type, ChangeType.TIMELINE_CHANGE)
        self.assertEqual(result.materiality_level, MaterialityLevel.HIGH)

    def test_non_material_formatting_change(self):
        result = self.engine.reconcile(
            {"section": "annual_leave", "value": "Employees are entitled to paid annual leave."},
            {"section": "annual_leave", "value": "Employees are entitled to paid annual leave!"},
        )

        self.assertFalse(result.semantic_change_detected)
        self.assertEqual(result.change_type, ChangeType.NON_MATERIAL_FORMATTING)
        self.assertEqual(result.materiality_level, MaterialityLevel.INFORMATIONAL)

    def test_uses_fallback_after_deterministic_checks(self):
        fallback = StubFallback()
        engine = SemanticReconciliationEngine(fallback=fallback)

        result = engine.reconcile(
            {"section": "policy", "text": "Guidance may vary by local interpretation."},
            {"section": "policy", "text": "Guidance may vary based on local operating interpretation."},
        )

        self.assertTrue(fallback.called)
        self.assertEqual(result.human_readable_summary, "Fallback classified ambiguous wording.")


if __name__ == "__main__":
    unittest.main()
