from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel


# ── Course schemas ─────────────────────────────────────────────────────────────

class CourseCreate(BaseModel):
    code: str
    name: str
    description: Optional[str] = None


class CourseUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None


class CourseRead(BaseModel):
    id: int
    code: str
    name: str
    description: Optional[str]
    is_active: bool
    created_at: datetime
    created_by: int

    model_config = {"from_attributes": True}


class CourseWithEnrollmentCount(CourseRead):
    enrolled_students: int = 0


# ── Enrollment schemas ─────────────────────────────────────────────────────────

class EnrollmentCreate(BaseModel):
    student_id: int
    course_id: int


class BulkEnrollmentCreate(BaseModel):
    """Enroll multiple students in a course at once."""
    course_id: int
    student_ids: List[int]


class EnrollmentRead(BaseModel):
    id: int
    student_id: int
    course_id: int
    enrolled_at: datetime
    is_active: bool

    model_config = {"from_attributes": True}


class EnrollmentWithDetails(EnrollmentRead):
    student_full_name: str
    student_email: str
    student_id_number: Optional[str]
    course_code: str
    course_name: str
