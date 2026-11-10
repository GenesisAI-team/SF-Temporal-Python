"""Direct tests for the H2 pipeline activities and their port wiring (GEN-47).

Acceptance: planning resolves the approved spec (or fails closed with the
stable code), preparation is idempotent per run key with a hard budget,
agent/verify/publish map port outcomes to workflow-plane results, and every
transactional question (branch creation, commit counts, PR search) is
delegated to the injected ports.
"""

import json
from pathlib import Path
from typing import Any

import pytest

import super_factory.temporal.activities.pipeline as pipeline_activities
from super_factory.contracts.approved_task import ApprovedTaskSpec
from super_factory.contracts.pipeline import (
    AgentRunCommand,
    AgentRunRecord,
    PlanRunCommand,
    PrepareRunCommand,
    PublishCommand,
    TaskSpecQuery,
    VerificationCommand,
    VerificationOutcome,
)
from super_factory.contracts.run_ledger import PipelineRunRecord
from super_factory.contracts.scm import CommitInfo, PullRequestRef, PushInfo, WorkspaceStatus
from super_factory.domain.pipeline import (
    REASON_BUDGET_EXHAUSTED,
    REASON_CHANGES_EMPTY,
    REASON_SPEC_SOURCE_UNAVAILABLE,
)
from super_factory.planning.ports import SpecSourceUnavailable
from super_factory.scm.ports import SCMUnavailable


class FakeSpecSource:
    """TaskSpecSource double resolving a canned spec (or raising)."""

    def __init__(self, raise_unavailable: bool = False) -> None:
        self.queries: list[TaskSpecQuery] = []
        self.raise_unavailable = raise_unavailable

    async def resolve(self, query: TaskSpecQuery) -> ApprovedTaskSpec:
        self.queries.append(query)
        if self.raise_unavailable:
            raise SpecSourceUnavailable("no approved spec file")
        return ApprovedTaskSpec(
            issue_id=query.issue_id,
            spec_version=1,
            repository=query.repository,
            base_branch=query.base_branch,
            objective="Do the thing",
            acceptance_criteria=["works", "tested"],
        )


class FakeGitWorkspaces:
    def __init__(self) -> None:
        self.ensure_calls: list[tuple[str, str, str, str]] = []
        self.commits: list[tuple[str, str]] = []
        self.pushes: list[tuple[str, str]] = []
        self.ahead: int = 2
        self.raise_on_ensure: Exception | None = None

    async def ensure_workspace(
        self, repository: str, base_branch: str, branch_name: str, workspace_path: str
    ) -> WorkspaceStatus:
        if self.raise_on_ensure is not None:
            raise self.raise_on_ensure
        self.ensure_calls.append((repository, base_branch, branch_name, workspace_path))
        return WorkspaceStatus(path=workspace_path, existed=False, branch_existed=False)

    async def commit_all(self, workspace_path: str, message: str) -> CommitInfo:
        self.commits.append((workspace_path, message))
        return CommitInfo(committed=True, sha="cafe123", files_committed=3)

    async def push_branch(self, workspace_path: str, branch_name: str) -> PushInfo:
        self.pushes.append((workspace_path, branch_name))
        return PushInfo(pushed=True, detail="new branch")

    async def count_commits_ahead(self, workspace_path: str, base_branch: str) -> int:
        return self.ahead


class FakePullRequests:
    def __init__(self, existing: PullRequestRef | None = None) -> None:
        self.existing = existing
        self.searches: list[tuple[str, str]] = []
        self.opened: list[tuple[str, str, str, str, str]] = []

    async def find_open(self, repository: str, head_branch: str) -> PullRequestRef | None:
        self.searches.append((repository, head_branch))
        return self.existing

    async def open(
        self, repository: str, base_branch: str, head_branch: str, title: str, body: str
    ) -> PullRequestRef:
        self.opened.append((repository, base_branch, head_branch, title, body))
        return PullRequestRef(
            number=42,
            url=f"https://github.com/{repository}/pull/42",
            head_branch=head_branch,
            base_branch=base_branch,
        )


class FakeLedger:
    def __init__(self, records: tuple[PipelineRunRecord, ...] = ()) -> None:
        self._records: list[PipelineRunRecord] = list(records)

    async def runs_for_issue(self, issue_id: str) -> tuple[PipelineRunRecord, ...]:
        return tuple(r for r in self._records if r.issue_id == issue_id)

    async def record_run(self, record: PipelineRunRecord) -> bool:
        if any(r.run_key == record.run_key for r in self._records):
            return False
        self._records.append(record)
        return True


class FakeAgent:
    def __init__(self, record: AgentRunRecord) -> None:
        self.record = record
        self.commands: list[AgentRunCommand] = []

    async def run(self, command: AgentRunCommand) -> AgentRunRecord:
        self.commands.append(command)
        return self.record


class FakeVerifier:
    def __init__(self, outcome: VerificationOutcome) -> None:
        self.outcome = outcome
        self.commands: list[VerificationCommand] = []

    async def run(self, command: VerificationCommand) -> VerificationOutcome:
        self.commands.append(command)
        return self.outcome


@pytest.fixture
def ports(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Wire fakes into the activity module and force settings to tmp paths."""
    monkeypatch.setenv("SF_FACTORY_WORKSPACE_ROOT", str(tmp_path / "ws"))
    monkeypatch.setenv("SF_FACTORY_RUN_LEDGER_PATH", str(tmp_path / "runs.jsonl"))
    monkeypatch.setenv("SF_FACTORY_BUDGET_RUNS_PER_ISSUE", "2")
    git = FakeGitWorkspaces()
    pulls = FakePullRequests()
    ledger = FakeLedger()
    agent = FakeAgent(AgentRunRecord(completed=True, commands=("codex exec",), evidence=("done",)))
    verifier = FakeVerifier(
        VerificationOutcome(passed=True, commands=("pytest",), evidence=("ok",))
    )
    pipeline_activities.set_git_workspaces(git)
    pipeline_activities.set_pull_request_service(pulls)
    pipeline_activities.set_run_ledger(ledger)
    pipeline_activities.set_coding_agent(agent)
    pipeline_activities.set_verification_runner(verifier)
    try:
        yield {"git": git, "pulls": pulls, "ledger": ledger, "agent": agent, "verifier": verifier}
    finally:
        pipeline_activities.reset_pipeline_ports()


def test_plan_run_builds_deterministic_plan(ports: dict[str, Any]) -> None:
    source = FakeSpecSource()
    pipeline_activities.set_task_spec_source(source)
    plan = _execute(
        pipeline_activities.plan_run_activity(
            PlanRunCommand(
                issue_id="GEN-47", repository="a/b", base_branch="main", title="H2 agente"
            )
        )
    )
    assert plan.ok
    assert plan.run_key == "GEN-47-v1"
    assert plan.branch_name == "feat/gen-47-h2-agente"
    assert plan.objective == "Do the thing"
    assert plan.acceptance_criteria == ("works", "tested")
    assert source.queries[0].repository == "a/b"


def test_plan_run_fails_closed_without_spec_source() -> None:
    pipeline_activities.set_task_spec_source(FakeSpecSource(raise_unavailable=True))
    plan = _execute(
        pipeline_activities.plan_run_activity(
            PlanRunCommand(issue_id="GEN-47", repository="a/b", base_branch="main", title="T")
        )
    )
    assert plan.ok is False
    assert plan.failure_code == REASON_SPEC_SOURCE_UNAVAILABLE


def test_prepare_run_creates_ledger_record_and_budget(ports: dict[str, Any]) -> None:
    preparation = _execute(
        pipeline_activities.prepare_run_activity(
            PrepareRunCommand(
                issue_id="GEN-47",
                repository="a/b",
                spec_version=1,
                run_key="GEN-47-v1",
                branch_name="feat/gen-47-t",
                base_branch="main",
            )
        )
    )
    assert preparation.ok
    assert preparation.budget_remaining == 1
    assert "gen-47-v1" in preparation.workspace_path
    assert ports["git"].ensure_calls[0][2] == "feat/gen-47-t"
    assert [record.run_key for record in ports["ledger"]._records] == ["GEN-47-v1"]
    record = ports["ledger"]._records[0]
    assert record.outcome == "PREPARED"


def test_prepare_run_enforces_budget(ports: dict[str, Any]) -> None:
    ports["ledger"]._records.extend(
        (
            PipelineRunRecord(
                run_key="GEN-47-v2",
                issue_id="GEN-47",
                spec_version=2,
                repository="a/b",
                branch_name="b",
                recorded_at="t",
                outcome="PREPARED",
            ),
            PipelineRunRecord(
                run_key="GEN-47-v3",
                issue_id="GEN-47",
                spec_version=3,
                repository="a/b",
                branch_name="b",
                recorded_at="t",
                outcome="PREPARED",
            ),
        )
    )
    preparation = _execute(
        pipeline_activities.prepare_run_activity(
            PrepareRunCommand(
                issue_id="GEN-47",
                repository="a/b",
                spec_version=1,
                run_key="GEN-47-v1",
                branch_name="feat/gen-47-t",
                base_branch="main",
            )
        )
    )
    assert preparation.ok is False
    assert preparation.failure_code == REASON_BUDGET_EXHAUSTED
    assert ports["git"].ensure_calls == []


def test_prepare_run_does_not_reticketed_budget_for_same_run_key(
    ports: dict[str, Any],
) -> None:
    ports["ledger"]._records.append(
        PipelineRunRecord(
            run_key="GEN-47-v1",
            issue_id="GEN-47",
            spec_version=1,
            repository="a/b",
            branch_name="feat/gen-47-t",
            recorded_at="t",
            outcome="PREPARED",
        )
    )
    preparation = _execute(
        pipeline_activities.prepare_run_activity(
            PrepareRunCommand(
                issue_id="GEN-47",
                repository="a/b",
                spec_version=1,
                run_key="GEN-47-v1",
                branch_name="feat/gen-47-t",
                base_branch="main",
            )
        )
    )
    assert preparation.ok
    assert preparation.budget_remaining == 1
    assert len(ports["ledger"]._records) == 1


def test_prepare_run_propagates_scm_unavailable(ports: dict[str, Any]) -> None:
    ports["git"].raise_on_ensure = SCMUnavailable("git clone failed")
    with pytest.raises(SCMUnavailable, match="git clone failed"):
        _execute(
            pipeline_activities.prepare_run_activity(
                PrepareRunCommand(
                    issue_id="GEN-47",
                    repository="a/b",
                    spec_version=1,
                    run_key="GEN-47-v1",
                    branch_name="feat/gen-47-t",
                    base_branch="main",
                )
            )
        )
    assert ports["ledger"]._records == []


def _execute(call: Any) -> Any:
    import asyncio

    return asyncio.run(call)


def test_agent_activity_delegates_to_port(ports: dict[str, Any]) -> None:
    command = AgentRunCommand(
        issue_id="GEN-47",
        repository="a/b",
        spec_version=1,
        run_key="GEN-47-v1",
        branch_name="feat/gen-47-t",
        base_branch="main",
        objective="Do the thing",
        acceptance_criteria=("works", "tested"),
        exclusions=(),
        constraints=(),
        dependencies=(),
        workspace_path="/ws/gen-47-v1",
    )
    record = _execute(pipeline_activities.run_coding_agent_activity(command))
    assert record.completed
    assert ports["agent"].commands == [command]


def test_verify_activity_delegates_to_port(ports: dict[str, Any]) -> None:
    command = VerificationCommand(
        issue_id="GEN-47",
        run_key="GEN-47-v1",
        workspace_path="/ws",
        acceptance_criteria=("works", "tested"),
    )
    outcome = _execute(pipeline_activities.verify_run_activity(command))
    assert outcome.passed
    assert ports["verifier"].commands == [command]


def _publish_command(**overrides: object) -> PublishCommand:
    fields: dict[str, object] = {
        "issue_id": "GEN-47",
        "repository": "a/b",
        "run_key": "GEN-47-v1",
        "branch_name": "feat/gen-47-t",
        "base_branch": "main",
        "workspace_path": "/ws/gen-47-v1",
        "objective": "Do the thing",
        "acceptance_criteria": ("works", "tested"),
        "linear_url_template": "https://linear.app/genesisnavarra/issue/{issue_id}",
    }
    fields.update(overrides)
    return PublishCommand(**fields)


def test_publish_creates_new_pr_and_returns_reference(ports: dict[str, Any]) -> None:
    outcome = _execute(pipeline_activities.publish_pr_activity(_publish_command()))
    assert outcome.published
    assert outcome.pr_number == 42
    assert not outcome.updated_existing
    git = ports["git"]
    assert git.commits[0][1] == "feat(gen-47): Do the thing"
    assert git.pushes[0][1] == "feat/gen-47-t"
    pulls = ports["pulls"]
    assert pulls.searches == [("a/b", "feat/gen-47-t")]
    assert len(pulls.opened) == 1
    opened = pulls.opened[0]
    assert opened[3] == "feat(gen-47): Do the thing"
    assert "https://linear.app/genesisnavarra/issue/GEN-47" in opened[4]
    assert "- [x] works" in opened[4]


def test_publish_reuses_existing_pr_without_duplicates(ports: dict[str, Any]) -> None:
    ports["pulls"].existing = PullRequestRef(
        number=7,
        url="https://github.com/a/b/pull/7",
        head_branch="feat/gen-47-t",
        base_branch="main",
    )
    outcome = _execute(pipeline_activities.publish_pr_activity(_publish_command()))
    assert outcome.published
    assert outcome.updated_existing is True
    assert outcome.pr_number == 7
    assert ports["pulls"].opened == []


def test_publish_blocks_on_empty_changeset(ports: dict[str, Any]) -> None:
    ports["git"].ahead = 0
    outcome = _execute(pipeline_activities.publish_pr_activity(_publish_command()))
    assert outcome.published is False
    assert outcome.failure_code == REASON_CHANGES_EMPTY
    assert ports["git"].pushes == []
    assert ports["pulls"].opened == []


def test_publish_propagates_git_failures_for_retries(ports: dict[str, Any]) -> None:
    class _BrokenGit(FakeGitWorkspaces):
        async def push_branch(self, workspace_path: str, branch_name: str) -> PushInfo:
            raise SCMUnavailable("push rejected: remote hung up")

    broken = _BrokenGit()
    pipeline_activities.set_git_workspaces(broken)
    with pytest.raises(SCMUnavailable, match="remote hung up"):
        _execute(pipeline_activities.publish_pr_activity(_publish_command()))


def test_default_resolvers_build_settings_driven_adapters(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SF_FACTORY_TASK_SPEC_PATH", str(tmp_path / "spec.json"))
    (tmp_path / "spec.json").write_text(
        json.dumps(
            {
                "issue_id": "GEN-47",
                "spec_version": 1,
                "repository": "a/b",
                "base_branch": "main",
                "objective": "approved",
                "acceptance_criteria": ["criterion"],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("SF_FACTORY_RUN_LEDGER_PATH", str(tmp_path / "runs.jsonl"))
    try:
        source = pipeline_activities.get_task_spec_source()
        ledger = pipeline_activities.get_run_ledger()
        from super_factory.persistence.run_ledger import JsonLinesRunLedger
        from super_factory.planning.ports import StaticFileSpecSource

        assert isinstance(source, StaticFileSpecSource)
        spec = _execute(
            source.resolve(
                TaskSpecQuery(
                    issue_id="GEN-47", repository="a/b", base_branch="main", title="t"
                )
            )
        )
        assert spec.objective == "approved"
        assert isinstance(ledger, JsonLinesRunLedger)
        assert ledger.path == tmp_path / "runs.jsonl"
    finally:
        pipeline_activities.reset_pipeline_ports()
