from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field


# ── Session schemas ───────────────────────────────────────────────────────────

class SessionCreate(BaseModel):
    title: str
    course_id: int                          # Must be a real course in the DB
    course_code: str                        # Kept for display convenience
    lecturer_latitude: float = Field(..., ge=-90, le=90)
    lecturer_longitude: float = Field(..., ge=-180, le=180)
    window_minutes: Optional[int] = Field(
        None,
        description="Override global SESSION_WINDOW_MINUTES for this session"
    )
    max_distance_meters: Optional[float] = Field(
        None,
        description="Override global MAX_DISTANCE_METERS for this session"
    )


class SessionRead(BaseModel):
    id: int
    title: str
    course_id: Optional[int]
    course_code: str
    lecturer_latitude: float
    lecturer_longitude: float
    started_at: datetime
    expires_at: datetime
    status: str
    lecturer_id: int
    max_distance_meters: Optional[float]

    model_config = {"from_attributes": True}


class SessionSummary(SessionRead):
    """Session with attendance count."""
    total_present: int = 0
    total_rejected: int = 0


class SessionClose(BaseModel):
    """Lecturer manually closes a session early."""
    session_id: int


# ── Attendance record schemas ─────────────────────────────────────────────────

class MarkAttendanceRequest(BaseModel):
    session_id: int

    # Layer 1 — QR token scanned from lecturer's rotating code
    qr_token: str = Field(..., min_length=32, max_length=64, description="Token scanned from the lecturer's QR code")

    student_latitude: float = Field(..., ge=-90, le=90)
    student_longitude: float = Field(..., ge=-180, le=180)

    # Layer 0 — Device signature: SHA256(model + resolution + android_id + password)
    # Computed on the student's device at login. Never contains raw password or device info.
    device_signature: str = Field("", description="SHA256 device fingerprint — empty string disables check (dev mode)")


class AttendanceRecordRead(BaseModel):
    id: int
    session_id: int
    student_id: int
    student_latitude: float
    student_longitude: float
    distance_meters: float
    status: str
    marked_at: datetime
    device_signature: Optional[str] = None

    model_config = {"from_attributes": True}


class AttendanceRecordWithStudent(AttendanceRecordRead):
    student_full_name: str
    student_email: str
    student_id_number: Optional[str]   # the student_id field on User


class AttendanceResult(BaseModel):
    """Response returned to student after marking attendance."""
    success: bool
    status: str                # "present" | "rejected" | error reason
    distance_meters: float
    max_allowed_meters: float
    message: str


# ── Session attendance list (lecturer view) ───────────────────────────────────

class SessionAttendanceReport(BaseModel):
    session: SessionRead
    records: List[AttendanceRecordWithStudent]
    total_present: int
    total_rejected: int
