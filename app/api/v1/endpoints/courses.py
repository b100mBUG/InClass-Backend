"""
Course Endpoints (Lecturer + Student)
======================================
Lecturers can create courses and view their course enrollments.
Students can browse and view their own enrolled courses.
"""

from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.core.security import require_lecturer, require_student, get_current_user
from app.schemas.course import CourseCreate, CourseRead, CourseWithEnrollmentCount, EnrollmentWithDetails
from app.services.course_service import (
    create_course, list_courses, get_course,
    get_course_enrollments, get_student_courses,
)

router = APIRouter(prefix="/courses", tags=["Courses"])


@router.post("", response_model=CourseRead, status_code=201)
def lecturer_create_course(
    payload: CourseCreate,
    db: Session = Depends(get_db),
    lecturer=Depends(require_lecturer),
):
    """Lecturer creates a new course."""
    return create_course(db, payload, lecturer)


@router.get("", response_model=List[CourseWithEnrollmentCount])
def browse_courses(
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    """List all active courses. Available to all authenticated users."""
    return list_courses(db, active_only=True)


@router.get("/my-courses", response_model=List[CourseRead])
def my_enrolled_courses(
    db: Session = Depends(get_db),
    student=Depends(require_student),
):
    """Student: view courses you are enrolled in."""
    return get_student_courses(db, student)


@router.get("/{course_id}", response_model=CourseWithEnrollmentCount)
def course_detail(
    course_id: int,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    """Get course details with enrollment count."""
    return get_course(db, course_id)


@router.get("/{course_id}/students", response_model=List[EnrollmentWithDetails])
def course_students(
    course_id: int,
    db: Session = Depends(get_db),
    _=Depends(require_lecturer),
):
    """Lecturer: view all students enrolled in a course."""
    return get_course_enrollments(db, course_id)
