"""Tests for the echo activity contract (unit-level)."""

from super_factory.temporal.activities.smoke import EchoInput, echo_activity


async def test_echo_activity_formats_step_and_message() -> None:
    result = await echo_activity(EchoInput(workflow_id="wf-1", step="preflight", message="hello"))
    assert result == "preflight: hello"


async def test_echo_activity_includes_workflow_id_for_traceability() -> None:
    payload = EchoInput(workflow_id="wf-42", step="record", message="x")
    result = await echo_activity(payload)
    assert result == "record: x"
    # workflow_id travels in the input for idempotency/traceability (audited in H1+)
    assert "wf-42" in repr(payload)
