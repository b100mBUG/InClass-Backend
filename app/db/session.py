from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

from app.core.config import settings

# Render gives DATABASE_URL as postgres:// but SQLAlchemy requires postgresql://
# This fixes it transparently — no manual env var editing needed.
_db_url = settings.DATABASE_URL
if _db_url.startswith("postgres://"):
    _db_url = _db_url.replace("postgres://", "postgresql://", 1)

engine = create_engine(
    _db_url,
    # connect_args only needed for SQLite — Postgres doesn't use check_same_thread
    connect_args={"check_same_thread": False} if "sqlite" in _db_url else {},
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
