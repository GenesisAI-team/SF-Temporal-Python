"""Temporal tests for the H3 review + bounded repair loop (GEN-52).

Acceptance: a test PR passes/fails according to verified gate evidence, the
independent reviewer (separate from the implementer) judges the changes
against the approved criteria, detected defects activate a bounded repair
loop (no infinite loops), spec drift blocks progress without repair, the
repair budget is hard (attempts never exceed the configured maximum), and
the workflow history replays deterministically.
"""

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
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
from super_factory.contracts.quality import (
    GateOutcome,
    ReviewCommand,
    ReviewFinding,
    ReviewOutcome,
)
from super_factory.contracts.scm import PullRequestRef
from super_factory.contracts.workflow_io import IssueWorkflowInput, IssueWorkflowResult
from super_factory.domain.quality import (
    FINDING_DEFECT,
    FINDING_SPEC_DRIFT,
    REASON_GATE_FAILED,
    REASON_REVIEW_FAILED,
    REASON_REVIEW_REJECTED,
    REASON_SPEC_DRIFT,
)
from super_factory.persistence.audit import JsonLinesAuditSink
from super_factory.temporal.activities.audit import (
    record_audit_activity,
    set_audit_sink,
)
from super_factory.temporal.activities.pipeline import (
    plan_run_activity,
    prepare_run_activity,
    publish_pr_activity,
    review_run_activity,
    run_coding_agent_activity,
    verify_run_activity,
)
from super_factory.temporal.activities.selection import select_issue_activity
from super_factory.temporal.workflows.issue import IssueWorkflow

pytestmark = pytest.mark.temporal

TASK_QUEUE = "tq-h3-tests"
REPO = "GenesisAI-team/SF-Temporal-Python"


def _input(**overrides: object) -> IssueWorkflowInput:
    fields: dict[str, object] = {
        "issue_id": "GEN-52",
        "repository": REPO,
        "issue_state": "Todo",
        "labels": ("Feature",),
        "title": "H3 \u2014 quality gates independientes",
        "delivery_id": "9f2d7a5e-1c3b-4a2d-8e5f-0b6c7d8e9f01",
        "event_action": "update",
        "event_type": "Issue",
        "selectable_states": ("Todo", "In Progress"),
        "allowed_repositories": (REPO,),
        "base_branch": "main",
        "pipeline_enabled": True,
        "max_repair_attempts": 2,
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
            objective="Produce an evidenced PR",
            acceptance_criteria=["gates pass", "review approves"],
            exclusions=["never touch the H1 webhook"],
            constraints=["no auto merge"],
        )


class FakeGitWorkspaces:
    def __init__(self) -> None:
        self.ensure_calls: list[str] = []
        self.pushes: list[str] = []

    async def ensure_workspace(
        self, repository: str, base_branch: str, branch_name: str, workspace_path: str
    ) -> Any:
        from super_factory.contracts.scm import WorkspaceStatus

        self.ensure_calls.append(branch_name)
        return WorkspaceStatus(path=workspace_path, existed=False, branch_existed=False)

    async def commit_all(self, workspace_path: str, message: str) -> Any:
        from super_factory.contracts.scm import CommitInfo

        return CommitInfo(committed=True, sha="c0ffee", files_committed=2)

    async def push_branch(self, workspace_path: str, branch_name: str) -> Any:
        from super_factory.contracts.scm import PushInfo

        self.pushes.append(branch_name)
        return PushInfo(pushed=True, detail="pushed")

    async def count_commits_ahead(self, workspace_path: str, base_branch: str) -> int:
        return 2


class FakePullRequests:
    def __init__(self) -> None:
        self.bodies: list[str] = []
        self.open_calls = 0

    async def find_open(self, repository: str, head_branch: str) -> PullRequestRef | None:
        return None

    async def open(
        self, repository: str, base_branch: str, head_branch: str, title: str, body: str
    ) -> PullRequestRef:
        self.open_calls += 1
        self.bodies.append(body)
        return PullRequestRef(
            number=21,
            url=f"https://github.com/{repository}/pull/21",
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
        self.commands: list[AgentRunCommand] = []

    async def run(self, command: AgentRunCommand) -> Any:
        self.commands.append(command)
        self.calls += 1
        result = self.outcomes[min(self.calls, len(self.outcomes)) - 1]
        if isinstance(result, BaseException):
            raise result
        return result


class FakeVerifier:
    def __init__(self, outcomes: list[Any]) -> None:
        self.outcomes = list(outcomes)
        self.calls = 0
        self.commands: list[VerificationCommand] = []

    async def run(self, command: VerificationCommand) -> Any:
        self.commands.append(command)
        self.calls += 1
        result = self.outcomes[min(self.calls, len(self.outcomes)) - 1]
        if isinstance(result, BaseException):
            raise result
        return result


class FakeReviewer:
    def __init__(self, outcomes: list[Any]) -> None:
        self.outcomes = list(outcomes)
        self.calls = 0
        self.commands: list[ReviewCommand] = []

    async def review(self, command: ReviewCommand) -> Any:
        self.commands.append(command)
        self.calls += 1
        result = self.outcomes[min(self.calls, len(self.outcomes)) - 1]
        if isinstance(result, BaseException):
            raise result
        return result


def _gates_ok() -> VerificationOutcome:
    return VerificationOutcome(
        passed=True,
        commands=("uv run pytest -q", "uv run ruff check .", "uv run mypy src"),
        evidence=("12 passed",),
        gates=(
            GateOutcome(gate="tests", passed=True, commands=("uv run pytest -q",)),
            GateOutcome(gate="lint", passed=True, commands=("uv run ruff check .",)),
            GateOutcome(gate="typecheck", passed=True, commands=("uv run mypy src",)),
        ),
    )


def _gates_failed(detail: str = "1 failed") -> VerificationOutcome:
    return VerificationOutcome(
        passed=False,
        commands=("uv run pytest -q",),
        evidence=("1 failed",),
        gates=(
            GateOutcome(
                gate="tests",
                passed=False,
                commands=("uv run pytest -q",),
                evidence=("1 failed",),
                failure_code=REASON_GATE_FAILED,
                failure_detail=detail,
            ),
        ),
        failure_code="VERIFICATION_FAILED",
        failure_detail=f"tests: {detail}",
    )


def _review_defects() -> ReviewOutcome:
    return ReviewOutcome(
        approved=False,
        findings=(ReviewFinding(kind=FINDING_DEFECT, detail="missing test"),),
        failure_code=REASON_REVIEW_REJECTED,
        failure_detail="DEFECT: missing test",
    )


def _review_drift() -> ReviewOutcome:
    return ReviewOutcome(
        approved=False,
        findings=(
            ReviewFinding(kind=FINDING_DEFECT, detail="style nit"),
            ReviewFinding(kind=FINDING_SPEC_DRIFT, detail="touched the H1 webhook"),
        ),
        spec_drift=True,
        failure_code=REASON_SPEC_DRIFT,
        failure_detail="DEFECT: style nit; SPEC_DRIFT: touched the H1 webhook",
    )


def _review_failed() -> ReviewOutcome:
    return ReviewOutcome(
        approved=False,
        failure_code=REASON_REVIEW_FAILED,
        failure_detail="reviewer produced no verdict",
    )


def _review_ok() -> ReviewOutcome:
    return ReviewOutcome(approved=True)


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
    reviewer: FakeReviewer,
    git: FakeGitWorkspaces | None = None,
    pulls: FakePullRequests | None = None,
    ledger: FakeLedger | None = None,
) -> FakeGitWorkspaces:
    git = git or FakeGitWorkspaces()
    pulls = pulls or FakePullRequests()
    ledger = ledger or FakeLedger()
    pipeline_activities.set_task_spec_source(FakeSpecSource())
    pipeline_activities.set_git_workspaces(git)
    pipeline_activities.set_pull_request_service(pulls)
    pipeline_activities.set_run_ledger(ledger)
    pipeline_activities.set_coding_agent(agent)
    pipeline_activities.set_verification_runner(verifier)
    pipeline_activities.set_reviewer(reviewer)
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
            review_run_activity,
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


def _repair_attempts(path: Path) -> list[str]:
    ids: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        entry = json.loads(line)
        if entry["event_type"] == "REPAIRING":
            ids.append(entry["event_delivery_id"])
    return ids


async def _in_env() -> Any:
    return await WorkflowEnvironment.start_time_skipping()


async def test_evidenced_pr_publishes_after_gates_and_review(
    artifacts: tuple[Any, Any],
) -> None:
    ledger_path, run_ledger = artifacts
    agent = FakeAgent([AgentRunRecord(completed=True, commands=("codex exec",))])
    verifier = FakeVerifier([_gates_ok()])
    reviewer = FakeReviewer([_review_ok()])
    git = _wire_ports(agent, verifier, reviewer, ledger=run_ledger)
    pulls = FakePullRequests()
    pipeline_activities.set_pull_request_service(pulls)
    async with await _in_env() as env:
        result = await _run(env, _input(), "issue-GEN-52a")
    assert result.workflow_state == "PR_READY"
    assert result.pull_request_url.endswith("/pull/21")
    assert agent.calls == 1
    assert verifier.calls == 1
    assert reviewer.calls == 1
    assert git.pushes == ["feat/gen-52-h3-quality-gates-independientes"]
    assert pulls.open_calls == 1
    # the PR body carries the verified gate evidence
    assert "- gate tests: PASSED" in pulls.bodies[0]
    events = _phases(ledger_path)
    for state in ("PLANNING", "PREPARING", "IMPLEMENTING", "VERIFYING", "REVIEWING", "PR_READY"):
        assert f"pipeline:{state}:PHASE_OK" in events, state
    assert "pipeline:BLOCKED:PHASE_BLOCKED" not in events
    # the reviewer command contrasts the approved scope with the gate evidence
    command = reviewer.commands[0]
    assert command.acceptance_criteria == ("gates pass", "review approves")
    assert command.exclusions == ("never touch the H1 webhook",)
    assert command.gate_summaries == (
        "gate tests: PASSED",
        "gate lint: PASSED",
        "gate typecheck: PASSED",
    )
    assert len(run_ledger.records) == 1


async def test_gate_failure_triggers_one_bounded_repair_then_publishes(
    artifacts: tuple[Any, Any],
) -> None:
    ledger_path, _ = artifacts
    agent = FakeAgent(
        [
            AgentRunRecord(completed=True, commands=("codex exec",)),
            AgentRunRecord(completed=True, commands=("codex exec (repair)",)),
        ]
    )
    verifier = FakeVerifier([_gates_failed(), _gates_ok()])
    reviewer = FakeReviewer([_review_ok()])
    _wire_ports(agent, verifier, reviewer)
    pipeline_activities.set_pull_request_service(FakePullRequests())
    async with await _in_env() as env:
        result = await _run(env, _input(), "issue-GEN-52b")
    assert result.workflow_state == "PR_READY"
    assert agent.calls == 2
    assert verifier.calls == 2
    assert reviewer.calls == 1
    # the repair agent session receives exactly the gate failure feedback
    assert agent.commands[1].defects == ("quality gate tests failed: 1 failed",)
    assert agent.commands[0].defects == ()
    attempts = _repair_attempts(ledger_path)
    assert len(attempts) == 1
    assert attempts[0].endswith("#REPAIRING#1")
    events = _phases(ledger_path)
    assert events.count("pipeline:REPAIRING:PHASE_OK") == 1
    assert events.count("pipeline:VERIFYING:PHASE_OK") == 1


async def test_review_defects_trigger_bounded_repair_then_publish(
    artifacts: tuple[Any, Any],
) -> None:
    ledger_path, _ = artifacts
    agent = FakeAgent(
        [
            AgentRunRecord(completed=True),
            AgentRunRecord(completed=True, commands=("codex exec (repair)",)),
        ]
    )
    verifier = FakeVerifier([_gates_ok()])
    reviewer = FakeReviewer([_review_defects(), _review_ok()])
    _wire_ports(agent, verifier, reviewer)
    pipeline_activities.set_pull_request_service(FakePullRequests())
    async with await _in_env() as env:
        result = await _run(env, _input(), "issue-GEN-52c")
    assert result.workflow_state == "PR_READY"
    assert agent.calls == 2
    assert reviewer.calls == 2
    assert agent.commands[1].defects == ("DEFECT: missing test",)
    assert _phases(ledger_path).count("pipeline:REPAIRING:PHASE_OK") == 1


async def test_spec_drift_blocks_without_repair(artifacts: tuple[Any, Any]) -> None:
    ledger_path, _ = artifacts
    agent = FakeAgent([AgentRunRecord(completed=True, commands=("codex exec",))])
    verifier = FakeVerifier([_gates_ok()])
    reviewer = FakeReviewer([_review_drift()])
    _wire_ports(agent, verifier, reviewer)
    pulls = FakePullRequests()
    pipeline_activities.set_pull_request_service(pulls)
    async with await _in_env() as env:
        result = await _run(env, _input(), "issue-GEN-52d")
    assert result.workflow_state == "BLOCKED"
    assert result.blocking_reasons == (
        "SPEC_DRIFT: DEFECT: style nit; SPEC_DRIFT: touched the H1 webhook",
    )
    assert agent.calls == 1
    assert reviewer.calls == 1
    assert pulls.open_calls == 0
    assert _repair_attempts(ledger_path) == []
    events = _phases(ledger_path)
    assert "pipeline:REPAIRING:PHASE_OK" not in events
    assert "pipeline:BLOCKED:PHASE_BLOCKED" in events


async def test_verdictless_review_blocks_without_repair(
    artifacts: tuple[Any, Any],
) -> None:
    ledger_path, _ = artifacts
    agent = FakeAgent([AgentRunRecord(completed=True)])
    verifier = FakeVerifier([_gates_ok()])
    reviewer = FakeReviewer([_review_failed()])
    _wire_ports(agent, verifier, reviewer)
    pipeline_activities.set_pull_request_service(FakePullRequests())
    async with await _in_env() as env:
        result = await _run(env, _input(), "issue-GEN-52e")
    assert result.workflow_state == "BLOCKED"
    assert result.blocking_reasons == ("REVIEW_FAILED: reviewer produced no verdict",)
    assert agent.calls == 1
    assert reviewer.calls == 1
    assert _repair_attempts(ledger_path) == []


async def test_persistent_gate_failures_exhaust_the_repair_budget(
    artifacts: tuple[Any, Any],
) -> None:
    ledger_path, _ = artifacts
    agent = FakeAgent(
        [AgentRunRecord(completed=True, commands=("codex exec",))] * 3
    )
    verifier = FakeVerifier([_gates_failed()])
    reviewer = FakeReviewer([_review_ok()])
    _wire_ports(agent, verifier, reviewer)
    pipeline_activities.set_pull_request_service(FakePullRequests())
    async with await _in_env() as env:
        result = await _run(env, _input(), "issue-GEN-52f")
    assert result.workflow_state == "BLOCKED"
    assert result.blocking_reasons[0].startswith("REPAIR_BUDGET_EXHAUSTED")
    assert "VERIFICATION_FAILED" in result.blocking_reasons[0]
    assert agent.calls == 3
    assert verifier.calls == 3
    assert reviewer.calls == 0
    attempts = _repair_attempts(ledger_path)
    assert attempts[0].endswith("#REPAIRING#1")
    assert attempts[1].endswith("#REPAIRING#2")
    assert len(attempts) == 2


async def test_zero_repair_budget_blocks_at_the_first_gate_failure(
    artifacts: tuple[Any, Any],
) -> None:
    ledger_path, _ = artifacts
    agent = FakeAgent([AgentRunRecord(completed=True)])
    verifier = FakeVerifier([_gates_failed()])
    reviewer = FakeReviewer([_review_ok()])
    _wire_ports(agent, verifier, reviewer)
    pipeline_activities.set_pull_request_service(FakePullRequests())
    async with await _in_env() as env:
        result = await _run(env, _input(max_repair_attempts=0), "issue-GEN-52g")
    assert result.workflow_state == "BLOCKED"
    assert result.blocking_reasons[0].startswith("REPAIR_BUDGET_EXHAUSTED")
    assert agent.calls == 1
    assert verifier.calls == 1
    assert _repair_attempts(ledger_path) == []


async def test_repair_budget_also_bounds_review_rejections(
    artifacts: tuple[Any, Any],
) -> None:
    _ledger_path, _ = artifacts
    agent = FakeAgent([AgentRunRecord(completed=True)] * 3)
    verifier = FakeVerifier([_gates_ok()])
    reviewer = FakeReviewer([_review_defects()])
    _wire_ports(agent, verifier, reviewer)
    pipeline_activities.set_pull_request_service(FakePullRequests())
    async with await _in_env() as env:
        result = await _run(env, _input(max_repair_attempts=2), "issue-GEN-52h")
    assert result.workflow_state == "BLOCKED"
    assert result.blocking_reasons[0].startswith("REPAIR_BUDGET_EXHAUSTED")
    assert "REVIEW_REJECTED" in result.blocking_reasons[0]
    assert agent.calls == 3
    assert reviewer.calls == 3


async def test_failing_repair_session_blocks(artifacts: tuple[Any, Any]) -> None:
    ledger_path, _ = artifacts
    agent = FakeAgent(
        [
            AgentRunRecord(completed=True),
            AgentRunRecord(
                completed=False,
                failure_code="AGENT_FAILED",
                failure_detail="repair session crashed",
            ),
        ]
    )
    verifier = FakeVerifier([_gates_failed()])
    reviewer = FakeReviewer([_review_ok()])
    _wire_ports(agent, verifier, reviewer)
    pipeline_activities.set_pull_request_service(FakePullRequests())
    async with await _in_env() as env:
        result = await _run(env, _input(), "issue-GEN-52i")
    assert result.workflow_state == "BLOCKED"
    assert result.blocking_reasons == ("AGENT_FAILED: repair session crashed",)
    assert agent.calls == 2
    assert _repair_attempts(ledger_path) != []


async def test_repair_history_replays_deterministically(
    artifacts: tuple[Any, Any],
) -> None:
    _, _ = artifacts
    agent = FakeAgent(
        [AgentRunRecord(completed=True), AgentRunRecord(completed=True)]
    )
    verifier = FakeVerifier([_gates_failed(), _gates_ok()])
    reviewer = FakeReviewer([_review_ok()])
    git = _wire_ports(agent, verifier, reviewer)
    pipeline_activities.set_pull_request_service(FakePullRequests())
    async with await _in_env() as env, Worker(
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
            review_run_activity,
            publish_pr_activity,
        ],
    ):
        handle = await env.client.start_workflow(
            IssueWorkflow.run,
            _input(),
            id="issue-GEN-52j",
            task_queue=TASK_QUEUE,
        )
        await handle.result()
        history = await handle.fetch_history()
    assert agent.calls == 2
    assert git.pushes == ["feat/gen-52-h3-quality-gates-independientes"]
    await Replayer(workflows=[IssueWorkflow]).replay_workflow(history)
