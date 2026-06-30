import logging

import requests


logger = logging.getLogger(__name__)


class OllamaProvider:
    """LLMProvider backed by a local Ollama instance. No rate limits."""

    def __init__(self, model="qwen2.5:7b", base_url="http://host.docker.internal:11434", temperature=0.0):
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.temperature = temperature

    @property
    def configured(self):
        try:
            resp = requests.get(f"{self.base_url}/api/tags", timeout=2)
            return resp.ok
        except Exception:
            return False

    def complete(self, prompt):
        response = requests.post(
            f"{self.base_url}/api/chat",
            json={
                "model": self.model,
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
                "options": {"temperature": self.temperature},
            },
            timeout=300,
        )
        response.raise_for_status()
        return response.json()["message"]["content"].strip()
