"""Temporal-boundary workflow I/O contracts (GEN-38 H1).

Plain frozen dataclasses: the Temporal SDK's default data converter
serializes dataclasses natively (temporalio 1.35), while the Pydantic
contracts above handle API-facing validation. One issue maps to exactly one
workflow execution (`issue-<GEN-N>`), so these types travel through:
endpoint → adapter → activity → workflow.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class IssueWorkflowInput:
    """Input of ``IssueWorkflow`` and of the selection activity."""

    issue_id: str
    repository: str
    issue_state: str
    labels: tuple[str, ...]
    title: str
    delivery_id: str
    event_action: str
    event_type: str
    selectable_states: tuple[str, ...]
    allowed_repositories: tuple[str, ...]


@dataclass(frozen=True)
class SelectIssueResult:
    """Output of the selection activity (reasons already formatted)."""

    approved: bool
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class IssueWorkflowResult:
    """Output of ``IssueWorkflow`` (H1 = selection only; agents come in H2)."""

    workflow_state: str
    issue_id: str
    repository: str
    blocking_reasons: tuple[str, ...]
