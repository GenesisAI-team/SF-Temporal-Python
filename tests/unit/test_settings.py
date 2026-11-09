"""Tests for application settings (C1 - TDD cycle)."""

from pathlib import Path

import pytest

from super_factory.config.settings import Settings, parse_selectable_states


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


def test_h1_webhook_settings_defaults() -> None:
    settings = _clean_settings()
    assert settings.linear_target_repository == ""
    assert settings.linear_selectable_states == "Todo,In Progress"
    assert settings.linear_timestamp_tolerance_seconds == 60
    assert settings.linear_dedupe_ttl_seconds == 86400
    assert settings.audit_log_path == Path("var/audit/events.jsonl")


def test_h1_webhook_settings_env_overrides(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("SF_LINEAR_TARGET_REPOSITORY", "GenesisAI-team/SF-Temporal-Python")
    monkeypatch.setenv("SF_LINEAR_SELECTABLE_STATES", "Todo")
    monkeypatch.setenv("SF_LINEAR_TIMESTAMP_TOLERANCE_SECONDS", "600")
    monkeypatch.setenv("SF_LINEAR_DEDUPE_TTL_SECONDS", "3600")
    monkeypatch.setenv("SF_AUDIT_LOG_PATH", "out/audit.jsonl")
    settings = _clean_settings()
    assert settings.linear_target_repository == "GenesisAI-team/SF-Temporal-Python"
    assert settings.linear_selectable_states == "Todo"
    assert settings.linear_timestamp_tolerance_seconds == 600
    assert settings.linear_dedupe_ttl_seconds == 3600
    assert settings.audit_log_path == Path("out/audit.jsonl")


def test_parse_selectable_states_trims_and_drops_blanks() -> None:
    assert parse_selectable_states("Todo, In Progress,") == ("Todo", "In Progress")
    assert parse_selectable_states("Done") == ("Done",)


@pytest.mark.parametrize("csv_text", ["", "   ", ",", " , "])
def test_parse_selectable_states_rejects_empty(csv_text: str) -> None:
    with pytest.raises(ValueError, match="selectable states"):
        parse_selectable_states(csv_text)
