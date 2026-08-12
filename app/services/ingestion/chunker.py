"""Text chunker.

Splits parsed segments into overlapping chunks, preferring paragraph
boundaries, then line, sentence, and finally word boundaries. Page numbers
are carried through for citations.
"""

from dataclasses import dataclass

from app.core.config import get_settings
from app.services.ingestion.parsers.base import ParsedSegment

SEPARATORS = ["\n\n", "\n", ". ", " "]


@dataclass
class TextChunk:
    text: str
    page_number: int | None = None


def _split_text(text: str, chunk_size: int, separators: list[str]) -> list[str]:
    """Recursively split text so every piece fits within chunk_size."""
    if len(text) <= chunk_size:
        return [text]
    if not separators:
        return [text[i : i + chunk_size] for i in range(0, len(text), chunk_size)]

    sep, rest = separators[0], separators[1:]
    parts = [p for p in text.split(sep) if p.strip()]
    if len(parts) <= 1:
        return _split_text(text, chunk_size, rest)

    pieces: list[str] = []
    current = ""
    for part in parts:
        candidate = f"{current}{sep}{part}" if current else part
        if len(candidate) <= chunk_size:
            current = candidate
        else:
            if current:
                pieces.append(current)
            if len(part) > chunk_size:
                pieces.extend(_split_text(part, chunk_size, rest))
                current = ""
            else:
                current = part
    if current:
        pieces.append(current)
    return pieces


def chunk_segments(segments: list[ParsedSegment]) -> list[TextChunk]:
    settings = get_settings()
    chunk_size = settings.chunk_size_chars
    overlap = settings.chunk_overlap_chars

    chunks: list[TextChunk] = []
    for segment in segments:
        pieces = _split_text(segment.text.strip(), chunk_size, SEPARATORS)
        previous_tail = ""
        for piece in pieces:
            text = f"{previous_tail}\n{piece}".strip() if previous_tail else piece
            chunks.append(TextChunk(text=text, page_number=segment.page_number))
            previous_tail = piece[-overlap:] if overlap and len(piece) > overlap else ""
    return [c for c in chunks if c.text.strip()]
