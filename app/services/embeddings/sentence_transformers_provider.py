"""Local embeddings via sentence-transformers (default: BAAI/bge-m3)."""

from app.core.config import get_settings
from app.services.embeddings.base import EmbeddingProvider


class SentenceTransformersProvider(EmbeddingProvider):
    def __init__(self) -> None:
        # Lazy import: sentence-transformers pulls in torch, which is slow to
        # load and unnecessary when the Ollama embedding provider is used.
        from sentence_transformers import SentenceTransformer

        self._model = SentenceTransformer(get_settings().embedding_model)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        vectors = self._model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
        return [v.tolist() for v in vectors]

    def embed_query(self, text: str) -> list[float]:
        return self.embed_documents([text])[0]
