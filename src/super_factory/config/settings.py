"""Application configuration (pydantic-settings, SF_ env prefix)."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Typed application settings loaded from SF_* environment variables."""

    model_config = SettingsConfigDict(env_prefix="SF_", extra="ignore")

    env: str = "development"
    log_level: str = "info"

    temporal_address: str = "localhost:7233"
    temporal_namespace: str = "default"
    temporal_task_queue: str = "factory-orchestration"

    linear_webhook_secret: str = ""
    github_app_id: str = ""
    github_app_private_key_path: str = ""
    database_url: str = ""


def get_settings() -> Settings:
    """Return application settings (reads environment at call time)."""
    return Settings()
