"""Signup, login, and admin approval of student accounts."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_admin
from app.core.security import create_access_token, hash_password, verify_password
from app.db import get_db
from app.models import Grade, User, UserRole, UserStatus

router = APIRouter()


# --- Schemas ---


class SignupRequest(BaseModel):
    email: EmailStr
    password: str
    full_name: str
    grade_id: int


class SignupResponse(BaseModel):
    id: int
    email: str
    full_name: str
    status: UserStatus

    model_config = {"from_attributes": True}


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserResponse(BaseModel):
    id: int
    email: str
    full_name: str
    role: UserRole
    status: UserStatus
    grade_id: int | None
    grade_name: str | None = None


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


def _user_response(user: User) -> UserResponse:
    return UserResponse(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=user.role,
        status=user.status,
        grade_id=user.grade_id,
        grade_name=user.grade.name if user.grade else None,
    )


# --- Signup / login ---


@router.post("/auth/signup", response_model=SignupResponse, status_code=201)
def signup(request: SignupRequest, db: Session = Depends(get_db)) -> User:
    if db.query(User).filter(User.email == request.email.lower()).first():
        raise HTTPException(status_code=409, detail="An account with this email already exists")
    if db.get(Grade, request.grade_id) is None:
        raise HTTPException(status_code=400, detail="Unknown grade")

    user = User(
        email=request.email.lower(),
        password_hash=hash_password(request.password),
        full_name=request.full_name,
        role=UserRole.student,
        status=UserStatus.pending,
        grade_id=request.grade_id,
    )
    db.add(user)
    db.commit()
    return user


@router.post("/auth/login", response_model=TokenResponse)
def login(request: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    user = db.query(User).filter(User.email == request.email.lower()).first()
    if user is None or not verify_password(request.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Incorrect email or password")
    if user.status == UserStatus.pending:
        raise HTTPException(status_code=403, detail="Your account is awaiting admin approval")
    if user.status == UserStatus.rejected:
        raise HTTPException(status_code=403, detail="Your account access has been revoked")

    token = create_access_token(user.id)
    return TokenResponse(access_token=token, user=_user_response(user))


@router.get("/auth/me", response_model=UserResponse)
def me(current_user: User = Depends(get_current_user)) -> UserResponse:
    return _user_response(current_user)


# --- Admin: approve/reject student signups ---


@router.get("/admin/users/pending", response_model=list[UserResponse])
def list_pending_users(
    _: User = Depends(require_admin), db: Session = Depends(get_db)
) -> list[UserResponse]:
    users = db.query(User).filter(User.status == UserStatus.pending).order_by(User.created_at).all()
    return [_user_response(u) for u in users]


@router.post("/admin/users/{user_id}/approve", response_model=UserResponse)
def approve_user(
    user_id: int, _: User = Depends(require_admin), db: Session = Depends(get_db)
) -> UserResponse:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    user.status = UserStatus.approved
    db.commit()
    return _user_response(user)


@router.post("/admin/users/{user_id}/reject", response_model=UserResponse)
def reject_user(
    user_id: int, _: User = Depends(require_admin), db: Session = Depends(get_db)
) -> UserResponse:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    user.status = UserStatus.rejected
    db.commit()
    return _user_response(user)
