"""Sandbox contracts (GEN-47): spec, instance identity and command outcomes.

Pydantic frozen models (ADR-0003) used between activities/adapters inside
the worker process; never serialized on the Temporal history plane.

Security posture baked into defaults: network isolation on, no credential
passthrough (there is deliberately no env/secret field), bounded CPU/RAM
and per-command timeouts.
"""

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from super_factory.domain.pipeline import is_valid_run_key


class SandboxSpec(BaseModel):
    """Policy + workspace snapshot for one sandbox instance per run."""

    model_config = ConfigDict(frozen=True)

    run_key: str
    workspace_path: str = Field(min_length=1)
    image: str = "python:3.12-slim"
    cpu_limit: float = Field(default=1.0, gt=0)
    memory_limit: str = "2g"
    command_timeout_seconds: int = Field(default=600, gt=0)
    network_isolated: bool = True
    run_as_non_root: bool = True

    @field_validator("run_key")
    @classmethod
    def _check_run_key(cls, value: str) -> str:
        if not is_valid_run_key(value):
            msg = "run_key must match GEN-N-vM"
            raise ValueError(msg)
        return value

    @field_validator("memory_limit")
    @classmethod
    def _check_memory_limit(cls, value: str) -> str:
        v = value.strip()
        if not v or not v[:-1].isdigit() or v[-1] not in {"b", "k", "m", "g"}:
            msg = "memory_limit must look like docker -m sizes ('2g', '512m', ...)"
            raise ValueError(msg)
        return v

    @model_validator(mode="after")
    def _check_workspace_shape(self) -> "SandboxSpec":
        path = self.workspace_path.strip()
        if self.workspace_path != path or not path:
            msg = "workspace_path must be non-blank and trimmed"
            raise ValueError(msg)
        return self


class SandboxInstance(BaseModel):
    """Handle of a started sandbox (container name)."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(min_length=1)


class SandboxCommand(BaseModel):
    """A command to execute inside a running sandbox (argv, no shell).

    Long payloads (agent prompts) travel via ``stdin_payload`` so they are
    never part of the argv scanned by the safety guard.
    """

    model_config = ConfigDict(frozen=True)

    argv: tuple[str, ...] = Field(min_length=1)
    workdir: str = "/workspace"
    timeout_seconds: float = Field(default=600.0, gt=0)
    stdin_payload: str | None = None

    @field_validator("argv")
    @classmethod
    def _check_argv(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if any(not item.strip() for item in value):
            msg = "argv items must not be blank"
            raise ValueError(msg)
        return value


class SandboxCommandOutcome(BaseModel):
    """Outcome of one sandbox command (bounded output tail)."""

    model_config = ConfigDict(frozen=True)

    exit_code: int | None
    output_tail: str = ""
    timed_out: bool = False
