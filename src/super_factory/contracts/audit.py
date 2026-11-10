"""Audit contract: durable correlation of issue / repository / workflow runs."""

from pydantic import BaseModel, ConfigDict, Field, field_validator


class WorkflowRunCorrelation(BaseModel):
    """One audit line: what event touched which issue and which run processed it.

    - Blocked candidates are audited without a workflow run
      (``workflow_id``/``workflow_run_id`` are ``None``, ``workflow_state`` is
      ``"-"``).
    - Selected candidates are audited by ``IssueWorkflow`` itself, which links
      the run identifiers (see ADR-0006). ``blocking_reasons`` entries are the
      stable ``"code: detail"`` strings; ``"-"`` marks approved decisions.
    """

    model_config = ConfigDict(frozen=True)

    recorded_at: str = Field(min_length=1)
    event_delivery_id: str = Field(min_length=1)
    event_action: str = Field(min_length=1)
    event_type: str = Field(min_length=1)
    issue_id: str = Field(min_length=1)
    repository: str = Field(min_length=1)
    selection_outcome: str = Field(min_length=1)
    workflow_state: str = Field(min_length=1)
    blocking_reasons: tuple[str, ...]
    workflow_id: str | None = None
    workflow_run_id: str | None = None

    @field_validator(
        "recorded_at",
        "event_delivery_id",
        "event_action",
        "event_type",
        "issue_id",
        "repository",
        "selection_outcome",
        "workflow_state",
    )
    @classmethod
    def _check_non_blank(cls, value: str) -> str:
        if not value.strip():
            msg = "value must not be blank"
            raise ValueError(msg)
        return value

    @field_validator("blocking_reasons")
    @classmethod
    def _check_reasons(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        for reason in value:
            if not reason.strip():
                msg = "blocking_reasons entries must not be blank"
                raise ValueError(msg)
        return value
