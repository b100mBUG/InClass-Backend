"""
Export Service
==============
Generates CSV exports of attendance data.

Used by:
    - Lecturers: export their own session report
    - Admins: export any session or full course attendance

The CSV is streamed directly as a response — no temp files on disk.
"""

import csv
import io
from datetime import timezone

from sqlalchemy.orm import Session

from app.models.attendance import AttendanceSession, AttendanceRecord, SessionStatus
from app.models.user import User


def export_session_csv(db: Session, session: AttendanceSession) -> bytes:
    """
    Build a CSV of all attendance records for a session.
    Returns raw bytes ready to be sent as a file download.

    Columns:
        Student Name | Student ID | Email | Status | Distance (m) | Marked At
    """
    output = io.StringIO()
    writer = csv.writer(output)

    # Header row
    writer.writerow([
        "Student Name",
        "Student ID Number",
        "Email",
        "Attendance Status",
        "Distance from Lecturer (m)",
        "Marked At (UTC)",
    ])

    records = (
        db.query(AttendanceRecord)
        .filter(AttendanceRecord.session_id == session.id)
        .order_by(AttendanceRecord.marked_at)
        .all()
    )

    for record in records:
        student = db.query(User).filter(User.id == record.student_id).first()
        marked_at = record.marked_at
        # Normalise to UTC-aware if SQLite returned naive datetime
        if marked_at.tzinfo is None:
            marked_at = marked_at.replace(tzinfo=timezone.utc)

        writer.writerow([
            student.full_name if student else "Unknown",
            student.student_id if student else "-",
            student.email if student else "-",
            record.status,
            f"{record.distance_meters:.1f}",
            marked_at.strftime("%Y-%m-%d %H:%M:%S"),
        ])

    return output.getvalue().encode("utf-8")


def export_course_csv(db: Session, course_id: int) -> bytes:
    """
    Build a CSV of all attendance records across every session of a course.
    Useful for end-of-semester reports.

    Columns:
        Session Title | Session Date | Student Name | Student ID | Email | Status | Distance (m)
    """
    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow([
        "Session Title",
        "Session Date (UTC)",
        "Student Name",
        "Student ID Number",
        "Email",
        "Attendance Status",
        "Distance from Lecturer (m)",
    ])

    sessions = (
        db.query(AttendanceSession)
        .filter(AttendanceSession.course_id == course_id)
        .order_by(AttendanceSession.started_at)
        .all()
    )

    for session in sessions:
        started_at = session.started_at
        if started_at.tzinfo is None:
            started_at = started_at.replace(tzinfo=timezone.utc)

        records = (
            db.query(AttendanceRecord)
            .filter(AttendanceRecord.session_id == session.id)
            .order_by(AttendanceRecord.marked_at)
            .all()
        )

        for record in records:
            student = db.query(User).filter(User.id == record.student_id).first()
            writer.writerow([
                session.title,
                started_at.strftime("%Y-%m-%d %H:%M:%S"),
                student.full_name if student else "Unknown",
                student.student_id if student else "-",
                student.email if student else "-",
                record.status,
                f"{record.distance_meters:.1f}",
            ])

    return output.getvalue().encode("utf-8")
