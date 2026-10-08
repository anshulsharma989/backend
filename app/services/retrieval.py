"""Vector similarity search over ingested chunks.

Grade filtering happens here, in the query itself — access control is
enforced at retrieval, not in the UI.
"""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import Chunk, Document, DocumentStatus, Subject


@dataclass
class RetrievedChunk:
    content: str
    document_title: str
    subject: str | None
    page_number: int | None
    distance: float


def search_chunks(
    db: Session,
    query_embedding: list[float],
    grade_id: int | None = None,
    subject_id: int | None = None,
    document_id: int | None = None,
    top_k: int | None = None,
) -> list[RetrievedChunk]:
    top_k = top_k or get_settings().top_k
    distance = Chunk.embedding.cosine_distance(query_embedding).label("distance")

    stmt = (
        select(Chunk, Document, Subject.name, distance)
        .join(Document, Chunk.document_id == Document.id)
        .outerjoin(Subject, Document.subject_id == Subject.id)
        .where(Document.status == DocumentStatus.ready)
    )
    if grade_id is not None:
        stmt = stmt.where(Document.grade_id == grade_id)
    if subject_id is not None:
        stmt = stmt.where(Document.subject_id == subject_id)
    if document_id:
        stmt = stmt.where(Document.id == document_id)
    stmt = stmt.order_by(distance).limit(top_k)

    return [
        RetrievedChunk(
            content=chunk.content,
            document_title=document.title,
            subject=subject_name,
            page_number=chunk.page_number,
            distance=dist,
        )
        for chunk, document, subject_name, dist in db.execute(stmt).all()
    ]
