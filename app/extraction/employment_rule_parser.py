import json
import logging

from pydantic import ValidationError

from app.models.employment_rule import EmploymentRule


logger = logging.getLogger(__name__)


class EmploymentRuleParser:
    def parse(self, raw_response, allowed_sections, source_url=None):
        try:
            payload = json.loads(self._strip_markdown_fence(raw_response))
        except json.JSONDecodeError as e:
            logger.warning(
                "Malformed AI extraction JSON",
                extra={"stage": "extraction_parse", "source_url": source_url, "failure": str(e)},
            )
            return []

        if not isinstance(payload, list):
            logger.warning(
                "AI extraction response must be a JSON array",
                extra={"stage": "extraction_parse", "source_url": source_url},
            )
            return []

        validated_rules = []
        for item in payload:
            if not isinstance(item, dict):
                logger.warning(
                    "AI extraction response item must be an object",
                    extra={"stage": "extraction_validate", "source_url": source_url},
                )
                continue

            try:
                rule = EmploymentRule.model_validate(
                    item,
                    context={"allowed_sections": allowed_sections},
                )
                validated_rules.append(rule.model_dump())
            except ValidationError as e:
                logger.warning(
                    "AI extraction validation failed",
                    extra={"stage": "extraction_validate", "source_url": source_url, "failure": str(e)},
                )

        return validated_rules

    def _strip_markdown_fence(self, raw_response):
        return raw_response.strip().replace("```json", "").replace("```", "").strip()
