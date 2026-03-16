"""
Course & Enrollment Models
===========================
Course     — a real academic course owned by an institution/admin.
Enrollment — the many-to-many link between students and courses.

A student can only mark attendance for sessions belonging to courses
they are enrolled in. This closes the open-door vulnerability in v1
where any student could mark any session.
"""

from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, DateTime, func
from sqlalchemy.orm import relationship

from app.db.session import Base


class Course(Base):
    __tablename__ = "courses"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(50), unique=True, nullable=False, index=True)
    name = Column(String(200), nullable=False)
    description = Column(String(500), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Who created/owns this course (admin or lecturer)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)

    # Relationships
    enrollments = relationship("Enrollment", back_populates="course", cascade="all, delete-orphan")
    sessions = relationship("AttendanceSession", back_populates="course")
    creator = relationship("User", foreign_keys=[created_by])


class Enrollment(Base):
    """
    Links a student to a course.
    A student can only mark attendance in sessions for courses they're enrolled in.
    """
    __tablename__ = "enrollments"

    id = Column(Integer, primary_key=True, index=True)
    student_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    course_id = Column(Integer, ForeignKey("courses.id"), nullable=False)
    enrolled_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)

    # Relationships
    student = relationship("User", foreign_keys=[student_id])
    course = relationship("Course", back_populates="enrollments")
