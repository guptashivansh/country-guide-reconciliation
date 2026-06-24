"""Tests for LLM provider registry."""
import pytest
from unittest.mock import patch, MagicMock
from app.llm import create_reconciliation_provider
from app.llm.claude_provider import ClaudeProvider
from app.llm.groq_provider import GroqProvider
from app.llm.gemini_provider import GeminiProvider


class TestProviderRegistry:
    def test_anthropic_selected_first(self):
        """Anthropic keys should be preferred when available."""
        provider = create_reconciliation_provider(
            api_keys_by_name={
                "anthropic": ["sk-ant-test"],
                "gemini": ["gem-test"],
                "groq": ["gsk-test"],
            },
            models_by_name={
                "anthropic": "claude-sonnet-4-6",
                "gemini": "gemini-2.0-flash",
                "groq": "llama-3.3-70b-versatile",
            },
        )
        assert isinstance(provider, ClaudeProvider)

    def test_gemini_fallback(self):
        """Gemini should be used when Anthropic keys are absent."""
        provider = create_reconciliation_provider(
            api_keys_by_name={
                "anthropic": [],
                "gemini": ["gem-test"],
                "groq": ["gsk-test"],
            },
            models_by_name={},
        )
        assert isinstance(provider, GeminiProvider)

    def test_groq_fallback(self):
        """Groq should be used as last resort."""
        provider = create_reconciliation_provider(
            api_keys_by_name={
                "anthropic": [],
                "gemini": [],
                "groq": ["gsk-test"],
            },
            models_by_name={},
        )
        assert isinstance(provider, GroqProvider)

    def test_no_keys_raises(self):
        """Should raise when no provider has keys."""
        with pytest.raises(RuntimeError, match="No LLM API keys configured"):
            create_reconciliation_provider(
                api_keys_by_name={"anthropic": [], "gemini": [], "groq": []},
                models_by_name={},
            )

    def test_none_keys_skipped(self):
        """None values in api_keys_by_name should be treated as unavailable."""
        provider = create_reconciliation_provider(
            api_keys_by_name={
                "anthropic": None,
                "gemini": None,
                "groq": ["gsk-test"],
            },
            models_by_name={},
        )
        assert isinstance(provider, GroqProvider)
