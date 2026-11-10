"""H2 PR-production activities (GEN-47): effects go through replaceable ports.

Sequence wired by ``IssueWorkflow``:
plan_run_activity (PLANNING) -> prepare_run_activity (PREPARING, budget +
workspace) -> run_coding_agent_activity (IMPLEMENTING) ->
verify_run_activity (VERIFYING) -> publish_pr_activity (REVIEWING).
Functional decisions come back as outcome values (workflow -> BLOCKED);
technical/transport failures raise so Temporal's retry policies absorb
them. All I/O passes through module ports with test setters.
"""

from datetime import UTC, datetime
from pathlib import Path

from temporalio import activity

from super_factory.agents.codex_cli import CodexCliAgent
from super_factory.agents.ports import CodingAgent
from super_factory.config.settings import get_settings
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
from super_factory.contracts.run_ledger import PipelineRunRecord
from super_factory.domain.pipeline import (
    REASON_BUDGET_EXHAUSTED,
    REASON_CHANGES_EMPTY,
    REASON_SPEC_SOURCE_UNAVAILABLE,
    branch_name_for,
    commit_message_for,
    pr_body_for,
    pr_title_for,
    run_key_for,
)
from super_factory.persistence.run_ledger import JsonLinesRunLedger, PipelineRunLedger
from super_factory.planning.ports import (
    SpecSourceUnavailable,
    StaticFileSpecSource,
    TaskSpecSource,
    UnavailableSpecSource,
)
from super_factory.process.subprocess import SubprocessCommandRunner
from super_factory.sandbox.docker import DockerSandboxRuntime
from super_factory.sandbox.ports import SandboxRuntime
from super_factory.scm.git_cli import GitCommandLineRunner
from super_factory.scm.github_cli import GhCliPullRequests
from super_factory.scm.ports import GitWorkspaces, PullRequestsService
from super_factory.verification.ports import VerificationRunner
from super_factory.verification.sandbox import SandboxVerificationRunner

_spec_source: TaskSpecSource | None = None
_git: GitWorkspaces | None = None
_pulls: PullRequestsService | None = None
_ledger: PipelineRunLedger | None = None
_agent: CodingAgent | None = None
_verifier: VerificationRunner | None = None


def set_task_spec_source(source: TaskSpecSource | None) -> None:
    """Replace the planning port (testing seam; None restores defaults)."""
    global _spec_source
    _spec_source = source


def set_git_workspaces(client: GitWorkspaces | None) -> None:
    """Replace the git workspace port (testing seam)."""
    global _git
    _git = client


def set_pull_request_service(client: PullRequestsService | None) -> None:
    """Replace the pull-request port (testing seam)."""
    global _pulls
    _pulls = client


def set_run_ledger(ledger: PipelineRunLedger | None) -> None:
    """Replace the run ledger port (testing seam)."""
    global _ledger
    _ledger = ledger


def set_coding_agent(agent: CodingAgent | None) -> None:
    """Replace the coding agent port (testing seam)."""
    global _agent
    _agent = agent


def set_verification_runner(runner: VerificationRunner | None) -> None:
    """Replace the verification runner port (testing seam)."""
    global _verifier
    _verifier = runner


def reset_pipeline_ports() -> None:
    """Restore settings-driven defaults (tests/production wiring)."""
    global _spec_source, _git, _pulls, _ledger, _agent, _verifier
    _spec_source = None
    _git = None
    _pulls = None
    _ledger = None
    _agent = None
    _verifier = None


def get_task_spec_source() -> TaskSpecSource:
    """TaskSpecSource built once from settings (spec file or fail-closed)."""
    global _spec_source
    if _spec_source is None:
        configured = get_settings().factory_task_spec_path
        if configured.strip():
            _spec_source = StaticFileSpecSource(configured)
        else:
            _spec_source = UnavailableSpecSource()
    return _spec_source


def get_git_workspaces() -> GitWorkspaces:
    """GitWorkspaces adapter (subprocess runner + git CLI)."""
    global _git
    if _git is None:
        _git = GitCommandLineRunner(SubprocessCommandRunner())
    return _git


def get_pull_request_service() -> PullRequestsService:
    """PullRequestsService adapter (subprocess runner + gh CLI)."""
    global _pulls
    if _pulls is None:
        _pulls = GhCliPullRequests(SubprocessCommandRunner())
    return _pulls


def get_run_ledger() -> PipelineRunLedger:
    """Run ledger adapter backed by the configured JSONL path."""
    global _ledger
    if _ledger is None:
        _ledger = JsonLinesRunLedger(get_settings().factory_run_ledger_path)
    return _ledger


def get_sandbox_runtime() -> SandboxRuntime:
    """Sandbox runtime adapter built from the configured limits."""
    return DockerSandboxRuntime(SubprocessCommandRunner())


def get_coding_agent() -> CodingAgent:
    """CodingAgent adapter (Codex CLI inside the sandbox runtime)."""
    global _agent
    if _agent is None:
        settings = get_settings()
        _agent = CodexCliAgent(
            get_sandbox_runtime(),
            sandbox_image=settings.factory_sandbox_image,
            command_timeout_seconds=float(settings.factory_sandbox_command_timeout_seconds),
        )
    return _agent


def get_verification_runner() -> VerificationRunner:
    """VerificationRunner adapter (tests inside the sandbox runtime)."""
    global _verifier
    if _verifier is None:
        settings = get_settings()
        _verifier = SandboxVerificationRunner(
            get_sandbox_runtime(),
            sandbox_image=settings.factory_sandbox_image,
            timeout_seconds=float(settings.factory_sandbox_command_timeout_seconds),
        )
    return _verifier


def workspace_path_for(run_key: str) -> Path:
    """Deterministic workspace directory per run key."""
    return Path(get_settings().factory_workspace_root) / run_key.lower()


@activity.defn(name="plan_run_activity")
async def plan_run_activity(command: PlanRunCommand) -> TaskPlan:
    """Resolve the approved specification and the deterministic names."""
    query = TaskSpecQuery(
        issue_id=command.issue_id,
        repository=command.repository,
        base_branch=command.base_branch,
        title=command.title,
    )
    try:
        spec = await get_task_spec_source().resolve(query)
    except SpecSourceUnavailable as exc:
        return TaskPlan(
            ok=False,
            failure_code=REASON_SPEC_SOURCE_UNAVAILABLE,
            failure_detail=str(exc),
        )
    return TaskPlan(
        ok=True,
        issue_id=spec.issue_id,
        spec_version=spec.spec_version,
        objective=spec.objective,
        acceptance_criteria=tuple(spec.acceptance_criteria),
        dependencies=tuple(spec.dependencies),
        exclusions=tuple(spec.exclusions),
        constraints=tuple(spec.constraints),
        run_key=run_key_for(spec.issue_id, spec.spec_version),
        branch_name=branch_name_for(spec.issue_id, command.title),
    )


@activity.defn(name="prepare_run_activity")
async def prepare_run_activity(command: PrepareRunCommand) -> RunPreparation:
    """Budget + ledger bookkeeping + idempotent workspace/branch creation.

    Failure/insert order matters: the run is only booked AFTER the
    workspace is guaranteed, so a technical retry never inflates budget.
    """
    ledger = get_run_ledger()
    runs = await ledger.runs_for_issue(command.issue_id)
    known = {run.run_key for run in runs}
    budget = get_settings().factory_budget_runs_per_issue
    if command.run_key not in known and len(known) >= budget:
        return RunPreparation(
            ok=False,
            failure_code=REASON_BUDGET_EXHAUSTED,
            failure_detail=(
                f"{command.issue_id} reached {len(known)} runs "
                f"(budget {budget}); no new run can be prepared"
            ),
        )
    workspace_path = str(workspace_path_for(command.run_key))
    status = await get_git_workspaces().ensure_workspace(
        repository=command.repository,
        base_branch=command.base_branch,
        branch_name=command.branch_name,
        workspace_path=workspace_path,
    )
    await ledger.record_run(
        PipelineRunRecord(
            run_key=command.run_key,
            issue_id=command.issue_id,
            spec_version=command.spec_version,
            repository=command.repository,
            branch_name=command.branch_name,
            recorded_at=datetime.now(tz=UTC).isoformat(),
            outcome="PREPARED",
        )
    )
    budget_remaining = max(0, budget - len(known | {command.run_key}))
    return RunPreparation(
        ok=True,
        workspace_path=workspace_path,
        branch_existed=status.branch_existed,
        budget_remaining=budget_remaining,
    )


@activity.defn(name="run_coding_agent_activity")
async def run_coding_agent_activity(command: AgentRunCommand) -> AgentRunRecord:
    """Execute the agent inside the sandbox; technical failures propagate."""
    if activity.in_activity():
        activity.heartbeat()
    return await get_coding_agent().run(command)


@activity.defn(name="verify_run_activity")
async def verify_run_activity(command: VerificationCommand) -> VerificationOutcome:
    """Re-run the tests inside the sandbox; technical failures propagate."""
    if activity.in_activity():
        activity.heartbeat()
    return await get_verification_runner().run(command)


@activity.defn(name="publish_pr_activity")
async def publish_pr_activity(command: PublishCommand) -> PublicationOutcome:
    """Commit, push and reuse-or-open the pull request (idempotent).

    Order: commit-all (idempotent) -> assert the branch has commits
    (CHANGES_EMPTY otherwise) -> push (idempotent) -> find_open (never
    duplicate PRs) -> open. SCM/gh failures raise for Temporal retries.
    """
    git = get_git_workspaces()
    await git.commit_all(
        command.workspace_path,
        commit_message_for(command.issue_id, command.objective),
    )
    ahead = await git.count_commits_ahead(command.workspace_path, command.base_branch)
    if ahead == 0:
        return PublicationOutcome(
            published=False,
            failure_code=REASON_CHANGES_EMPTY,
            failure_detail=(
                f"{command.issue_id} produced no commits ahead of {command.base_branch}"
            ),
        )
    await git.push_branch(command.workspace_path, command.branch_name)
    service = get_pull_request_service()
    existing = await service.find_open(
        repository=command.repository, head_branch=command.branch_name
    )
    if existing is not None:
        return PublicationOutcome(
            published=True,
            pr_url=existing.url,
            pr_number=existing.number,
            updated_existing=True,
        )
    created = await service.open(
        repository=command.repository,
        base_branch=command.base_branch,
        head_branch=command.branch_name,
        title=pr_title_for(command.issue_id, command.objective),
        body=pr_body_for(
            issue_id=command.issue_id,
            objective=command.objective,
            acceptance_criteria=command.acceptance_criteria,
            linear_template=command.linear_url_template,
        ),
    )
    return PublicationOutcome(published=True, pr_url=created.url, pr_number=created.number)
