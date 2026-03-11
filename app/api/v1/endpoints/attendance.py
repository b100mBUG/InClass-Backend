from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.core.security import require_student, get_current_user
from app.schemas.attendance import (
    MarkAttendanceRequest, AttendanceResult,
    AttendanceRecordRead, SessionRead,
)
from app.services.attendance_service import (
    mark_attendance,
    get_student_attendance_history,
    get_active_sessions,
)

router = APIRouter(prefix="/attendance", tags=["Attendance (Student)"])


@router.get("/active-sessions", response_model=List[SessionRead])
def list_active_sessions(
    db: Session = Depends(get_db),
    _=Depends(get_current_user),   # any authenticated user can browse
):
    """Return all currently open sessions the student can check into."""
    return get_active_sessions(db)


@router.post("/mark", response_model=AttendanceResult)
def mark_present(
    payload: MarkAttendanceRequest,
    db: Session = Depends(get_db),
    student=Depends(require_student),
):
    """
    Student marks themselves present.
    Submits GPS coordinates → backend checks distance from lecturer → records result.
    """
    return mark_attendance(db, payload, student)


@router.get("/my-history", response_model=List[AttendanceRecordRead])
def my_attendance_history(
    db: Session = Depends(get_db),
    student=Depends(require_student),
):
    """Student views their own attendance history across all sessions."""
    return get_student_attendance_history(db, student)
