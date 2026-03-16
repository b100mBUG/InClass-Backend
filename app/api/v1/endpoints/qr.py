"""
QR Endpoints
============
Exposes two endpoints related to QR code management:

    GET  /qr/{session_id}         — Lecturer fetches the current QR code image
                                    as a PNG stream. The frontend should poll this
                                    every QR_ROTATION_INTERVAL_SECONDS to always
                                    display a fresh code.

    GET  /qr/{session_id}/meta    — Returns token metadata in JSON (token string,
                                    created_at, expires_at) without the image.
                                    Useful for debugging or building a custom UI.

Access control:
    - Only the lecturer who owns the session can fetch its QR code.
    - Students never call these endpoints — they only scan and submit the token.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.core.security import require_lecturer
from app.models.qr import QRToken
from app.models.attendance import AttendanceSession, SessionStatus
from app.services.qr_service import get_current_qr_image

router = APIRouter(prefix="/qr", tags=["QR Codes (Lecturer)"])


@router.get(
    "/{session_id}",
    summary="Get current QR code image for a session",
    response_description="PNG image of the current rotating QR code",
    responses={
        200: {"content": {"image/png": {}}, "description": "QR code PNG"},
        403: {"description": "Not your session"},
        404: {"description": "Session not found"},
        410: {"description": "Session is not active"},
    },
)
def get_qr_image(
    session_id: int,
    db: Session = Depends(get_db),
    lecturer=Depends(require_lecturer),
):
    """
    Return the current QR code as a raw PNG image for the given session.

    The lecturer's frontend should call this endpoint on a timer matching
    QR_ROTATION_INTERVAL_SECONDS (e.g. every 30s) to always show the latest code.

    The QR image encodes only the token string. Students scan it and their app
    includes that token in the mark-attendance POST request.
    """
    # Fetch the session and verify it belongs to this lecturer
    session = db.query(AttendanceSession).filter(
        AttendanceSession.id == session_id
    ).first()

    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found.",
        )

    if session.lecturer_id != lecturer.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not own this session.",
        )

    # Only serve QR codes for active sessions — no point showing a QR for a
    # closed or expired session since students can't mark attendance anyway
    if session.status != SessionStatus.active:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail=f"Session is {session.status}. QR codes are only available for active sessions.",
        )

    # Generate the PNG image from the current token
    try:
        png_bytes, _ = get_current_qr_image(db, session_id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )

    # Return raw PNG bytes — the frontend renders this directly as an <img> tag
    return Response(content=png_bytes, media_type="image/png")


@router.get(
    "/{session_id}/meta",
    summary="Get QR token metadata (JSON)",
    tags=["QR Codes (Lecturer)"],
)
def get_qr_meta(
    session_id: int,
    db: Session = Depends(get_db),
    lecturer=Depends(require_lecturer),
):
    """
    Return the current token's metadata as JSON.

    Useful for:
        - Frontend countdown timers ("refreshes in Xs")
        - Debugging token rotation
        - Admin tools

    Does NOT return the token value itself in plain text for security —
    the token should only be read by scanning the QR image.
    """
    session = db.query(AttendanceSession).filter(
        AttendanceSession.id == session_id
    ).first()

    if not session:
        raise HTTPException(status_code=404, detail="Session not found.")

    if session.lecturer_id != lecturer.id:
        raise HTTPException(status_code=403, detail="You do not own this session.")

    qr_record = db.query(QRToken).filter(QRToken.session_id == session_id).first()

    if not qr_record:
        raise HTTPException(status_code=404, detail="No QR token found for this session.")

    return {
        "session_id": session_id,
        "created_at": qr_record.created_at,
        "expires_at": qr_record.expires_at,
        # We return a masked token hint (first 6 chars) so lecturers can verify
        # rotation is happening without exposing the full token in logs/responses
        "token_hint": qr_record.token[:6] + "...",
    }
