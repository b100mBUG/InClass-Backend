from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import router
from app.db.session import engine, Base

# Auto-create tables (use Alembic migrations for production)
import app.models.user       # noqa: F401 — register models with Base
import app.models.attendance  # noqa: F401

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Lesson Attendance Tracker",
    description="GPS-based attendance system for lecturers and students.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # Tighten this for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.get("/health", tags=["Health"])
def health_check():
    return {"status": "ok"}
