from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict
from sqlalchemy.engine import URL, make_url

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

    # Day 2 infrastructure contracts; clients/read routing are implemented on Days 3-6.
    PG_REPLICA_URL: str = ""
    PG_NODE_B_URL: str = ""  # future FDW site, intentionally unused in the one-host MVP
    MONGO_URI: str = ""
    MONGO_DB: str = "oldshop"
    STORAGE_BACKEND: Literal["local", "minio"] = "local"
    MINIO_ENDPOINT: str = "localhost:9000"
    MINIO_ACCESS_KEY: str = ""
    MINIO_SECRET_KEY: str = ""
    MINIO_SECURE: bool = False
    MINIO_BUCKET_PRODUCT_IMAGES: str = "product-images"
    MINIO_BUCKET_USER_AVATARS: str = "user-avatars"
    MINIO_BUCKET_ATTACHMENTS: str = "attachments"

    # ETL: one worker, at-least-once delivery; only metadata/read models use Mongo.
    ETL_POLL_SECONDS: int = 60
    ETL_BATCH_SIZE: int = 100
    ETL_MAX_ATTEMPTS: int = 5
    ETL_BACKOFF_SECONDS: int = 15

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
            self.DATABASE_URL = URL.create(
                "postgresql+psycopg2",
                username=self.DB_USER,
                password=self.DB_PASSWORD,
                host=self.DB_HOST,
                port=self.DB_PORT,
                database=self.DB_NAME,
            ).render_as_string(hide_password=False)
        else:
            url = make_url(self.DATABASE_URL)
            if url.drivername == "postgresql":
                url = url.set(drivername="postgresql+psycopg2")
            if url.drivername != "postgresql+psycopg2":
                raise ValueError("DATABASE_URL must use PostgreSQL with psycopg2")
            self.DATABASE_URL = url.render_as_string(hide_password=False)
            self.DB_HOST, self.DB_PORT = url.host or "", url.port or 5432
            self.DB_USER, self.DB_PASSWORD = url.username or "", url.password or ""
            if not url.database:
                raise ValueError("DATABASE_URL must identify a database")
            self.DB_NAME = url.database
        return self

    @property
    def database_connect_args(self) -> dict:
        url = make_url(self.DATABASE_URL)
        args = url.translate_connect_args(username="user", database="dbname")
        args.update(url.query)
        return args

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
