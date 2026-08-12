"""Application configuration.

Every provider choice (embeddings, LLM, models, chunk sizes) is driven by
environment variables so new languages/models can be plugged in without code
changes. See backend/.env.example. Run the app from the backend/ directory so
the .env file next to it is picked up.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Database
    database_url: str = "postgresql+psycopg://educator:educator@localhost:5432/educator"

    # Embeddings — bge-m3 is multilingual (English + Hindi, cross-lingual)
    embedding_provider: str = "sentence_transformers"  # or "ollama"
    embedding_model: str = "BAAI/bge-m3"
    embedding_dim: int = 1024

    # LLM
    llm_provider: str = "ollama"  # or "claude"
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:7b"
    anthropic_api_key: str = ""
    claude_model: str = "claude-opus-5"

    # Ingestion
    chunk_size_chars: int = 3200  # ~800 tokens
    chunk_overlap_chars: int = 400
    upload_dir: str = "./data/uploads"

    # Retrieval
    top_k: int = 6

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
