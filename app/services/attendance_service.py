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
from app.services.qr_service import generate_qr_for_session, validate_qr_token
from app.services.course_service import is_student_enrolled


# ── Lecturer: session management ──────────────────────────────────────────────

def create_session(db: Session, payload: SessionCreate, lecturer: User) -> SessionRead:
    """
    Lecturer opens a new attendance session, broadcasting their GPS location.
    After saving the session, we immediately generate the first QR token so the
    lecturer can start displaying the QR code without waiting for the scheduler.
    """
    window = payload.window_minutes or settings.SESSION_WINDOW_MINUTES
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=window)

    session = AttendanceSession(
        title=payload.title,
        course_code=payload.course_code,
        course_id=payload.course_id,
        lecturer_latitude=payload.lecturer_latitude,
        lecturer_longitude=payload.lecturer_longitude,
        expires_at=expires_at,
        lecturer_id=lecturer.id,
        max_distance_meters=payload.max_distance_meters,
    )
    db.add(session)
    db.commit()
    db.refresh(session)

    # Generate the first QR token immediately on session creation.
    # The background scheduler will rotate it every QR_ROTATION_INTERVAL_SECONDS.
    generate_qr_for_session(db, session.id)

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
    Student marks themselves present. Verification runs in layers:

        Layer 0 — Device signature  : Does this submission come from the student's registered device?
        Layer 1 — QR token check    : Did the student scan the real, current QR code?
        Layer 2 — Session expiry    : Is the attendance window still open?
        Layer 3 — Duplicate check   : Has this student already marked for this session?
        Layer 4 — GPS distance      : Is the student physically within the allowed radius?

    Failing Layers 0-3 returns an HTTP error (hard stop).
    Failing Layer 4 saves a REJECTED record so the lecturer can see attempted fraud.
    """
    session = _get_session_or_404(db, payload.session_id)
    _refresh_session_status(db, session)

    # ── Enrollment Guard ──────────────────────────────────────────────────────
    if session.course_id is not None:
        if not is_student_enrolled(db, student.id, session.course_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You are not enrolled in this course.",
            )

    # ── Layer 0: Device Signature Validation ──────────────────────────────────
    # On first attendance, we register the device signature for this student.
    # On all subsequent attendances, the submitted signature must match the stored one.
    # This ensures the submission always comes from the same physical device.
    # Empty signatures are allowed in dev/desktop mode — skips the check entirely.
    if payload.device_signature:
        if student.device_signature is None:
            # First time — register this device as the student's trusted device
            student.device_signature = payload.device_signature
            db.commit()
        elif student.device_signature != payload.device_signature:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Device verification failed. This submission did not come from your registered device.",
            )

    # ── Layer 1: QR Token Validation ─────────────────────────────────────────
    qr_valid, qr_reason = validate_qr_token(db, session.id, payload.qr_token)
    if not qr_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"QR verification failed: {qr_reason}",
        )

    # ── Layer 2: Session must be active ──────────────────────────────────────
    if session.status != SessionStatus.active:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail=f"Session is {session.status}. Attendance window has closed.",
        )

    # ── Layer 3: Prevent duplicate marking ───────────────────────────────────
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

    # ── Layer 4: GPS Distance Check ──────────────────────────────────────────
    max_dist = session.max_distance_meters or settings.MAX_DISTANCE_METERS

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
        device_signature=payload.device_signature or None,
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
