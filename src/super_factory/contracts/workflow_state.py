"""Workflow state model for the future IssueWorkflow (documented, not executed)."""

from enum import StrEnum


class IssueWorkflowState(StrEnum):
    """States of the future IssueWorkflow (H1). Documented now, implemented later."""

    READY = "READY"
    PREPARING = "PREPARING"
    PLANNING = "PLANNING"
    IMPLEMENTING = "IMPLEMENTING"
    VERIFYING = "VERIFYING"
    REVIEWING = "REVIEWING"
    REPAIRING = "REPAIRING"
    PR_READY = "PR_READY"
    AWAITING_MERGE = "AWAITING_MERGE"
    DONE = "DONE"
    BLOCKED = "BLOCKED"
    CANCELLED = "CANCELLED"
