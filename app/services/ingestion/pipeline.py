"""Ingestion pipeline: parse → chunk → embed → store.

Runs synchronously; the API wraps it in a FastAPI BackgroundTask for now and
it will move behind a Celery worker in M2 without changes to this module.
"""

import logging
from pathlib import Path

from sqlalchemy.orm import Session

from app.models import Chunk, Document, DocumentStatus
from app.services.embeddings import get_embedding_provider
from app.services.ingestion.chunker import chunk_segments
from app.services.ingestion.parsers import get_parser

logger = logging.getLogger(__name__)

EMBED_BATCH_SIZE = 32


def ingest_document(db: Session, document_id: int) -> None:
    """Process a queued document end-to-end, updating its status as it goes."""
    document = db.get(Document, document_id)
    if document is None:
        raise ValueError(f"Document {document_id} not found")

    document.status = DocumentStatus.processing
    document.error = None
    db.commit()

    try:
        path = Path(document.file_path)
        segments = get_parser(path).parse(path)
        chunks = chunk_segments(segments)
        if not chunks:
            raise ValueError("No text could be extracted from the file")

        logger.info(
            "Document %s (%s): %d segments -> %d chunks",
            document.id, document.title, len(segments), len(chunks),
        )

        # Re-ingesting replaces old chunks
        db.query(Chunk).filter(Chunk.document_id == document.id).delete()

        embedder = get_embedding_provider()
        for start in range(0, len(chunks), EMBED_BATCH_SIZE):
            batch = chunks[start : start + EMBED_BATCH_SIZE]
            vectors = embedder.embed_documents([c.text for c in batch])
            for offset, (chunk, vector) in enumerate(zip(batch, vectors)):
                db.add(
                    Chunk(
                        document_id=document.id,
                        chunk_index=start + offset,
                        page_number=chunk.page_number,
                        content=chunk.text,
                        embedding=vector,
                    )
                )
            db.commit()

        document.status = DocumentStatus.ready
        db.commit()
    except Exception as exc:
        logger.exception("Ingestion failed for document %s", document_id)
        db.rollback()
        document.status = DocumentStatus.failed
        document.error = str(exc)
        db.commit()
        raise
