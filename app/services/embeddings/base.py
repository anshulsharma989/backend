"""Embedding provider abstraction.

To integrate a new embedding model or backend, implement EmbeddingProvider
and add a branch to the factory in app/services/embeddings/__init__.py.
Remember: query and document embeddings must come from the same model, and
EMBEDDING_DIM must match the model's output size (re-ingest after changing).
"""

from abc import ABC, abstractmethod


class EmbeddingProvider(ABC):
    @abstractmethod
    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of document chunks."""

    @abstractmethod
    def embed_query(self, text: str) -> list[float]:
        """Embed a search query."""
