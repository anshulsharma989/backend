"""Grades and subjects catalog — admin-managed, read by everyone."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_admin
from app.db import get_db
from app.models import Document, Grade, Subject, User, UserRole

router = APIRouter()


class GradeResponse(BaseModel):
    id: int
    name: str

    model_config = {"from_attributes": True}


class SubjectResponse(BaseModel):
    id: int
    grade_id: int
    name: str

    model_config = {"from_attributes": True}


class GradeCreateRequest(BaseModel):
    name: str


class SubjectCreateRequest(BaseModel):
    grade_id: int
    name: str


@router.get("/grades", response_model=list[GradeResponse])
def list_grades(db: Session = Depends(get_db)) -> list[Grade]:
    return db.query(Grade).order_by(Grade.name).all()


@router.get("/subjects", response_model=list[SubjectResponse])
def list_subjects(
    grade_id: int | None = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[Subject]:
    # Students always see their own grade's subjects, regardless of the query
    # param; admins may filter by any grade_id or omit it for all subjects.
    effective_grade_id = grade_id
    if current_user.role != UserRole.admin:
        effective_grade_id = current_user.grade_id

    query = db.query(Subject)
    if effective_grade_id is not None:
        query = query.filter(Subject.grade_id == effective_grade_id)
    return query.order_by(Subject.name).all()


@router.post("/admin/grades", response_model=GradeResponse, status_code=201)
def create_grade(
    request: GradeCreateRequest, _: User = Depends(require_admin), db: Session = Depends(get_db)
) -> Grade:
    if db.query(Grade).filter(Grade.name == request.name).first():
        raise HTTPException(status_code=409, detail="Grade already exists")
    grade = Grade(name=request.name)
    db.add(grade)
    db.commit()
    return grade


@router.delete("/admin/grades/{grade_id}", status_code=204)
def delete_grade(
    grade_id: int, _: User = Depends(require_admin), db: Session = Depends(get_db)
) -> None:
    grade = db.get(Grade, grade_id)
    if grade is None:
        raise HTTPException(status_code=404, detail="Grade not found")
    if db.query(Document).filter(Document.grade_id == grade_id).first():
        raise HTTPException(status_code=409, detail="Grade is in use by one or more documents")
    if db.query(User).filter(User.grade_id == grade_id).first():
        raise HTTPException(status_code=409, detail="Grade is in use by one or more users")
    db.delete(grade)  # subjects cascade
    db.commit()


@router.post("/admin/subjects", response_model=SubjectResponse, status_code=201)
def create_subject(
    request: SubjectCreateRequest,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> Subject:
    if db.get(Grade, request.grade_id) is None:
        raise HTTPException(status_code=400, detail="Unknown grade")
    if (
        db.query(Subject)
        .filter(Subject.grade_id == request.grade_id, Subject.name == request.name)
        .first()
    ):
        raise HTTPException(status_code=409, detail="Subject already exists for this grade")
    subject = Subject(grade_id=request.grade_id, name=request.name)
    db.add(subject)
    db.commit()
    return subject


@router.delete("/admin/subjects/{subject_id}", status_code=204)
def delete_subject(
    subject_id: int, _: User = Depends(require_admin), db: Session = Depends(get_db)
) -> None:
    subject = db.get(Subject, subject_id)
    if subject is None:
        raise HTTPException(status_code=404, detail="Subject not found")
    if db.query(Document).filter(Document.subject_id == subject_id).first():
        raise HTTPException(status_code=409, detail="Subject is in use by one or more documents")
    db.delete(subject)
    db.commit()
