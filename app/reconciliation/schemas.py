from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class MaterialityLevel(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MODERATE = "MODERATE"
    LOW = "LOW"
    INFORMATIONAL = "INFORMATIONAL"


class ChangeType(str, Enum):
    NUMERIC_THRESHOLD_CHANGE = "NUMERIC_THRESHOLD_CHANGE"
    ELIGIBILITY_CHANGE = "ELIGIBILITY_CHANGE"
    REQUIREMENT_ADDED = "REQUIREMENT_ADDED"
    REQUIREMENT_REMOVED = "REQUIREMENT_REMOVED"
    TIMELINE_CHANGE = "TIMELINE_CHANGE"
    NON_MATERIAL_FORMATTING = "NON_MATERIAL_FORMATTING"


class NumericThreshold(BaseModel):
    label: str = ""
    value: float
    unit: str = ""
    comparator: Optional[str] = None

    @field_validator("label", "unit", mode="before")
    @classmethod
    def normalize_optional_text(cls, value):
        if value is None:
            return ""
        return str(value).strip()

    @field_validator("comparator", mode="before")
    @classmethod
    def normalize_comparator(cls, value):
        if value is None:
            return None
        stripped = str(value).strip()
        return stripped or None


class TimelineRequirement(BaseModel):
    label: str = ""
    value: str
    unit: str = ""

    @field_validator("label", "value", "unit", mode="before")
    @classmethod
    def normalize_text(cls, value):
        return "" if value is None else str(value).strip()


class CanonicalComplianceRule(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    rule_id: Optional[str] = None
    country: Optional[str] = None
    jurisdiction: Optional[str] = None
    section: str = ""
    title: Optional[str] = None
    text: str = ""
    requirements: list[str] = Field(default_factory=list)
    eligibility: list[str] = Field(default_factory=list)
    numeric_thresholds: list[NumericThreshold] = Field(default_factory=list)
    timelines: list[TimelineRequirement] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def accept_common_rule_shapes(cls, data):
        if not isinstance(data, dict):
            return data

        normalized = dict(data)
        if "text" not in normalized and "value" in normalized:
            normalized["text"] = normalized["value"]
        if "text" not in normalized and "canonical_text" in normalized:
            normalized["text"] = normalized["canonical_text"]
        if "section" not in normalized and "name" in normalized:
            normalized["section"] = normalized["name"]
        return normalized

    @field_validator("rule_id", "country", "jurisdiction", "section", "title", "text", mode="before")
    @classmethod
    def normalize_text_fields(cls, value):
        return "" if value is None else str(value).strip()

    @field_validator("requirements", "eligibility", mode="before")
    @classmethod
    def normalize_string_list(cls, value):
        if value is None:
            return []
        if isinstance(value, str):
            return [value.strip()] if value.strip() else []
        return [str(item).strip() for item in value if str(item).strip()]


class SemanticReconciliationResult(BaseModel):
    semantic_change_detected: bool
    materiality_level: MaterialityLevel
    change_type: ChangeType
    human_readable_summary: str
    reasoning: list[str] = Field(default_factory=list)
