from sqlalchemy import (
    Column, Integer, String, Float, Boolean,
    DateTime, ForeignKey, Enum, func
)
from sqlalchemy.orm import relationship
import enum

from app.db.session import Base


class SessionStatus(str, enum.Enum):
    active = "active"
    expired = "expired"
    closed = "closed"


class AttendanceStatus(str, enum.Enum):
    present = "present"
    absent = "absent"
    rejected = "rejected"   # Marked but outside allowed distance


class AttendanceSession(Base):
    """
    A single lecture session opened by a lecturer.
    The lecturer's GPS coordinates are captured when the session is started.
    Students can mark attendance within the session window.
    """
    __tablename__ = "attendance_sessions"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(200), nullable=False)
    course_code = Column(String(50), nullable=False)

    # Lecturer's location — the source of truth
    lecturer_latitude = Column(Float, nullable=False)
    lecturer_longitude = Column(Float, nullable=False)

    # Time window
    started_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)   # computed on create

    status = Column(Enum(SessionStatus), default=SessionStatus.active, nullable=False)

    # Config overrides (optional — falls back to global settings)
    max_distance_meters = Column(Float, nullable=True)

    # FK
    lecturer_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    # Relationships
    lecturer = relationship("User", back_populates="sessions_created")
    attendance_records = relationship("AttendanceRecord", back_populates="session")


class AttendanceRecord(Base):
    """
    One record per student per session.
    Stores the student's GPS at mark-time and whether they were close enough.
    """
    __tablename__ = "attendance_records"

    id = Column(Integer, primary_key=True, index=True)

    # Student's location at mark-time
    student_latitude = Column(Float, nullable=False)
    student_longitude = Column(Float, nullable=False)
    distance_meters = Column(Float, nullable=False)   # computed distance from lecturer

    status = Column(Enum(AttendanceStatus), nullable=False)
    marked_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # FKs
    session_id = Column(Integer, ForeignKey("attendance_sessions.id"), nullable=False)
    student_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    # Relationships
    session = relationship("AttendanceSession", back_populates="attendance_records")
    student = relationship("User", back_populates="attendance_records")
