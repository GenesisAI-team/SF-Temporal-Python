"""Tests for the sandbox verification runner (GEN-47).

Acceptance: the gate re-runs the test command inside an ephemeral sandbox,
maps outcomes honestly (passed / VERIFICATION_FAILED with output detail),
propagates unavailability for retries, and cleans up the sandbox on every
path.
"""

import pytest

from super_factory.contracts.pipeline import VerificationCommand
from super_factory.contracts.sandboxing import (
    SandboxCommand,
    SandboxCommandOutcome,
    SandboxInstance,
    SandboxSpec,
)
from super_factory.domain.pipeline import REASON_VERIFICATION_FAILED
from super_factory.sandbox.ports import SandboxUnavailable
from super_factory.verification.sandbox import SandboxVerificationRunner


class FakeSandboxRuntime:
    def __init__(self) -> None:
        self.started_specs: list[SandboxSpec] = []
        self.commands: list[SandboxCommand] = []
        self.cleaned: list[str] = []
        self.raise_on_start: Exception | None = None
        self.outcome = SandboxCommandOutcome(exit_code=0, output_tail="1 passed")

    async def ensure_sandbox(self, spec: SandboxSpec) -> SandboxInstance:
        if self.raise_on_start is not None:
            raise self.raise_on_start
        self.started_specs.append(spec)
        return SandboxInstance(id=f"factory-sandbox-{spec.run_key.lower()}")

    async def run_in_sandbox(
        self, instance: SandboxInstance, command: SandboxCommand
    ) -> SandboxCommandOutcome:
        self.commands.append(command)
        return self.outcome

    async def cleanup(self, instance: SandboxInstance) -> None:
        self.cleaned.append(instance.id)


def _command(**overrides: object) -> VerificationCommand:
    fields: dict[str, object] = {
        "issue_id": "GEN-47",
        "run_key": "GEN-47-v1",
        "workspace_path": "/ws/gen-47-v1",
        "acceptance_criteria": ("works",),
    }
    fields.update(overrides)
    return VerificationCommand(**fields)


async def test_verification_runs_tests_and_reports_pass() -> None:
    sandbox = FakeSandboxRuntime()
    runner = SandboxVerificationRunner(sandbox)
    outcome = await runner.run(_command())
    assert outcome.passed
    assert outcome.commands == ("uv run pytest -q",)
    assert "1 passed" in "".join(outcome.evidence)
    assert sandbox.commands[0].argv == ("uv", "run", "pytest", "-q")
    assert sandbox.cleaned == ["factory-sandbox-gen-47-v1"]


async def test_verification_maps_failure_honestly() -> None:
    sandbox = FakeSandboxRuntime()
    sandbox.outcome = SandboxCommandOutcome(exit_code=3, output_tail="1 failed")
    outcome = await SandboxVerificationRunner(sandbox).run(_command())
    assert not outcome.passed
    assert outcome.failure_code == REASON_VERIFICATION_FAILED
    assert "1 failed" in outcome.failure_detail
    assert len(sandbox.cleaned) == 1


async def test_verification_maps_timeout_honestly() -> None:
    sandbox = FakeSandboxRuntime()
    sandbox.outcome = SandboxCommandOutcome(exit_code=None, timed_out=True)
    outcome = await SandboxVerificationRunner(sandbox).run(_command())
    assert not outcome.passed
    assert outcome.failure_detail == "verification timed out"


async def test_verification_propagates_outage_and_cleans_up() -> None:
    sandbox = FakeSandboxRuntime()
    sandbox.raise_on_start = SandboxUnavailable("docker daemon down")
    with pytest.raises(SandboxUnavailable, match="docker daemon down"):
        await SandboxVerificationRunner(sandbox).run(_command())
    assert sandbox.cleaned == []


def test_verification_platform_parameters() -> None:
    sandbox = FakeSandboxRuntime()
    runner = SandboxVerificationRunner(
        sandbox,
        sandbox_image="ghcr.io/genesis/sandbox-codex:0.42",
        test_command=("pytest", "-q"),
        timeout_seconds=120.0,
    )
    assert runner.sandbox_command_timeout_seconds == 120.0
