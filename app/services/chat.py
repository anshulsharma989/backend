"""Conversational Q&A with memory (Phase 2).

Flow per turn:
  1. Load/create the conversation and its recent history.
  2. Condense a follow-up ("why does it do that?") into a standalone search
     query using the LLM, so retrieval isn't confused by pronouns.
  3. Retrieve chunks (grade/subject filters from the conversation).
  4. Send history + context + question to the LLM (blocking or streaming).
  5. Persist both the user and assistant messages with sources.
"""

import logging
from collections.abc import Iterator
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import Conversation, Message, MessageRole
from app.services.embeddings import get_embedding_provider
from app.services.llm import get_llm_provider
from app.services.qa import NO_CONTEXT_ANSWER, SYSTEM_PROMPT, Source, _build_user_prompt
from app.services.retrieval import search_chunks

logger = logging.getLogger(__name__)

CONDENSE_SYSTEM = """\
Rewrite the student's latest question as a single standalone question that \
can be understood without the conversation, in the same language. Resolve \
pronouns and references using the conversation. Output ONLY the rewritten \
question, nothing else.\
"""


@dataclass
class ChatTurn:
    """Everything prepared for one turn, before the LLM writes the answer."""

    conversation: Conversation
    question: str
    llm_messages: list[dict[str, str]]
    sources: list[Source] = field(default_factory=list)
    has_context: bool = True


@dataclass
class ChatResult:
    conversation_id: int
    message_id: int
    answer: str
    sources: list[Source]


def _get_or_create_conversation(
    db: Session,
    conversation_id: int | None,
    question: str,
    grade: str | None,
    subject: str | None,
) -> Conversation:
    if conversation_id is not None:
        conversation = db.get(Conversation, conversation_id)
        if conversation is None:
            raise ValueError(f"Conversation {conversation_id} not found")
        return conversation
    conversation = Conversation(title=question[:120], grade=grade, subject=subject)
    db.add(conversation)
    db.commit()
    return conversation


def _condense_question(question: str, history: list[Message]) -> str:
    """Rewrite a follow-up into a standalone question for retrieval."""
    transcript = "\n".join(
        f"{m.role.value}: {m.content}" for m in history[-4:]
    )
    prompt = f"Conversation:\n{transcript}\n\nLatest question: {question}"
    try:
        condensed = get_llm_provider().generate(CONDENSE_SYSTEM, prompt).strip()
        # Guard against a chatty model returning an essay instead of a question
        if condensed and len(condensed) < 4 * len(prompt):
            logger.info("Condensed %r -> %r", question, condensed)
            return condensed
    except Exception:
        logger.exception("Follow-up condensing failed; using the raw question")
    return question


def prepare_turn(
    db: Session,
    question: str,
    conversation_id: int | None = None,
    grade: str | None = None,
    subject: str | None = None,
    document_id: int | None = None,
) -> ChatTurn:
    settings = get_settings()
    conversation = _get_or_create_conversation(db, conversation_id, question, grade, subject)
    history = conversation.messages[-settings.history_turns :]

    search_text = question
    if history and settings.condense_followups:
        search_text = _condense_question(question, history)

    query_embedding = get_embedding_provider().embed_query(search_text)
    chunks = search_chunks(
        db,
        query_embedding,
        grade=conversation.grade or grade,
        subject=conversation.subject or subject,
        document_id=document_id,
    )

    if not chunks:
        return ChatTurn(
            conversation=conversation, question=question, llm_messages=[], has_context=False
        )

    # Prior turns as plain messages (without their old context blocks), then
    # the current question wrapped with fresh context passages.
    llm_messages = [{"role": m.role.value, "content": m.content} for m in history]
    llm_messages.append({"role": "user", "content": _build_user_prompt(question, chunks)})

    sources = [
        Source(
            index=i,
            document_title=c.document_title,
            subject=c.subject,
            page_number=c.page_number,
        )
        for i, c in enumerate(chunks, start=1)
    ]
    return ChatTurn(
        conversation=conversation,
        question=question,
        llm_messages=llm_messages,
        sources=sources,
    )


def finalize_turn(db: Session, turn: ChatTurn, answer: str) -> Message:
    """Persist the user question + assistant answer; returns the assistant message."""
    db.add(
        Message(
            conversation_id=turn.conversation.id,
            role=MessageRole.user,
            content=turn.question,
        )
    )
    assistant = Message(
        conversation_id=turn.conversation.id,
        role=MessageRole.assistant,
        content=answer,
        sources=[vars(s) for s in turn.sources],
    )
    db.add(assistant)
    db.commit()
    return assistant


def ask(
    db: Session,
    question: str,
    conversation_id: int | None = None,
    grade: str | None = None,
    subject: str | None = None,
    document_id: int | None = None,
) -> ChatResult:
    """Blocking one-call chat turn."""
    turn = prepare_turn(db, question, conversation_id, grade, subject, document_id)
    if not turn.has_context:
        answer = NO_CONTEXT_ANSWER
    else:
        answer = get_llm_provider().chat(SYSTEM_PROMPT, turn.llm_messages)
    message = finalize_turn(db, turn, answer)
    return ChatResult(
        conversation_id=turn.conversation.id,
        message_id=message.id,
        answer=answer,
        sources=turn.sources,
    )


def ask_stream(
    db: Session,
    question: str,
    conversation_id: int | None = None,
    grade: str | None = None,
    subject: str | None = None,
    document_id: int | None = None,
) -> Iterator[dict]:
    """Streaming chat turn. Yields event dicts:

    {"type": "start", "conversation_id": ...}
    {"type": "token", "text": ...}          (repeatedly)
    {"type": "done", "message_id": ..., "sources": [...]}
    """
    turn = prepare_turn(db, question, conversation_id, grade, subject, document_id)
    yield {"type": "start", "conversation_id": turn.conversation.id}

    parts: list[str] = []
    if not turn.has_context:
        parts.append(NO_CONTEXT_ANSWER)
        yield {"type": "token", "text": NO_CONTEXT_ANSWER}
    else:
        for token in get_llm_provider().chat_stream(SYSTEM_PROMPT, turn.llm_messages):
            parts.append(token)
            yield {"type": "token", "text": token}

    message = finalize_turn(db, turn, "".join(parts))
    yield {
        "type": "done",
        "message_id": message.id,
        "sources": [vars(s) for s in turn.sources],
    }
