"""Claude provider via the official Anthropic SDK (blocking and streaming).

Enable with LLM_PROVIDER=claude and ANTHROPIC_API_KEY set. The model is
configurable via CLAUDE_MODEL (default: claude-opus-5).
"""

from collections.abc import Iterator

from app.core.config import get_settings
from app.services.llm.base import LLMProvider

REFUSAL_ANSWER = "I can't help with that question."


class ClaudeProvider(LLMProvider):
    def __init__(self) -> None:
        import anthropic

        settings = get_settings()
        self._client = anthropic.Anthropic(api_key=settings.anthropic_api_key or None)
        self._model = settings.claude_model

    def chat(self, system: str, messages: list[dict[str, str]]) -> str:
        response = self._client.messages.create(
            model=self._model,
            max_tokens=2048,
            system=system,
            messages=messages,
        )
        if response.stop_reason == "refusal":
            return REFUSAL_ANSWER
        return "".join(block.text for block in response.content if block.type == "text")

    def chat_stream(self, system: str, messages: list[dict[str, str]]) -> Iterator[str]:
        with self._client.messages.stream(
            model=self._model,
            max_tokens=2048,
            system=system,
            messages=messages,
        ) as stream:
            yield from stream.text_stream
            final = stream.get_final_message()
            if final.stop_reason == "refusal":
                yield REFUSAL_ANSWER
