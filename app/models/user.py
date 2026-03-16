from sqlalchemy import Column, Integer, String, Enum
from sqlalchemy.orm import relationship
import enum

from app.db.session import Base


class UserRole(str, enum.Enum):
    admin = "admin"
    lecturer = "lecturer"
    student = "student"


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    full_name = Column(String(100), nullable=False)
    email = Column(String(255), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    role = Column(Enum(UserRole), nullable=False)
    student_id = Column(String(50), unique=True, nullable=True)   # For students

    # Device signature — registered on first attendance submission.
    # SHA256(device_model + resolution + android_id + password)
    # Null until the student marks their first attendance.
    device_signature = Column(String(64), nullable=True, index=True)

    # Relationships
    sessions_created = relationship("AttendanceSession", back_populates="lecturer")
    attendance_records = relationship("AttendanceRecord", back_populates="student")
