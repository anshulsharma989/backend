"""Parser abstraction.

Each supported file format implements BaseParser and registers itself with
@register_parser. Adding a new format = one new file + one decorator; nothing
else in the pipeline changes.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ParsedSegment:
    """A unit of extracted text with its source location (for citations)."""

    text: str
    page_number: int | None = None


class BaseParser(ABC):
    @abstractmethod
    def parse(self, path: Path) -> list[ParsedSegment]:
        """Extract text segments from the file."""


_REGISTRY: dict[str, type[BaseParser]] = {}


def register_parser(*extensions: str):
    def decorator(cls: type[BaseParser]) -> type[BaseParser]:
        for ext in extensions:
            _REGISTRY[ext.lower().lstrip(".")] = cls
        return cls

    return decorator


def get_parser(path: Path) -> BaseParser:
    ext = path.suffix.lower().lstrip(".")
    if ext not in _REGISTRY:
        supported = ", ".join(sorted(_REGISTRY))
        raise ValueError(f"Unsupported file type '.{ext}'. Supported: {supported}")
    return _REGISTRY[ext]()


def supported_extensions() -> list[str]:
    return sorted(_REGISTRY)
