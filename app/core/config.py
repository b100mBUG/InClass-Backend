from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str = "sqlite:///./attendance.db"
    SECRET_KEY: str = "dev-secret-key-change-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    # Attendance validation
    MAX_DISTANCE_METERS: float = 50.0       # Max allowed distance from lecturer
    SESSION_WINDOW_MINUTES: int = 120        # How long students can mark attendance after session starts

    # QR code rotation
    # QR_TOKEN_LIFETIME_SECONDS: how long a single token stays valid.
    # Set slightly longer than the rotation interval to tolerate scheduler lag —
    # e.g. if rotation runs every 30s, tokens live for 45s so there is always
    # a valid token even if the scheduler fires a few seconds late.
    QR_TOKEN_LIFETIME_SECONDS: int = 45

    # QR_ROTATION_INTERVAL_SECONDS: how often APScheduler replaces all tokens.
    # 30 seconds is aggressive enough to stop screenshot-sharing attacks while
    # still giving a student reasonable time to scan and submit.
    QR_ROTATION_INTERVAL_SECONDS: int = 30

    class Config:
        env_file = ".env"


settings = Settings()
