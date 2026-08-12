"""Vector similarity search over ingested chunks.

Grade filtering happens here, in the query itself — access control is
enforced at retrieval, not in the UI.
"""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import Chunk, Document, DocumentStatus


@dataclass
class RetrievedChunk:
    content: str
    document_title: str
    subject: str | None
    grade: str | None
    page_number: int | None
    distance: float


def search_chunks(
    db: Session,
    query_embedding: list[float],
    grade: str | None = None,
    subject: str | None = None,
    document_id: int | None = None,
    top_k: int | None = None,
) -> list[RetrievedChunk]:
    top_k = top_k or get_settings().top_k
    distance = Chunk.embedding.cosine_distance(query_embedding).label("distance")

    stmt = (
        select(Chunk, Document, distance)
        .join(Document, Chunk.document_id == Document.id)
        .where(Document.status == DocumentStatus.ready)
    )
    if grade:
        stmt = stmt.where(Document.grade == grade)
    if subject:
        stmt = stmt.where(Document.subject == subject)
    if document_id:
        stmt = stmt.where(Document.id == document_id)
    stmt = stmt.order_by(distance).limit(top_k)

    return [
        RetrievedChunk(
            content=chunk.content,
            document_title=document.title,
            subject=document.subject,
            grade=document.grade,
            page_number=chunk.page_number,
            distance=dist,
        )
        for chunk, document, dist in db.execute(stmt).all()
    ]
