"""
Central configuration for CostGuard AI.

Everything that can vary between environments (local Docker, free-tier
cloud hosting, CI) is read from environment variables so the same image
runs everywhere with no code changes. Defaults match the docker-compose
setup so `docker compose up` works with zero manual config.
"""

from functools import lru_cache
from typing import Literal, ClassVar
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    BASE_DIR: ClassVar[Path] = Path(__file__).resolve().parents[3]

    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )
    # --- App ---
    APP_NAME: str = "CostGuard AI"
    ENV: Literal["development", "production", "test"] = "development"
    API_V1_PREFIX: str = "/api/v1"

    # --- Security / Auth ---
    JWT_SECRET_KEY: str = "change-me-in-production-this-is-not-secure"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24 hours

    # --- Database (Postgres) ---
    # Preferred: set DATABASE_URL_OVERRIDE directly (e.g. your Neon
    # connection string). If left blank, the URL is built from the
    # individual POSTGRES_* fields below instead - this is what lets the
    # bundled docker-compose Postgres container keep working with zero
    # config changes.
    DATABASE_URL_OVERRIDE: str = ""
    POSTGRES_HOST: str = "postgres"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str = "costguard"
    POSTGRES_USER: str = "costguard"
    POSTGRES_PASSWORD: str = "costguard_password"

    @property
    def DATABASE_URL(self) -> str:
        if self.DATABASE_URL_OVERRIDE:
            return self.DATABASE_URL_OVERRIDE
        return (
            f"postgresql+psycopg2://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    # --- Redis ---
    # Preferred: set REDIS_URL_OVERRIDE directly (e.g. your Upstash
    # connection string, which starts with rediss:// for TLS). If left
    # blank, the URL is built from the individual REDIS_* fields below
    # instead, for the bundled docker-compose Redis container.
    REDIS_URL_OVERRIDE: str = ""
    REDIS_HOST: str = "redis"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    REDIS_TTL_SECONDS: int = 3600  # 1-hour cache TTL per spec

    @property
    def REDIS_URL(self) -> str:
        if self.REDIS_URL_OVERRIDE:
            return self.REDIS_URL_OVERRIDE
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"

    # --- LLM provider (free tier). "groq", "gemini", "auto", or "none" (stub mode) ---
    LLM_PROVIDER: Literal["groq", "gemini", "auto", "none"] = "auto"
    GROQ_API_KEY: str = ""
    GROQ_MODEL: str = "llama-3.1-70b-versatile"
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-1.5-flash"

    # --- Embeddings for RAG ---
    EMBEDDING_MODEL: str = "all-MiniLM-L6-v2"  # free, local sentence-transformers model

    # --- File storage ---
    UPLOAD_DIR: str = "/app/data/uploads"
    FAISS_INDEX_DIR: str = "/app/data/faiss_index"

    # --- Rate limiting on LLM endpoints ---
    LLM_RATE_LIMIT_PER_MINUTE: int = 20

    # --- Nightly job schedule (cron-style hour, 0-23, UTC) ---
    NIGHTLY_JOB_HOUR: int = 2

    # --- Drift detection thresholds ---
    PSI_DRIFT_THRESHOLD: float = 0.2
    KS_PVALUE_THRESHOLD: float = 0.05
    MAPE_DEGRADATION_THRESHOLD_PCT: float = 15.0


@lru_cache
def get_settings() -> Settings:
    return Settings()