"""Question answering: embed question → retrieve chunks → generate answer."""

from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.services.embeddings import get_embedding_provider
from app.services.llm import get_llm_provider
from app.services.retrieval import RetrievedChunk, search_chunks

SYSTEM_PROMPT = """\
You are a helpful, patient tutor for school students. Answer the student's \
question using ONLY the context passages provided. Rules:
- If the answer is not in the context, say you couldn't find it in their \
books — do not answer from general knowledge.
- Answer in the same language the student asked in (English or Hindi).
- Cite the passages you used with their bracket numbers, e.g. [1], [2].
- Explain clearly at a level appropriate for a school student.\
"""

NO_CONTEXT_ANSWER = (
    "I couldn't find anything about this in your books. "
    "Try rephrasing the question or asking your teacher."
)


@dataclass
class Source:
    index: int
    document_title: str
    subject: str | None
    page_number: int | None


@dataclass
class AnswerResult:
    answer: str
    sources: list[Source] = field(default_factory=list)


def _build_user_prompt(question: str, chunks: list[RetrievedChunk]) -> str:
    context_parts = []
    for i, chunk in enumerate(chunks, start=1):
        location = f"{chunk.document_title}"
        if chunk.page_number:
            location += f", page {chunk.page_number}"
        context_parts.append(f"[{i}] ({location})\n{chunk.content}")
    context = "\n\n".join(context_parts)
    return f"Context passages:\n\n{context}\n\nStudent's question: {question}"


def answer_question(
    db: Session,
    question: str,
    grade: str | None = None,
    subject: str | None = None,
    document_id: int | None = None,
) -> AnswerResult:
    query_embedding = get_embedding_provider().embed_query(question)
    chunks = search_chunks(
        db, query_embedding, grade=grade, subject=subject, document_id=document_id
    )
    if not chunks:
        return AnswerResult(answer=NO_CONTEXT_ANSWER)

    answer = get_llm_provider().generate(
        system=SYSTEM_PROMPT,
        user=_build_user_prompt(question, chunks),
    )
    sources = [
        Source(
            index=i,
            document_title=chunk.document_title,
            subject=chunk.subject,
            page_number=chunk.page_number,
        )
        for i, chunk in enumerate(chunks, start=1)
    ]
    return AnswerResult(answer=answer, sources=sources)
