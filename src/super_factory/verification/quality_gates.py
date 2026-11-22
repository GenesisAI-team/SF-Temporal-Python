"""Independent quality-gate runner (GEN-52): the pipeline's own checks.

Executes the configured gate suite (tests, lint, typecheck by default) step
by step inside an ephemeral sandbox after the agent session. Gates are
independent: a failing gate never prevents the remaining gates from running,
but the steps of one gate stop at its first failing step (later steps depend
on earlier ones). The gate is honest: it never reports success without
executing (no simulation).
"""

import contextlib

from super_factory.contracts.pipeline import VerificationCommand, VerificationOutcome
from super_factory.contracts.quality import GateOutcome
from super_factory.contracts.sandboxing import SandboxCommand, SandboxInstance, SandboxSpec
from super_factory.domain.pipeline import REASON_VERIFICATION_FAILED
from super_factory.domain.quality import REASON_GATE_FAILED, GateDefinition, default_gate_suite
from super_factory.sandbox.ports import SandboxRuntime, SandboxUnavailable

_DEFAULT_IMAGE = "python:3.12-slim"
_DEFAULT_TIMEOUT_SECONDS = 600.0


class SandboxQualityGatesRunner:
    """Real ``VerificationRunner`` executing the gate suite in the sandbox."""

    def __init__(
        self,
        sandbox_runtime: SandboxRuntime,
        *,
        sandbox_image: str = _DEFAULT_IMAGE,
        gates: tuple[GateDefinition, ...] = default_gate_suite(),
        timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        self._sandbox = sandbox_runtime
        self._sandbox_image = sandbox_image
        self._gates = gates
        self._timeout_seconds = timeout_seconds

    @property
    def gates(self) -> tuple[GateDefinition, ...]:
        """The configured independent gates (ops introspection)."""
        return self._gates

    @property
    def sandbox_command_timeout_seconds(self) -> float:
        """Timeout expected for each gate step (ops introspection)."""
        return self._timeout_seconds

    async def run(self, command: VerificationCommand) -> VerificationOutcome:
        spec = SandboxSpec(
            run_key=command.run_key,
            workspace_path=command.workspace_path,
            image=self._sandbox_image,
        )
        instance = await self._sandbox.ensure_sandbox(spec)
        gate_outcomes: list[GateOutcome] = []
        try:
            for gate in self._gates:
                gate_outcomes.append(await self._run_gate(instance, gate))
        except SandboxUnavailable:
            with contextlib.suppress(RuntimeError, OSError):
                await self._sandbox.cleanup(instance)
            raise
        with contextlib.suppress(RuntimeError, OSError):
            await self._sandbox.cleanup(instance)
        commands = tuple(
            step_command for gate in gate_outcomes for step_command in gate.commands
        )
        evidence = tuple(
            output for gate in gate_outcomes for output in gate.evidence
        )
        failed = [gate for gate in gate_outcomes if not gate.passed]
        passed = not failed
        if passed:
            return VerificationOutcome(
                passed=True, commands=commands, evidence=evidence, gates=tuple(gate_outcomes)
            )
        detail = "; ".join(f"{gate.gate}: {gate.failure_detail}" for gate in failed)
        return VerificationOutcome(
            passed=False,
            commands=commands,
            evidence=evidence,
            gates=tuple(gate_outcomes),
            failure_code=REASON_VERIFICATION_FAILED,
            failure_detail=detail,
        )

    async def _run_gate(
        self, instance: SandboxInstance, gate: GateDefinition
    ) -> GateOutcome:
        """Run one gate's steps in order, stopping at the first failing step."""
        commands: list[str] = []
        evidence: list[str] = []
        for step in gate.steps:
            outcome = await self._sandbox.run_in_sandbox(
                instance,
                SandboxCommand(argv=step, timeout_seconds=self._timeout_seconds),
            )
            commands.append(" ".join(step))
            if outcome.output_tail.strip():
                evidence.append(outcome.output_tail)
            if outcome.timed_out or outcome.exit_code is None or outcome.exit_code != 0:
                detail = outcome.output_tail.strip() or (
                    "step timed out" if outcome.timed_out else f"step exit={outcome.exit_code}"
                )
                return GateOutcome(
                    gate=gate.name,
                    passed=False,
                    commands=tuple(commands),
                    evidence=tuple(evidence),
                    failure_code=REASON_GATE_FAILED,
                    failure_detail=detail,
                )
        return GateOutcome(
            gate=gate.name,
            passed=True,
            commands=tuple(commands),
            evidence=tuple(evidence),
        )
