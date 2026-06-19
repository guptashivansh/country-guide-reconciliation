from typing import Protocol


class LLMProvider(Protocol):
    """A chat-completion backend. Implementations own their own vendor SDK, auth, and retry/rotation logic."""

    def complete(self, prompt: str) -> str:
        ...
