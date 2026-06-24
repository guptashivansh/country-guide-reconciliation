from pydantic import BaseModel, Field, field_validator


class EmploymentRule(BaseModel):
    section: str
    value: str
    confidence: float = Field(ge=0, le=1)
    severity: str
    source_paragraph: str

    @field_validator("section")
    @classmethod
    def validate_section(cls, value, info):
        section = value.strip()
        allowed_sections = set(info.context.get("allowed_sections", [])) if info.context else set()
        if not section:
            raise ValueError("section is required")
        if allowed_sections and section not in allowed_sections:
            raise ValueError(f"unsupported section: {section}")
        return section

    @field_validator("value", "source_paragraph")
    @classmethod
    def validate_required_text(cls, value):
        if not isinstance(value, str) or not value.strip():
            raise ValueError("field must be a non-empty string")
        return value.strip()

    @field_validator("severity")
    @classmethod
    def normalize_severity(cls, value):
        _ALIASES = {
            "high": "critical", "severe": "critical", "urgent": "critical",
            "medium": "major", "moderate": "major", "significant": "major",
            "important": "major",
            "low": "minor", "minimal": "minor", "negligible": "minor",
            "informational": "minor", "info": "minor",
        }
        severity = value.strip().lower()
        severity = _ALIASES.get(severity, severity)
        if severity not in {"critical", "major", "minor"}:
            raise ValueError(f"unsupported severity: {value}")
        return severity
