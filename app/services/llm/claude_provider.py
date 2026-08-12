"""Claude provider via the official Anthropic SDK.

Enable with LLM_PROVIDER=claude and ANTHROPIC_API_KEY set. The model is
configurable via CLAUDE_MODEL (default: claude-opus-5).
"""

from app.core.config import get_settings
from app.services.llm.base import LLMProvider


class ClaudeProvider(LLMProvider):
    def __init__(self) -> None:
        import anthropic

        settings = get_settings()
        self._client = anthropic.Anthropic(api_key=settings.anthropic_api_key or None)
        self._model = settings.claude_model

    def generate(self, system: str, user: str) -> str:
        response = self._client.messages.create(
            model=self._model,
            max_tokens=2048,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        if response.stop_reason == "refusal":
            return "I can't help with that question."
        return "".join(block.text for block in response.content if block.type == "text")
