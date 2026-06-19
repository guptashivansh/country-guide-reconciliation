import logging

from groq import Groq
from groq import RateLimitError


logger = logging.getLogger(__name__)


class GroqProvider:
    """LLMProvider backed by Groq. Rotates across multiple keys on rate limit."""

    def __init__(self, api_keys, model="llama-3.3-70b-versatile", temperature=0.0):
        if isinstance(api_keys, str):
            api_keys = [api_keys] if api_keys else []
        self._clients = [Groq(api_key=k) for k in api_keys if k]
        self._current = 0
        self.model = model
        self.temperature = temperature

    @property
    def configured(self):
        return bool(self._clients)

    def _rotate_key(self):
        self._current = (self._current + 1) % len(self._clients)
        logger.info("Rotated to next Groq API key", extra={"key_index": self._current})

    def complete(self, prompt):
        if not self._clients:
            raise RuntimeError("No Groq API key configured")

        for _ in range(len(self._clients)):
            try:
                response = self._clients[self._current].chat.completions.create(
                    model=self.model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=self.temperature,
                )
                return response.choices[0].message.content.strip()
            except RateLimitError:
                logger.warning("Groq quota exceeded on key %d, rotating to next key", self._current)
                self._rotate_key()

        raise RateLimitError("All Groq API keys have exhausted their quota")
