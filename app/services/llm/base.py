"""LLM provider abstraction.

Swapping the answer-generating model = implementing this interface and adding
a branch to the factory in app/services/llm/__init__.py. Ollama runs locally
today; the Claude provider is ready behind LLM_PROVIDER=claude.

Messages use the common chat shape: [{"role": "user"|"assistant", "content": str}].
"""

from abc import ABC, abstractmethod
from collections.abc import Iterator


class LLMProvider(ABC):
    @abstractmethod
    def chat(self, system: str, messages: list[dict[str, str]]) -> str:
        """Generate a completion for a system prompt + conversation messages."""

    def chat_stream(self, system: str, messages: list[dict[str, str]]) -> Iterator[str]:
        """Yield the completion incrementally. Default: one chunk (no streaming)."""
        yield self.chat(system, messages)

    def generate(self, system: str, user: str) -> str:
        """Convenience for single-turn use."""
        return self.chat(system, [{"role": "user", "content": user}])
