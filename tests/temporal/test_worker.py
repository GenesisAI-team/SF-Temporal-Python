"""Tests for the worker builder (TDD cycle C9, part 2).

build_worker is the single place that registers workflows and activities on
a task queue. Proven against a real (time-skipping) Temporal environment.
"""

from pathlib import Path

import pytest
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from super_factory.contracts.workflow_io import IssueWorkflowInput
from super_factory.persistence.audit import JsonLinesAuditSink
from super_factory.temporal.activities.audit import set_audit_sink
from super_factory.temporal.workers.factory_worker import build_worker
from super_factory.temporal.workers.queues import TASK_QUEUE_ORCHESTRATION
from super_factory.temporal.workflows.issue import IssueWorkflow
from super_factory.temporal.workflows.smoke import SmokeWorkflow


def test_build_worker_rejects_blank_task_queue() -> None:
    with pytest.raises(ValueError, match="task_queue"):
        build_worker(client=None, task_queue="  ")  # type: ignore[arg-type]


async def test_build_worker_registers_workflow_and_activity() -> None:
    async with await WorkflowEnvironment.start_time_skipping() as env:
        worker = build_worker(env.client)
        assert isinstance(worker, Worker)
        assert worker.task_queue == TASK_QUEUE_ORCHESTRATION
        # registration is proven for real below
        async with worker:
            result = await env.client.execute_workflow(
                SmokeWorkflow.run,
                "worker-check",
                id="worker-smoke-1",
                task_queue=TASK_QUEUE_ORCHESTRATION,
            )
        assert result == ["preflight: worker-check", "record: worker-check"]


def _issue_input() -> IssueWorkflowInput:
    repo = "GenesisAI-team/SF-Temporal-Python"
    return IssueWorkflowInput(
        issue_id="GEN-60",
        repository=repo,
        issue_state="Todo",
        labels=("Feature",),
        title="H1",
        delivery_id="234d1a4e-b617-4388-90fe-adc3633d6b72",
        event_action="update",
        event_type="Issue",
        selectable_states=("Todo", "In Progress"),
        allowed_repositories=(repo,),
    )


async def test_build_worker_registers_issue_workflow(tmp_path: Path) -> None:
    ledger = JsonLinesAuditSink(tmp_path / "audit.jsonl")
    set_audit_sink(ledger)
    try:
        async with await WorkflowEnvironment.start_time_skipping() as env, build_worker(
            env.client
        ):
            result = await env.client.execute_workflow(
                IssueWorkflow.run,
                _issue_input(),
                id="issue-GEN-60",
                task_queue=TASK_QUEUE_ORCHESTRATION,
            )
    finally:
        set_audit_sink(None)
    assert result.workflow_state == "READY"
    assert ledger.path.exists() and (tmp_path / "audit.jsonl").exists()
