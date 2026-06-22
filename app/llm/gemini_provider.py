import logging

from google import genai
from google.genai import errors as genai_errors


logger = logging.getLogger(__name__)


class GeminiProvider:
    """LLMProvider backed by Google Gemini. Rotates across multiple keys on rate limit."""

    def __init__(self, api_keys, model="gemini-2.0-flash", temperature=0.0):
        if isinstance(api_keys, str):
            api_keys = [api_keys] if api_keys else []
        self._keys = [k for k in api_keys if k]
        self._clients = [genai.Client(api_key=k) for k in self._keys]
        self._current = 0
        self.model = model
        self.temperature = temperature

    @property
    def configured(self):
        return bool(self._clients)

    def _rotate_key(self):
        self._current = (self._current + 1) % len(self._clients)
        logger.info("Rotated to next Gemini API key", extra={"key_index": self._current})

    def complete(self, prompt):
        if not self._clients:
            raise RuntimeError("No Gemini API key configured")

        for _ in range(len(self._clients)):
            try:
                response = self._clients[self._current].models.generate_content(
                    model=self.model,
                    contents=prompt,
                    config={
                        "temperature": self.temperature,
                        "max_output_tokens": 1024,
                    },
                )
                return response.text.strip()
            except genai_errors.ClientError as e:
                if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                    logger.warning("Gemini quota exceeded on key %d, rotating to next key", self._current)
                    self._rotate_key()
                else:
                    raise

        raise RuntimeError("All Gemini API keys have exhausted their quota")
