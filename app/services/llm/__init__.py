"""LLM provider factory — selected via LLM_PROVIDER."""

from functools import lru_cache

from app.core.config import get_settings
from app.services.llm.base import LLMProvider  # noqa: F401


@lru_cache
def get_llm_provider() -> LLMProvider:
    provider = get_settings().llm_provider
    if provider == "ollama":
        from app.services.llm.ollama_provider import OllamaProvider

        return OllamaProvider()
    if provider == "claude":
        from app.services.llm.claude_provider import ClaudeProvider

        return ClaudeProvider()
    raise ValueError(f"Unknown LLM_PROVIDER: {provider}")
