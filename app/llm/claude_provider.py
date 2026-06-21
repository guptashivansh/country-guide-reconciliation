import logging

import anthropic


logger = logging.getLogger(__name__)


class ClaudeProvider:
    """LLMProvider backed by Anthropic Claude. Rotates across multiple keys on rate limit."""

    def __init__(self, api_keys, model="claude-sonnet-4-6", temperature=0.0, max_tokens=1024):
        if isinstance(api_keys, str):
            api_keys = [api_keys] if api_keys else []
        self._clients = [anthropic.Anthropic(api_key=k) for k in api_keys if k]
        self._current = 0
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens

    @property
    def configured(self):
        return bool(self._clients)

    def _rotate_key(self):
        self._current = (self._current + 1) % len(self._clients)
        logger.info("Rotated to next Anthropic API key", extra={"key_index": self._current})

    def complete(self, prompt):
        if not self._clients:
            raise RuntimeError("No Anthropic API key configured")

        for _ in range(len(self._clients)):
            try:
                response = self._clients[self._current].messages.create(
                    model=self.model,
                    max_tokens=self.max_tokens,
                    temperature=self.temperature,
                    messages=[{"role": "user", "content": prompt}],
                )
                text = next((block.text for block in response.content if block.type == "text"), "")
                return text.strip()
            except anthropic.RateLimitError:
                logger.warning("Anthropic quota exceeded on key %d, rotating to next key", self._current)
                self._rotate_key()

        raise RuntimeError("All Anthropic API keys have exhausted their quota")
