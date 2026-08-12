"""Plain text and Markdown parser."""

from pathlib import Path

from app.services.ingestion.parsers.base import BaseParser, ParsedSegment, register_parser


@register_parser("txt", "md", "markdown")
class TextParser(BaseParser):
    def parse(self, path: Path) -> list[ParsedSegment]:
        text = path.read_text(encoding="utf-8", errors="replace").strip()
        return [ParsedSegment(text=text)] if text else []
