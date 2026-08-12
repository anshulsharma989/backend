"""Embedding provider factory — selected via EMBEDDING_PROVIDER."""

from functools import lru_cache

from app.core.config import get_settings
from app.services.embeddings.base import EmbeddingProvider  # noqa: F401


@lru_cache
def get_embedding_provider() -> EmbeddingProvider:
    provider = get_settings().embedding_provider
    if provider == "sentence_transformers":
        from app.services.embeddings.sentence_transformers_provider import (
            SentenceTransformersProvider,
        )

        return SentenceTransformersProvider()
    if provider == "ollama":
        from app.services.embeddings.ollama_provider import OllamaEmbeddingProvider

        return OllamaEmbeddingProvider()
    raise ValueError(f"Unknown EMBEDDING_PROVIDER: {provider}")
