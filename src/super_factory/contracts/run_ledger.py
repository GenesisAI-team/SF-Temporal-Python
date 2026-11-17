"""Run-ledger contracts (GEN-47): durable per-issue run bookkeeping."""

from pydantic import BaseModel, ConfigDict, Field, field_validator

from super_factory.domain.pipeline import is_valid_run_key
from super_factory.domain.repository_spec import is_valid_repository
from super_factory.domain.task_spec import all_non_empty, is_valid_issue_id


class PipelineRunRecord(BaseModel):
    """One recorded pipeline run (idempotent per ``run_key``)."""

    model_config = ConfigDict(frozen=True)

    run_key: str
    issue_id: str
    spec_version: int = Field(ge=1)
    repository: str
    branch_name: str = Field(min_length=1)
    recorded_at: str = Field(min_length=1)
    outcome: str = Field(min_length=1)
    pr_url: str = ""

    @field_validator("run_key")
    @classmethod
    def _check_run_key(cls, value: str) -> str:
        if not is_valid_run_key(value):
            msg = f"run_key {value!r} must match GEN-N-vM"
            raise ValueError(msg)
        return value

    @field_validator("issue_id")
    @classmethod
    def _check_issue_id(cls, value: str) -> str:
        if not is_valid_issue_id(value):
            msg = f"issue_id {value!r} must match the GEN-N format"
            raise ValueError(msg)
        return value

    @field_validator("repository")
    @classmethod
    def _check_repository(cls, value: str) -> str:
        if not is_valid_repository(value):
            msg = f"repository {value!r} must be in the form owner/name"
            raise ValueError(msg)
        return value

    @field_validator("branch_name")
    @classmethod
    def _check_branch_name(cls, value: str) -> str:
        if not value.strip():
            msg = "branch_name must not be blank"
            raise ValueError(msg)
        return value

    @field_validator("outcome")
    @classmethod
    def _check_outcome(cls, value: str) -> str:
        if not all_non_empty([value]):
            msg = "outcome must not be blank"
            raise ValueError(msg)
        return value
