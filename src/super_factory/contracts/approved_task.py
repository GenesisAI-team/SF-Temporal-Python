"""Contract for an approved, versioned task specification (Pydantic)."""

from pydantic import BaseModel, ConfigDict, Field, field_validator

from super_factory.domain.task_spec import all_non_empty, is_non_empty, is_valid_issue_id


class ApprovedTaskSpec(BaseModel):
    """Immutable, approved specification of a task (source: Linear GEN-N).

    This is the contract the future IssueWorkflow will consume. It carries the
    human-approved version so agents can detect spec drift later (H3).
    """

    model_config = ConfigDict(frozen=True)

    issue_id: str
    spec_version: int = Field(ge=1)
    repository: str
    base_branch: str = "main"
    objective: str
    acceptance_criteria: list[str]
    dependencies: list[str] = Field(default_factory=list)
    exclusions: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)

    @field_validator("issue_id")
    @classmethod
    def _check_issue_id(cls, value: str) -> str:
        if not is_valid_issue_id(value):
            msg = "issue_id must match the GEN-N format"
            raise ValueError(msg)
        return value

    @field_validator("repository")
    @classmethod
    def _check_repository(cls, value: str) -> str:
        parts = value.split("/")
        if len(parts) != 2 or not all(p.strip() for p in parts):
            msg = "repository must be in the form owner/name"
            raise ValueError(msg)
        return value

    @field_validator("objective")
    @classmethod
    def _check_objective(cls, value: str) -> str:
        if not is_non_empty(value):
            msg = "objective must not be blank"
            raise ValueError(msg)
        return value

    @field_validator("acceptance_criteria")
    @classmethod
    def _check_acceptance_criteria(cls, value: list[str]) -> list[str]:
        if not value or not all_non_empty(value):
            msg = "acceptance_criteria must be a non-empty list of non-blank strings"
            raise ValueError(msg)
        return value

    @field_validator("exclusions", "constraints")
    @classmethod
    def _check_non_blank_lists(cls, value: list[str]) -> list[str]:
        if not all_non_empty(value):
            msg = "list items must not be blank"
            raise ValueError(msg)
        return value

    @field_validator("dependencies")
    @classmethod
    def _check_dependencies(cls, value: list[str]) -> list[str]:
        for dep in value:
            if not is_valid_issue_id(dep):
                msg = f"dependency {dep!r} must match the GEN-N format"
                raise ValueError(msg)
        return value
