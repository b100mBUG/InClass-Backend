"""
Admin Endpoints
===============
System-wide management. Admin role required for all routes.

Covers:
    - User listing and basic management
    - Course creation, updating, deactivation
    - Enrollment management (enroll, bulk enroll, unenroll)
    - System-wide attendance overview
"""

from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.core.security import require_admin
from app.models.user import User, UserRole
from app.schemas.user import UserRead
from app.schemas.course import (
    CourseCreate, CourseUpdate, CourseRead, CourseWithEnrollmentCount,
    EnrollmentCreate, BulkEnrollmentCreate, EnrollmentRead, EnrollmentWithDetails,
)
from app.services.course_service import (
    create_course, update_course, list_courses, get_course,
    enroll_student, bulk_enroll, unenroll_student, get_course_enrollments,
)

router = APIRouter(prefix="/admin", tags=["Admin"])


# ── User management ────────────────────────────────────────────────────────────

@router.get("/users", response_model=List[UserRead])
def list_users(
    role: Optional[str] = Query(None, description="Filter by role: admin, lecturer, student"),
    db: Session = Depends(get_db),
    _=Depends(require_admin),
):
    """List all registered users, optionally filtered by role."""
    query = db.query(User)
    if role:
        query = query.filter(User.role == role)
    return query.order_by(User.full_name).all()


@router.get("/users/{user_id}", response_model=UserRead)
def get_user(
    user_id: int,
    db: Session = Depends(get_db),
    _=Depends(require_admin),
):
    """Get a single user by ID."""
    from fastapi import HTTPException, status
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    return user


# ── Course management ──────────────────────────────────────────────────────────

@router.post("/courses", response_model=CourseRead, status_code=201)
def admin_create_course(
    payload: CourseCreate,
    db: Session = Depends(get_db),
    admin=Depends(require_admin),
):
    """Create a new course. Course codes must be unique."""
    return create_course(db, payload, admin)


@router.get("/courses", response_model=List[CourseWithEnrollmentCount])
def admin_list_courses(
    active_only: bool = Query(True),
    db: Session = Depends(get_db),
    _=Depends(require_admin),
):
    """List all courses with enrollment counts."""
    return list_courses(db, active_only=active_only)


@router.get("/courses/{course_id}", response_model=CourseWithEnrollmentCount)
def admin_get_course(
    course_id: int,
    db: Session = Depends(get_db),
    _=Depends(require_admin),
):
    """Get a course by ID with enrollment count."""
    return get_course(db, course_id)


@router.patch("/courses/{course_id}", response_model=CourseRead)
def admin_update_course(
    course_id: int,
    payload: CourseUpdate,
    db: Session = Depends(get_db),
    _=Depends(require_admin),
):
    """Update course name, description, or active status."""
    return update_course(db, course_id, payload)


# ── Enrollment management ──────────────────────────────────────────────────────

@router.post("/enrollments", response_model=EnrollmentRead, status_code=201)
def admin_enroll_student(
    payload: EnrollmentCreate,
    db: Session = Depends(get_db),
    _=Depends(require_admin),
):
    """Enroll a single student in a course."""
    return enroll_student(db, payload)


@router.post("/enrollments/bulk", status_code=201)
def admin_bulk_enroll(
    payload: BulkEnrollmentCreate,
    db: Session = Depends(get_db),
    _=Depends(require_admin),
):
    """Enroll multiple students in a course at once. Returns a summary."""
    return bulk_enroll(db, payload)


@router.delete("/enrollments/{student_id}/{course_id}")
def admin_unenroll_student(
    student_id: int,
    course_id: int,
    db: Session = Depends(get_db),
    _=Depends(require_admin),
):
    """Remove a student from a course (soft delete)."""
    return unenroll_student(db, student_id, course_id)


@router.get("/courses/{course_id}/enrollments", response_model=List[EnrollmentWithDetails])
def admin_course_enrollments(
    course_id: int,
    db: Session = Depends(get_db),
    _=Depends(require_admin),
):
    """List all students enrolled in a course."""
    return get_course_enrollments(db, course_id)
