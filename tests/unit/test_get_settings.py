"""Tests for the settings accessor."""

from super_factory.config.settings import get_settings


def test_get_settings_reads_current_environment(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("SF_ENV", "ci")
    settings = get_settings()
    assert settings.env == "ci"


def test_get_settings_returns_settings_instance() -> None:
    assert type(get_settings()).__name__ == "Settings"
