"""Temporal tests for SmokeWorkflow (TDD cycles C7-C8).

SmokeWorkflow is a deliberate MINIMAL demo of deterministic orchestration.
It is NOT the future IssueWorkflow (H1).
"""

from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Replayer, Worker

from super_factory.temporal.activities.smoke import echo_activity
from super_factory.temporal.workflows.smoke import SmokeWorkflow

TASK_QUEUE = "tq-smoke-tests"


async def test_smoke_workflow_returns_activity_results() -> None:
    async with await WorkflowEnvironment.start_time_skipping() as env, Worker(
        env.client,
        task_queue=TASK_QUEUE,
        workflows=[SmokeWorkflow],
        activities=[echo_activity],
    ):
        result = await env.client.execute_workflow(
            SmokeWorkflow.run,
            "hello-gen17",
            id="smoke-1",
            task_queue=TASK_QUEUE,
        )
    assert result == ["preflight: hello-gen17", "record: hello-gen17"]


async def test_smoke_workflow_replays_history_deterministically() -> None:
    async with await WorkflowEnvironment.start_time_skipping() as env, Worker(
        env.client,
        task_queue=TASK_QUEUE,
        workflows=[SmokeWorkflow],
        activities=[echo_activity],
    ):
        handle = await env.client.start_workflow(
            SmokeWorkflow.run,
            "replay-check",
            id="smoke-replay",
            task_queue=TASK_QUEUE,
        )
        await handle.result()
        history = await handle.fetch_history()

    await Replayer(workflows=[SmokeWorkflow]).replay_workflow(history)
