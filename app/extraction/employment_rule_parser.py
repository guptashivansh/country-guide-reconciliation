import json
import logging
import re

from pydantic import ValidationError

from app.models.employment_rule import EmploymentRule


logger = logging.getLogger(__name__)


class EmploymentRuleParser:
    def parse(self, raw_response, allowed_sections, source_url=None):
        try:
            cleaned = self._strip_markdown_fence(raw_response).replace("\x00", "")
            payload = json.loads(cleaned)
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

        allowed_lookup = {self._to_snake_case(s): s for s in allowed_sections}

        validated_rules = []
        for item in payload:
            if not isinstance(item, dict):
                logger.warning(
                    "AI extraction response item must be an object",
                    extra={"stage": "extraction_validate", "source_url": source_url},
                )
                continue

            if "section" in item:
                normalized = self._to_snake_case(item["section"])
                if normalized in allowed_lookup:
                    item["section"] = allowed_lookup[normalized]

            try:
                rule = EmploymentRule.model_validate(
                    item,
                    context={"allowed_sections": allowed_sections},
                )
                validated_rules.append(rule.model_dump())
            except ValidationError as e:
                logger.warning(
                    "AI extraction validation failed for section %s",
                    item.get("section", "?"),
                    extra={"stage": "extraction_validate", "source_url": source_url, "failure": str(e)},
                )

        return validated_rules

    @staticmethod
    def _to_snake_case(s):
        s = re.sub(r"[^a-zA-Z0-9]+", "_", s.strip()).strip("_").lower()
        s = re.sub(r"([a-z])([A-Z])", r"\1_\2", s).lower()
        return s

    def _strip_markdown_fence(self, raw_response):
        return raw_response.strip().replace("```json", "").replace("```", "").strip()
