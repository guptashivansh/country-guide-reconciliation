import json
import unittest

from app.reconciliation.llm_reconciliation_service import LLMReconciliationEngine
from app.reconciliation.schemas import ChangeType, MaterialityLevel


class FakeProvider:
    def __init__(self, responses):
        self.responses = list(responses)
        self.prompts = []

    def complete(self, prompt):
        self.prompts.append(prompt)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def _payload(**overrides):
    base = {
        "semantic_change_detected": True,
        "materiality_level": "HIGH",
        "change_type": "NUMERIC_THRESHOLD_CHANGE",
        "human_readable_summary": "CPF contribution rate increased from 17% to 18%.",
        "reasoning": ["Numeric value changed from 17 to 18 in a social security context."],
    }
    base.update(overrides)
    return json.dumps(base)


class LLMReconciliationEngineTest(unittest.TestCase):
    def test_parses_valid_json_response(self):
        provider = FakeProvider([_payload()])
        engine = LLMReconciliationEngine(provider)

        result = engine.reconcile(
            {"section": "social_security", "value": "Employers must contribute CPF at 17 percent."},
            {"section": "social_security", "value": "Employers must contribute CPF at 18 percent."},
        )

        self.assertTrue(result.semantic_change_detected)
        self.assertEqual(result.materiality_level, MaterialityLevel.HIGH)
        self.assertEqual(result.change_type, ChangeType.NUMERIC_THRESHOLD_CHANGE)

    def test_includes_country_and_section_in_prompt(self):
        provider = FakeProvider([_payload()])
        engine = LLMReconciliationEngine(provider)

        engine.reconcile(
            {"country": "Singapore", "section": "social_security", "value": "Old text"},
            {"country": "Singapore", "section": "social_security", "value": "New text"},
        )

        self.assertIn("Singapore", provider.prompts[0])
        self.assertIn("social_security", provider.prompts[0])
        self.assertIn("Old text", provider.prompts[0])
        self.assertIn("New text", provider.prompts[0])

    def test_strips_markdown_fence_before_parsing(self):
        provider = FakeProvider([f"```json\n{_payload()}\n```"])
        engine = LLMReconciliationEngine(provider)

        result = engine.reconcile(
            {"section": "annual_leave", "value": "old"},
            {"section": "annual_leave", "value": "new"},
        )

        self.assertEqual(result.change_type, ChangeType.NUMERIC_THRESHOLD_CHANGE)

    def test_retries_on_malformed_json_then_succeeds(self):
        provider = FakeProvider(["not valid json", _payload(materiality_level="LOW")])
        engine = LLMReconciliationEngine(provider, max_attempts=2)

        result = engine.reconcile(
            {"section": "annual_leave", "value": "old"},
            {"section": "annual_leave", "value": "new"},
        )

        self.assertEqual(result.materiality_level, MaterialityLevel.LOW)
        self.assertEqual(len(provider.prompts), 2)

    def test_raises_after_exhausting_attempts_on_invalid_response(self):
        provider = FakeProvider(["not valid json", "still not valid"])
        engine = LLMReconciliationEngine(provider, max_attempts=2)

        with self.assertRaises(RuntimeError):
            engine.reconcile(
                {"section": "annual_leave", "value": "old"},
                {"section": "annual_leave", "value": "new"},
            )

    def test_retries_on_provider_exception(self):
        provider = FakeProvider([RuntimeError("rate limited"), _payload()])
        engine = LLMReconciliationEngine(provider, max_attempts=2)

        result = engine.reconcile(
            {"section": "annual_leave", "value": "old"},
            {"section": "annual_leave", "value": "new"},
        )

        self.assertEqual(result.change_type, ChangeType.NUMERIC_THRESHOLD_CHANGE)

    def test_rejects_response_with_invalid_enum_value(self):
        provider = FakeProvider([
            _payload(materiality_level="EXTREME"),
            _payload(),
        ])
        engine = LLMReconciliationEngine(provider, max_attempts=2)

        result = engine.reconcile(
            {"section": "annual_leave", "value": "old"},
            {"section": "annual_leave", "value": "new"},
        )

        self.assertEqual(result.materiality_level, MaterialityLevel.HIGH)
        self.assertEqual(len(provider.prompts), 2)


if __name__ == "__main__":
    unittest.main()
