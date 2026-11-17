"""Tests for the H3 independent quality-gate runner (GEN-52).

Acceptance: the runner executes the whole gate suite inside an ephemeral
sandbox (gates run independently of each other's failures), stops the steps
of a gate at its first failing step, maps outcomes honestly (GATE_FAILED per
gate, VERIFICATION_FAILED for the aggregate with the failed-gate detail),
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
from super_factory.domain.quality import REASON_GATE_FAILED, GateDefinition, default_gate_suite
from super_factory.sandbox.ports import SandboxUnavailable
from super_factory.verification.quality_gates import SandboxQualityGatesRunner


class FakeSandboxRuntime:
    def __init__(self) -> None:
        self.started_specs: list[SandboxSpec] = []
        self.commands: list[SandboxCommand] = []
        self.cleaned: list[str] = []
        self.raise_on_start: Exception | None = None
        self.scripts: dict[tuple[str, ...], SandboxCommandOutcome] = {}
        self.default_outcome = SandboxCommandOutcome(exit_code=0, output_tail="ok")

    async def ensure_sandbox(self, spec: SandboxSpec) -> SandboxInstance:
        if self.raise_on_start is not None:
            raise self.raise_on_start
        self.started_specs.append(spec)
        return SandboxInstance(id=f"factory-sandbox-{spec.run_key.lower()}")

    async def run_in_sandbox(
        self, instance: SandboxInstance, command: SandboxCommand
    ) -> SandboxCommandOutcome:
        self.commands.append(command)
        return self.scripts.get(command.argv, self.default_outcome)

    async def cleanup(self, instance: SandboxInstance) -> None:
        self.cleaned.append(instance.id)


def _command(**overrides: object) -> VerificationCommand:
    fields: dict[str, object] = {
        "issue_id": "GEN-52",
        "run_key": "GEN-52-v1",
        "workspace_path": "/ws/gen-52-v1",
        "acceptance_criteria": ("gates run",),
    }
    fields.update(overrides)
    return VerificationCommand(**fields)  # type: ignore[arg-type]


async def test_every_gate_runs_and_reports_independent_evidence() -> None:
    sandbox = FakeSandboxRuntime()
    sandbox.scripts = {
        ("uv", "run", "pytest", "-q"): SandboxCommandOutcome(exit_code=0, output_tail="12 passed"),
    }
    runner = SandboxQualityGatesRunner(sandbox)
    outcome = await runner.run(_command())
    assert outcome.passed
    assert len(outcome.gates) == 3
    assert [gate.gate for gate in outcome.gates] == ["tests", "lint", "typecheck"]
    assert all(gate.passed for gate in outcome.gates)
    assert outcome.commands == (
        "uv run pytest -q",
        "uv run ruff check .",
        "uv run mypy src",
    )
    assert "12 passed" in "".join(outcome.evidence)
    assert sandbox.cleaned == ["factory-sandbox-gen-52-v1"]


async def test_failing_gate_keeps_later_gates_running() -> None:
    sandbox = FakeSandboxRuntime()
    sandbox.scripts = {
        ("uv", "run", "pytest", "-q"): SandboxCommandOutcome(exit_code=1, output_tail="1 failed"),
    }
    outcome = await SandboxQualityGatesRunner(sandbox).run(_command())
    assert not outcome.passed
    tests_gate, lint_gate, typecheck_gate = outcome.gates
    assert not tests_gate.passed
    assert tests_gate.failure_code == REASON_GATE_FAILED
    assert "1 failed" in tests_gate.failure_detail
    assert lint_gate.passed
    assert typecheck_gate.passed
    assert outcome.failure_code == REASON_VERIFICATION_FAILED
    assert "tests" in outcome.failure_detail
    assert len(sandbox.commands) == 3
    assert len(sandbox.cleaned) == 1


async def test_gate_steps_stop_at_the_first_failing_step() -> None:
    sandbox = FakeSandboxRuntime()
    coverage_gate = GateDefinition(name="coverage", steps=(("step", "one"), ("step", "two")))
    sandbox.scripts = {("step", "one"): SandboxCommandOutcome(exit_code=2, output_tail="boom")}
    runner = SandboxQualityGatesRunner(sandbox, gates=(coverage_gate,))
    outcome = await runner.run(_command())
    assert not outcome.passed
    (gate,) = outcome.gates
    assert gate.commands == ("step one",)
    assert ("step", "two") not in [command.argv for command in sandbox.commands]
    assert "boom" in outcome.failure_detail


async def test_gate_timeout_is_reported_honestly() -> None:
    sandbox = FakeSandboxRuntime()
    sandbox.scripts = {
        ("uv", "run", "pytest", "-q"): SandboxCommandOutcome(
            exit_code=None, output_tail="", timed_out=True
        )
    }
    outcome = await SandboxQualityGatesRunner(sandbox).run(_command())
    assert not outcome.passed
    assert outcome.gates[0].failure_detail == "step timed out"


async def test_unavailable_sandbox_propagates_after_cleanup() -> None:
    sandbox = FakeSandboxRuntime()
    sandbox.raise_on_start = SandboxUnavailable("docker daemon unreachable")
    runner = SandboxQualityGatesRunner(sandbox)
    with pytest.raises(SandboxUnavailable, match="unreachable"):
        await runner.run(_command())
    assert sandbox.cleaned == []


async def test_custom_gate_suite_is_honored() -> None:
    sandbox = FakeSandboxRuntime()
    gate = GateDefinition(name="custom", steps=(("echo", "hi"),))
    runner = SandboxQualityGatesRunner(sandbox, gates=(gate,))
    outcome = await runner.run(_command())
    assert outcome.passed
    assert [g.gate for g in outcome.gates] == ["custom"]
    assert sandbox.commands[0].argv == ("echo", "hi")


async def test_default_suite_matches_the_domain_definition() -> None:
    sandbox = FakeSandboxRuntime()
    runner = SandboxQualityGatesRunner(sandbox)
    assert len(runner.gates) == len(default_gate_suite())
    assert runner.sandbox_command_timeout_seconds > 0
