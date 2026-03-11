from datetime import datetime, timedelta, timezone
from typing import List

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.attendance import AttendanceSession, AttendanceRecord, SessionStatus, AttendanceStatus
from app.models.user import User
from app.schemas.attendance import (
    SessionCreate, SessionRead, SessionSummary,
    MarkAttendanceRequest, AttendanceResult,
    AttendanceRecordRead, AttendanceRecordWithStudent,
    SessionAttendanceReport,
)
from app.services.geo import is_within_range


# ── Lecturer: session management ──────────────────────────────────────────────

def create_session(db: Session, payload: SessionCreate, lecturer: User) -> SessionRead:
    """Lecturer opens a new attendance session, broadcasting their GPS location."""
    window = payload.window_minutes or settings.SESSION_WINDOW_MINUTES
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=window)

    session = AttendanceSession(
        title=payload.title,
        course_code=payload.course_code,
        lecturer_latitude=payload.lecturer_latitude,
        lecturer_longitude=payload.lecturer_longitude,
        expires_at=expires_at,
        lecturer_id=lecturer.id,
        max_distance_meters=payload.max_distance_meters,
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return SessionRead.model_validate(session)


def close_session(db: Session, session_id: int, lecturer: User) -> SessionRead:
    """Lecturer manually closes a session before it expires."""
    session = _get_session_or_404(db, session_id)
    _assert_session_owner(session, lecturer)

    session.status = SessionStatus.closed
    db.commit()
    db.refresh(session)
    return SessionRead.model_validate(session)


def expire_stale_sessions(db: Session) -> int:
    """
    Mark sessions as expired if their window has passed.
    Call this as a background task or via a scheduler.
    Returns number of sessions expired.
    """
    now = datetime.now(timezone.utc)
    stale = (
        db.query(AttendanceSession)
        .filter(
            AttendanceSession.status == SessionStatus.active,
            AttendanceSession.expires_at <= now,
        )
        .all()
    )
    for s in stale:
        s.status = SessionStatus.expired
    db.commit()
    return len(stale)


def get_lecturer_sessions(db: Session, lecturer: User) -> List[SessionSummary]:
    """Return all sessions created by this lecturer, enriched with attendance counts."""
    sessions = (
        db.query(AttendanceSession)
        .filter(AttendanceSession.lecturer_id == lecturer.id)
        .order_by(AttendanceSession.started_at.desc())
        .all()
    )
    result = []
    for s in sessions:
        _refresh_session_status(db, s)
        summary = SessionSummary.model_validate(s)
        summary.total_present = sum(1 for r in s.attendance_records if r.status == AttendanceStatus.present)
        summary.total_rejected = sum(1 for r in s.attendance_records if r.status == AttendanceStatus.rejected)
        result.append(summary)
    return result


def get_session_report(db: Session, session_id: int, lecturer: User) -> SessionAttendanceReport:
    """Full attendance report for a session — lecturer only."""
    session = _get_session_or_404(db, session_id)
    _assert_session_owner(session, lecturer)
    _refresh_session_status(db, session)

    records = []
    for r in session.attendance_records:
        student = db.query(User).filter(User.id == r.student_id).first()
        records.append(
            AttendanceRecordWithStudent(
                **AttendanceRecordRead.model_validate(r).model_dump(),
                student_full_name=student.full_name,
                student_email=student.email,
                student_id_number=student.student_id,
            )
        )

    present_count = sum(1 for r in records if r.status == AttendanceStatus.present)
    rejected_count = sum(1 for r in records if r.status == AttendanceStatus.rejected)

    return SessionAttendanceReport(
        session=SessionRead.model_validate(session),
        records=records,
        total_present=present_count,
        total_rejected=rejected_count,
    )


# ── Student: mark attendance ──────────────────────────────────────────────────

def mark_attendance(
    db: Session,
    payload: MarkAttendanceRequest,
    student: User,
) -> AttendanceResult:
    """
    Student submits their GPS coordinates.
    - Checks session is still active (not expired/closed).
    - Checks student hasn't already marked for this session.
    - Computes distance from lecturer's coordinates.
    - Records as PRESENT or REJECTED.
    """
    session = _get_session_or_404(db, payload.session_id)
    _refresh_session_status(db, session)

    # Session must be active
    if session.status != SessionStatus.active:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail=f"Session is {session.status}. Attendance window has closed.",
        )

    # Prevent duplicate marking
    existing = (
        db.query(AttendanceRecord)
        .filter(
            AttendanceRecord.session_id == session.id,
            AttendanceRecord.student_id == student.id,
        )
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Attendance already marked for this session.",
        )

    # Determine allowed distance
    max_dist = session.max_distance_meters or settings.MAX_DISTANCE_METERS

    # Geolocation check
    within_range, distance = is_within_range(
        lecturer_lat=session.lecturer_latitude,
        lecturer_lon=session.lecturer_longitude,
        student_lat=payload.student_latitude,
        student_lon=payload.student_longitude,
        max_distance_meters=max_dist,
    )

    attendance_status = AttendanceStatus.present if within_range else AttendanceStatus.rejected

    record = AttendanceRecord(
        session_id=session.id,
        student_id=student.id,
        student_latitude=payload.student_latitude,
        student_longitude=payload.student_longitude,
        distance_meters=round(distance, 2),
        status=attendance_status,
    )
    db.add(record)
    db.commit()

    return AttendanceResult(
        success=within_range,
        status=attendance_status.value,
        distance_meters=round(distance, 2),
        max_allowed_meters=max_dist,
        message=(
            "Attendance marked successfully. You are present."
            if within_range
            else f"You are {distance:.0f}m away from the class location. Maximum allowed is {max_dist:.0f}m."
        ),
    )


def get_student_attendance_history(
    db: Session,
    student: User,
) -> List[AttendanceRecordRead]:
    """Return all attendance records for a student."""
    records = (
        db.query(AttendanceRecord)
        .filter(AttendanceRecord.student_id == student.id)
        .order_by(AttendanceRecord.marked_at.desc())
        .all()
    )
    return [AttendanceRecordRead.model_validate(r) for r in records]


def get_active_sessions(db: Session) -> List[SessionRead]:
    """Return all currently active sessions — students can browse and pick theirs."""
    expire_stale_sessions(db)
    sessions = (
        db.query(AttendanceSession)
        .filter(AttendanceSession.status == SessionStatus.active)
        .order_by(AttendanceSession.started_at.desc())
        .all()
    )
    return [SessionRead.model_validate(s) for s in sessions]


# ── Private helpers ───────────────────────────────────────────────────────────

def _get_session_or_404(db: Session, session_id: int) -> AttendanceSession:
    session = db.query(AttendanceSession).filter(AttendanceSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    return session


def _assert_session_owner(session: AttendanceSession, lecturer: User):
    if session.lecturer_id != lecturer.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your session")


def _refresh_session_status(db: Session, session: AttendanceSession):
    """Lazily expire a session if its window has passed."""
    if (
        session.status == SessionStatus.active
        and session.expires_at.replace(tzinfo=timezone.utc) <= datetime.now(timezone.utc)
    ):
        session.status = SessionStatus.expired
        db.commit()
