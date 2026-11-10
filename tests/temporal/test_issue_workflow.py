"""Temporal tests for IssueWorkflow (GEN-38 H1, time-skipping).

Acceptance: valid selection completes READY; Done/Canceled/unapproved issues
are blocked with reasons; audit lines persist correlation; transient sink
failures are absorbed by the activity retry policy; history replays
deterministically so the workflow is resumable and traceable.
"""

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from temporalio.client import WorkflowHandle
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Replayer, Worker

from super_factory.contracts.audit import WorkflowRunCorrelation
from super_factory.contracts.workflow_io import IssueWorkflowInput, IssueWorkflowResult
from super_factory.persistence.audit import JsonLinesAuditSink
from super_factory.temporal.activities.audit import record_audit_activity, set_audit_sink
from super_factory.temporal.activities.selection import select_issue_activity
from super_factory.temporal.workflows.issue import IssueWorkflow

pytestmark = pytest.mark.temporal

TASK_QUEUE = "tq-issue-tests"
REPO = "GenesisAI-team/SF-Temporal-Python"


def _input(**overrides: object) -> IssueWorkflowInput:
    fields: dict[str, object] = {
        "issue_id": "GEN-38",
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


@pytest.fixture
def ledger(tmp_path: Path) -> Iterator[Path]:
    ledger_path = tmp_path / "audit.jsonl"
    set_audit_sink(JsonLinesAuditSink(ledger_path))
    try:
        yield ledger_path
    finally:
        set_audit_sink(None)


async def _run(env: Any, data: IssueWorkflowInput, workflow_id: str) -> IssueWorkflowResult:
    async with Worker(
        env.client,
        task_queue=TASK_QUEUE,
        workflows=[IssueWorkflow],
        activities=[select_issue_activity, record_audit_activity],
    ):
        return await env.client.execute_workflow(
            IssueWorkflow.run,
            data,
            id=workflow_id,
            task_queue=TASK_QUEUE,
        )


def _first_audit_entry(path: Path) -> dict[str, Any]:
    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    return json.loads(lines[0])


async def test_selected_issue_completes_ready_and_audits(ledger: Path) -> None:
    async with await WorkflowEnvironment.start_time_skipping() as env:
        result = await _run(env, _input(), "issue-GEN-38")
    assert result.workflow_state == "READY"
    assert result.issue_id == "GEN-38"
    assert result.repository == REPO
    assert result.blocking_reasons == ()
    entry = _first_audit_entry(ledger)
    assert entry["selection_outcome"] == "SELECTED"
    assert entry["workflow_id"] == "issue-GEN-38"
    assert entry["workflow_state"] == "READY"
    assert entry["workflow_run_id"]


async def test_done_issue_is_blocked_with_reason(ledger: Path) -> None:
    async with await WorkflowEnvironment.start_time_skipping() as env:
        result = await _run(env, _input(issue_state="Done"), "issue-GEN-39")
    assert result.workflow_state == "BLOCKED"
    assert result.blocking_reasons == ("STATE_NOT_SELECTABLE: Done",)
    entry = _first_audit_entry(ledger)
    assert entry["selection_outcome"] == "BLOCKED"
    assert entry["workflow_state"] == "BLOCKED"


async def test_canceled_issue_is_blocked(ledger: Path) -> None:
    async with await WorkflowEnvironment.start_time_skipping() as env:
        result = await _run(env, _input(issue_state="Canceled"), "issue-GEN-40")
    assert result.workflow_state == "BLOCKED"


async def test_unapproved_backlog_issue_is_blocked(ledger: Path) -> None:
    async with await WorkflowEnvironment.start_time_skipping() as env:
        result = await _run(env, _input(issue_state="Backlog"), "issue-GEN-41")
    assert result.workflow_state == "BLOCKED"
    assert not any(reason.startswith("STATE_UNRESOLVED") for reason in result.blocking_reasons)


class _FlakySink:
    """Fails its first call to prove the activity retry policy absorbs errors."""

    def __init__(self) -> None:
        self.attempts = 0
        self.recorded: list[WorkflowRunCorrelation] = []

    async def record(self, entry: WorkflowRunCorrelation) -> None:
        self.attempts += 1
        if self.attempts < 2:
            msg = "transient sink outage"
            raise RuntimeError(msg)
        self.recorded.append(entry)


async def test_transient_audit_failure_is_absorbed_by_retries() -> None:
    flaky = _FlakySink()
    set_audit_sink(flaky)
    try:
        async with await WorkflowEnvironment.start_time_skipping() as env:
            result = await _run(env, _input(), "issue-GEN-42")
    finally:
        set_audit_sink(None)
    assert result.workflow_state == "READY"
    assert flaky.attempts == 2
    assert flaky.recorded[0].selection_outcome == "SELECTED"


async def test_workflow_history_replays_deterministically(ledger: Path) -> None:
    async with await WorkflowEnvironment.start_time_skipping() as env, Worker(
        env.client,
        task_queue=TASK_QUEUE,
        workflows=[IssueWorkflow],
        activities=[select_issue_activity, record_audit_activity],
    ):
        handle: WorkflowHandle = await env.client.start_workflow(
            IssueWorkflow.run,
            _input(issue_id="GEN-45"),
            id="issue-GEN-45",
            task_queue=TASK_QUEUE,
        )
        await handle.result()
        history = await handle.fetch_history()
    await Replayer(workflows=[IssueWorkflow]).replay_workflow(history)
