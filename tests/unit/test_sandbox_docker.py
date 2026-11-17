"""Tests for the Docker sandbox adapter (GEN-47) against a scripted runner.

Acceptance: two hardening axes — the container argv carries network/cpus/
memory/capability/read-only/tmpfs/non-root restrictions with a deterministic
container name, and the command path blocks dangerous commands before any
docker call. Runner-level failures map to explicit SandboxUnavailable.
"""

import pytest

from super_factory.contracts.sandboxing import (
    SandboxCommand,
    SandboxCommandOutcome,
    SandboxInstance,
    SandboxSpec,
)
from super_factory.process.ports import CommandOutcome, CommandRequest
from super_factory.sandbox.docker import DockerSandboxRuntime
from super_factory.sandbox.ports import (
    SandboxCommandRejected,
    SandboxUnavailable,
)


class ScriptedRunner:
    """CommandRunner double: matches argv prefixes to scripted outcomes."""

    def __init__(self) -> None:
        self.requests: list[CommandRequest] = []
        self.script: dict[tuple[str, ...], CommandOutcome] = {}

    def on(
        self,
        prefix: tuple[str, ...],
        *,
        exit_code: int = 0,
        stdout_tail: str = "",
        stderr_tail: str = "",
        timed_out: bool = False,
    ) -> "ScriptedRunner":
        self.script[prefix] = CommandOutcome(
            exit_code=exit_code,
            stdout_tail=stdout_tail,
            stderr_tail=stderr_tail,
            timed_out=timed_out,
        )
        return self

    async def run(self, request: CommandRequest) -> CommandOutcome:
        self.requests.append(request)
        for prefix, outcome in self.script.items():
            if tuple(request.argv[: len(prefix)]) == prefix:
                return outcome
        return CommandOutcome(exit_code=0)


def _spec(**overrides: object) -> SandboxSpec:
    fields: dict[str, object] = {"run_key": "GEN-47-v1", "workspace_path": "/ws"}
    fields.update(overrides)
    return SandboxSpec(**fields)


async def test_ensure_sandbox_hardens_and_names_container() -> None:
    runner = ScriptedRunner()
    runtime = DockerSandboxRuntime(runner)
    instance = await runtime.ensure_sandbox(_spec())
    assert instance == SandboxInstance(id="factory-sandbox-gen-47-v1")
    argv = list(runner.requests[0].argv)
    assert argv[0:2] == ["docker", "run"]
    for flag_pair in (
        (("--name", "factory-sandbox-gen-47-v1")),
        (("--network", "none")),
        (("--cpus", "1.0")),
        (("--memory", "2g")),
        (("--security-opt", "no-new-privileges")),
        (("--cap-drop", "ALL")),
        (("--read-only",)),
        (("--tmpfs", "/tmp:rw,noexec,nosuid,size=512m")),  # noqa: S108 - in-container scratch
        (("-v", "/ws:/workspace")),
        (("-w", "/workspace")),
        (("--user", "1000:1000")),
        (("python:3.12-slim", "sleep", "infinity")),
    ):
        assert all(item in argv for item in flag_pair), flag_pair


async def test_ensure_sandbox_can_relax_isolation_and_user() -> None:
    runner = ScriptedRunner()
    runtime = DockerSandboxRuntime(runner)
    await runtime.ensure_sandbox(_spec(network_isolated=False, run_as_non_root=False))
    argv = list(runner.requests[0].argv)
    assert "--user" not in argv
    assert "none" not in argv
    assert "bridge" in argv


async def test_ensure_sandbox_maps_runner_failures() -> None:
    runner = ScriptedRunner().on(("docker", "run"), exit_code=125, stderr_tail="nil")
    runtime = DockerSandboxRuntime(runner)
    with pytest.raises(SandboxUnavailable, match="docker run failed"):
        await runtime.ensure_sandbox(_spec())


async def test_run_in_sandbox_executes_and_collects_output() -> None:
    runner = ScriptedRunner().on(
        ("docker", "exec"), exit_code=2, stdout_tail="", stderr_tail="boom"
    )
    runtime = DockerSandboxRuntime(runner)
    instance = SandboxInstance(id="factory-sandbox-gen-47-v1")
    outcome = await runtime.run_in_sandbox(
        instance, SandboxCommand(argv=("uv", "run", "pytest", "-q"), workdir="/workspace")
    )
    assert outcome == SandboxCommandOutcome(exit_code=2, output_tail="boom")
    argv = list(runner.requests[0].argv)
    assert argv[:5] == ["docker", "exec", "-w", "/workspace", instance.id]
    assert runner.requests[0].stdin is None


async def test_run_in_sandbox_combines_streams_in_order() -> None:
    runner = ScriptedRunner().on(
        ("docker", "exec"), exit_code=0, stdout_tail="PASS", stderr_tail="warn"
    )
    runtime = DockerSandboxRuntime(runner)
    outcome = await runtime.run_in_sandbox(
        SandboxInstance(id="i"), SandboxCommand(argv=("pytest",))
    )
    assert "PASS" in outcome.output_tail
    assert "warn" in outcome.output_tail
    assert outcome.output_tail.index("PASS") < outcome.output_tail.index("warn")


async def test_run_in_sandbox_blocks_dangerous_commands_before_docker() -> None:
    runner = ScriptedRunner()
    runtime = DockerSandboxRuntime(runner)
    with pytest.raises(SandboxCommandRejected, match="DESTRUCTIVE_REMOVAL"):
        await runtime.run_in_sandbox(
            SandboxInstance(id="i"), SandboxCommand(argv=("bash", "-c", "rm -rf /"))
        )
    assert not any(r.argv[:2] == ["docker", "exec"] for r in runner.requests)


async def test_run_in_sandbox_marks_timeouts() -> None:
    runner = ScriptedRunner().on(("docker", "exec"), timed_out=True)
    runtime = DockerSandboxRuntime(runner)
    outcome = await runtime.run_in_sandbox(
        SandboxInstance(id="i"), SandboxCommand(argv=("sleep", "900"))
    )
    assert outcome.timed_out
    assert outcome.exit_code is None


async def test_cleanup_removes_container_best_effort() -> None:
    runner = ScriptedRunner().on(("docker", "rm"), exit_code=1, stderr_tail="gone")
    runtime = DockerSandboxRuntime(runner)
    await runtime.cleanup(SandboxInstance(id="factory-sandbox-gen-47-v1"))
    assert runner.requests[0].argv == (
        "docker",
        "rm",
        "-f",
        "factory-sandbox-gen-47-v1",
    )
