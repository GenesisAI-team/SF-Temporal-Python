"""Sandbox verification adapter (GEN-47): the pipeline's own test gate.

Reuses the sandbox runtime to execute the repository's test command inside
an ephemeral sandbox after the agent session. The gate is honest: it never
reports success without executing (no simulation).
"""

import contextlib

from super_factory.contracts.pipeline import (
    VerificationCommand,
    VerificationOutcome,
)
from super_factory.contracts.sandboxing import SandboxCommand, SandboxSpec
from super_factory.domain.pipeline import REASON_VERIFICATION_FAILED
from super_factory.sandbox.ports import SandboxRuntime, SandboxUnavailable

_DEFAULT_IMAGE = "python:3.12-slim"
_DEFAULT_COMMAND: tuple[str, ...] = ("uv", "run", "pytest", "-q")
_DEFAULT_TIMEOUT_SECONDS = 600.0


class SandboxVerificationRunner:
    """Real ``VerificationRunner`` executing the tests inside the sandbox."""

    def __init__(
        self,
        sandbox_runtime: SandboxRuntime,
        *,
        sandbox_image: str = _DEFAULT_IMAGE,
        test_command: tuple[str, ...] = _DEFAULT_COMMAND,
        timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        self._sandbox = sandbox_runtime
        self._sandbox_image = sandbox_image
        self._test_command = test_command
        self._timeout_seconds = timeout_seconds

    async def run(self, command: VerificationCommand) -> VerificationOutcome:
        spec = SandboxSpec(
            run_key=command.run_key,
            workspace_path=command.workspace_path,
            image=self._sandbox_image,
        )
        instance = await self._sandbox.ensure_sandbox(spec)
        sand_command = SandboxCommand(
            argv=self._test_command, timeout_seconds=self._timeout_seconds
        )
        try:
            outcome = await self._sandbox.run_in_sandbox(instance, sand_command)
        except SandboxUnavailable:
            with contextlib.suppress(RuntimeError, OSError):
                await self._sandbox.cleanup(instance)
            raise
        with contextlib.suppress(RuntimeError, OSError):
            await self._sandbox.cleanup(instance)
        commands = (" ".join(self._test_command),)
        evidence = (outcome.output_tail,) if outcome.output_tail.strip() else ()
        passed = not outcome.timed_out and outcome.exit_code == 0
        if passed:
            return VerificationOutcome(passed=True, commands=commands, evidence=evidence)
        detail = outcome.output_tail.strip() or (
            "verification timed out"
            if outcome.timed_out
            else f"verification exit={outcome.exit_code}"
        )
        return VerificationOutcome(
            passed=False,
            commands=commands,
            evidence=evidence,
            failure_code=REASON_VERIFICATION_FAILED,
            failure_detail=detail,
        )
