"""Tests for application settings (C1 - TDD cycle)."""

from super_factory.config.settings import Settings


def _clean_settings(**overrides: object) -> Settings:
    """Build Settings ignoring any .env file, for deterministic tests."""
    return Settings(_env_file=None, **overrides)  # type: ignore[arg-type]


def test_defaults_without_env() -> None:
    settings = _clean_settings()
    assert settings.env == "development"
    assert settings.log_level == "info"
    assert settings.temporal_address == "localhost:7233"
    assert settings.temporal_namespace == "default"
    assert settings.temporal_task_queue == "factory-orchestration"
    assert settings.linear_webhook_secret == ""
    assert settings.database_url == ""


def test_env_vars_override_defaults(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("SF_ENV", "testing")
    monkeypatch.setenv("SF_LOG_LEVEL", "debug")
    monkeypatch.setenv("SF_TEMPORAL_ADDRESS", "temporal:7233")
    monkeypatch.setenv("SF_LINEAR_WEBHOOK_SECRET", "top-secret")
    settings = _clean_settings()
    assert settings.env == "testing"
    assert settings.log_level == "debug"
    assert settings.temporal_address == "temporal:7233"
    assert settings.linear_webhook_secret == "top-secret"


def test_constructor_overrides_beat_env(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("SF_ENV", "testing")
    settings = _clean_settings(env="unit")
    assert settings.env == "unit"
