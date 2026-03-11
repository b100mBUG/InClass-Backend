from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.core.security import require_lecturer
from app.schemas.attendance import (
    SessionCreate, SessionRead, SessionSummary,
    SessionClose, SessionAttendanceReport,
)
from app.services.attendance_service import (
    create_session,
    close_session,
    get_lecturer_sessions,
    get_session_report,
    expire_stale_sessions,
)

router = APIRouter(prefix="/sessions", tags=["Sessions (Lecturer)"])


@router.post("", response_model=SessionRead, status_code=201)
def open_session(
    payload: SessionCreate,
    db: Session = Depends(get_db),
    lecturer=Depends(require_lecturer),
):
    """
    Lecturer opens a new attendance session.
    Captures the lecturer's current GPS coordinates as the attendance anchor.
    """
    return create_session(db, payload, lecturer)


@router.post("/{session_id}/close", response_model=SessionRead)
def close_session_early(
    session_id: int,
    db: Session = Depends(get_db),
    lecturer=Depends(require_lecturer),
):
    """Lecturer manually closes a session before the time window expires."""
    return close_session(db, session_id, lecturer)


@router.get("", response_model=List[SessionSummary])
def list_my_sessions(
    db: Session = Depends(get_db),
    lecturer=Depends(require_lecturer),
):
    """List all sessions created by the logged-in lecturer with attendance counts."""
    return get_lecturer_sessions(db, lecturer)


@router.get("/{session_id}/report", response_model=SessionAttendanceReport)
def session_report(
    session_id: int,
    db: Session = Depends(get_db),
    lecturer=Depends(require_lecturer),
):
    """Full attendance report for a session — who attended, distances, timestamps."""
    return get_session_report(db, session_id, lecturer)


@router.post("/expire-stale", status_code=200)
def trigger_expire_stale(db: Session = Depends(get_db), _=Depends(require_lecturer)):
    """
    Manually trigger expiry of stale sessions.
    In production, wire this to a cron job / APScheduler instead.
    """
    count = expire_stale_sessions(db)
    return {"expired_sessions": count}
