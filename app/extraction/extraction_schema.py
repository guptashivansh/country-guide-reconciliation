def build_response_schema(allowed_sections):
    """Build a JSON schema that constrains the LLM to only use allowed section names."""
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "employment_rules",
            "strict": True,
            "schema": {
                "type": "object",
                "properties": {
                    "rules": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "section": {
                                    "type": "string",
                                    "enum": list(allowed_sections),
                                },
                                "value": {"type": "string"},
                                "confidence": {"type": "number"},
                                "severity": {
                                    "type": "string",
                                    "enum": ["critical", "major", "minor"],
                                },
                                "source_paragraph": {"type": "string"},
                            },
                            "required": ["section", "value", "confidence", "severity", "source_paragraph"],
                            "additionalProperties": False,
                        },
                    },
                },
                "required": ["rules"],
                "additionalProperties": False,
            },
        },
    }


EXTRACTION_PROMPT = """You are a legal compliance analyst for an Employer of Record (EOR) company.

Analyze the following content from {source_url} and extract employment rules for {country}.

This is chunk {chunk_index} of {chunk_count} from the source.

Extract values ONLY for these sections if found: {sections_str}

For each rule found, provide:
- section: must be one of the allowed section names listed above
- value: the extracted rule as a clear, concise string (e.g. "12 days per year", "30 days notice required")
- confidence: float between 0.0 and 1.0
- severity: "critical" (visa/permit/termination rules), "major" (wage/tax/leave rules), or "minor" (procedural/administrative)
- source_paragraph: the exact sentence from the content that supports this value

Only include sections where you find a specific, concrete value.
If no rules are found, return an empty rules array.

Content:
{content}
"""
