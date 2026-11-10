"""Tests for the git CLI workspaces adapter (GEN-47) with a scripted runner.

Acceptance: workspace ensure is idempotent per (repository, branch) — reuse
existing checkouts, create the missing branch, clone missing workspaces;
commit/push behave idempotently; runner/git failures surface as
SCMUnavailable.
"""

from pathlib import Path

import pytest

from super_factory.contracts.scm import CommitInfo, PushInfo, WorkspaceStatus
from super_factory.process.ports import ProcessLaunchError
from super_factory.scm.git_cli import GitCommandLineRunner
from super_factory.scm.ports import SCMUnavailable
from tests.unit.command_runner_stubs import ScriptedRunner

REPO = "GenesisAI-team/SF-Temporal-Python"
WS = "C:/tmp/ws/gen-47-v1"


async def test_ensure_workspace_clones_when_absent(tmp_path: Path) -> None:
    runner = ScriptedRunner()
    adapter = GitCommandLineRunner(runner)
    path = tmp_path / "gen-47-v1"
    status = await adapter.ensure_workspace(
        repository=REPO,
        base_branch="main",
        branch_name="feat/gen-47-h2",
        workspace_path=str(path),
    )
    assert isinstance(status, WorkspaceStatus)
    assert status.path == str(path)
    assert status.existed is False
    assert status.branch_existed is False
    clone_argv = list(runner.requests[0].argv)
    assert clone_argv[:4] == ["git", "clone", "--branch", "main"]
    assert clone_argv[-2:] == [REPO, str(path)]
    checkout_argv = list(runner.requests[1].argv)
    assert checkout_argv[:3] == ["git", "checkout", "-b"]
    assert "feat/gen-47-h2" in checkout_argv
    assert runner.requests[1].cwd == str(path)


async def test_ensure_workspace_reuses_existing_checkout_and_branch(tmp_path: Path) -> None:
    path = tmp_path / "gen-47-v1"
    path.mkdir()
    (path / ".git").mkdir()
    runner = ScriptedRunner().on(("git", "rev-parse", "--verify"), stdout_tail="abc123\n")
    adapter = GitCommandLineRunner(runner)
    status = await adapter.ensure_workspace(
        repository=REPO,
        base_branch="main",
        branch_name="feat/gen-47-h2",
        workspace_path=str(path),
    )
    assert status.existed is True
    assert status.branch_existed is True
    assert len(runner.requests) == 1


async def test_ensure_workspace_creates_missing_branch_on_existing_checkout(
    tmp_path: Path,
) -> None:
    path = tmp_path / "ws"
    path.mkdir()
    (path / ".git").mkdir()
    runner = ScriptedRunner().on(("git", "rev-parse", "--verify"), exit_code=1)
    adapter = GitCommandLineRunner(runner)
    status = await adapter.ensure_workspace(
        repository=REPO,
        base_branch="main",
        branch_name="feat/gen-47-h2",
        workspace_path=str(path),
    )
    assert status.existed is True
    assert status.branch_existed is False
    checkout_argv = list(runner.requests[1].argv)
    assert checkout_argv[:3] == ["git", "checkout", "-b"]


async def test_ensure_workspace_rejects_path_without_git_dir(tmp_path: Path) -> None:
    path = tmp_path / "not-a-repo"
    path.mkdir()
    adapter = GitCommandLineRunner(ScriptedRunner())
    with pytest.raises(SCMUnavailable, match="without a git repository"):
        await adapter.ensure_workspace(
            repository=REPO, base_branch="main", branch_name="b", workspace_path=str(path)
        )


async def test_commit_all_is_clean_when_nothing_to_commit() -> None:
    runner = ScriptedRunner().on(("git", "status", "--porcelain"), stdout_tail="")
    adapter = GitCommandLineRunner(runner)
    info = await adapter.commit_all(workspace_path=WS, message="msg")
    assert isinstance(info, CommitInfo)
    assert info.committed is False
    assert info.detail == "working tree clean"
    assert len(runner.requests) == 1


async def test_commit_all_stages_and_commits_dirty_tree() -> None:
    runner = (
        ScriptedRunner()
        .on(("git", "status", "--porcelain"), stdout_tail=" M a.py\n?? b.txt\n")
        .on(("git", "add"), exit_code=0)
        .on(("git", "commit"), exit_code=0)
        .on(("git", "rev-parse"), stdout_tail="deadbeef\n")
    )
    adapter = GitCommandLineRunner(runner)
    info = await adapter.commit_all(workspace_path=WS, message="feat(gen-47): work")
    assert info.committed is True
    assert info.sha == "deadbeef"
    assert info.files_committed == 2
    add_argv = list(runner.requests[1].argv)
    assert add_argv[:2] == ["git", "add"]
    commit_argv = list(runner.requests[2].argv)
    assert "feat(gen-47): work" in commit_argv


async def test_commit_all_surfaces_git_failures() -> None:
    runner = (
        ScriptedRunner()
        .on(("git", "status", "--porcelain"), stdout_tail=" M a.py\n")
        .on(("git", "commit"), exit_code=128, stderr_tail="identity unknown")
    )
    adapter = GitCommandLineRunner(runner)
    with pytest.raises(SCMUnavailable, match="identity unknown"):
        await adapter.commit_all(workspace_path=WS, message="m")


async def test_push_branch_reports_success() -> None:
    runner = ScriptedRunner().on(("git", "push"), stdout_tail="Everything up-to-date\n")
    adapter = GitCommandLineRunner(runner)
    info = await adapter.push_branch(workspace_path=WS, branch_name="feat/gen-47-h2")
    assert isinstance(info, PushInfo)
    assert info.pushed is True
    argv = list(runner.requests[0].argv)
    assert argv[:2] == ["git", "push"]
    assert "feat/gen-47-h2" in argv


async def test_push_branch_surfaces_failures() -> None:
    runner = ScriptedRunner().on(
        ("git", "push"), exit_code=128, stderr_tail="remote: permission denied"
    )
    adapter = GitCommandLineRunner(runner)
    with pytest.raises(SCMUnavailable, match="permission denied"):
        await adapter.push_branch(workspace_path=WS, branch_name="b")


async def test_count_commits_ahead_parses_stdout() -> None:
    runner = ScriptedRunner().on(("git", "rev-list"), stdout_tail="3\n")
    adapter = GitCommandLineRunner(runner)
    assert await adapter.count_commits_ahead(workspace_path=WS, base_branch="main") == 3


async def test_count_commits_ahead_surfaces_failures() -> None:
    runner = ScriptedRunner().on(
        ("git", "rev-list"), exit_code=128, stderr_tail="unknown revision base"
    )
    adapter = GitCommandLineRunner(runner)
    with pytest.raises(SCMUnavailable, match="rev-list failed"):
        await adapter.count_commits_ahead(workspace_path=WS, base_branch="main")


async def test_runner_launch_failures_map_to_scm_unavailable(tmp_path: Path) -> None:
    path = tmp_path / "ws"
    path.mkdir()
    (path / ".git").mkdir()

    class _BrokenRunner(ScriptedRunner):
        async def run(self, request: object) -> object:
            raise ProcessLaunchError("cannot launch git: FileNotFoundError")

    adapter = GitCommandLineRunner(_BrokenRunner())
    with pytest.raises(SCMUnavailable, match="cannot launch"):
        await adapter.ensure_workspace(
            repository=REPO, base_branch="main", branch_name="b", workspace_path=str(path)
        )
