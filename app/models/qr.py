"""
QR Token Model
==============
Each active attendance session has exactly ONE QRToken record at any time.
The background scheduler (APScheduler) rotates this token every 30 seconds,
making screenshot-sharing attacks useless — by the time a student sends a
screenshot to an absent friend, the token is already dead.

Flow:
    1. Lecturer opens a session  →  first QRToken is created automatically.
    2. Scheduler fires every 30s →  rotate_all_active_tokens() replaces old tokens.
    3. Student scans QR          →  their app reads the token embedded in the QR image.
    4. Student marks attendance  →  backend validates token is current before GPS check.
"""

from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, func
from sqlalchemy.orm import relationship

from app.db.session import Base


class QRToken(Base):
    __tablename__ = "qr_tokens"

    id = Column(Integer, primary_key=True, index=True)

    # The session this token belongs to (one active token per session at a time)
    session_id = Column(
        Integer,
        ForeignKey("attendance_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # The secret value embedded in the QR code image.
    # Generated as a UUID4 hex string — unpredictable and unique each rotation.
    token = Column(String(64), nullable=False, unique=True, index=True)

    # When this specific token was created (used to display "refreshes in Xs" on frontend)
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # When this token expires.  Set to created_at + QR_TOKEN_LIFETIME_SECONDS.
    # The scheduler will replace it before this time, but we keep the field
    # so the validation layer can double-check even if the scheduler was briefly slow.
    expires_at = Column(DateTime(timezone=True), nullable=False)

    # Relationship back to the session (useful for joins / reports)
    session = relationship("AttendanceSession", back_populates="qr_token")
