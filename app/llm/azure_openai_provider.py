import time

from openai import OpenAI
from openai import RateLimitError

from app.extraction import extraction_logger as log


class AzureOpenAIProvider:
    """LLMProvider backed by Azure AI Model Inference (OpenAI-compatible)."""

    RPM_PER_KEY = 10

    def __init__(self, api_keys, model="gpt-4o-mini", temperature=0.0, base_url=None):
        if isinstance(api_keys, str):
            api_keys = [api_keys] if api_keys else []
        self._keys = [k for k in api_keys if k]
        self._clients = [OpenAI(base_url=base_url, api_key=k, max_retries=0) for k in self._keys]
        self._current = 0
        self.model = model
        self.temperature = temperature
        self._min_interval = 60.0 / (self.RPM_PER_KEY * max(len(self._clients), 1))
        self._last_call = 0.0

    @property
    def configured(self):
        return bool(self._clients)

    def _rotate_key(self):
        self._current = (self._current + 1) % len(self._clients)

    def _throttle(self):
        elapsed = time.time() - self._last_call
        if elapsed < self._min_interval:
            time.sleep(self._min_interval - elapsed)
        self._last_call = time.time()

    def complete(self, prompt):
        if not self._clients:
            raise RuntimeError("No Azure OpenAI API key configured")

        max_attempts = 8
        for attempt in range(max_attempts):
            self._throttle()
            try:
                response = self._clients[self._current].chat.completions.create(
                    model=self.model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=self.temperature,
                )
                self._rotate_key()
                return response.choices[0].message.content.strip()
            except RateLimitError as e:
                retry_after = getattr(e, 'retry_after', None)
                if not retry_after and hasattr(e, 'response') and e.response:
                    retry_after = e.response.headers.get('retry-after')
                backoff = int(retry_after) if retry_after else min(15 * (2 ** attempt), 120)
                log.log_rate_limited("Azure reconciliation", backoff, attempt + 1, max_attempts)
                self._rotate_key()
                time.sleep(backoff)

        raise RateLimitError("All Azure OpenAI API keys have exhausted their quota")
