"""
Application Entry Point
=======================
Sets up the FastAPI app with:
    - CORS middleware
    - API router (auth, sessions, attendance, qr)
    - APScheduler background job that rotates QR tokens every
      QR_ROTATION_INTERVAL_SECONDS (default: 30 seconds)

The scheduler is started on app startup and shut down cleanly on app shutdown
using FastAPI's lifespan context manager — this is the modern replacement for
the deprecated @app.on_event("startup") / @app.on_event("shutdown") pattern.
"""

from contextlib import asynccontextmanager

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import router
from app.core.config import settings
from app.db.session import engine, Base, SessionLocal

# Register all models with SQLAlchemy Base so create_all() picks them up
import app.models.user        # noqa: F401
import app.models.attendance  # noqa: F401
import app.models.qr          # noqa: F401
import app.models.course      # noqa: F401


def rotate_qr_tokens_job():
    """
    The function APScheduler calls on every tick.

    Opens its own database session (schedulers run outside the request/response
    cycle so we cannot use FastAPI's get_db() dependency here), calls the
    rotation service, then closes the session cleanly regardless of errors.

    Any exception is caught and printed rather than crashing the scheduler --
    a single failed rotation is acceptable; losing the scheduler is not.
    """
    from app.services.qr_service import rotate_all_active_tokens

    db = SessionLocal()
    try:
        count = rotate_all_active_tokens(db)
        if count:
            # Only log when there was something to rotate -- avoids log spam
            # when no sessions are active (e.g. nights / weekends)
            print(f"[QR Scheduler] Rotated tokens for {count} active session(s).")
    except Exception as exc:
        print(f"[QR Scheduler] ERROR during token rotation: {exc}")
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    FastAPI lifespan handler -- runs startup logic before yield,
    shutdown logic after yield.

    Startup:
        1. Create all database tables (dev-only; use Alembic in production).
        2. Start the APScheduler background scheduler.
        3. Register the QR rotation job to fire every QR_ROTATION_INTERVAL_SECONDS.

    Shutdown:
        1. Stop the scheduler gracefully (wait=False so it doesn't block shutdown
           by waiting for a running job to finish).
    """
    # -- Startup ---------------------------------------------------------------
    # Create tables -- replace with Alembic migrations for production
    Base.metadata.create_all(bind=engine)

    # Initialise the background scheduler
    scheduler = BackgroundScheduler(
        job_defaults={
            # If the scheduler misses a firing (e.g. server was briefly overloaded),
            # run it immediately on the next available slot rather than queuing up
            # multiple missed firings.
            "misfire_grace_time": 10,
            "coalesce": True,
        }
    )

    # Register the QR rotation job as an interval job.
    # 'id' lets us reference or remove the job later if needed.
    scheduler.add_job(
        rotate_qr_tokens_job,
        trigger="interval",
        seconds=settings.QR_ROTATION_INTERVAL_SECONDS,
        id="qr_token_rotation",
        replace_existing=True,
    )

    scheduler.start()
    print(
        f"[QR Scheduler] Started. Rotating tokens every "
        f"{settings.QR_ROTATION_INTERVAL_SECONDS}s."
    )

    yield  # Application runs here

    # -- Shutdown --------------------------------------------------------------
    scheduler.shutdown(wait=False)
    print("[QR Scheduler] Stopped.")


# -- FastAPI app ---------------------------------------------------------------

app = FastAPI(
    title="Lesson Attendance Tracker",
    description=(
        "GPS + QR-based attendance system.\n\n"
        "**Verification layers (in order):**\n"
        "1. QR token -- student must scan the rotating code displayed by the lecturer\n"
        "2. Session expiry -- attendance window must still be open\n"
        "3. Duplicate guard -- one submission per student per session\n"
        "4. GPS radius -- student must be within the configured distance\n"
    ),
    version="1.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # TODO: tighten to your frontend domain before production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.get("/health", tags=["Health"])
def health_check():
    """Simple liveness check -- useful for Docker health checks and load balancers."""
    return {"status": "ok"}
