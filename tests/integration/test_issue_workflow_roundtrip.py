"""Integration test: IssueWorkflow roundtrip against a REAL Temporal server (GEN-38).

Requires the docker compose stack (see infrastructure/docker/compose.yaml):
    docker compose -f infrastructure/docker/compose.yaml up -d --wait
    uv run pytest tests/integration -m integration -v

The connection/namespace readiness helpers are shared with the smoke
roundtrip test module.
"""

import asyncio
import json
import uuid
from pathlib import Path

import pytest

from super_factory.config.settings import get_settings
from super_factory.contracts.workflow_io import IssueWorkflowInput
from super_factory.temporal.workers.queues import TASK_QUEUE_ORCHESTRATION
from super_factory.temporal.workers.run import run_worker
from super_factory.temporal.workflows.issue import IssueWorkflow
from tests.integration.test_worker_roundtrip import _connect_when_namespace_ready

pytestmark = pytest.mark.integration


def _issue_input() -> IssueWorkflowInput:
    repo = "GenesisAI-team/SF-Temporal-Python"
    return IssueWorkflowInput(
        issue_id=f"GEN-IT-{uuid.uuid4().int % 100000}",
        repository=repo,
        issue_state="Todo",
        labels=("Feature",),
        title="H1 integration",
        delivery_id=str(uuid.uuid4()),
        event_action="update",
        event_type="Issue",
        selectable_states=("Todo", "In Progress"),
        allowed_repositories=(repo,),
    )


async def test_issue_workflow_completes_on_real_server(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SF_AUDIT_LOG_PATH", str(tmp_path / "audit.jsonl"))
    settings = get_settings()
    client = await _connect_when_namespace_ready(
        settings.temporal_address, settings.temporal_namespace
    )
    worker_task = asyncio.create_task(run_worker())
    data = _issue_input()
    try:
        result = await asyncio.wait_for(
            client.execute_workflow(
                IssueWorkflow.run,
                data,
                id=f"issue-{data.issue_id}",
                task_queue=TASK_QUEUE_ORCHESTRATION,
            ),
            timeout=60,
        )
        assert result.workflow_state == "READY"
    finally:
        worker_task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await worker_task

    ledger = tmp_path / "audit.jsonl"
    assert ledger.exists(), "workflow must persist the audit correlation"
    entry = json.loads(ledger.read_text(encoding="utf-8").splitlines()[0])
    assert entry["issue_id"] == data.issue_id
    assert entry["selection_outcome"] == "SELECTED"
    assert entry["workflow_run_id"]
