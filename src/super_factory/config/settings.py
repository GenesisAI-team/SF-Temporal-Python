"""Application configuration (pydantic-settings, SF_ env prefix)."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


def parse_selectable_states(csv_text: str) -> tuple[str, ...]:
    """Parse the comma-separated selectable Linear states into a tuple."""
    states = tuple(item.strip() for item in csv_text.split(",") if item.strip())
    if not states:
        msg = "linear selectable states must contain at least one entry"
        raise ValueError(msg)
    return states


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

    linear_target_repository: str = ""
    linear_selectable_states: str = "Todo,In Progress"
    linear_timestamp_tolerance_seconds: int = 60
    linear_dedupe_ttl_seconds: int = 86400
    audit_log_path: Path = Path("var/audit/events.jsonl")

    # H2 — PR production pipeline (GEN-47)
    factory_pipeline_enabled: bool = False
    factory_workspace_root: Path = Path("var/factory/workspaces")
    factory_run_ledger_path: Path = Path("var/audit/runs.jsonl")
    factory_budget_runs_per_issue: int = 2
    factory_task_spec_path: str = ""
    factory_sandbox_image: str = "python:3.12-slim"
    factory_sandbox_cpu: float = 1.0
    factory_sandbox_memory: str = "2g"
    factory_sandbox_command_timeout_seconds: int = 600
    factory_base_branch: str = "main"
    factory_linear_issue_url_template: str = (
        "https://linear.app/genesisnavarra/issue/{issue_id}"
    )


def get_settings() -> Settings:
    """Return application settings (reads environment at call time)."""
    return Settings()
