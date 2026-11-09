"""IssueWorkflow: durable issue selection for the Software Factory (H1).

One Linear approved issue ⇒ exactly one workflow execution (id
``issue-<GEN-N>``, reuse policy rejects duplicates). The workflow only
orchestrates: it runs the selection activity and the audit activity, updates
its memo for traceability, and returns the decision. No coding agents are
scheduled here yet — that is H2 (see ADR-0006).
"""

from datetime import timedelta

from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    from super_factory.contracts.workflow_io import (
        IssueWorkflowInput,
        IssueWorkflowResult,
    )
    from super_factory.contracts.workflow_state import IssueWorkflowState
    from super_factory.temporal.activities.audit import (
        RecordAuditInput,
        record_audit_activity,
    )
    from super_factory.temporal.activities.selection import select_issue_activity
    from temporalio.common import RetryPolicy

_DECISION_RETENTION = timedelta(seconds=10)
_AUDIT_RETENTION = timedelta(seconds=30)

_DECISION_RETRIES = RetryPolicy(
    maximum_attempts=3,
    initial_interval=timedelta(seconds=1),
    backoff_coefficient=2.0,
)
_AUDIT_RETRIES = RetryPolicy(
    maximum_attempts=5,
    initial_interval=timedelta(seconds=1),
    backoff_coefficient=2.0,
)


@workflow.defn(name="IssueWorkflow")
class IssueWorkflow:
    """Durable, resumable selection pipeline for one approved issue."""

    @workflow.run
    async def run(self, data: IssueWorkflowInput) -> IssueWorkflowResult:
        workflow_id = workflow.info().workflow_id
        workflow_run_id = workflow.info().run_id
        check = await workflow.execute_activity(
            select_issue_activity,
            data,
            start_to_close_timeout=_DECISION_RETENTION,
            retry_policy=_DECISION_RETRIES,
        )
        workflow_state = (
            IssueWorkflowState.READY if check.approved else IssueWorkflowState.BLOCKED
        )
        await workflow.execute_activity(
            record_audit_activity,
            RecordAuditInput(
                delivery_id=data.delivery_id,
                event_action=data.event_action,
                event_type=data.event_type,
                issue_id=data.issue_id,
                repository=data.repository,
                workflow_id=workflow_id,
                workflow_run_id=workflow_run_id,
                selection_outcome="SELECTED" if check.approved else "BLOCKED",
                workflow_state=workflow_state.value,
                blocking_reasons=check.reasons,
            ),
            start_to_close_timeout=_AUDIT_RETENTION,
            retry_policy=_AUDIT_RETRIES,
        )
        workflow.upsert_memo(
            {
                "issue_id": data.issue_id,
                "repository": data.repository,
                "linear_delivery_id": data.delivery_id,
                "workflow_state": workflow_state.value,
                "blocking_reasons": "; ".join(check.reasons),
            }
        )
        return IssueWorkflowResult(
            workflow_state=workflow_state.value,
            issue_id=data.issue_id,
            repository=data.repository,
            blocking_reasons=check.reasons,
        )
