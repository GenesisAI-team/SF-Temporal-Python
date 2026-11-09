"""Selection activity: apply the pure selector inside the workflow run (H1).

No I/O — applying criteria is a plain computation, registered as an activity
so the decision outcome becomes part of Temporal history (durable and
deterministic on replay).
"""

from temporalio import activity

from super_factory.contracts.workflow_io import IssueWorkflowInput, SelectIssueResult
from super_factory.domain.issue_selection import (
    BlockingReason,
    evaluate_issue_selection,
    format_blocking_reason,
)


def _format_reason(reason: BlockingReason) -> str:
    return format_blocking_reason(reason)


@activity.defn(name="select_issue_activity")
async def select_issue_activity(data: IssueWorkflowInput) -> SelectIssueResult:
    """Decide whether the candidate issue enters the factory; reasons formatted."""
    decision = evaluate_issue_selection(
        issue_id=data.issue_id,
        issue_state=data.issue_state,
        repository=data.repository,
        selectable_states=data.selectable_states,
        allowed_repositories=data.allowed_repositories,
    )
    return SelectIssueResult(
        approved=decision.approved,
        reasons=tuple(_format_reason(reason) for reason in decision.reasons),
    )
