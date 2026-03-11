from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str = "sqlite:///./attendance.db"
    SECRET_KEY: str = "dev-secret-key-change-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    # Attendance validation
    MAX_DISTANCE_METERS: float = 50.0       # Max allowed distance from lecturer
    SESSION_WINDOW_MINUTES: int = 15        # How long students can mark attendance after session starts

    class Config:
        env_file = ".env"


settings = Settings()
