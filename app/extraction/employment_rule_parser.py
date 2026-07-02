import json
import logging

from pydantic import ValidationError

from app.models.employment_rule import EmploymentRule


logger = logging.getLogger(__name__)


class EmploymentRuleParser:
    def parse(self, raw_response, allowed_sections, source_url=None):
        try:
            cleaned = self._strip_markdown_fence(raw_response).replace("\x00", "")
            payload = json.loads(cleaned)
        except json.JSONDecodeError as e:
            logger.warning("Malformed AI extraction JSON: %s", e)
            return []

        if not isinstance(payload, list):
            logger.warning("AI extraction response must be a JSON array")
            return []

        validated_rules = []
        for item in payload:
            if not isinstance(item, dict):
                continue
            try:
                rule = EmploymentRule.model_validate(
                    item,
                    context={"allowed_sections": allowed_sections},
                )
                validated_rules.append(rule.model_dump())
            except ValidationError as e:
                logger.warning(
                    "Validation failed for section %s: %s",
                    item.get("section", "?"), e,
                )

        return validated_rules

    @staticmethod
    def _strip_markdown_fence(raw_response):
        return raw_response.strip().replace("```json", "").replace("```", "").strip()
