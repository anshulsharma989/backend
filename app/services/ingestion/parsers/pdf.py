"""PDF parser with automatic OCR fallback for scanned pages.

Digital pages: text extracted with PyMuPDF (fast, keeps page numbers).
Scanned pages (no extractable text): rendered to an image and OCR'd with
Tesseract using English + Hindi language packs, when tesseract is installed.
"""

import logging
from pathlib import Path

import pymupdf

from app.services.ingestion.parsers.base import BaseParser, ParsedSegment, register_parser

logger = logging.getLogger(__name__)

OCR_LANGUAGES = "eng+hin"
OCR_RENDER_DPI = 300


def _ocr_page(page: "pymupdf.Page") -> str:
    try:
        import io

        import pytesseract
        from PIL import Image
    except ImportError:
        logger.warning(
            "Page %d has no extractable text and pytesseract/Pillow are not "
            "installed — skipping OCR.",
            page.number + 1,
        )
        return ""
    try:
        pixmap = page.get_pixmap(dpi=OCR_RENDER_DPI)
        image = Image.open(io.BytesIO(pixmap.tobytes("png")))
        return pytesseract.image_to_string(image, lang=OCR_LANGUAGES)
    except Exception:
        logger.exception("OCR failed for page %d", page.number + 1)
        return ""


@register_parser("pdf")
class PdfParser(BaseParser):
    def parse(self, path: Path) -> list[ParsedSegment]:
        segments: list[ParsedSegment] = []
        with pymupdf.open(path) as doc:
            for page in doc:
                text = page.get_text().strip()
                if not text:
                    text = _ocr_page(page).strip()
                if text:
                    segments.append(ParsedSegment(text=text, page_number=page.number + 1))
        return segments
