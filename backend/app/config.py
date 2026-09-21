"""Application settings loaded from environment / .env file."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central configuration. All values can be overridden via env vars."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "VoxReady API"
    database_url: str = "sqlite+aiosqlite:///./voxready.db"

    # Auth
    dev_auth: bool = False
    dev_auth_secret: str = "dev-secret-change-me"
    dev_token_ttl_hours: int = 8
    jwks_url: str | None = None
    jwt_issuer: str | None = None
    jwt_audience: str | None = None

    # CORS
    cors_origins: str = "http://localhost:3000"

    # Storage of recordings
    storage_dir: str = "./storage"
    upload_signing_secret: str = "upload-secret-change-me"
    upload_url_ttl_minutes: int = 15
    read_url_ttl_minutes: int = 60
    max_upload_size_bytes: int = 500 * 1024 * 1024

    # Outgoing webhooks
    webhook_endpoints: str = ""  # comma-separated list of HTTPS URLs
    webhook_secret: str = "webhook-secret-change-me"
    webhook_max_retries: int = 3

    # Background processing
    analysis_step_seconds: float = 0.5
    analysis_estimated_seconds: int = 30
    retention_job_interval_seconds: float = 86400.0
    enable_analysis_worker: bool = True
    enable_retention_job: bool = True

    # Labeling sampling (~10% random review)
    labeling_random_sample_rate: int = 10

    @property
    def webhook_endpoint_list(self) -> list[str]:
        return [e.strip() for e in self.webhook_endpoints.split(",") if e.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
