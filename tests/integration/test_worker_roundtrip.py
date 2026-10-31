"""Integration test: worker + workflow against a REAL Temporal server.

Requires the docker compose stack (see infrastructure/docker/compose.yaml):
    docker compose -f infrastructure/docker/compose.yaml up -d --wait
    uv run pytest -m integration
"""

import asyncio
import uuid

import pytest
from temporalio.client import Client

from super_factory.config.settings import get_settings
from super_factory.temporal.workers.queues import TASK_QUEUE_ORCHESTRATION
from super_factory.temporal.workers.run import run_worker
from super_factory.temporal.workflows.smoke import SmokeWorkflow

pytestmark = pytest.mark.integration


async def test_worker_roundtrip_completes_workflow() -> None:
    settings = get_settings()
    worker_task = asyncio.create_task(run_worker())
    try:
        client = await Client.connect(
            settings.temporal_address,
            namespace=settings.temporal_namespace,
        )
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
