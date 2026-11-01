"""Tests for workflow state contract (TDD cycle C4)."""

from super_factory.contracts.workflow_state import IssueWorkflowState


def test_issue_workflow_state_values_are_stable() -> None:
    assert [s.value for s in IssueWorkflowState] == [
        "READY",
        "PREPARING",
        "PLANNING",
        "IMPLEMENTING",
        "VERIFYING",
        "REVIEWING",
        "REPAIRING",
        "PR_READY",
        "AWAITING_MERGE",
        "DONE",
        "BLOCKED",
        "CANCELLED",
    ]
