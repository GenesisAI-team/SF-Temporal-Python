"""Integration test: worker + workflow against a REAL Temporal server.

Requires the docker compose stack (see infrastructure/docker/compose.yaml):
    docker compose -f infrastructure/docker/compose.yaml up -d --wait
    uv run pytest -m integration

Note: a fresh temporalio/auto-setup registers the `default` namespace
asynchronously, so connections are retried until the namespace exists.
"""

import asyncio
import time
import uuid

import pytest
from temporalio.client import Client
from temporalio.service import RPCError

from super_factory.config.settings import get_settings
from super_factory.temporal.workers.queues import TASK_QUEUE_ORCHESTRATION
from super_factory.temporal.workers.run import run_worker
from super_factory.temporal.workflows.smoke import SmokeWorkflow

pytestmark = pytest.mark.integration

_NAMESPACE_WAIT_SECONDS = 90


async def _connect_when_ready(address: str, namespace: str) -> Client:
    """Connect to Temporal, retrying while the namespace is still being created."""
    deadline = time.monotonic() + _NAMESPACE_WAIT_SECONDS
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            return await Client.connect(address, namespace=namespace)
        except RPCError as exc:
            last_error = exc
            await asyncio.sleep(2)
    msg = f"Temporal at {address} not ready after {_NAMESPACE_WAIT_SECONDS}s"
    raise RuntimeError(msg) from last_error


async def test_worker_roundtrip_completes_workflow() -> None:
    settings = get_settings()
    # Connect first: run_worker() would die on the not-yet-created namespace.
    client = await _connect_when_ready(
        settings.temporal_address,
        settings.temporal_namespace,
    )
    worker_task = asyncio.create_task(run_worker())
    try:
        workflow_id = f"integration-smoke-{uuid.uuid4()}"
        result = await asyncio.wait_for(
            client.execute_workflow(
                SmokeWorkflow.run,
                "integration",
                id=workflow_id,
                task_queue=TASK_QUEUE_ORCHESTRATION,
            ),
            timeout=60,
        )
        assert result == ["preflight: integration", "record: integration"]

        handle = client.get_workflow_handle(workflow_id)
        history = await handle.fetch_history()
        assert history.events, "workflow history must contain events"
    finally:
        worker_task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await worker_task
