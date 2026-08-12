"""Parser package: importing this registers all built-in parsers."""

from app.services.ingestion.parsers import csv_file, docx_file, pdf, text  # noqa: F401
from app.services.ingestion.parsers.base import (  # noqa: F401
    BaseParser,
    ParsedSegment,
    get_parser,
    supported_extensions,
)
