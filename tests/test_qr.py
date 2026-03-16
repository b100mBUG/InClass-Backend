"""
QR Service Tests
================
Tests for token generation, rotation, image creation, and validation.

These tests use an in-memory SQLite database so they are fast, isolated,
and require no external services.  Each test gets a fresh DB via the
`db` fixture — no shared state between tests.
"""

import pytest
from datetime import datetime, timedelta, timezone
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.session import Base
from app.models.user import User, UserRole
from app.models.attendance import AttendanceSession, SessionStatus
from app.models.qr import QRToken  # noqa: F401 — must import to register with Base
from app.services.qr_service import (
    generate_qr_for_session,
    rotate_all_active_tokens,
    get_current_qr_image,
    validate_qr_token,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def db():
    """
    Provide a fresh in-memory SQLite session for each test.
    All tables are created before the test and dropped after.
    """
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    SessionFactory = sessionmaker(bind=engine)
    session = SessionFactory()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)


@pytest.fixture
def lecturer(db):
    """Create and persist a lecturer user."""
    user = User(
        full_name="Dr. Test",
        email="lecturer@test.com",
        hashed_password="hashed",
        role=UserRole.lecturer,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def active_session(db, lecturer):
    """Create and persist an active attendance session."""
    session = AttendanceSession(
        title="Test Lecture",
        course_code="CS101",
        lecturer_latitude=-0.3031,
        lecturer_longitude=36.0800,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=30),
        status=SessionStatus.active,
        lecturer_id=lecturer.id,
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


# ── Token Generation ──────────────────────────────────────────────────────────

class TestGenerateQrForSession:
    def test_creates_token_record(self, db, active_session):
        """A QRToken row should exist after generation."""
        token = generate_qr_for_session(db, active_session.id)
        assert token is not None
        assert token.session_id == active_session.id

    def test_token_is_32_char_hex(self, db, active_session):
        """Token must be a 32-character hex string (UUID4 without hyphens)."""
        token = generate_qr_for_session(db, active_session.id)
        assert len(token.token) == 32
        # All characters must be valid hex
        int(token.token, 16)

    def test_token_has_future_expiry(self, db, active_session):
        """Token expiry must be in the future."""
        token = generate_qr_for_session(db, active_session.id)
        expiry = token.expires_at
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=timezone.utc)
        assert expiry > datetime.now(timezone.utc)

    def test_regenerate_replaces_old_token(self, db, active_session):
        """Calling generate twice should replace the old token, not duplicate it."""
        first = generate_qr_for_session(db, active_session.id)
        second = generate_qr_for_session(db, active_session.id)

        # Only one token should exist in the DB for this session
        count = db.query(QRToken).filter(QRToken.session_id == active_session.id).count()
        assert count == 1

        # The stored token must be the second one
        assert second.token != first.token


# ── Token Rotation ────────────────────────────────────────────────────────────

class TestRotateAllActiveTokens:
    def test_rotates_active_sessions(self, db, active_session):
        """rotate_all_active_tokens should replace the token for active sessions."""
        original = generate_qr_for_session(db, active_session.id)
        original_value = original.token

        count = rotate_all_active_tokens(db)
        assert count == 1

        # Token in DB should now be different
        new_record = db.query(QRToken).filter(
            QRToken.session_id == active_session.id
        ).first()
        assert new_record.token != original_value

    def test_does_not_rotate_expired_sessions(self, db, lecturer):
        """Expired sessions should not get new tokens."""
        expired_session = AttendanceSession(
            title="Old Lecture",
            course_code="CS101",
            lecturer_latitude=-0.3031,
            lecturer_longitude=36.0800,
            expires_at=datetime.now(timezone.utc) - timedelta(minutes=5),
            status=SessionStatus.expired,
            lecturer_id=lecturer.id,
        )
        db.add(expired_session)
        db.commit()

        count = rotate_all_active_tokens(db)
        assert count == 0

    def test_returns_zero_when_no_active_sessions(self, db):
        """Should return 0 when there are no active sessions."""
        count = rotate_all_active_tokens(db)
        assert count == 0


# ── QR Image Generation ───────────────────────────────────────────────────────

class TestGetCurrentQrImage:
    def test_returns_png_bytes(self, db, active_session):
        """Should return valid PNG bytes (PNG header: \\x89PNG)."""
        generate_qr_for_session(db, active_session.id)
        png_bytes, token_str = get_current_qr_image(db, active_session.id)

        # PNG files always start with this 8-byte signature
        assert png_bytes[:4] == b'\x89PNG'
        assert len(token_str) == 32

    def test_raises_when_no_token(self, db, active_session):
        """Should raise ValueError if no token exists yet for the session."""
        with pytest.raises(ValueError):
            get_current_qr_image(db, active_session.id)


# ── Token Validation ──────────────────────────────────────────────────────────

class TestValidateQrToken:
    def test_valid_token_passes(self, db, active_session):
        """A freshly generated token should validate successfully."""
        qr = generate_qr_for_session(db, active_session.id)
        valid, reason = validate_qr_token(db, active_session.id, qr.token)
        assert valid is True
        assert reason == ""

    def test_wrong_token_fails(self, db, active_session):
        """Submitting a wrong token should fail with a descriptive reason."""
        generate_qr_for_session(db, active_session.id)
        valid, reason = validate_qr_token(db, active_session.id, "wrongtoken" * 3)
        assert valid is False
        assert "Invalid QR token" in reason

    def test_expired_token_fails(self, db, active_session):
        """A token whose expiry is in the past should be rejected."""
        qr = generate_qr_for_session(db, active_session.id)

        # Manually backdate the expiry to simulate an expired token
        qr.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        db.commit()

        valid, reason = validate_qr_token(db, active_session.id, qr.token)
        assert valid is False
        assert "expired" in reason.lower()

    def test_missing_token_record_fails(self, db, active_session):
        """If no QR token exists for the session at all, validation must fail."""
        valid, reason = validate_qr_token(db, active_session.id, "anytoken")
        assert valid is False
        assert "No active QR token" in reason
