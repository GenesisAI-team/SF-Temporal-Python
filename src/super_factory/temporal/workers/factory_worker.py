"""Worker entrypoints for the Software Factory.

Run locally with the Temporal dev server (docker compose):

    uv run python -m super_factory.temporal.workers.run
"""

from temporalio.client import Client
from temporalio.worker import Worker

from super_factory.temporal.activities.smoke import echo_activity
from super_factory.temporal.workers.queues import TASK_QUEUE_ORCHESTRATION
from super_factory.temporal.workflows.smoke import SmokeWorkflow


def build_worker(client: Client, *, task_queue: str = TASK_QUEUE_ORCHESTRATION) -> Worker:
    """Build the orchestration worker with its registered workflows/activities.

    Central registration point: adding a workflow or activity to the factory
    happens here (and in CI tests), never ad-hoc in scripts.
    """
    if not task_queue.strip():
        msg = "task_queue must be a non-empty string"
        raise ValueError(msg)
    return Worker(
        client,
        task_queue=task_queue,
        workflows=[SmokeWorkflow],
        activities=[echo_activity],
    )
