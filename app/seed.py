"""Idempotent seed data: grades, subjects, and (optionally) admin/student accounts.

Run via: python -m app.cli seed

Separate from migrations on purpose — migrations own table *structure*,
this owns initial *data*. Safe to run repeatedly: existing rows (matched by
name/email) are left untouched.
"""

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import hash_password
from app.models import Grade, Subject, User, UserRole, UserStatus

GRADES = [f"Grade {n}" for n in range(6, 13)]  # Grade 6 .. Grade 12
SUBJECTS = ["Mathematics", "Science", "English", "Hindi", "Social Science"]


def seed_grades_and_subjects(db: Session) -> tuple[int, int]:
    grades_created = 0
    subjects_created = 0
    for grade_name in GRADES:
        grade = db.query(Grade).filter(Grade.name == grade_name).first()
        if grade is None:
            grade = Grade(name=grade_name)
            db.add(grade)
            db.commit()
            grades_created += 1
        for subject_name in SUBJECTS:
            exists = (
                db.query(Subject)
                .filter(Subject.grade_id == grade.id, Subject.name == subject_name)
                .first()
            )
            if exists is None:
                db.add(Subject(grade_id=grade.id, name=subject_name))
                subjects_created += 1
    db.commit()
    return grades_created, subjects_created


def seed_admin(db: Session) -> str:
    """Creates a dev-convenience admin from SEED_ADMIN_EMAIL/SEED_ADMIN_PASSWORD
    settings, if set and no user with that email exists yet. For a real admin
    account, prefer the interactive `python -m app.cli create-admin` instead —
    this path exists so a fresh environment can be scripted end-to-end.
    Returns "created" | "exists" | "unset"."""
    settings = get_settings()
    email = settings.seed_admin_email
    password = settings.seed_admin_password
    full_name = settings.seed_admin_name
    if not email or not password:
        return "unset"
    if db.query(User).filter(User.email == email.lower()).first():
        return "exists"
    db.add(
        User(
            email=email.lower(),
            password_hash=hash_password(password),
            full_name=full_name,
            role=UserRole.admin,
            status=UserStatus.approved,
        )
    )
    db.commit()
    return "created"


def seed_student(db: Session) -> str:
    """Creates a dev-convenience, already-approved student from
    SEED_STUDENT_EMAIL/SEED_STUDENT_PASSWORD/SEED_STUDENT_GRADE settings, if
    set and no user with that email exists yet. Bypasses the normal
    signup-then-admin-approval flow — for real students, let them sign up.
    Returns "created" | "exists" | "unset" | "bad_grade"."""
    settings = get_settings()
    email = settings.seed_student_email
    password = settings.seed_student_password
    full_name = settings.seed_student_name
    grade_name = settings.seed_student_grade or GRADES[0]
    if not email or not password:
        return "unset"
    if db.query(User).filter(User.email == email.lower()).first():
        return "exists"
    grade = db.query(Grade).filter(Grade.name == grade_name).first()
    if grade is None:
        return "bad_grade"
    db.add(
        User(
            email=email.lower(),
            password_hash=hash_password(password),
            full_name=full_name,
            role=UserRole.student,
            status=UserStatus.approved,
            grade_id=grade.id,
        )
    )
    db.commit()
    return "created"


_ADMIN_MESSAGES = {
    "created": "Admin account created from SEED_ADMIN_EMAIL/SEED_ADMIN_PASSWORD",
    "exists": "Admin account already exists (SEED_ADMIN_EMAIL) — left untouched",
    "unset": (
        "No admin seeded — set SEED_ADMIN_EMAIL/SEED_ADMIN_PASSWORD before seeding, "
        "or run `python -m app.cli create-admin` interactively."
    ),
}

_STUDENT_MESSAGES = {
    "created": "Student account created from SEED_STUDENT_EMAIL/SEED_STUDENT_PASSWORD",
    "exists": "Student account already exists (SEED_STUDENT_EMAIL) — left untouched",
    "bad_grade": "SEED_STUDENT_GRADE not found among seeded grades — skipped student seed",
    "unset": (
        "No student seeded — set SEED_STUDENT_EMAIL/SEED_STUDENT_PASSWORD before seeding, "
        "or have students sign up + get approved normally."
    ),
}


def run_seed(db: Session) -> None:
    grades_created, subjects_created = seed_grades_and_subjects(db)
    print(f"Grades created: {grades_created}, subjects created: {subjects_created}")
    print(_ADMIN_MESSAGES[seed_admin(db)])
    print(_STUDENT_MESSAGES[seed_student(db)])
