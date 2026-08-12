"""API routes for the walking skeleton.

Auth and grade-scoped student sessions arrive in M4 — until then, /ask
accepts an optional grade filter directly.
"""

import shutil
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
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db import get_db, get_session_factory
from app.models import Document, DocumentStatus
from app.services.ingestion.parsers import supported_extensions
from app.services.ingestion.pipeline import ingest_document
from app.services.qa import answer_question

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
