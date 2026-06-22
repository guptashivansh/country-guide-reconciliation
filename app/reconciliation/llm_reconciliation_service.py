import json
import logging

from pydantic import ValidationError

from app.reconciliation.schemas import CanonicalComplianceRule, SemanticReconciliationResult


logger = logging.getLogger(__name__)

_CLASSIFICATION_GUIDANCE = """
- CRITICAL: the change affects visa, work permit, or immigration eligibility; or a mandatory \
requirement was removed
- HIGH: the change affects minimum wage, tax, social security, pension, termination, dismissal, \
or overtime; or a numeric threshold moved by 25% or more; or the population of workers covered \
by the rule changed
- MODERATE: a numeric threshold, deadline, or timeline changed, but the rule is not in a \
high-impact domain
- LOW: the wording changed and a requirement was added, but no numeric, eligibility, or timeline \
signal was found
- INFORMATIONAL: no material compliance change — punctuation, capitalization, spacing, or \
non-substantive rewording only
""".strip()


class LLMReconciliationEngine:
    """Classifies the materiality and type of a compliance rule change via an LLM call."""

    def __init__(self, provider, max_attempts=2):
        self.provider = provider
        self.max_attempts = max_attempts

    def reconcile(self, old_rule, new_rule) -> SemanticReconciliationResult:
        old = self._coerce_rule(old_rule)
        new = self._coerce_rule(new_rule)
        prompt = self._build_prompt(old, new)

        last_error = None
        for attempt in range(1, self.max_attempts + 1):
            try:
                raw = self.provider.complete(prompt)
            except Exception as e:
                last_error = e
                logger.warning(
                    "LLM reconciliation call failed — retrying",
                    extra={"stage": "reconciliation_classify", "attempt": attempt, "failure": str(e)},
                )
                continue

            try:
                payload = json.loads(self._strip_markdown_fence(raw))
                return SemanticReconciliationResult.model_validate(payload)
            except (json.JSONDecodeError, ValidationError) as e:
                last_error = e
                logger.warning(
                    "LLM reconciliation response invalid — retrying",
                    extra={"stage": "reconciliation_classify", "attempt": attempt, "failure": str(e), "raw_response": raw},
                )

        raise RuntimeError(f"LLM reconciliation failed after {self.max_attempts} attempts: {last_error}")

    def _coerce_rule(self, rule) -> CanonicalComplianceRule:
        if isinstance(rule, CanonicalComplianceRule):
            return rule
        return CanonicalComplianceRule.model_validate(rule)

    def _build_prompt(self, old: CanonicalComplianceRule, new: CanonicalComplianceRule) -> str:
        country = old.country or new.country or "an unspecified jurisdiction"
        section = old.section or new.section or "unspecified"
        return f"""
You are a compliance analyst reviewing a proposed change to an employment rule for {country}.

Section: {section}

PREVIOUS VALUE:
{old.text}

PROPOSED NEW VALUE:
{new.text}

Classify this change. Return a JSON object with exactly these fields:
- semantic_change_detected: true or false — false only if the change is purely cosmetic \
(punctuation, capitalization, spacing, or rewording with no change in meaning)
- materiality_level: one of CRITICAL, HIGH, MODERATE, LOW, INFORMATIONAL
- change_type: one of NUMERIC_THRESHOLD_CHANGE, ELIGIBILITY_CHANGE, REQUIREMENT_ADDED, \
REQUIREMENT_REMOVED, TIMELINE_CHANGE, NON_MATERIAL_FORMATTING
- human_readable_summary: one sentence describing what changed
- reasoning: an array of short strings explaining the classification

Classification guidance:
{_CLASSIFICATION_GUIDANCE}

Return ONLY valid JSON. No explanation. No markdown. No backticks.
""".strip()

    def _strip_markdown_fence(self, raw_response: str) -> str:
        return raw_response.strip().replace("```json", "").replace("```", "").strip()
