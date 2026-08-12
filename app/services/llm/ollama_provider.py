"""Local LLM via Ollama's /api/chat endpoint."""

import httpx

from app.core.config import get_settings
from app.services.llm.base import LLMProvider


class OllamaProvider(LLMProvider):
    def __init__(self) -> None:
        settings = get_settings()
        self._base_url = settings.ollama_base_url.rstrip("/")
        self._model = settings.ollama_model
        # Local models on CPU can take a while for long contexts
        self._client = httpx.Client(timeout=300.0)

    def generate(self, system: str, user: str) -> str:
        response = self._client.post(
            f"{self._base_url}/api/chat",
            json={
                "model": self._model,
                "stream": False,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            },
        )
        if response.status_code == 404:
            raise RuntimeError(
                f"Ollama does not have model '{self._model}' "
                f"(response: {response.text.strip()}). "
                f"Run `ollama pull {self._model}` or set OLLAMA_MODEL in .env "
                "to a model listed by `ollama list`."
            )
        response.raise_for_status()
        return response.json()["message"]["content"]
