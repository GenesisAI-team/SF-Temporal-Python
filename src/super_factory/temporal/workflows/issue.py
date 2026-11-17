"""IssueWorkflow: durable selection + PR production (H1 + H2, GEN-47).

One Linear approved issue => exactly one workflow execution (id
``issue-<GEN-N>``, reuse policy rejects duplicates). Selection is audited as
in H1. When ``data.pipeline_enabled`` is set, the workflow continues into
the H2 PR-production pipeline (plan -> prepare -> agent -> verify ->
publish), advancing its memo state and leaving one audit line per phase.
Deterministic by construction: it only runs activities; every port/model
and the Temporal SDK stay behind them.
"""

from datetime import timedelta

from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    from temporalio.common import RetryPolicy

    from super_factory.contracts.pipeline import (
        AgentRunCommand,
        PlanRunCommand,
        PrepareRunCommand,
        PublishCommand,
        VerificationCommand,
    )
    from super_factory.contracts.workflow_io import (
        IssueWorkflowInput,
        IssueWorkflowResult,
    )
    from super_factory.contracts.workflow_state import IssueWorkflowState
    from super_factory.domain.pipeline import pipeline_audit_delivery_id
    from super_factory.temporal.activities.audit import (
        RecordAuditInput,
        record_audit_activity,
    )
    from super_factory.temporal.activities.pipeline import (
        plan_run_activity,
        prepare_run_activity,
        publish_pr_activity,
        run_coding_agent_activity,
        verify_run_activity,
    )
    from super_factory.temporal.activities.selection import select_issue_activity

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

_PLAN_TIMEOUT = timedelta(seconds=60)
_PREPARE_TIMEOUT = timedelta(seconds=600)
_AGENT_TIMEOUT = timedelta(seconds=30 * 60)
_VERIFY_TIMEOUT = timedelta(seconds=15 * 60)
_PUBLISH_TIMEOUT = timedelta(seconds=5 * 60)


def _phase_retries(attempts: int, initial: int = 1) -> RetryPolicy:
    """Technical retry axes per phase (functional results are values)."""
    return RetryPolicy(
        maximum_attempts=attempts,
        initial_interval=timedelta(seconds=initial),
        backoff_coefficient=2.0,
    )

_PLAN_RETRIES = _phase_retries(attempts=3)
_PREPARE_RETRIES = _phase_retries(attempts=3)
_AGENT_RETRIES = _phase_retries(attempts=2, initial=2)
_VERIFY_RETRIES = _phase_retries(attempts=3)
_PUBLISH_RETRIES = _phase_retries(attempts=3)


@workflow.defn(name="IssueWorkflow")
class IssueWorkflow:
    """Durable, resumable selection + PR-production pipeline per issue."""

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
        if check.approved and data.pipeline_enabled:
            return await self._produce_pull_request(data, workflow_run_id)
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

    async def _produce_pull_request(
        self, data: IssueWorkflowInput, workflow_run_id: str
    ) -> IssueWorkflowResult:
        """Run the H2 pipeline backed by outcome contracts (never by choice)."""
        plan = await workflow.execute_activity(
            plan_run_activity,
            PlanRunCommand(
                issue_id=data.issue_id,
                repository=data.repository,
                base_branch=data.base_branch,
                title=data.title,
            ),
            start_to_close_timeout=_PLAN_TIMEOUT,
            retry_policy=_PLAN_RETRIES,
        )
        if not plan.ok:
            return await self._finish_blocked(
                data, "-", plan.failure_code, plan.failure_detail
            )
        workflow.upsert_memo(
            {
                "issue_id": data.issue_id,
                "repository": data.repository,
                "workflow_state": IssueWorkflowState.PLANNING.value,
                "run_key": plan.run_key,
                "branch_name": plan.branch_name,
            }
        )
        await self._audit_phase(
            data, plan.run_key, IssueWorkflowState.PLANNING, ok=True, run_id=workflow_run_id
        )
        preparation = await workflow.execute_activity(
            prepare_run_activity,
            PrepareRunCommand(
                issue_id=data.issue_id,
                repository=data.repository,
                spec_version=plan.spec_version,
                run_key=plan.run_key,
                branch_name=plan.branch_name,
                base_branch=data.base_branch,
            ),
            start_to_close_timeout=_PREPARE_TIMEOUT,
            retry_policy=_PREPARE_RETRIES,
        )
        if not preparation.ok:
            return await self._finish_blocked(
                data, plan.run_key, preparation.failure_code, preparation.failure_detail
            )
        workflow.upsert_memo(
            {
                "issue_id": data.issue_id,
                "repository": data.repository,
                "workflow_state": IssueWorkflowState.PREPARING.value,
                "run_key": plan.run_key,
                "branch_name": plan.branch_name,
                "workspace_path": preparation.workspace_path,
            }
        )
        await self._audit_phase(
            data, plan.run_key, IssueWorkflowState.PREPARING, ok=True, run_id=workflow_run_id
        )
        agent_command = AgentRunCommand(
            issue_id=data.issue_id,
            repository=data.repository,
            spec_version=plan.spec_version,
            run_key=plan.run_key,
            branch_name=plan.branch_name,
            base_branch=data.base_branch,
            objective=plan.objective,
            acceptance_criteria=plan.acceptance_criteria,
            exclusions=plan.exclusions,
            constraints=plan.constraints,
            dependencies=plan.dependencies,
            workspace_path=preparation.workspace_path,
        )
        agent_record = await workflow.execute_activity(
            run_coding_agent_activity,
            agent_command,
            start_to_close_timeout=_AGENT_TIMEOUT,
            retry_policy=_AGENT_RETRIES,
        )
        if not agent_record.completed:
            return await self._finish_blocked(
                data,
                plan.run_key,
                agent_record.failure_code,
                agent_record.failure_detail,
            )
        workflow.upsert_memo(
            {
                "issue_id": data.issue_id,
                "repository": data.repository,
                "workflow_state": IssueWorkflowState.IMPLEMENTING.value,
                "run_key": plan.run_key,
            }
        )
        await self._audit_phase(
            data, plan.run_key, IssueWorkflowState.IMPLEMENTING, ok=True, run_id=workflow_run_id
        )
        verification = await workflow.execute_activity(
            verify_run_activity,
            VerificationCommand(
                issue_id=data.issue_id,
                run_key=plan.run_key,
                workspace_path=preparation.workspace_path,
                acceptance_criteria=plan.acceptance_criteria,
            ),
            start_to_close_timeout=_VERIFY_TIMEOUT,
            retry_policy=_VERIFY_RETRIES,
        )
        if not verification.passed:
            return await self._finish_blocked(
                data,
                plan.run_key,
                verification.failure_code,
                verification.failure_detail,
            )
        workflow.upsert_memo(
            {
                "issue_id": data.issue_id,
                "repository": data.repository,
                "workflow_state": IssueWorkflowState.VERIFYING.value,
                "run_key": plan.run_key,
            }
        )
        await self._audit_phase(
            data, plan.run_key, IssueWorkflowState.VERIFYING, ok=True, run_id=workflow_run_id
        )
        publication = await workflow.execute_activity(
            publish_pr_activity,
            PublishCommand(
                issue_id=data.issue_id,
                repository=data.repository,
                run_key=plan.run_key,
                branch_name=plan.branch_name,
                base_branch=data.base_branch,
                workspace_path=preparation.workspace_path,
                objective=plan.objective,
                acceptance_criteria=plan.acceptance_criteria,
                linear_url_template="https://linear.app/genesisnavarra/issue/{issue_id}",
            ),
            start_to_close_timeout=_PUBLISH_TIMEOUT,
            retry_policy=_PUBLISH_RETRIES,
        )
        if not publication.published:
            return await self._finish_blocked(
                data, plan.run_key, publication.failure_code, publication.failure_detail
            )
        workflow.upsert_memo(
            {
                "issue_id": data.issue_id,
                "repository": data.repository,
                "workflow_state": IssueWorkflowState.REVIEWING.value,
                "run_key": plan.run_key,
            }
        )
        await self._audit_phase(
            data, plan.run_key, IssueWorkflowState.REVIEWING, ok=True, run_id=workflow_run_id
        )
        workflow.upsert_memo(
            {
                "issue_id": data.issue_id,
                "repository": data.repository,
                "workflow_state": IssueWorkflowState.PR_READY.value,
                "run_key": plan.run_key,
                "pull_request_url": publication.pr_url,
            }
        )
        await self._audit_phase(
            data, plan.run_key, IssueWorkflowState.PR_READY, ok=True, run_id=workflow_run_id
        )
        return IssueWorkflowResult(
            workflow_state=IssueWorkflowState.PR_READY.value,
            issue_id=data.issue_id,
            repository=data.repository,
            blocking_reasons=(),
            pull_request_url=publication.pr_url,
            pull_request_number=publication.pr_number,
        )

    async def _finish_blocked(
        self,
        data: IssueWorkflowInput,
        run_key: str,
        failure_code: str,
        failure_detail: str,
    ) -> IssueWorkflowResult:
        """Audit + memo the functional blocker with its stable reason."""
        reason = f"{failure_code}: {failure_detail}" if failure_detail else failure_code
        await workflow.execute_activity(
            record_audit_activity,
            RecordAuditInput(
                delivery_id=pipeline_audit_delivery_id(
                    data.delivery_id, run_key, IssueWorkflowState.BLOCKED.value
                ),
                event_action="pipeline",
                event_type=IssueWorkflowState.BLOCKED.value,
                issue_id=data.issue_id,
                repository=data.repository,
                workflow_id=workflow.info().workflow_id,
                workflow_run_id=workflow.info().run_id,
                selection_outcome="PHASE_BLOCKED",
                workflow_state=IssueWorkflowState.BLOCKED.value,
                blocking_reasons=(reason,),
            ),
            start_to_close_timeout=_AUDIT_RETENTION,
            retry_policy=_AUDIT_RETRIES,
        )
        workflow.upsert_memo(
            {
                "issue_id": data.issue_id,
                "repository": data.repository,
                "workflow_state": IssueWorkflowState.BLOCKED.value,
                "run_key": run_key,
                "blocking_reasons": reason,
            }
        )
        return IssueWorkflowResult(
            workflow_state=IssueWorkflowState.BLOCKED.value,
            issue_id=data.issue_id,
            repository=data.repository,
            blocking_reasons=(reason,),
        )

    async def _audit_phase(
        self,
        data: IssueWorkflowInput,
        run_key: str,
        state: IssueWorkflowState,
        *,
        ok: bool,
        run_id: str,
    ) -> None:
        """One durable audit line per completed phase (idempotent per phase)."""
        await workflow.execute_activity(
            record_audit_activity,
            RecordAuditInput(
                delivery_id=pipeline_audit_delivery_id(
                    data.delivery_id, run_key, state.value
                ),
                event_action="pipeline",
                event_type=state.value,
                issue_id=data.issue_id,
                repository=data.repository,
                workflow_id=workflow.info().workflow_id,
                workflow_run_id=run_id,
                selection_outcome="PHASE_OK",
                workflow_state=state.value,
                blocking_reasons=(),
            ),
            start_to_close_timeout=_AUDIT_RETENTION,
            retry_policy=_AUDIT_RETRIES,
        )
