"""Contract tests for the H2 pipeline data crossing Temporal activities (GEN-47).

Acceptance: pipeline-plane contracts are frozen dataclasses with fail-fast
validation, so ok/outcome objects always carry their payload and failure
objects always carry a code+detail; port payload contracts are Pydantic
frozen models validated per ADR-0003.
"""

from dataclasses import FrozenInstanceError

import pytest
from pydantic import ValidationError

from super_factory.contracts.pipeline import (
    AgentRunCommand,
    AgentRunRecord,
    PlanRunCommand,
    PrepareRunCommand,
    PublicationOutcome,
    PublishCommand,
    RunPreparation,
    TaskPlan,
    TaskSpecQuery,
    VerificationCommand,
    VerificationOutcome,
)
from super_factory.contracts.sandboxing import (
    SandboxCommand,
    SandboxCommandOutcome,
    SandboxInstance,
    SandboxSpec,
)
from super_factory.contracts.scm import (
    CommitInfo,
    PullRequestRef,
    PushInfo,
    WorkspaceStatus,
)


def test_plan_run_command_is_frozen() -> None:
    command = PlanRunCommand(issue_id="GEN-47", repository="a/b", base_branch="main", title="T")
    with pytest.raises(FrozenInstanceError):
        command.title = "other"  # type: ignore[misc]


def test_task_spec_query_is_frozen() -> None:
    query = TaskSpecQuery(issue_id="GEN-47", repository="a/b", base_branch="main", title="T")
    with pytest.raises(FrozenInstanceError):
        query.title = "other"  # type: ignore[misc]


def _plan(**overrides: object) -> TaskPlan:
    fields: dict[str, object] = {
        "ok": True,
        "issue_id": "GEN-47",
        "spec_version": 1,
        "objective": "g",
        "acceptance_criteria": ("c",),
        "run_key": "GEN-47-v1",
        "branch_name": "b",
    }
    fields.update(overrides)
    return TaskPlan(**fields)


def _preparation(**overrides: object) -> RunPreparation:
    fields: dict[str, object] = {"ok": True, "workspace_path": "/ws"}
    fields.update(overrides)
    return RunPreparation(**fields)


def test_task_plan_ok_carries_full_spec() -> None:
    plan = _plan()
    assert plan.ok
    assert plan.run_key == "GEN-47-v1"


def test_task_plan_ok_requires_full_spec() -> None:
    with pytest.raises(ValueError, match="full approved specification"):
        _plan(objective="")


def test_task_plan_ok_requires_matching_run_key_and_issue() -> None:
    with pytest.raises(ValueError, match="derived from issue_id"):
        _plan(run_key="GEN-48-v1")
    with pytest.raises(ValueError, match="valid run key"):
        _plan(run_key="initial")


def test_task_plan_ok_requires_branch_name() -> None:
    with pytest.raises(ValueError, match="branch name"):
        _plan(branch_name="  ")


def test_task_plan_failure_requires_code_and_detail() -> None:
    failed = TaskPlan(ok=False, failure_code="SPEC_SOURCE_UNAVAILABLE", failure_detail="no file")
    assert failed.run_key == ""
    with pytest.raises(ValueError, match="failure_code"):
        TaskPlan(ok=False, failure_code="BROKEN", failure_detail="")
    with pytest.raises(ValueError, match="failure_code"):
        TaskPlan(ok=False, failure_code="", failure_detail="x")


def test_preparation_and_agent_contracts_validate() -> None:
    command = PrepareRunCommand(
        issue_id="GEN-47",
        repository="a/b",
        spec_version=1,
        run_key="GEN-47-v1",
        branch_name="feat/gen-47-goal",
        base_branch="main",
    )
    assert command.run_key == "GEN-47-v1"
    preparation = _preparation(branch_existed=False, budget_remaining=1)
    assert preparation.budget_remaining == 1
    with pytest.raises(ValueError, match="workspace_path"):
        _preparation(workspace_path="  ")
    with pytest.raises(ValueError, match="failure_code"):
        RunPreparation(ok=False, failure_code="", failure_detail="x")
    blocked = RunPreparation(
        ok=False, failure_code="BUDGET_EXHAUSTED", failure_detail="limit reached"
    )
    assert blocked.failure_code == "BUDGET_EXHAUSTED"
    with pytest.raises(ValueError, match="must not carry a failure code"):
        _preparation(failure_code="BOOM", failure_detail="x")


def test_agent_run_record_validates_outcome_consistency() -> None:
    record = AgentRunRecord(completed=True, commands=("cmd",), evidence=("e",))
    assert record.completed
    with pytest.raises(ValueError, match="must not carry a failure_code"):
        AgentRunRecord(completed=True, failure_code="AGENT_FAILED", failure_detail="d")
    with pytest.raises(ValueError, match="carry failure_code"):
        AgentRunRecord(completed=False, failure_code="", failure_detail="")


def test_verification_outcome_and_publish_outcome_validate() -> None:
    outcome = VerificationOutcome(passed=True, commands=("pytest",), evidence=("ok",))
    assert outcome.passed
    failing = VerificationOutcome(
        passed=False, failure_code="VERIFICATION_FAILED", failure_detail="tests"
    )
    assert not failing.passed
    with pytest.raises(ValueError, match="failure_code"):
        VerificationOutcome(passed=False)
    publication = PublicationOutcome(
        published=True, pr_url="https://github.com/a/b/pull/1", pr_number=1
    )
    assert publication.published
    with pytest.raises(ValueError, match="pr_url"):
        PublicationOutcome(published=True)
    with pytest.raises(ValueError, match="failure_code"):
        PublicationOutcome(published=False)
    reused = PublicationOutcome(
        published=True,
        pr_url="https://github.com/a/b/pull/2",
        pr_number=2,
        updated_existing=True,
    )
    assert reused.updated_existing
    failing = PublicationOutcome(
        published=False, failure_code="PUBLISH_FAILED", failure_detail="gh"
    )
    assert failing.failure_code == "PUBLISH_FAILED"
    with pytest.raises(ValueError, match="failed publications must not set updated_existing"):
        PublicationOutcome(published=False, updated_existing=True)


def test_publish_and_verification_commands_are_frozen() -> None:
    publish = PublishCommand(
        issue_id="GEN-47",
        repository="a/b",
        run_key="GEN-47-v1",
        branch_name="feat/gen-47-goal",
        base_branch="main",
        workspace_path="/ws",
        objective="goal",
        acceptance_criteria=("c",),
        linear_url_template="https://linear.app/genesisnavarra/issue/{issue_id}",
    )
    with pytest.raises(FrozenInstanceError):
        publish.repository = "x/y"  # type: ignore[misc]
    verify = VerificationCommand(
        issue_id="GEN-47", run_key="GEN-47-v1", workspace_path="/ws", acceptance_criteria=("c",)
    )
    with pytest.raises(FrozenInstanceError):
        verify.workspace_path = "/other"  # type: ignore[misc]


def test_sandbox_spec_defaults_secure() -> None:
    spec = SandboxSpec(run_key="GEN-47-v1", workspace_path="/ws")
    assert spec.network_isolated is True
    assert spec.run_as_non_root is True
    assert spec.image == "python:3.12-slim"
    assert spec.cpu_limit == 1.0
    assert spec.memory_limit == "2g"
    assert spec.command_timeout_seconds > 0
    with pytest.raises(ValidationError):
        SandboxSpec(run_key="nope", workspace_path="/ws")
    with pytest.raises(ValidationError):
        SandboxSpec(run_key="GEN-47-v1", workspace_path="/ws", memory_limit="banana")
    assert SandboxSpec(
        run_key="GEN-47-v1", workspace_path="/ws", memory_limit="512m"
    ).memory_limit == "512m"
    with pytest.raises(ValidationError):
        SandboxSpec(run_key="GEN-47-v1", workspace_path=" /ws ")


def test_sandbox_command_requires_argv_with_items() -> None:
    outcome = SandboxCommandOutcome(exit_code=0, output_tail="done")
    assert outcome.exit_code == 0
    timeout_outcome = SandboxCommandOutcome(exit_code=None, timed_out=True)
    assert timeout_outcome.timed_out
    instance = SandboxInstance(id="factory-sandbox-gen-47-v1")
    assert instance.id.startswith("factory-sandbox-")
    with pytest.raises(ValidationError):
        SandboxCommand(argv=())
    with pytest.raises(ValidationError):
        SandboxCommand(argv=("python", "  "))


def test_scm_contract_shapes() -> None:
    status = WorkspaceStatus(path="/ws", existed=True, branch_existed=False)
    assert status.existed
    commit = CommitInfo(committed=True, sha="abc123", files_committed=2)
    assert commit.sha == "abc123"
    push = PushInfo(pushed=True, detail="origin/main")
    assert push.pushed
    ref = PullRequestRef(
        number=7, url="https://github.com/a/b/pull/7", head_branch="feat/x", base_branch="main"
    )
    assert ref.number == 7
    with pytest.raises(ValidationError):
        PullRequestRef(number=0, url="u", head_branch="h", base_branch="b")


def test_scm_validators_fail_fast() -> None:
    with pytest.raises(ValidationError):
        WorkspaceStatus(path=" /ws ", existed=True, branch_existed=True)
    with pytest.raises(ValidationError):
        CommitInfo(committed=True, files_committed=-1)
    with pytest.raises(ValidationError):
        CommitInfo(committed=True, sha=" abc123 ")
    assert CommitInfo(committed=False, detail="clean").files_committed == 0
    with pytest.raises(ValidationError):
        PullRequestRef(number=1, url=" u ", head_branch="h", base_branch="b")
    with pytest.raises(ValidationError):
        PushInfo(pushed=True, detail=" ")


def test_agent_run_command_is_frozen() -> None:
    command = AgentRunCommand(
        issue_id="GEN-47",
        repository="a/b",
        spec_version=1,
        run_key="GEN-47-v1",
        branch_name="feat/gen-47-goal",
        base_branch="main",
        objective="goal",
        acceptance_criteria=("c",),
        exclusions=(),
        constraints=(),
        dependencies=(),
        workspace_path="/ws",
    )
    with pytest.raises(FrozenInstanceError):
        command.objective = "x"  # type: ignore[misc]
