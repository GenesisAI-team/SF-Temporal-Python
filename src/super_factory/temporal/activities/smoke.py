"""Minimal activity used by SmokeWorkflow (bootstrap demo only)."""

from dataclasses import dataclass

from temporalio import activity


@dataclass(frozen=True)
class EchoInput:
    """Input for the echo activity. workflow_id travels for traceability."""

    workflow_id: str
    step: str
    message: str


@activity.defn(name="echo_activity")
async def echo_activity(input: EchoInput) -> str:
    """Return '<step>: <message>'. Pure formatting; no I/O, idempotent by design.

    Async so the Worker needs no activity_executor. Blocking activities
    (H2: Codex, Docker) must be sync AND register an activity_executor.
    """
    return f"{input.step}: {input.message}"
