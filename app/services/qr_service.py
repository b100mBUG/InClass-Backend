"""
QR Service
==========
Handles everything related to QR token lifecycle:

    - generate_qr_for_session()   →  creates the first token when a session opens
    - rotate_all_active_tokens()  →  called by the scheduler every 30s; replaces all
                                     active-session tokens with fresh ones
    - get_current_qr_image()      →  builds a PNG QR code image from the current token
    - validate_qr_token()         →  checks a student-submitted token against the DB;
                                     returns True/False + a failure reason

Why rotate actively (scheduler) instead of lazily (on request)?
    Lazy rotation only refreshes when someone calls the endpoint.
    If the lecturer opens a session but nobody hits /qr for 5 minutes, the token
    is 5 minutes old — plenty of time to screenshot-share.
    Active rotation ensures the token is ALWAYS ≤ 30s old, regardless of traffic.
"""

import io
import uuid
from datetime import datetime, timedelta, timezone

import qrcode
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.attendance import AttendanceSession, SessionStatus
from app.models.qr import QRToken


# ── Internal helper ───────────────────────────────────────────────────────────

def _make_token() -> str:
    """Generate a cryptographically random token string (UUID4, no hyphens)."""
    return uuid.uuid4().hex  # 32-char lowercase hex, e.g. "a3f1b2c4d5e6..."


def _token_expiry() -> datetime:
    """Return the expiry datetime for a freshly minted token."""
    return datetime.now(timezone.utc) + timedelta(
        seconds=settings.QR_TOKEN_LIFETIME_SECONDS
    )


# ── Public API ────────────────────────────────────────────────────────────────

def generate_qr_for_session(db: Session, session_id: int) -> QRToken:
    """
    Create the FIRST QRToken for a newly opened session.
    Called once inside create_session() — the scheduler takes over from there.

    If a token already exists (e.g. session was re-activated), it is replaced.
    """
    # Remove any stale token that might exist (safety net)
    db.query(QRToken).filter(QRToken.session_id == session_id).delete()

    token = QRToken(
        session_id=session_id,
        token=_make_token(),
        expires_at=_token_expiry(),
    )
    db.add(token)
    db.commit()
    db.refresh(token)
    return token


def rotate_all_active_tokens(db: Session) -> int:
    """
    Replace QR tokens for every currently ACTIVE session.
    Called by APScheduler every QR_ROTATION_INTERVAL_SECONDS (default 30s).

    Returns the number of sessions whose tokens were rotated — useful for logs.

    Strategy:
        1. Find all active sessions that have an existing QR token.
        2. Delete the old token.
        3. Insert a fresh token.
        Done in a single transaction per session to avoid a window where
        the session has NO valid token.
    """
    # Fetch all active sessions that have a QR token record
    active_sessions = (
        db.query(AttendanceSession)
        .filter(AttendanceSession.status == SessionStatus.active)
        .all()
    )

    rotated = 0
    for session in active_sessions:
        # Delete the existing token for this session (if any)
        db.query(QRToken).filter(QRToken.session_id == session.id).delete()

        # Insert a brand-new token
        new_token = QRToken(
            session_id=session.id,
            token=_make_token(),
            expires_at=_token_expiry(),
        )
        db.add(new_token)
        rotated += 1

    db.commit()
    return rotated


def get_current_qr_image(db: Session, session_id: int) -> tuple[bytes, str]:
    """
    Return (png_bytes, current_token_string) for the given session.

    The PNG is generated on-the-fly from the current token — we never store
    images in the database, only the token string.

    The token string is also returned so the frontend can display metadata
    (e.g. "token refreshes in Xs") without decoding the image.

    Raises ValueError if no active token exists for this session.
    """
    qr_record = (
        db.query(QRToken)
        .filter(QRToken.session_id == session_id)
        .first()
    )

    if not qr_record:
        raise ValueError(f"No QR token found for session {session_id}. "
                         "The session may be expired or not yet started.")

    # Build the QR code image in memory (no disk I/O)
    # The data embedded in the QR is just the raw token string.
    # The mobile app reads this string and includes it in the mark-attendance request.
    qr = qrcode.QRCode(
        version=1,                          # smallest QR size; upgrade if token grows
        error_correction=qrcode.constants.ERROR_CORRECT_M,  # ~15% error tolerance
        box_size=10,
        border=4,
    )
    qr.add_data(qr_record.token)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")

    # Write PNG bytes to an in-memory buffer
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)

    return buffer.read(), qr_record.token


def validate_qr_token(db: Session, session_id: int, submitted_token: str) -> tuple[bool, str]:
    """
    Validate a token submitted by a student during mark-attendance.

    Returns:
        (True, "")                          — token is valid
        (False, "human-readable reason")    — token is invalid

    Checks performed (in order):
        1. Does a token record exist for this session?
        2. Does the submitted token match the stored token?   (timing-safe via ==)
        3. Has the token expired?  (belt-and-suspenders — scheduler should have
           already replaced it, but we guard against scheduler lag)
    """
    qr_record = (
        db.query(QRToken)
        .filter(QRToken.session_id == session_id)
        .first()
    )

    # Check 1 — token record must exist
    if not qr_record:
        return False, "No active QR token found for this session."

    # Check 2 — submitted token must exactly match stored token
    if qr_record.token != submitted_token:
        return False, (
            "Invalid QR token. The code may have rotated — please scan again."
        )

    # Check 3 — belt-and-suspenders expiry check
    now = datetime.now(timezone.utc)
    token_expiry = qr_record.expires_at

    # Make token_expiry timezone-aware if it came back naive from SQLite
    if token_expiry.tzinfo is None:
        token_expiry = token_expiry.replace(tzinfo=timezone.utc)

    if now > token_expiry:
        return False, (
            "QR token has expired. Please scan the latest code shown on screen."
        )

    return True, ""
