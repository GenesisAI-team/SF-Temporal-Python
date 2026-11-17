"""Process-execution port: the single gateway for external commands (GEN-47).

Every adapter that shells out (subprocess runner, docker, git, gh) goes
through ``CommandRunner`` so tests substitute scripted fakes and production
has exactly one real implementation. Long payloads (agent prompts) travel
via ``stdin``, never argv, so the safety guard scans control text only.
"""

from collections.abc import Mapping
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator


class CommandRequest(BaseModel):
    """One external command to launch (argv, no shell)."""

    model_config = ConfigDict(frozen=True)

    argv: tuple[str, ...] = Field(min_length=1)
    cwd: str | None = None
    env: Mapping[str, str] | None = None
    timeout_seconds: float = Field(default=120.0, gt=0)
    stdin: str | None = None

    @field_validator("argv")
    @classmethod
    def _check_argv(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if any(not item.strip() for item in value):
            msg = "argv items must not be blank"
            raise ValueError(msg)
        return value

    @field_validator("cwd")
    @classmethod
    def _check_cwd(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            msg = "cwd must be blank-free when provided"
            raise ValueError(msg)
        return value


class CommandOutcome(BaseModel):
    """Outcome of one external command (bounded output tails)."""

    model_config = ConfigDict(frozen=True)

    exit_code: int | None
    stdout_tail: str = ""
    stderr_tail: str = ""
    timed_out: bool = False


class ProcessLaunchError(RuntimeError):
    """The command binary could not be launched (missing/permission)."""


class CommandRunner(Protocol):
    """Port for launching external commands."""

    async def run(self, request: CommandRequest) -> CommandOutcome:
        """Run one command and return its bounded outcome."""
        ...
