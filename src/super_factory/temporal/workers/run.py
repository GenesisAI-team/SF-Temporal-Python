"""Process entrypoint that connects to Temporal and runs the worker forever.

INFRASTRUCTURE tier (0% coverage required): a thin process boundary whose real
behaviour is proven by tests/integration/test_worker_roundtrip.py against a
live Temporal server. Keep logic out of this module.
"""

import asyncio

from temporalio.client import Client

from super_factory.config.settings import get_settings
from super_factory.temporal.workers.factory_worker import build_worker


async def run_worker() -> None:
    """Connect to Temporal and run the orchestration worker forever."""
    settings = get_settings()
    client = await Client.connect(
        settings.temporal_address,
        namespace=settings.temporal_namespace,
    )
    worker = build_worker(client)
    print(f"worker polling task queue {worker.task_queue!r} at {settings.temporal_address}")
    await worker.run()


if __name__ == "__main__":
    asyncio.run(run_worker())
