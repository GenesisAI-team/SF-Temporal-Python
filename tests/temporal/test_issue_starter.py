"""Tests for the Temporal SDK adapter that starts/recovers IssueWorkflow runs.

start_or_recover guarantees create-or-recover semantics: one unique durable
run per issue id (Temporal id reuse policy REJECT_DUPLICATE).
"""

import pytest
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

pytestmark = pytest.mark.temporal

from super_factory.contracts.workflow_io import IssueWorkflowInput, WorkflowStartResult
from super_factory.integrations.temporal_sdk.starter import IssueWorkflowStarter
from super_factory.temporal.activities.audit import record_audit_activity, set_audit_sink
from super_factory.temporal.activities.selection import select_issue_activity
from super_factory.persistence.audit import JsonLinesAuditSink
from super_factory.temporal.workflows.issue import IssueWorkflow

TASK_QUEUE = "tq-starter-tests"
REPO = "GenesisAI-team/SF-Temporal-Python"


def _input(**overrides: object) -> IssueWorkflowInput:
    fields: dict[str, object] = {
        "issue_id": "GEN-50",
        "repository": REPO,
        "issue_state": "Todo",
        "labels": ("Feature",),
        "title": "H1",
        "delivery_id": "234d1a4e-b617-4388-90fe-adc3633d6b72",
        "event_action": "update",
        "event_type": "Issue",
        "selectable_states": ("Todo", "In Progress"),
        "allowed_repositories": (REPO,),
    }
    fields.update(overrides)
    return IssueWorkflowInput(**fields)


async def test_start_or_recover_creates_then_recovers_single_run(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    set_audit_sink(JsonLinesAuditSink(tmp_path / "audit.jsonl"))
    try:
        async with await WorkflowEnvironment.start_time_skipping() as env:
            starter = IssueWorkflowStarter(client=env.client, task_queue=TASK_QUEUE)
            async with Worker(
                env.client,
                task_queue=TASK_QUEUE,
                workflows=[IssueWorkflow],
                activities=[select_issue_activity, record_audit_activity],
            ):
                first = await starter.start_or_recover(_input())
                assert first.started is True
                assert first.workflow_id == "issue-GEN-50"
                assert first.run_id

                second = await starter.start_or_recover(_input())
                assert second == WorkflowStartResult(
                    workflow_id="issue-GEN-50",
                    run_id=first.run_id,
                    started=False,
                )
    finally:
        set_audit_sink(None)


def test_result_contract_is_frozen() -> None:
    result = WorkflowStartResult(workflow_id="issue-GEN-1", run_id="r", started=True)
    with pytest.raises(AttributeError):
        result.workflow_id = "other"  # type: ignore[misc]
