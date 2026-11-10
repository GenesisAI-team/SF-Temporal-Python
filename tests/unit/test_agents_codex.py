"""Tests for the Codex CLI coding-agent adapter (GEN-47) against a fake sandbox.

Acceptance: the agent runs one sandboxed codex session per command (prompt
transported via stdin, never argv), maps the sandbox outcome into an
AgentRunRecord (completed / failed / safety-rejected), and always cleans up
the ephemeral sandbox — including on failure paths.
"""

import pytest

from super_factory.agents.codex_cli import CodexCliAgent
from super_factory.contracts.pipeline import AgentRunCommand
from super_factory.contracts.sandboxing import (
    SandboxCommand,
    SandboxCommandOutcome,
    SandboxInstance,
    SandboxSpec,
)
from super_factory.domain.pipeline import REASON_AGENT_BLOCKED, REASON_AGENT_FAILED
from super_factory.sandbox.ports import SandboxCommandRejected, SandboxUnavailable
from tests.unit.command_runner_stubs import ScriptedRunner


class FakeSandboxRuntime:
    """SandboxRuntime double: scripted outcomes per invocation, records calls."""

    def __init__(self) -> None:
        self.started_specs: list[SandboxSpec] = []
        self.commands: list[SandboxCommand] = []
        self.cleaned: list[str] = []
        self.raise_on_start: Exception | None = None
        self.raise_on_run: Exception | None = None
        self.outcome = SandboxCommandOutcome(exit_code=0, output_tail="done")

    async def ensure_sandbox(self, spec: SandboxSpec) -> SandboxInstance:
        if self.raise_on_start is not None:
            raise self.raise_on_start
        self.started_specs.append(spec)
        return SandboxInstance(id=f"factory-sandbox-{spec.run_key.lower()}")

    async def run_in_sandbox(
        self, instance: SandboxInstance, command: SandboxCommand
    ) -> SandboxCommandOutcome:
        if self.raise_on_run is not None:
            raise self.raise_on_run
        self.commands.append(command)
        return self.outcome

    async def cleanup(self, instance: SandboxInstance) -> None:
        self.cleaned.append(instance.id)


def _command(**overrides: object) -> AgentRunCommand:
    fields: dict[str, object] = {
        "issue_id": "GEN-47",
        "repository": "a/b",
        "spec_version": 1,
        "run_key": "GEN-47-v1",
        "branch_name": "feat/gen-47-goal",
        "base_branch": "main",
        "objective": "Do the thing",
        "acceptance_criteria": ("works", "tested"),
        "exclusions": (),
        "constraints": (),
        "dependencies": (),
        "workspace_path": "/ws/gen-47-v1",
    }
    fields.update(overrides)
    return AgentRunCommand(**fields)


async def test_agent_runs_codex_session_inside_sandbox_and_cleans_up() -> None:
    sandbox = FakeSandboxRuntime()
    agent = CodexCliAgent(sandbox_runtime=sandbox)
    record = await agent.run(_command())
    assert record.completed is True
    assert record.failure_code == ""
    assert record.commands and "codex" in record.commands[0]
    assert "done" in "".join(record.evidence)
    assert len(sandbox.started_specs) == 1
    spec = sandbox.started_specs[0]
    assert spec.run_key == "GEN-47-v1"
    assert spec.workspace_path == "/ws/gen-47-v1"
    assert spec.network_isolated is True
    assert sandbox.cleaned == ["factory-sandbox-gen-47-v1"]


async def test_agent_transports_prompt_via_stdin_not_argv() -> None:
    sandbox = FakeSandboxRuntime()
    agent = CodexCliAgent(sandbox_runtime=sandbox)
    await agent.run(_command())
    command = sandbox.commands[0]
    assert command.argv == ("codex", "exec")
    prompt = command.stdin_payload
    assert prompt is not None
    for needle in ("Do the thing", "- works", "- tested", "feat/gen-47-goal", "main"):
        assert needle in prompt
    assert "/workspace" in prompt
    assert "no network" in prompt


async def test_agent_maps_nonzero_exec_to_failure_and_still_cleans_up() -> None:
    sandbox = FakeSandboxRuntime()
    sandbox.outcome = SandboxCommandOutcome(exit_code=5, output_tail="pytest failed")
    agent = CodexCliAgent(sandbox_runtime=sandbox)
    record = await agent.run(_command())
    assert record.completed is False
    assert record.failure_code == REASON_AGENT_FAILED
    assert "pytest failed" in record.failure_detail
    assert len(sandbox.cleaned) == 1


async def test_agent_maps_safety_rejection_to_blocked_record() -> None:
    sandbox = FakeSandboxRuntime()
    sandbox.raise_on_run = SandboxCommandRejected(
        code="DESTRUCTIVE_REMOVAL", detail="rm -rf against root, home or glob targets"
    )
    agent = CodexCliAgent(sandbox_runtime=sandbox)
    record = await agent.run(_command())
    assert record.completed is False
    assert record.failure_code == REASON_AGENT_BLOCKED
    assert "DESTRUCTIVE_REMOVAL" in record.failure_detail
    assert len(sandbox.cleaned) == 1


async def test_agent_propagates_sandbox_unavailability_for_retries() -> None:
    sandbox = FakeSandboxRuntime()
    sandbox.raise_on_start = SandboxUnavailable("docker daemon down")
    agent = CodexCliAgent(sandbox_runtime=sandbox)
    with pytest.raises(SandboxUnavailable, match="docker daemon down"):
        await agent.run(_command())
    assert sandbox.cleaned == []


async def test_agent_propagates_outage_mid_run_but_cleans_up() -> None:
    sandbox = FakeSandboxRuntime()
    sandbox.raise_on_run = SandboxUnavailable("docker exec lost")
    agent = CodexCliAgent(sandbox_runtime=sandbox)
    with pytest.raises(SandboxUnavailable, match="docker exec lost"):
        await agent.run(_command())
    assert sandbox.cleaned == ["factory-sandbox-gen-47-v1"]


def test_agent_platform_parameterization() -> None:
    sandbox = FakeSandboxRuntime()
    agent = CodexCliAgent(
        sandbox_runtime=sandbox,
        platform="codex-cli",
        sandbox_image="ghcr.io/genesis/sandbox-codex:0.42",
    )
    assert agent.platform == "codex-cli"
    assert agent.sandbox_image == "ghcr.io/genesis/sandbox-codex:0.42"


def test_scripted_runner_helper_is_connected() -> None:
    assert ScriptedRunner().stdin_seen == []
