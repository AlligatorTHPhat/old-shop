from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Application settings, read from environment variables (and `.env` for local dev)."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # App
    PROJECT_NAME: str = "OldShop API"
    PROJECT_VERSION: str = "2.0.0"
    ENVIRONMENT: Literal["development", "test", "production"] = "development"
    DEBUG: bool = False
    API_V1_STR: str = "/api/v1"
    CORS_ORIGINS: Annotated[list[str], NoDecode] = ["http://localhost:4200", "http://127.0.0.1:4200"]

    # Logging
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: Literal["json", "text"] = "text"

    # Database: either a full DATABASE_URL or the DB_* parts
    DATABASE_URL: str = ""
    DB_HOST: str = "localhost"
    DB_PORT: int = 5432
    DB_USER: str = "postgres"
    DB_PASSWORD: str = ""
    DB_NAME: str = "oldshop"
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20

    # Auth
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    # Files
    MEDIA_DIR: Path = BACKEND_DIR / "media"
    MAX_UPLOAD_BYTES: int = 2 * 1024 * 1024

    # Mail (OTP). Leave SMTP_USER empty to disable sending.
    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 465
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""

    # PayPal
    PAYPAL_CLIENT_ID: str = ""
    PAYPAL_SECRET: str = ""
    PAYPAL_API_URL: str = "https://api-m.sandbox.paypal.com"
    USD_VND_RATE: int = 25400

    # Fraud detection model artifacts (fraud_model.joblib + scaler.joblib)
    FRAUD_MODEL_DIR: Path = BACKEND_DIR / "ml_artifacts"

    # Google Apps Script contact relay. Leave the URL empty to only store messages in the DB.
    GAS_WEBHOOK_URL: str = ""
    GAS_SHARED_SECRET: str = ""

    @model_validator(mode="before")
    @classmethod
    def _split_cors_origins(cls, data: dict) -> dict:
        origins = data.get("CORS_ORIGINS")
        if isinstance(origins, str):
            data["CORS_ORIGINS"] = [o.strip() for o in origins.split(",") if o.strip()]
        return data

    @model_validator(mode="after")
    def _build_database_url(self) -> "Settings":
        if not self.DATABASE_URL:
            self.DATABASE_URL = (
                f"postgresql+psycopg2://{self.DB_USER}:{self.DB_PASSWORD}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
            )
        elif self.DATABASE_URL.startswith("postgresql://"):
            # SQLAlchemy 2.1 maps the bare scheme to psycopg 3; we ship psycopg2.
            self.DATABASE_URL = self.DATABASE_URL.replace("postgresql://", "postgresql+psycopg2://", 1)
        return self

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
