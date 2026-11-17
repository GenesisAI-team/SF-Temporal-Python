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


def test_h2_pipeline_settings_defaults() -> None:
    settings = _clean_settings()
    assert settings.factory_pipeline_enabled is False
    assert settings.factory_workspace_root == Path("var/factory/workspaces")
    assert settings.factory_run_ledger_path == Path("var/audit/runs.jsonl")
    assert settings.factory_budget_runs_per_issue == 2
    assert settings.factory_task_spec_path == ""
    assert settings.factory_sandbox_image == "python:3.12-slim"
    assert settings.factory_sandbox_cpu == 1.0
    assert settings.factory_sandbox_memory == "2g"
    assert settings.factory_sandbox_command_timeout_seconds == 600
    assert settings.factory_base_branch == "main"
    assert (
        settings.factory_linear_issue_url_template
        == "https://linear.app/genesisnavarra/issue/{issue_id}"
    )


def test_h2_pipeline_settings_env_overrides(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("SF_FACTORY_PIPELINE_ENABLED", "true")
    monkeypatch.setenv("SF_FACTORY_WORKSPACE_ROOT", "out/ws")
    monkeypatch.setenv("SF_FACTORY_RUN_LEDGER_PATH", "out/runs.jsonl")
    monkeypatch.setenv("SF_FACTORY_BUDGET_RUNS_PER_ISSUE", "5")
    monkeypatch.setenv("SF_FACTORY_TASK_SPEC_PATH", "/env/spec.json")
    monkeypatch.setenv("SF_FACTORY_SANDBOX_IMAGE", "ghcr.io/genesis/sandbox-codex:0.1")
    monkeypatch.setenv("SF_FACTORY_SANDBOX_CPU", "2.0")
    monkeypatch.setenv("SF_FACTORY_SANDBOX_MEMORY", "4g")
    monkeypatch.setenv("SF_FACTORY_SANDBOX_COMMAND_TIMEOUT_SECONDS", "900")
    monkeypatch.setenv("SF_FACTORY_BASE_BRANCH", "develop")
    settings = _clean_settings()
    assert settings.factory_pipeline_enabled is True
    assert settings.factory_workspace_root == Path("out/ws")
    assert settings.factory_run_ledger_path == Path("out/runs.jsonl")
    assert settings.factory_budget_runs_per_issue == 5
    assert settings.factory_task_spec_path == "/env/spec.json"
    assert settings.factory_sandbox_image == "ghcr.io/genesis/sandbox-codex:0.1"
    assert settings.factory_sandbox_cpu == 2.0
    assert settings.factory_sandbox_memory == "4g"
    assert settings.factory_sandbox_command_timeout_seconds == 900
    assert settings.factory_base_branch == "develop"


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
