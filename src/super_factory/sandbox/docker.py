"""Docker sandbox adapter (GEN-47): one ephemeral container per run.

Container policy (hardened by default):
- deterministic container name ``factory-sandbox-<run_key>``,
- network isolation (``--network none``), no capabilities,
  no privilege escalation, read-only rootfs, bounded CPU/RAM,
- workspace mounted read-write at ``/workspace``, tmpfs scratch at ``/tmp``,
- non-root execution (configurable via the spec).

Runs never outlive the session: cleanup removes the container even after
failures. Runner-level failures map to ``SandboxUnavailable`` (retryable).
"""

import contextlib

from super_factory.contracts.sandboxing import (
    SandboxCommand,
    SandboxCommandOutcome,
    SandboxInstance,
    SandboxSpec,
)
from super_factory.domain.safety import find_forbidden_command
from super_factory.process.ports import (
    CommandOutcome,
    CommandRequest,
    CommandRunner,
    ProcessLaunchError,
)
from super_factory.sandbox.ports import SandboxCommandRejected, SandboxUnavailable

_LAUNCH_TIMEOUT_SECONDS = 120.0
_OUTPUT_KEEP = 4000


def container_name_for(run_key: str) -> str:
    """Deterministic, docker-safe container name per run key."""
    return f"factory-sandbox-{run_key.lower()}"


class DockerSandboxRuntime:
    """Real ``SandboxRuntime`` built on docker run/exec/rm."""

    def __init__(self, command_runner: CommandRunner) -> None:
        self._runner = command_runner

    async def ensure_sandbox(self, spec: SandboxSpec) -> SandboxInstance:
        name = container_name_for(spec.run_key)
        request = CommandRequest(
            argv=self._start_argv(spec, name), timeout_seconds=_LAUNCH_TIMEOUT_SECONDS
        )
        outcome = await self._launch(request)
        if outcome.timed_out or outcome.exit_code is None:
            raise SandboxUnavailable("docker run failed: timed out")
        if outcome.exit_code != 0:
            detail = (outcome.stderr_tail or outcome.stdout_tail).strip()
            raise SandboxUnavailable(f"docker run failed: {detail}")
        return SandboxInstance(id=name)

    async def run_in_sandbox(
        self, instance: SandboxInstance, command: SandboxCommand
    ) -> SandboxCommandOutcome:
        violation = find_forbidden_command(command.argv)
        if violation is not None:
            raise SandboxCommandRejected(code=violation.code, detail=violation.detail)
        argv: list[str] = ["docker", "exec"]
        if command.stdin_payload is not None:
            argv.append("-i")
        argv.extend(("-w", command.workdir, instance.id))
        argv.extend(command.argv)
        outcome = await self._launch(
            CommandRequest(
                argv=tuple(argv),
                timeout_seconds=command.timeout_seconds,
                stdin=command.stdin_payload,
            )
        )
        tail = "\n".join(
            part
            for part in (outcome.stdout_tail, outcome.stderr_tail)
            if part.strip()
        )
        bounded = tail if len(tail) <= _OUTPUT_KEEP else f"…(truncated)\n{tail[-_OUTPUT_KEEP:]}"
        return SandboxCommandOutcome(
            exit_code=outcome.exit_code if not outcome.timed_out else None,
            output_tail=bounded,
            timed_out=outcome.timed_out,
        )

    async def cleanup(self, instance: SandboxInstance) -> None:
        with contextlib.suppress(SandboxUnavailable):
            await self._launch(
                CommandRequest(
                    argv=("docker", "rm", "-f", instance.id),
                    timeout_seconds=_LAUNCH_TIMEOUT_SECONDS,
                )
            )

    async def _launch(self, request: CommandRequest) -> CommandOutcome:
        try:
            return await self._runner.run(request)
        except ProcessLaunchError as exc:
            raise SandboxUnavailable(str(exc)) from exc

    @staticmethod
    def _start_argv(spec: SandboxSpec, name: str) -> tuple[str, ...]:
        argv: list[str] = [
            "docker",
            "run",
            "-d",
            "--name",
            name,
            "--network",
            "none" if spec.network_isolated else "bridge",
            "--cpus",
            str(spec.cpu_limit),
            "--memory",
            spec.memory_limit,
            "--security-opt",
            "no-new-privileges",
            "--cap-drop",
            "ALL",
            "--read-only",
            "--tmpfs",
            "/tmp:rw,noexec,nosuid,size=512m",  # noqa: S108 - in-container scratch, not a host temp file
        ]
        if spec.run_as_non_root:
            argv.extend(("--user", "1000:1000"))
        argv.extend(
            (
                "-v",
                f"{spec.workspace_path}:/workspace",
                "-w",
                "/workspace",
                spec.image,
                "sleep",
                "infinity",
            )
        )
        return tuple(argv)
