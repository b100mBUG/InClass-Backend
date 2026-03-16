"""
Course Service
==============
Handles all business logic for courses and enrollments.

Rules:
    - Only admins and lecturers can create courses.
    - Only admins can enroll/unenroll students.
    - Students can view courses they're enrolled in.
    - Lecturers can only open sessions for existing courses.
"""

from typing import List

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.course import Course, Enrollment
from app.models.user import User, UserRole
from app.schemas.course import (
    CourseCreate, CourseUpdate, CourseRead, CourseWithEnrollmentCount,
    EnrollmentCreate, BulkEnrollmentCreate, EnrollmentRead, EnrollmentWithDetails,
)


# ── Course CRUD ────────────────────────────────────────────────────────────────

def create_course(db: Session, payload: CourseCreate, creator: User) -> CourseRead:
    if db.query(Course).filter(Course.code == payload.code).first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Course with code '{payload.code}' already exists.",
        )

    course = Course(
        code=payload.code,
        name=payload.name,
        description=payload.description,
        created_by=creator.id,
    )
    db.add(course)
    db.commit()
    db.refresh(course)
    return CourseRead.model_validate(course)


def update_course(db: Session, course_id: int, payload: CourseUpdate) -> CourseRead:
    course = _get_course_or_404(db, course_id)
    if payload.name is not None:
        course.name = payload.name
    if payload.description is not None:
        course.description = payload.description
    if payload.is_active is not None:
        course.is_active = payload.is_active
    db.commit()
    db.refresh(course)
    return CourseRead.model_validate(course)


def list_courses(db: Session, active_only: bool = True) -> List[CourseWithEnrollmentCount]:
    query = db.query(Course)
    if active_only:
        query = query.filter(Course.is_active == True)
    courses = query.order_by(Course.code).all()

    result = []
    for c in courses:
        item = CourseWithEnrollmentCount.model_validate(c)
        item.enrolled_students = (
            db.query(Enrollment)
            .filter(Enrollment.course_id == c.id, Enrollment.is_active == True)
            .count()
        )
        result.append(item)
    return result


def get_course(db: Session, course_id: int) -> CourseWithEnrollmentCount:
    course = _get_course_or_404(db, course_id)
    item = CourseWithEnrollmentCount.model_validate(course)
    item.enrolled_students = (
        db.query(Enrollment)
        .filter(Enrollment.course_id == course.id, Enrollment.is_active == True)
        .count()
    )
    return item


# ── Enrollment management ──────────────────────────────────────────────────────

def enroll_student(db: Session, payload: EnrollmentCreate) -> EnrollmentRead:
    """Enroll a single student in a course."""
    _get_course_or_404(db, payload.course_id)
    student = _get_student_or_404(db, payload.student_id)

    existing = db.query(Enrollment).filter(
        Enrollment.student_id == payload.student_id,
        Enrollment.course_id == payload.course_id,
    ).first()

    if existing:
        if existing.is_active:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Student is already enrolled in this course.",
            )
        # Re-activate a previously dropped enrollment
        existing.is_active = True
        db.commit()
        db.refresh(existing)
        return EnrollmentRead.model_validate(existing)

    enrollment = Enrollment(student_id=student.id, course_id=payload.course_id)
    db.add(enrollment)
    db.commit()
    db.refresh(enrollment)
    return EnrollmentRead.model_validate(enrollment)


def bulk_enroll(db: Session, payload: BulkEnrollmentCreate) -> dict:
    """Enroll multiple students in a course at once. Returns a summary."""
    _get_course_or_404(db, payload.course_id)

    enrolled = []
    skipped = []
    errors = []

    for student_id in payload.student_ids:
        student = db.query(User).filter(User.id == student_id, User.role == UserRole.student).first()
        if not student:
            errors.append({"student_id": student_id, "reason": "Student not found"})
            continue

        existing = db.query(Enrollment).filter(
            Enrollment.student_id == student_id,
            Enrollment.course_id == payload.course_id,
        ).first()

        if existing:
            if existing.is_active:
                skipped.append(student_id)
            else:
                existing.is_active = True
                enrolled.append(student_id)
        else:
            db.add(Enrollment(student_id=student_id, course_id=payload.course_id))
            enrolled.append(student_id)

    db.commit()
    return {
        "course_id": payload.course_id,
        "enrolled": len(enrolled),
        "skipped_already_enrolled": len(skipped),
        "errors": errors,
    }


def unenroll_student(db: Session, student_id: int, course_id: int) -> dict:
    """Soft-delete an enrollment (sets is_active = False)."""
    enrollment = db.query(Enrollment).filter(
        Enrollment.student_id == student_id,
        Enrollment.course_id == course_id,
        Enrollment.is_active == True,
    ).first()

    if not enrollment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Active enrollment not found.",
        )

    enrollment.is_active = False
    db.commit()
    return {"message": f"Student {student_id} unenrolled from course {course_id}."}


def get_course_enrollments(db: Session, course_id: int) -> List[EnrollmentWithDetails]:
    """List all active students enrolled in a course."""
    _get_course_or_404(db, course_id)
    enrollments = db.query(Enrollment).filter(
        Enrollment.course_id == course_id,
        Enrollment.is_active == True,
    ).all()

    result = []
    for e in enrollments:
        student = db.query(User).filter(User.id == e.student_id).first()
        course = db.query(Course).filter(Course.id == e.course_id).first()
        result.append(EnrollmentWithDetails(
            **EnrollmentRead.model_validate(e).model_dump(),
            student_full_name=student.full_name,
            student_email=student.email,
            student_id_number=student.student_id,
            course_code=course.code,
            course_name=course.name,
        ))
    return result


def get_student_courses(db: Session, student: User) -> List[CourseRead]:
    """Courses a student is actively enrolled in."""
    enrollments = db.query(Enrollment).filter(
        Enrollment.student_id == student.id,
        Enrollment.is_active == True,
    ).all()
    course_ids = [e.course_id for e in enrollments]
    courses = db.query(Course).filter(Course.id.in_(course_ids), Course.is_active == True).all()
    return [CourseRead.model_validate(c) for c in courses]


def is_student_enrolled(db: Session, student_id: int, course_id: int) -> bool:
    """Check if a student has an active enrollment in a course."""
    return db.query(Enrollment).filter(
        Enrollment.student_id == student_id,
        Enrollment.course_id == course_id,
        Enrollment.is_active == True,
    ).first() is not None


# ── Private helpers ────────────────────────────────────────────────────────────

def _get_course_or_404(db: Session, course_id: int) -> Course:
    course = db.query(Course).filter(Course.id == course_id).first()
    if not course:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course not found.")
    return course


def _get_student_or_404(db: Session, student_id: int) -> User:
    student = db.query(User).filter(
        User.id == student_id,
        User.role == UserRole.student,
    ).first()
    if not student:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Student with id {student_id} not found.",
        )
    return student
