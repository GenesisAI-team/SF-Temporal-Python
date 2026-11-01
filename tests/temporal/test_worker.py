"""Tests for the worker builder (TDD cycle C9, part 2).

build_worker is the single place that registers workflows and activities on
a task queue. Proven against a real (time-skipping) Temporal environment.
"""

import pytest
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from super_factory.temporal.workers.factory_worker import build_worker
from super_factory.temporal.workers.queues import TASK_QUEUE_ORCHESTRATION
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
