"""Application configuration loaded from environment / .env file."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Gemini Flash
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.0-flash"

    # Auth
    jwt_secret: str = "change-me"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7

    # Database
    database_url: str = "sqlite:///./imdb.db"

    # Pipeline
    confidence_threshold: float = 0.7
    off_api_base: str = "https://world.openfoodfacts.org"
    gemini_timeout_seconds: float = 60.0

    # CORS
    cors_origins: str = "http://localhost:3000,http://localhost:5173"

    # Runtime / ops
    environment: str = "development"  # "production" enforces stricter checks
    log_level: str = "INFO"
    api_prefix: str = "/api/v1"
    # Dev convenience: create tables on startup. In production set this False and
    # manage schema with Alembic (`alembic upgrade head`).
    auto_create_tables: bool = True

    # Upload limits / cost guards (each image is a paid VLM call)
    max_upload_files: int = 20
    max_upload_mb: int = 10
    allowed_image_types: str = "image/jpeg,image/png,image/webp"

    # Where scanned source images are stored (swap for S3/GCS later)
    upload_dir: str = "./uploads"

    # Auth rate limiting (login brute-force guard)
    login_max_attempts: int = 5
    login_window_seconds: int = 60

    # Pagination
    default_page_size: int = 50
    max_page_size: int = 200

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def allowed_image_type_set(self) -> set[str]:
        return {t.strip().lower() for t in self.allowed_image_types.split(",") if t.strip()}

    @property
    def is_production(self) -> bool:
        return self.environment.lower() in {"production", "prod"}

    @property
    def jwt_secret_is_default(self) -> bool:
        return self.jwt_secret in {"change-me", "change-me-to-a-long-random-string", ""}


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
