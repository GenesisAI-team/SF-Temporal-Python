"""Temporal tests for the extended IssueWorkflow PR-production pipeline (GEN-47).

Acceptance: with the pipeline enabled the workflow advances through
PLANNING -> PREPARING -> IMPLEMENTING -> VERIFYING -> REVIEWING -> PR_READY
with one audit line per phase (never duplicated by retries, never duplicated
PRs when one already exists), functional failures resolve to BLOCKED with
stable reason codes, transient agent outages are absorbed by the retry
policy, and disabling the pipeline preserves H1 behavior completely.
"""

import asyncio
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from temporalio.client import WorkflowHandle
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Replayer, Worker

import super_factory.temporal.activities.pipeline as pipeline_activities
from super_factory.contracts.pipeline import (
    AgentRunCommand,
    AgentRunRecord,
    TaskSpecQuery,
    VerificationCommand,
    VerificationOutcome,
)
from super_factory.contracts.scm import PullRequestRef
from super_factory.contracts.workflow_io import IssueWorkflowInput, IssueWorkflowResult
from super_factory.persistence.audit import JsonLinesAuditSink
from super_factory.scm.ports import SCMUnavailable
from super_factory.temporal.activities.audit import (
    record_audit_activity,
    set_audit_sink,
)
from super_factory.temporal.activities.pipeline import (
    plan_run_activity,
    prepare_run_activity,
    publish_pr_activity,
    run_coding_agent_activity,
    verify_run_activity,
)
from super_factory.temporal.activities.selection import select_issue_activity
from super_factory.temporal.workflows.issue import IssueWorkflow

pytestmark = pytest.mark.temporal

TASK_QUEUE = "tq-pipeline-tests"
REPO = "GenesisAI-team/SF-Temporal-Python"


def _input(**overrides: object) -> IssueWorkflowInput:
    fields: dict[str, object] = {
        "issue_id": "GEN-47",
        "repository": REPO,
        "issue_state": "Todo",
        "labels": ("Feature",),
        "title": "H2 \u2014 agente Codex aislado",
        "delivery_id": "234d1a4e-b617-4388-90fe-adc3633d6b72",
        "event_action": "update",
        "event_type": "Issue",
        "selectable_states": ("Todo", "In Progress"),
        "allowed_repositories": (REPO,),
        "base_branch": "main",
        "pipeline_enabled": False,
    }
    fields.update(overrides)
    return IssueWorkflowInput(**fields)


class FakeSpecSource:
    async def resolve(self, query: TaskSpecQuery) -> Any:
        from super_factory.contracts.approved_task import ApprovedTaskSpec

        return ApprovedTaskSpec(
            issue_id=query.issue_id,
            spec_version=1,
            repository=query.repository,
            base_branch=query.base_branch,
            objective="Produce an isolated PR",
            acceptance_criteria=["branch and PR exist", "audit trail"],
        )


class FakeGitWorkspaces:
    def __init__(self) -> None:
        self.ensure_calls: list[str] = []
        self.commits: list[str] = []
        self.pushes: list[str] = []

    async def ensure_workspace(
        self, repository: str, base_branch: str, branch_name: str, workspace_path: str
    ) -> Any:
        from super_factory.contracts.scm import WorkspaceStatus

        self.ensure_calls.append(branch_name)
        return WorkspaceStatus(path=workspace_path, existed=False, branch_existed=False)

    async def commit_all(self, workspace_path: str, message: str) -> Any:
        from super_factory.contracts.scm import CommitInfo

        self.commits.append(message)
        return CommitInfo(committed=True, sha="c0ffee", files_committed=2)

    async def push_branch(self, workspace_path: str, branch_name: str) -> Any:
        from super_factory.contracts.scm import PushInfo

        self.pushes.append(branch_name)
        return PushInfo(pushed=True, detail="pushed")

    async def count_commits_ahead(self, workspace_path: str, base_branch: str) -> int:
        return 2


class FakePullRequests:
    def __init__(self, existing: PullRequestRef | None = None) -> None:
        from super_factory.contracts.scm import PullRequestRef as _Ref

        self.existing = existing
        self.open_calls = 0
        self._ref = _Ref

    async def find_open(self, repository: str, head_branch: str) -> PullRequestRef | None:
        return self.existing

    async def open(
        self, repository: str, base_branch: str, head_branch: str, title: str, body: str
    ) -> PullRequestRef:
        self.open_calls += 1
        return self._ref(
            number=13,
            url=f"https://github.com/{repository}/pull/13",
            head_branch=head_branch,
            base_branch=base_branch,
        )


class FakeLedger:
    def __init__(self) -> None:
        self.records: list[Any] = []

    async def runs_for_issue(self, issue_id: str) -> tuple[Any, ...]:

        return tuple(r for r in self.records if r.issue_id == issue_id)

    async def record_run(self, record: Any) -> bool:
        self.records.append(record)
        return True


class FakeAgent:
    def __init__(self, outcomes: list[Any]) -> None:
        self.outcomes = list(outcomes)
        self.calls = 0

    async def run(self, command: AgentRunCommand) -> Any:
        self.calls += 1
        result = self.outcomes[min(self.calls, len(self.outcomes)) - 1]
        if isinstance(result, BaseException):
            raise result
        return result


class FakeVerifier:
    def __init__(self, outcome: Any) -> None:
        self.outcome = outcome

    async def run(self, command: VerificationCommand) -> Any:
        return self.outcome


@pytest.fixture
def artifacts(tmp_path: Path) -> tuple[Any, Any]:
    ledger_path = tmp_path / "audit.jsonl"
    set_audit_sink(JsonLinesAuditSink(ledger_path))
    run_ledger = FakeLedger()
    try:
        yield ledger_path, run_ledger
    finally:
        set_audit_sink(None)


def _wire_ports(
    agent: FakeAgent,
    verifier: FakeVerifier,
    git: FakeGitWorkspaces | None = None,
    pulls: FakePullRequests | None = None,
    ledger: FakeLedger | None = None,
    spec_source: FakeSpecSource | None = None,
) -> FakeGitWorkspaces:
    git = git or FakeGitWorkspaces()
    pulls = pulls or FakePullRequests()
    ledger = ledger or FakeLedger()
    spec_source = spec_source or FakeSpecSource()
    pipeline_activities.set_task_spec_source(spec_source)
    pipeline_activities.set_git_workspaces(git)
    pipeline_activities.set_pull_request_service(pulls)
    pipeline_activities.set_run_ledger(ledger)
    pipeline_activities.set_coding_agent(agent)
    pipeline_activities.set_verification_runner(verifier)
    return git


@pytest.fixture(autouse=True)
def _reset_ports() -> Iterator[None]:
    try:
        yield
    finally:
        pipeline_activities.reset_pipeline_ports()


async def _run(env: Any, data: IssueWorkflowInput, workflow_id: str) -> IssueWorkflowResult:
    async with Worker(
        env.client,
        task_queue=TASK_QUEUE,
        workflows=[IssueWorkflow],
        activities=[
            select_issue_activity,
            record_audit_activity,
            plan_run_activity,
            prepare_run_activity,
            run_coding_agent_activity,
            verify_run_activity,
            publish_pr_activity,
        ],
    ):
        return await env.client.execute_workflow(
            IssueWorkflow.run,
            data,
            id=workflow_id,
            task_queue=TASK_QUEUE,
            memo={"issue_id": data.issue_id},
        )


def _phases(path: Path) -> list[str]:
    events: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        entry = json.loads(line)
        events.append(f"{entry['event_action']}:{entry['workflow_state']}:{entry['selection_outcome']}")
    return events


async def test_pipeline_happy_path_reaches_pr_ready(artifacts: tuple[Any, Any]) -> None:
    ledger_path, run_ledger = artifacts
    agent = FakeAgent(
        [AgentRunRecord(completed=True, commands=("codex exec",), evidence=("pass",))]
    )
    verifier = FakeVerifier(
        VerificationOutcome(passed=True, commands=("pytest",), evidence=("ok",))
    )
    git = _wire_ports(agent, verifier, ledger=run_ledger)
    pulls_ok = FakePullRequests()
    pipeline_activities.set_pull_request_service(pulls_ok)
    async with await WorkflowEnvironment.start_time_skipping() as env:
        result = await _run(env, _input(pipeline_enabled=True), "issue-GEN-47a")
    assert result.workflow_state == "PR_READY"
    assert result.pull_request_url == "https://github.com/GenesisAI-team/SF-Temporal-Python/pull/13"
    assert result.pull_request_number == 13
    assert agent.calls == 1
    assert verifier is not None
    assert git.ensure_calls == ["feat/gen-47-h2-agente-codex-aislado"]
    assert git.pushes == ["feat/gen-47-h2-agente-codex-aislado"]
    assert pulls_ok.open_calls == 1
    events = _phases(ledger_path)
    for state in ("PLANNING", "PREPARING", "IMPLEMENTING", "VERIFYING", "REVIEWING", "PR_READY"):
        assert f"pipeline:{state}:PHASE_OK" in events, state
    assert len(run_ledger.records) == 1


async def test_pipeline_agent_failure_blocks_without_publishing(
    artifacts: tuple[Any, Any],
) -> None:
    ledger_path, run_ledger = artifacts
    agent = FakeAgent(
        [
            AgentRunRecord(
                completed=False,
                failure_code="AGENT_FAILED",
                failure_detail="package missing",
            )
        ]
    )
    verifier = FakeVerifier(VerificationOutcome(passed=True))
    git = _wire_ports(agent, verifier, ledger=run_ledger)
    pulls = FakePullRequests()
    pipeline_activities.set_pull_request_service(pulls)
    async with await WorkflowEnvironment.start_time_skipping() as env:
        result = await _run(env, _input(pipeline_enabled=True), "issue-GEN-47b")
    assert result.workflow_state == "BLOCKED"
    assert result.blocking_reasons == ("AGENT_FAILED: package missing",)
    assert pulls.open_calls == 0
    assert git.pushes == []
    events = _phases(ledger_path)
    assert "pipeline:IMPLEMENTING:PHASE_OK" not in events
    assert "pipeline:BLOCKED:PHASE_BLOCKED" in events


async def test_pipeline_budget_exhausted_blocks(artifacts: tuple[Any, Any]) -> None:
    _, run_ledger = artifacts
    from super_factory.contracts.run_ledger import PipelineRunRecord

    run_ledger.records.extend(
        (
            PipelineRunRecord(
                run_key="GEN-47-v2",
                issue_id="GEN-47",
                spec_version=2,
                repository=REPO,
                branch_name="feat/o",
                recorded_at="t",
                outcome="PREPARED",
            ),
            PipelineRunRecord(
                run_key="GEN-47-v3",
                issue_id="GEN-47",
                spec_version=3,
                repository=REPO,
                branch_name="feat/o",
                recorded_at="t",
                outcome="PREPARED",
            ),
        )
    )
    agent = FakeAgent([AgentRunRecord(completed=True)])
    verifier = FakeVerifier(VerificationOutcome(passed=True))
    _wire_ports(agent, verifier, ledger=run_ledger)
    async with await WorkflowEnvironment.start_time_skipping() as env:
        result = await _run(env, _input(pipeline_enabled=True), "issue-GEN-47c")
    assert result.workflow_state == "BLOCKED"
    assert any(
        reason.startswith("BUDGET_EXHAUSTED") for reason in result.blocking_reasons
    )


async def test_pipeline_planning_unavailable_blocks(artifacts: tuple[Any, Any]) -> None:
    ledger_path, _ = artifacts
    from super_factory.planning.ports import SpecSourceUnavailable

    class _Unconfigured:
        async def resolve(self, query: TaskSpecQuery) -> Any:
            raise SpecSourceUnavailable("no task spec source is configured")

    agent = FakeAgent([AgentRunRecord(completed=True)])
    verifier = FakeVerifier(VerificationOutcome(passed=True))
    _wire_ports(agent, verifier, spec_source=_Unconfigured())
    async with await WorkflowEnvironment.start_time_skipping() as env:
        result = await _run(env, _input(pipeline_enabled=True), "issue-GEN-47d")
    assert result.workflow_state == "BLOCKED"
    assert any(
        reason.startswith("SPEC_SOURCE_UNAVAILABLE") for reason in result.blocking_reasons
    )
    assert not any("PREPARING" in event for event in _phases(ledger_path))


async def test_pipeline_verification_failure_blocks(artifacts: tuple[Any, Any]) -> None:
    _, run_ledger = artifacts
    agent = FakeAgent([AgentRunRecord(completed=True, commands=("codex exec",))])
    verifier = FakeVerifier(
        VerificationOutcome(
            passed=False, failure_code="VERIFICATION_FAILED", failure_detail="1 failed"
        )
    )
    git = _wire_ports(agent, verifier, ledger=run_ledger)
    pulls = FakePullRequests()
    pipeline_activities.set_pull_request_service(pulls)
    async with await WorkflowEnvironment.start_time_skipping() as env:
        result = await _run(env, _input(pipeline_enabled=True), "issue-GEN-47e")
    assert result.workflow_state == "BLOCKED"
    assert result.blocking_reasons == ("VERIFICATION_FAILED: 1 failed",)
    assert pulls.open_calls == 0
    assert git.pushes == []


async def test_existing_pr_is_reused_not_duplicated(artifacts: tuple[Any, Any]) -> None:
    _, run_ledger = artifacts
    agent = FakeAgent([AgentRunRecord(completed=True, commands=("codex exec",))])
    verifier = FakeVerifier(VerificationOutcome(passed=True))
    git = _wire_ports(agent, verifier, ledger=run_ledger)
    pulls = FakePullRequests(
        existing=PullRequestRef(
            number=5,
            url="https://github.com/GenesisAI-team/SF-Temporal-Python/pull/5",
            head_branch="feat/gen-47-h2-agente-codex-aislado",
            base_branch="main",
        )
    )
    pipeline_activities.set_pull_request_service(pulls)
    async with await WorkflowEnvironment.start_time_skipping() as env:
        result = await _run(env, _input(pipeline_enabled=True), "issue-GEN-47f")
    assert result.workflow_state == "PR_READY"
    assert result.pull_request_number == 5
    assert pulls.open_calls == 0
    # the branch is still idempotently committed/pushed (reuse scenario evidence)
    assert len(git.pushes) == 1


async def test_transient_agent_outage_is_absorbed_by_retries(
    artifacts: tuple[Any, Any],
) -> None:
    ledger_path, _ = artifacts
    from super_factory.sandbox.ports import SandboxUnavailable

    agent = FakeAgent(
        [
            SandboxUnavailable("docker daemon con hiccup"),
            AgentRunRecord(completed=True, commands=("codex exec",), evidence=("pass",)),
        ]
    )
    verifier = FakeVerifier(VerificationOutcome(passed=True))
    _wire_ports(agent, verifier)
    pipeline_activities.set_pull_request_service(FakePullRequests())
    async with await WorkflowEnvironment.start_time_skipping() as env:
        result = await _run(env, _input(pipeline_enabled=True), "issue-GEN-47g")
    assert result.workflow_state == "PR_READY"
    assert agent.calls == 2
    events = _phases(ledger_path)
    assert events.count("pipeline:IMPLEMENTING:PHASE_OK") == 1


def test_publish_service_failure_exhausted_retries_fail_workflow(
    artifacts: tuple[Any, Any],
) -> None:
    """Runs in its own event loop: Windows + activity-retry exhaustion + the
    pytest-asyncio loop have proven unreliable together for this scenario
    (the same scenario completes promptly in a dedicated loop)."""
    asyncio.run(_publish_failure_scenario())


async def _publish_failure_scenario() -> None:
    agent = FakeAgent([AgentRunRecord(completed=True, commands=("codex exec",))])
    verifier = FakeVerifier(VerificationOutcome(passed=True))

    class _BrokenPulls(FakePullRequests):
        async def open(
            self, repository: str, base_branch: str, head_branch: str, title: str, body: str
        ) -> PullRequestRef:
            raise SCMUnavailable("gh down")

    git = _wire_ports(agent, verifier)
    pipeline_activities.set_pull_request_service(_BrokenPulls())
    async with await WorkflowEnvironment.start_time_skipping() as env, Worker(
        env.client,
        task_queue=TASK_QUEUE,
        workflows=[IssueWorkflow],
        activities=[
            select_issue_activity,
            record_audit_activity,
            plan_run_activity,
            prepare_run_activity,
            run_coding_agent_activity,
            verify_run_activity,
            publish_pr_activity,
        ],
    ):
        handle: WorkflowHandle = await env.client.start_workflow(
            IssueWorkflow.run,
            _input(pipeline_enabled=True),
            id="issue-GEN-47h",
            task_queue=TASK_QUEUE,
        )
        try:
            await asyncio.wait_for(handle.result(), timeout=90)
            pytest.fail("workflow should have failed, not completed")
        except Exception as failure:
            cause = failure
            while cause.__cause__ is not None:
                cause = cause.__cause__
            text = str(cause)
    assert "gh down" in text, text
    assert len(git.pushes) >= 3


async def test_pipeline_empty_changeset_blocks(artifacts: tuple[Any, Any]) -> None:
    _, run_ledger = artifacts
    agent = FakeAgent([AgentRunRecord(completed=True, commands=("codex exec",))])
    verifier = FakeVerifier(VerificationOutcome(passed=True))

    class _EmptyGit(FakeGitWorkspaces):
        async def count_commits_ahead(self, workspace_path: str, base_branch: str) -> int:
            return 0

    _wire_ports(agent, verifier, git=_EmptyGit(), ledger=run_ledger)
    pipeline_activities.set_pull_request_service(FakePullRequests())
    async with await WorkflowEnvironment.start_time_skipping() as env:
        result = await _run(env, _input(pipeline_enabled=True), "issue-GEN-47k")
    assert result.workflow_state == "BLOCKED"
    assert any(reason.startswith("CHANGES_EMPTY") for reason in result.blocking_reasons)


async def test_disabled_pipeline_keeps_h1_behavior(artifacts: tuple[Any, Any]) -> None:
    ledger_path, _ = artifacts
    agent = FakeAgent([AgentRunRecord(completed=True)])
    verifier = FakeVerifier(VerificationOutcome(passed=True))
    _wire_ports(agent, verifier)
    async with await WorkflowEnvironment.start_time_skipping() as env:
        result = await _run(env, _input(), "issue-GEN-47i")
    assert result.workflow_state == "READY"
    assert agent.calls == 0
    events = _phases(ledger_path)
    assert events == ["update:READY:SELECTED"]


async def test_pipeline_history_replays_deterministically(
    artifacts: tuple[Any, Any],
) -> None:
    _, run_ledger = artifacts
    agent = FakeAgent(
        [AgentRunRecord(completed=True, commands=("codex exec",), evidence=("pass",))]
    )
    verifier = FakeVerifier(VerificationOutcome(passed=True))
    git = _wire_ports(agent, verifier, ledger=run_ledger)
    pipeline_activities.set_pull_request_service(FakePullRequests())
    async with await WorkflowEnvironment.start_time_skipping() as env, Worker(
        env.client,
        task_queue=TASK_QUEUE,
        workflows=[IssueWorkflow],
        activities=[
            select_issue_activity,
            record_audit_activity,
            plan_run_activity,
            prepare_run_activity,
            run_coding_agent_activity,
            verify_run_activity,
            publish_pr_activity,
        ],
    ):
        handle = await env.client.start_workflow(
            IssueWorkflow.run,
            _input(pipeline_enabled=True),
            id="issue-GEN-47j",
            task_queue=TASK_QUEUE,
        )
        await handle.result()
        history = await handle.fetch_history()
    assert git.pushes == ["feat/gen-47-h2-agente-codex-aislado"]
    await Replayer(workflows=[IssueWorkflow]).replay_workflow(history)
