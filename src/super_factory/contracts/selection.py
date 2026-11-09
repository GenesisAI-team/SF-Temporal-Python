"""Cross-layer selection contracts (GEN-38 H1).

- ``IssueSelectionCriteria``: rules that gate issue selection (built from
  ``SF_*`` settings by the application layer).
- ``IssueSnapshot``: single-issue view extracted from a verified Linear event.

The pure blocking decision (``evaluate_issue_selection`` results) lives in
``domain/``; its small immutable types are re-exported here so outer layers
only depend on ``contracts``.
"""

from pydantic import BaseModel, ConfigDict, Field, field_validator

from super_factory.domain.issue_selection import BlockingReason, IssueSelectionResult
from super_factory.domain.issue_selection import (
    format_blocking_reasons as format_blocking_reasons,
)
from super_factory.domain.repository_spec import is_valid_repository
from super_factory.domain.task_spec import is_non_empty

__all__ = [
    "BlockingReason",
    "IssueSelectionCriteria",
    "IssueSelectionResult",
    "IssueSnapshot",
    "format_blocking_reasons",
]


class IssueSelectionCriteria(BaseModel):
    """Rules that decide which approved Linear issues enter the factory."""

    model_config = ConfigDict(frozen=True)

    selectable_states: tuple[str, ...] = Field(min_length=1)
    allowed_repositories: tuple[str, ...]

    @field_validator("selectable_states")
    @classmethod
    def _check_selectable_states(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not all(is_non_empty(state) for state in value):
            msg = "selectable_states entries must not be blank"
            raise ValueError(msg)
        return value

    @field_validator("allowed_repositories")
    @classmethod
    def _check_allowed_repositories(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        for repository in value:
            if not is_valid_repository(repository):
                msg = f"allowed_repositories entry {repository!r} must be owner/name"
                raise ValueError(msg)
        return value


class IssueSnapshot(BaseModel):
    """Single-issue view parsed from a verified Linear event.

    Deliberately tolerant: unresolved states or foreign identifiers are valid
    data here — the pure selector in ``domain/`` blocks them with reasons so
    every rejection stays auditable.
    """

    model_config = ConfigDict(frozen=True)

    issue_id: str
    title: str
    state: str
    labels: tuple[str, ...]
