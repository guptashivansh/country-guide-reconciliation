"""LLM provider registry.

``create_reconciliation_provider`` picks the highest-priority backend that has
at least one API key configured.  Priority order: Anthropic > Gemini > Groq.
"""

from app.llm.claude_provider import ClaudeProvider
from app.llm.gemini_provider import GeminiProvider
from app.llm.groq_provider import GroqProvider

# Priority-ordered list of (name, provider_class, default_model)
_PROVIDER_ORDER = [
    ("anthropic", ClaudeProvider, "claude-sonnet-4-6"),
    ("gemini", GeminiProvider, "gemini-2.0-flash"),
    ("groq", GroqProvider, "llama-3.3-70b-versatile"),
]


def create_reconciliation_provider(api_keys_by_name, models_by_name=None):
    """Return an LLMProvider instance for the highest-priority backend with keys.

    Parameters
    ----------
    api_keys_by_name : dict[str, list[str] | None]
        Mapping of provider name to a list of API keys (or ``None`` / empty list
        when unavailable).
    models_by_name : dict[str, str] | None
        Optional mapping of provider name to model identifier override.

    Raises
    ------
    RuntimeError
        If no provider has any API keys configured.
    """
    models_by_name = models_by_name or {}

    for name, cls, default_model in _PROVIDER_ORDER:
        keys = api_keys_by_name.get(name)
        if keys:  # truthy: non-None, non-empty list
            model = models_by_name.get(name, default_model)
            return cls(keys, model=model)

    raise RuntimeError("No LLM API keys configured")
