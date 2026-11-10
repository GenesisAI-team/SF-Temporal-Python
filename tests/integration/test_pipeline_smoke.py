"""H2 smoke: IssueWorkflow PR-production end-to-end on the REAL Temporal stack.

Requires the docker compose stack plus git, and proves the H2 wiring with
ZERO real tokens or network credentials:

- REAL Temporal server + real worker (``run_worker``) with real activity code.
- REAL planning: an approved ``ApprovedTaskSpec`` JSON file (the input an
  operator produces from an approved Linear issue).
- REAL git: workspace creation, commit and push into a LOCAL bare remote
  (no GitHub, no tokens; ``git push`` over the filesystem).
- SIMULATED ports (explicit test doubles, never reported as real):
  sandbox runtime, coding agent, verification runner and the GitHub
  pull-request service.

Success = the approved issue produced exactly one pushed branch + one PR
reference with a complete per-phase audit trail; a duplicate delivery-id run
can never start again (REJECT_DUPLICATE) and the run ledger keeps one entry
per run key.
"""

import asyncio
import json
import subprocess
import uuid
from pathlib import Path
from typing import Any

import pytest
from temporalio.client import Client

import super_factory.temporal.activities.pipeline as pipeline_activities
from super_factory.config.settings import get_settings
from super_factory.contracts.pipeline import (
    AgentRunCommand,
    AgentRunRecord,
    VerificationCommand,
    VerificationOutcome,
)
from super_factory.contracts.workflow_io import IssueWorkflowInput
from super_factory.integrations.temporal_sdk.starter import IssueWorkflowStarter
from super_factory.persistence.audit import JsonLinesAuditSink
from super_factory.temporal.activities.audit import set_audit_sink
from super_factory.temporal.workers.queues import TASK_QUEUE_ORCHESTRATION
from super_factory.temporal.workers.run import run_worker
from super_factory.temporal.workflows.issue import IssueWorkflow
from tests.integration.test_worker_roundtrip import _connect_when_namespace_ready

pytestmark = pytest.mark.integration

REPO_LABEL = "GenesisAI-team/SF-Temporal-Python"
TITLE_SUFFIX = "H2 smoke agente produce PR"
TASK_QUEUE = TASK_QUEUE_ORCHESTRATION


class _LocalEnsureGit:
    """Real-git adapter whose clone step points at a local bare remote."""

    def __init__(self, real: Any, bare_path: Path) -> None:
        self._real = real
        self._bare = bare_path

    async def ensure_workspace(
        self, repository: str, base_branch: str, branch_name: str, workspace_path: str
    ) -> Any:
        return await self._real.ensure_workspace(
            repository=str(self._bare),
            base_branch=base_branch,
            branch_name=branch_name,
            workspace_path=workspace_path,
        )

    def __getattr__(self, name: str) -> Any:
        return getattr(self._real, name)


class _SandboxlessAgent:
    """Simulated coding agent: writes one evidence file in the workspace."""

    def __init__(self) -> None:
        self.commands: list[AgentRunCommand] = []

    async def run(self, command: AgentRunCommand) -> AgentRunRecord:
        self.commands.append(command)
        evidence = Path(command.workspace_path) / "FACTORY-EVIDENCE.md"
        evidence.write_text(
            f"simulated agent run {command.run_key} for {command.issue_id}\n",
            encoding="utf-8",
        )
        return AgentRunRecord(
            completed=True,
            commands=("codex exec (simulated in smoke)",),
            evidence=(f"evidence file written: {evidence.name}",),
        )


class _PassingVerifier:
    """Simulated verification runner that records the attempt."""

    def __init__(self) -> None:
        self.commands: list[VerificationCommand] = []

    async def run(self, command: VerificationCommand) -> VerificationOutcome:
        self.commands.append(command)
        return VerificationOutcome(
            passed=True,
            commands=("uv run pytest -q (simulated in smoke)",),
            evidence=("1 passed",),
        )


class _HubFake:
    """Simulated GitHub: remembers opened PRs by head branch (find_open works)."""

    def __init__(self) -> None:
        self.opened: dict[str, tuple[int, str]] = {}

    async def find_open(self, repository: str, head_branch: str) -> Any:
        from super_factory.contracts.scm import PullRequestRef

        record = self.opened.get(head_branch)
        if record is None:
            return None
        number, url = record
        return PullRequestRef(
            number=number, url=url, head_branch=head_branch, base_branch="main"
        )

    async def open(
        self, repository: str, base_branch: str, head_branch: str, title: str, body: str
    ) -> Any:
        from super_factory.contracts.scm import PullRequestRef

        number = 101 + len(self.opened)
        url = f"https://git.example/{repository}/pull/{number}"
        self.opened[head_branch] = (number, url)
        return PullRequestRef(
            number=number, url=url, head_branch=head_branch, base_branch=base_branch
        )


def _git(*args: str, cwd: Path | None = None) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def _make_bare_remote(tmp_path: Path) -> Path:
    """Build a tiny real repo (one main commit) cloned into a local bare remote."""
    source = tmp_path / "source"
    source.mkdir(parents=True)
    _git("init", "-b", "main", cwd=source)
    _git("config", "user.email", "factory@local", cwd=source)
    _git("config", "user.name", "Factory Smoke", cwd=source)
    (source / "README.md").write_text("# smoke source\n", encoding="utf-8")
    _git("add", "-A", cwd=source)
    _git("commit", "-m", "chore: smoke base", cwd=source)
    bare = tmp_path / "remote.git"
    _git("clone", "--bare", str(source), str(bare))
    return bare


class Harness:
    """Smoke harness: unique issue id, settings paths and expectations."""

    def __init__(self, tmp_path: Path, issue_id: str) -> None:
        self.tmp_path = tmp_path
        self.issue_id = issue_id
        self.branch = f"feat/{issue_id.lower()}-h2-smoke-agente-produce-pr"


@pytest.fixture
def harness(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Harness:
    """Point every settings path at tmp and inject the approved spec file."""
    unique_issue = f"GEN-{47000 + uuid.uuid4().int % 9000}"
    monkeypatch.setenv("SF_FACTORY_WORKSPACE_ROOT", str(tmp_path / "workspaces"))
    monkeypatch.setenv("SF_FACTORY_RUN_LEDGER_PATH", str(tmp_path / "runs.jsonl"))
    monkeypatch.setenv("SF_AUDIT_LOG_PATH", str(tmp_path / "audit.jsonl"))
    monkeypatch.setenv("SF_FACTORY_PIPELINE_ENABLED", "true")
    monkeypatch.setenv("SF_LINEAR_TARGET_REPOSITORY", REPO_LABEL)
    spec_file = tmp_path / "approved-spec.json"
    spec_file.write_text(
        json.dumps(
            {
                "issue_id": unique_issue,
                "spec_version": 1,
                "repository": REPO_LABEL,
                "base_branch": "main",
                "objective": "H2 smoke: isolated agent produces a PR",
                "acceptance_criteria": [
                    "one branch per issue",
                    "one PR per issue",
                    "audit trail per phase",
                ],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("SF_FACTORY_TASK_SPEC_PATH", str(spec_file))
    return Harness(tmp_path=tmp_path, issue_id=unique_issue)


def _issue_input(issue_id: str) -> IssueWorkflowInput:
    return IssueWorkflowInput(
        issue_id=issue_id,
        repository=REPO_LABEL,
        issue_state="Todo",
        labels=("Feature",),
        title=f"{TITLE_SUFFIX}",
        delivery_id=str(uuid.uuid4()),
        event_action="update",
        event_type="Issue",
        selectable_states=("Todo", "In Progress"),
        allowed_repositories=(REPO_LABEL,),
        base_branch="main",
        pipeline_enabled=True,
    )


async def _run_issue_workflow(client: Client, data: IssueWorkflowInput, workflow_id: str) -> Any:
    return await asyncio.wait_for(
        client.execute_workflow(
            IssueWorkflow.run,
            data,
            id=workflow_id,
            task_queue=TASK_QUEUE,
        ),
        timeout=120,
    )


async def test_h2_pipeline_produces_branch_and_pr_without_tokens(harness: Harness) -> None:
    tmp_path = harness.tmp_path
    bare = _make_bare_remote(tmp_path)
    real_git = pipeline_activities.GitCommandLineRunner(
        pipeline_activities.SubprocessCommandRunner()
    )
    set_audit_sink(JsonLinesAuditSink(tmp_path / "audit.jsonl"))
    pipeline_activities.set_git_workspaces(_LocalEnsureGit(real_git, bare))
    pipeline_activities.set_run_ledger(
        pipeline_activities.JsonLinesRunLedger(tmp_path / "runs.jsonl")
    )
    agent = _SandboxlessAgent()
    verifier = _PassingVerifier()
    hub = _HubFake()
    pipeline_activities.set_coding_agent(agent)
    pipeline_activities.set_verification_runner(verifier)
    pipeline_activities.set_pull_request_service(hub)
    data = _issue_input(harness.issue_id)
    try:
        settings = get_settings()
        client = await _connect_when_namespace_ready(
            settings.temporal_address, settings.temporal_namespace
        )
        worker_task = asyncio.create_task(run_worker())
        recovered_run: Any = None
        try:
            result = await _run_issue_workflow(client, data, f"issue-{data.issue_id}")
            assert result.workflow_state == "PR_READY", result.blocking_reasons
            assert result.pull_request_number == 101
            assert len(hub.opened) == 1
            # Duplicate delivery for the same issue: the production starter
            # adapter (REJECT_DUPLICATE) must recover, never start a second run.
            duplicate = _issue_input(harness.issue_id)
            starter = IssueWorkflowStarter(client=client, task_queue=TASK_QUEUE)
            recovered_run = await starter.start_or_recover(duplicate)
        finally:
            worker_task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await worker_task

        assert recovered_run is not None and recovered_run.started is False
        assert recovered_run.workflow_id == f"issue-{data.issue_id}"
        heads = _git("ls-remote", "--heads", str(bare))
        assert f"refs/heads/{harness.branch}" in heads
        pushed_commits = _git("log", "--oneline", "--branches", cwd=bare)
        assert (
            f"feat({harness.issue_id.lower()}): H2 smoke: isolated agent produces a PR"
            in pushed_commits
        )
        assert len(agent.commands) == 1
        assert len(verifier.commands) == 1

        audit_lines = (tmp_path / "audit.jsonl").read_text(encoding="utf-8").splitlines()
        phases = [json.loads(line)["event_type"] for line in audit_lines]
        expected_phases = ("PLANNING", "PREPARING", "IMPLEMENTING", "VERIFYING", "REVIEWING")
        for phase in expected_phases:
            assert phases.count(phase) == 1, phase
        deployments = [json.loads(line) for line in audit_lines]
        assert any(entry["selection_outcome"] == "SELECTED" for entry in deployments)
        ledger_lines = (tmp_path / "runs.jsonl").read_text(encoding="utf-8").splitlines()
        assert len(ledger_lines) == 1
        run_record = json.loads(ledger_lines[0])
        assert run_record["run_key"] == f"{harness.issue_id}-v1"
        assert run_record["branch_name"] == harness.branch
    finally:
        pipeline_activities.reset_pipeline_ports()
        set_audit_sink(None)
