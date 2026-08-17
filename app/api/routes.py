"""API routes for the walking skeleton.

Auth and grade-scoped student sessions arrive in M4 — until then, /ask
accepts an optional grade filter directly.
"""

import json
import shutil
from datetime import datetime
from pathlib import Path

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
)
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db import get_db, get_session_factory
from app.models import (
    Conversation,
    Document,
    DocumentStatus,
    Message,
    MessageRole,
)
from app.services import chat as chat_service
from app.services.ingestion.parsers import supported_extensions
from app.services.ingestion.pipeline import ingest_document
from app.services.qa import answer_question
from app.services.quiz import generate_quiz

router = APIRouter()


# --- Schemas ---


class AskRequest(BaseModel):
    question: str
    grade: str | None = None
    subject: str | None = None
    document_id: int | None = None


class SourceResponse(BaseModel):
    index: int
    document_title: str
    subject: str | None
    page_number: int | None


class AskResponse(BaseModel):
    answer: str
    sources: list[SourceResponse]


class DocumentResponse(BaseModel):
    id: int
    title: str
    subject: str | None
    grade: str | None
    language: str
    file_type: str
    status: DocumentStatus
    error: str | None

    model_config = {"from_attributes": True}


# --- Routes ---


@router.get("/health")
def health() -> dict:
    return {"status": "ok"}


@router.post("/ask", response_model=AskResponse)
def ask(request: AskRequest, db: Session = Depends(get_db)) -> AskResponse:
    if not request.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty")
    result = answer_question(
        db,
        question=request.question,
        grade=request.grade,
        subject=request.subject,
        document_id=request.document_id,
    )
    return AskResponse(
        answer=result.answer,
        sources=[SourceResponse(**vars(s)) for s in result.sources],
    )


def _run_ingestion(document_id: int) -> None:
    """Background task entrypoint — uses its own DB session."""
    db = get_session_factory()()
    try:
        ingest_document(db, document_id)
    except Exception:
        pass  # status/error already recorded on the document by the pipeline
    finally:
        db.close()


@router.post("/admin/documents", response_model=DocumentResponse, status_code=202)
def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    title: str = Form(...),
    subject: str | None = Form(None),
    grade: str | None = Form(None),
    language: str = Form("en"),
    db: Session = Depends(get_db),
) -> Document:
    extension = Path(file.filename or "").suffix.lower().lstrip(".")
    if extension not in supported_extensions():
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type. Supported: {', '.join(supported_extensions())}",
        )

    upload_dir = Path(get_settings().upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)

    document = Document(
        title=title,
        subject=subject,
        grade=grade,
        language=language,
        file_path="",
        file_type=extension,
        status=DocumentStatus.queued,
    )
    db.add(document)
    db.commit()

    destination = upload_dir / f"{document.id}.{extension}"
    with destination.open("wb") as out:
        shutil.copyfileobj(file.file, out)
    document.file_path = str(destination)
    db.commit()

    background_tasks.add_task(_run_ingestion, document.id)
    return document


@router.get("/admin/documents", response_model=list[DocumentResponse])
def list_documents(db: Session = Depends(get_db)) -> list[Document]:
    return db.query(Document).order_by(Document.created_at.desc()).all()


@router.get("/admin/documents/{document_id}", response_model=DocumentResponse)
def get_document(document_id: int, db: Session = Depends(get_db)) -> Document:
    document = db.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return document


@router.delete("/admin/documents/{document_id}", status_code=204)
def delete_document(document_id: int, db: Session = Depends(get_db)) -> None:
    document = db.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    if document.file_path:
        Path(document.file_path).unlink(missing_ok=True)
    db.delete(document)  # chunks cascade
    db.commit()


# --- Chat with memory (Phase 2) ---


class ChatRequest(BaseModel):
    question: str
    conversation_id: int | None = None  # omit to start a new conversation
    grade: str | None = None
    subject: str | None = None
    document_id: int | None = None


class ChatResponse(BaseModel):
    conversation_id: int
    message_id: int
    answer: str
    sources: list[SourceResponse]


class ConversationResponse(BaseModel):
    id: int
    title: str | None
    grade: str | None
    subject: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class MessageResponse(BaseModel):
    id: int
    role: MessageRole
    content: str
    sources: list | None
    rating: int | None
    created_at: datetime

    model_config = {"from_attributes": True}


class FeedbackRequest(BaseModel):
    rating: int  # +1 (helpful) or -1 (not helpful)
    comment: str | None = None


@router.post("/chat/ask", response_model=ChatResponse)
def chat_ask(request: ChatRequest, db: Session = Depends(get_db)) -> ChatResponse:
    if not request.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty")
    try:
        result = chat_service.ask(
            db,
            question=request.question,
            conversation_id=request.conversation_id,
            grade=request.grade,
            subject=request.subject,
            document_id=request.document_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return ChatResponse(
        conversation_id=result.conversation_id,
        message_id=result.message_id,
        answer=result.answer,
        sources=[SourceResponse(**vars(s)) for s in result.sources],
    )


@router.post("/chat/ask/stream")
def chat_ask_stream(request: ChatRequest, db: Session = Depends(get_db)) -> StreamingResponse:
    """Server-Sent Events: `start` → many `token` events → `done` (with sources)."""
    if not request.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty")

    def event_stream():
        try:
            for event in chat_service.ask_stream(
                db,
                question=request.question,
                conversation_id=request.conversation_id,
                grade=request.grade,
                subject=request.subject,
                document_id=request.document_id,
            ):
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        except Exception as exc:  # surface errors as an SSE event, not a broken stream
            yield f"data: {json.dumps({'type': 'error', 'detail': str(exc)})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.get("/chat/conversations", response_model=list[ConversationResponse])
def list_conversations(db: Session = Depends(get_db)) -> list[Conversation]:
    return db.query(Conversation).order_by(Conversation.created_at.desc()).all()


@router.get("/chat/conversations/{conversation_id}/messages", response_model=list[MessageResponse])
def list_messages(conversation_id: int, db: Session = Depends(get_db)) -> list[Message]:
    conversation = db.get(Conversation, conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conversation.messages


@router.post("/chat/messages/{message_id}/feedback", response_model=MessageResponse)
def submit_feedback(
    message_id: int, request: FeedbackRequest, db: Session = Depends(get_db)
) -> Message:
    if request.rating not in (1, -1):
        raise HTTPException(status_code=400, detail="rating must be 1 or -1")
    message = db.get(Message, message_id)
    if message is None:
        raise HTTPException(status_code=404, detail="Message not found")
    if message.role != MessageRole.assistant:
        raise HTTPException(status_code=400, detail="Feedback applies to assistant messages")
    message.rating = request.rating
    message.feedback_comment = request.comment
    db.commit()
    return message


# --- Quiz (Phase 2) ---


class QuizRequest(BaseModel):
    grade: str | None = None
    subject: str | None = None
    document_id: int | None = None
    num_questions: int | None = None


@router.post("/quiz")
def create_quiz(request: QuizRequest, db: Session = Depends(get_db)) -> dict:
    result = generate_quiz(
        db,
        grade=request.grade,
        subject=request.subject,
        document_id=request.document_id,
        num_questions=request.num_questions,
    )
    if result.get("questions") is None:
        raise HTTPException(status_code=422, detail=result)
    return result


# --- Admin analytics (Phase 2, minimal) ---


@router.get("/admin/analytics")
def analytics(db: Session = Depends(get_db)) -> dict:
    questions = db.scalar(
        select(func.count()).select_from(Message).where(Message.role == MessageRole.user)
    )
    helpful = db.scalar(
        select(func.count()).select_from(Message).where(Message.rating == 1)
    )
    not_helpful = db.scalar(
        select(func.count()).select_from(Message).where(Message.rating == -1)
    )
    recent = db.scalars(
        select(Message)
        .where(Message.role == MessageRole.user)
        .order_by(Message.id.desc())
        .limit(20)
    ).all()
    return {
        "total_questions": questions,
        "feedback": {"helpful": helpful, "not_helpful": not_helpful},
        "recent_questions": [m.content for m in recent],
    }
