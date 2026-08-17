"""Quiz generation (Phase 2): "test me on Chapter 4".

Samples random chunks from the selected books and asks the LLM to write
multiple-choice questions grounded in them, returned as JSON.
"""

import json
import logging
import re

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import Chunk, Document, DocumentStatus
from app.services.llm import get_llm_provider

logger = logging.getLogger(__name__)

QUIZ_SYSTEM = """\
You create quizzes for school students from textbook passages. Return ONLY a \
JSON array, no other text. Each element: {"question": str, "options": \
[str, str, str, str], "answer_index": int (0-3), "explanation": str}. \
Questions must be answerable from the passages alone. Write in the same \
language as the passages.\
"""


def _sample_chunks(
    db: Session,
    grade: str | None,
    subject: str | None,
    document_id: int | None,
    limit: int,
) -> list[Chunk]:
    stmt = (
        select(Chunk)
        .join(Document, Chunk.document_id == Document.id)
        .where(Document.status == DocumentStatus.ready)
    )
    if grade:
        stmt = stmt.where(Document.grade == grade)
    if subject:
        stmt = stmt.where(Document.subject == subject)
    if document_id:
        stmt = stmt.where(Document.id == document_id)
    stmt = stmt.order_by(func.random()).limit(limit)
    return list(db.scalars(stmt).all())


def _extract_json_array(text: str) -> list | None:
    """Local models wrap JSON in prose/code fences — find the array anyway."""
    match = re.search(r"\[.*\]", text, re.DOTALL)
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
        return data if isinstance(data, list) else None
    except json.JSONDecodeError:
        return None


def generate_quiz(
    db: Session,
    grade: str | None = None,
    subject: str | None = None,
    document_id: int | None = None,
    num_questions: int | None = None,
) -> dict:
    num_questions = num_questions or get_settings().quiz_questions
    chunks = _sample_chunks(db, grade, subject, document_id, limit=num_questions * 2)
    if not chunks:
        return {"questions": None, "error": "No ready documents match the given filters"}

    passages = "\n\n---\n\n".join(c.content[:1500] for c in chunks)
    prompt = (
        f"Textbook passages:\n\n{passages}\n\n"
        f"Create exactly {num_questions} multiple-choice questions."
    )
    raw = get_llm_provider().chat(QUIZ_SYSTEM, [{"role": "user", "content": prompt}])

    questions = _extract_json_array(raw)
    if questions is None:
        logger.warning("Quiz output was not valid JSON; returning raw text")
        return {"questions": None, "raw": raw, "error": "Model did not return valid JSON"}
    return {"questions": questions[:num_questions]}
