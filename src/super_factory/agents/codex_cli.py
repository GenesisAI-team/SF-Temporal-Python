"""Codex CLI coding-agent adapter (GEN-47).

The agent runs a single non-interactive session inside an ephemeral sandbox
(``codex exec``, prompt delivered via stdin so the safety guard only scans
control argv). Real agent execution needs a sandbox image containing the
Codex CLI (configure ``SF_AGENT_SANDBOX_IMAGE``); without it the run fails
honestly — nothing is simulated.

Every session cleans up its sandbox, including after failures.
"""

import contextlib

from super_factory.contracts.pipeline import AgentRunCommand, AgentRunRecord
from super_factory.contracts.sandboxing import (
    SandboxCommand,
    SandboxInstance,
    SandboxSpec,
)
from super_factory.domain.pipeline import (
    REASON_AGENT_BLOCKED,
    REASON_AGENT_FAILED,
    build_agent_prompt,
)
from super_factory.sandbox.ports import (
    SandboxCommandRejected,
    SandboxRuntime,
    SandboxUnavailable,
)

_DEFAULT_PLATFORM = "codex-cli"
_DEFAULT_PROGRAM = "codex"
_DEFAULT_SANDBOX_IMAGE = "python:3.12-slim"
_DEFAULT_COMMAND_TIMEOUT_SECONDS = 600


async def _best_effort_cleanup(sandbox: SandboxRuntime, agent: SandboxInstance) -> None:
    """Cleanup must never mask the real outcome."""
    with contextlib.suppress(RuntimeError, OSError):
        await sandbox.cleanup(agent)


class CodexCliAgent:
    """Real ``CodingAgent`` executing Codex inside a sandbox runtime."""

    def __init__(
        self,
        sandbox_runtime: SandboxRuntime,
        *,
        platform: str = _DEFAULT_PLATFORM,
        program: str = _DEFAULT_PROGRAM,
        sandbox_image: str = _DEFAULT_SANDBOX_IMAGE,
        command_timeout_seconds: float = _DEFAULT_COMMAND_TIMEOUT_SECONDS,
    ) -> None:
        self._sandbox = sandbox_runtime
        self.platform = platform
        self._program = program
        self._sandbox_image = sandbox_image
        self._command_timeout_seconds = command_timeout_seconds

    @property
    def sandbox_image(self) -> str:
        """Sandbox image used for agent execution (ops configurable)."""
        return self._sandbox_image

    async def run(self, command: AgentRunCommand) -> AgentRunRecord:
        spec = SandboxSpec(
            run_key=command.run_key,
            workspace_path=command.workspace_path,
            image=self._sandbox_image,
            command_timeout_seconds=int(self._command_timeout_seconds),
        )
        instance = await self._sandbox.ensure_sandbox(spec)
        prompt = build_agent_prompt(
            objective=command.objective,
            acceptance_criteria=command.acceptance_criteria,
            base_branch=command.base_branch,
            branch_name=command.branch_name,
        )
        launched = SandboxCommand(
            argv=(self._program, "exec"),
            stdin_payload=prompt,
            timeout_seconds=self._command_timeout_seconds,
        )
        commands = (" ".join(launched.argv),)
        try:
            outcome = await self._sandbox.run_in_sandbox(instance, launched)
        except SandboxCommandRejected as rejected:
            await _best_effort_cleanup(self._sandbox, instance)
            return AgentRunRecord(
                completed=False,
                commands=commands,
                failure_code=REASON_AGENT_BLOCKED,
                failure_detail=f"{rejected.code}: {rejected.detail}",
            )
        except SandboxUnavailable:
            await _best_effort_cleanup(self._sandbox, instance)
            raise
        await _best_effort_cleanup(self._sandbox, instance)
        evidence = (outcome.output_tail,) if outcome.output_tail.strip() else ()
        failed = outcome.timed_out or outcome.exit_code is None or outcome.exit_code != 0
        if failed:
            detail = outcome.output_tail.strip() or (
                "sandbox command timed out"
                if outcome.timed_out
                else f"sandbox command exit={outcome.exit_code}"
            )
            return AgentRunRecord(
                completed=False,
                commands=commands,
                evidence=evidence,
                failure_code=REASON_AGENT_FAILED,
                failure_detail=detail,
            )
        return AgentRunRecord(completed=True, commands=commands, evidence=evidence)
