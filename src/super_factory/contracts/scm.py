"""SCM contracts (GEN-47): git workspaces and GitHub pull requests.

Pydantic frozen models (ADR-0003) for the SCM ports consumed by the
publication activity inside the worker process.
"""

from pydantic import BaseModel, ConfigDict, Field, field_validator


class WorkspaceStatus(BaseModel):
    """Workspace (branch checkout) ensured on disk before the agent run."""

    model_config = ConfigDict(frozen=True)

    path: str = Field(min_length=1)
    existed: bool
    branch_existed: bool

    @field_validator("path")
    @classmethod
    def _check_path(cls, value: str) -> str:
        if value != value.strip():
            msg = "path must be trimmed"
            raise ValueError(msg)
        return value


class CommitInfo(BaseModel):
    """Outcome of committing every pending change onto the factory branch."""

    model_config = ConfigDict(frozen=True)

    committed: bool
    sha: str = ""
    files_committed: int = Field(default=0, ge=0)
    detail: str = ""

    @field_validator("sha", "detail")
    @classmethod
    def _check_trimmed(cls, value: str) -> str:
        if value != value.strip():
            msg = "values must be trimmed"
            raise ValueError(msg)
        return value


class PushInfo(BaseModel):
    """Outcome of pushing the factory branch to the configured remote."""

    model_config = ConfigDict(frozen=True)

    pushed: bool
    detail: str = ""

    @field_validator("detail")
    @classmethod
    def _check_detail(cls, value: str) -> str:
        if value != value.strip():
            msg = "values must be trimmed"
            raise ValueError(msg)
        return value


class PullRequestRef(BaseModel):
    """Reference of a real (existing or newly created) GitHub pull request."""

    model_config = ConfigDict(frozen=True)

    number: int = Field(ge=1)
    url: str = Field(min_length=1)
    head_branch: str = Field(min_length=1)
    base_branch: str = Field(min_length=1)

    @field_validator("url", "head_branch", "base_branch")
    @classmethod
    def _check_trimmed(cls, value: str) -> str:
        if value != value.strip():
            msg = "values must be trimmed"
            raise ValueError(msg)
        return value

