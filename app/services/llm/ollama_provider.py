"""Local LLM via Ollama's /api/chat endpoint (blocking and streaming)."""

import json
from collections.abc import Iterator

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

    def _payload(self, system: str, messages: list[dict[str, str]], stream: bool) -> dict:
        return {
            "model": self._model,
            "stream": stream,
            "messages": [{"role": "system", "content": system}, *messages],
        }

    def _raise_if_missing_model(self, status_code: int, body: str) -> None:
        if status_code == 404:
            raise RuntimeError(
                f"Ollama does not have model '{self._model}' "
                f"(response: {body.strip()}). "
                f"Run `ollama pull {self._model}` or set OLLAMA_MODEL in .env "
                "to a model listed by `ollama list`."
            )

    def chat(self, system: str, messages: list[dict[str, str]]) -> str:
        response = self._client.post(
            f"{self._base_url}/api/chat",
            json=self._payload(system, messages, stream=False),
        )
        self._raise_if_missing_model(response.status_code, response.text)
        response.raise_for_status()
        return response.json()["message"]["content"]

    def chat_stream(self, system: str, messages: list[dict[str, str]]) -> Iterator[str]:
        with self._client.stream(
            "POST",
            f"{self._base_url}/api/chat",
            json=self._payload(system, messages, stream=True),
        ) as response:
            if response.status_code >= 400:
                body = response.read().decode(errors="replace")
                self._raise_if_missing_model(response.status_code, body)
                response.raise_for_status()
            # Ollama streams one JSON object per line
            for line in response.iter_lines():
                if not line:
                    continue
                data = json.loads(line)
                token = data.get("message", {}).get("content", "")
                if token:
                    yield token
                if data.get("done"):
                    break
