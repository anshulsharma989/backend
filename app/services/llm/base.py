"""LLM provider abstraction.

Swapping the answer-generating model = implementing this interface and adding
a branch to the factory in app/services/llm/__init__.py. Ollama runs locally
today; the Claude provider is ready behind LLM_PROVIDER=claude.
"""

from abc import ABC, abstractmethod


class LLMProvider(ABC):
    @abstractmethod
    def generate(self, system: str, user: str) -> str:
        """Generate a completion for a system prompt + user message."""
