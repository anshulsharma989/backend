"""Embeddings via Ollama's /api/embed endpoint.

Set EMBEDDING_PROVIDER=ollama and EMBEDDING_MODEL to an Ollama embedding
model (e.g. "bge-m3" after `ollama pull bge-m3`).
"""

import httpx

from app.core.config import get_settings
from app.services.embeddings.base import EmbeddingProvider


class OllamaEmbeddingProvider(EmbeddingProvider):
    def __init__(self) -> None:
        settings = get_settings()
        self._base_url = settings.ollama_base_url.rstrip("/")
        self._model = settings.embedding_model
        self._client = httpx.Client(timeout=120.0)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        response = self._client.post(
            f"{self._base_url}/api/embed",
            json={"model": self._model, "input": texts},
        )
        response.raise_for_status()
        return response.json()["embeddings"]

    def embed_query(self, text: str) -> list[float]:
        return self.embed_documents([text])[0]
