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
{language_instruction}
This is chunk {chunk_index} of {chunk_count} from the source.

Extract values ONLY for these sections if found: {sections_str}

For each rule found, provide:
- section: must be one of the allowed section names listed above
- value: the extracted rule as a clear, concise string IN ENGLISH with specific numbers, durations, or thresholds (e.g. "12 days per year", "30 days notice required", "During probation: 2 weeks; After probation: 1 month")
- confidence: float between 0.0 and 1.0
- severity: "critical" (visa/permit/termination rules), "major" (wage/tax/leave rules), or "minor" (procedural/administrative)
- source_paragraph: the exact sentence from the content that supports this value (keep in the original language)

Only include sections where you find a specific, concrete value.
Do NOT extract vague references to laws or acts without the actual rule details (e.g. "as per the Employment Act" or "Notice period required for dismissal as per the Protection Against Dismissal Act" are NOT acceptable — extract the specific durations, amounts, or conditions instead).
If the content only names a law without stating the concrete rule, omit that section entirely.
If the content is mostly navigation, cookie banners, browser warnings, or search forms with no substantive employment law content, return an empty rules array.
If no rules are found, return an empty rules array.

Content:
{content}
"""


def build_language_instruction(content_language):
    if not content_language or content_language == "en":
        return ""
    LANGUAGE_NAMES = {
        "es": "Spanish", "fr": "French", "de": "German", "pt": "Portuguese",
        "it": "Italian", "nl": "Dutch", "pl": "Polish", "cs": "Czech",
        "bg": "Bulgarian", "ro": "Romanian", "hr": "Croatian", "hu": "Hungarian",
        "sk": "Slovak", "sl": "Slovenian", "et": "Estonian", "lt": "Lithuanian",
        "lv": "Latvian", "el": "Greek", "tr": "Turkish", "ar": "Arabic",
        "zh": "Chinese", "ja": "Japanese", "ko": "Korean", "th": "Thai",
        "vi": "Vietnamese", "id": "Indonesian", "ms": "Malay", "hi": "Hindi",
        "bn": "Bengali", "ne": "Nepali", "si": "Sinhala", "ka": "Georgian",
        "uk": "Ukrainian", "sr": "Serbian", "mk": "Macedonian", "sq": "Albanian",
        "he": "Hebrew", "fa": "Persian", "sw": "Swahili", "mg": "Malagasy",
    }
    lang_name = LANGUAGE_NAMES.get(content_language, content_language)
    return (
        f"\nThe source content is in {lang_name}. Read and understand it in {lang_name}, "
        f"but write ALL extracted values in English. Keep source_paragraph in the original {lang_name}.\n"
    )


MIN_USEFUL_CONTENT_LENGTH = 500

BOILERPLATE_SIGNALS = [
    "skip to", "cookie", "accept all", "privacy policy", "terms of use",
    "sign in", "log in", "search", "subscribe", "menu", "navigation",
    "enable javascript", "browser which will not be supported",
    "upgrade your browser", "enable cookies", "javascript is required",
]


def is_content_extractable(text):
    if not text or len(text.strip()) < MIN_USEFUL_CONTENT_LENGTH:
        return False, "content_too_short"
    lines = text.strip().split("\n")
    non_empty = [l.strip() for l in lines if l.strip()]
    if not non_empty:
        return False, "content_empty"
    lower_text = text.lower()
    boilerplate_hits = sum(1 for sig in BOILERPLATE_SIGNALS if sig in lower_text)
    substantive_lines = [l for l in non_empty if len(l) > 40 and not any(sig in l.lower() for sig in BOILERPLATE_SIGNALS)]
    if len(substantive_lines) < 3 and boilerplate_hits >= 3:
        return False, "content_is_boilerplate"
    return True, "ok"
