"""Auth dependencies: who's calling, and what grade/subject they may see."""

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy.orm import Session

from app.core.security import decode_access_token
from app.db import get_db
from app.models import Subject, User, UserRole, UserStatus

_bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = decode_access_token(credentials.credentials)
        user_id = int(payload["sub"])
    except (JWTError, KeyError, ValueError):
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid token")
    # Re-checked fresh from the DB (not trusted from the token) so an admin
    # approving/rejecting a user takes effect immediately on their next request.
    if user.status != UserStatus.approved:
        detail = (
            "Your account is awaiting admin approval"
            if user.status == UserStatus.pending
            else "Your account access has been revoked"
        )
        raise HTTPException(status_code=403, detail=detail)
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != UserRole.admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


def resolve_scope(
    current_user: User,
    requested_grade_id: int | None,
    requested_subject_id: int | None,
    db: Session,
) -> tuple[int | None, int | None]:
    """Students: grade is always their own account's grade; a requested
    subject must belong to it. Admins: both values pass through untouched."""
    if current_user.role == UserRole.admin:
        return requested_grade_id, requested_subject_id

    grade_id = current_user.grade_id
    subject_id = requested_subject_id
    if subject_id is not None:
        subject = db.get(Subject, subject_id)
        if subject is None or subject.grade_id != grade_id:
            raise HTTPException(status_code=400, detail="Subject does not belong to your grade")
    return grade_id, subject_id
