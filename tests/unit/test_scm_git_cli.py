"""Tests for the git CLI workspaces adapter (GEN-47) with a scripted runner.

Acceptance: workspace ensure is idempotent per (repository, branch) — reuse
existing checkouts, create the missing branch, clone missing workspaces;
commit/push behave idempotently; runner/git failures surface as
SCMUnavailable; agent-controlled git metadata (hooks/config) is neutralized
before every host-side git operation (P1 review finding).
"""

from pathlib import Path

import pytest

from super_factory.contracts.scm import CommitInfo, PushInfo, WorkspaceStatus
from super_factory.process.ports import CommandRequest, ProcessLaunchError
from super_factory.process.subprocess import SubprocessCommandRunner
from super_factory.scm.git_cli import GitCommandLineRunner, sanitize_agent_git_metadata
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
    assert clone_argv[-2:] == [f"https://github.com/{REPO}.git", str(path)]
    checkout_argv = list(runner.requests[1].argv)
    assert checkout_argv[:3] == ["git", "checkout", "-b"]
    assert "feat/gen-47-h2" in checkout_argv
    assert runner.requests[1].cwd == str(path)


async def _clone_source_for(
    repository: str, path: Path, *, template: str | None = None
) -> str:
    runner = ScriptedRunner()
    adapter = (
        GitCommandLineRunner(runner)
        if template is None
        else GitCommandLineRunner(runner, repository_url_template=template)
    )
    status = await adapter.ensure_workspace(
        repository=repository,
        base_branch="main",
        branch_name="feat/gen-47-h2",
        workspace_path=str(path),
    )
    assert status.existed is False
    return list(runner.requests[0].argv)[-2]


async def test_ensure_workspace_resolves_slug_to_https_clone_url(
    tmp_path: Path,
) -> None:
    assert (
        await _clone_source_for(REPO, tmp_path / "ws")
        == f"https://github.com/{REPO}.git"
    )


async def test_ensure_workspace_uses_configured_transport_template(
    tmp_path: Path,
) -> None:
    assert (
        await _clone_source_for(
            REPO,
            tmp_path / "ws",
            template="git@github.com:{repository}.git",
        )
        == f"git@github.com:{REPO}.git"
    )


async def test_ensure_workspace_passes_urls_and_local_paths_through(
    tmp_path: Path,
) -> None:
    url = "https://example.com/owner/repo.git"
    assert await _clone_source_for(url, tmp_path / "u") == url
    scp = "git@github.com:owner/repo.git"
    assert await _clone_source_for(scp, tmp_path / "s") == scp
    local = str(tmp_path / "remote.git")
    assert await _clone_source_for(local, tmp_path / "l") == local
    relative = "./fixtures/repo"
    assert await _clone_source_for(relative, tmp_path / "r") == relative


def test_git_runner_rejects_template_without_placeholder() -> None:
    with pytest.raises(ValueError, match="placeholder"):
        GitCommandLineRunner(
            ScriptedRunner(), repository_url_template="https://github.com/fixed"
        )


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
        .on(("git", "-c"), exit_code=0)
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
    assert commit_argv[:2] == ["git", "-c"]
    assert "user.name=SF-Temporal-Python Factory" in commit_argv
    assert "feat(gen-47): work" in commit_argv
    indexed_message = commit_argv[commit_argv.index("-m") + 1]
    assert indexed_message == "feat(gen-47): work"


async def test_commit_identity_is_configurable() -> None:
    runner = (
        ScriptedRunner()
        .on(("git", "status", "--porcelain"), stdout_tail=" M a.py\n")
        .on(("git", "-c"), exit_code=0)
        .on(("git", "rev-parse"), stdout_tail="cafe\n")
    )
    adapter = GitCommandLineRunner(
        runner, user_name="Genesis Bot", user_email="bot@genesis.example"
    )
    await adapter.commit_all(workspace_path=WS, message="m")
    commit_argv = list(runner.requests[2].argv)
    assert "user.name=Genesis Bot" in commit_argv
    assert "user.email=bot@genesis.example" in commit_argv


async def test_commit_all_surfaces_git_failures() -> None:
    runner = (
        ScriptedRunner()
        .on(("git", "status", "--porcelain"), stdout_tail=" M a.py\n")
        .on(("git", "-c"), exit_code=128, stderr_tail="identity unknown")
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


# --- P1 review finding: agent-controlled git metadata must never execute ---


async def _run_git(argv: tuple[str, ...], cwd: Path) -> None:
    """Run a real git command (test setup only); fail loudly on errors."""
    outcome = await SubprocessCommandRunner().run(
        CommandRequest(argv=("git", *argv), cwd=str(cwd), timeout_seconds=60.0)
    )
    assert outcome.exit_code == 0, outcome.stderr_tail or outcome.stdout_tail


async def _fresh_real_repo(tmp_path: Path) -> Path:
    """Create a real git repository with one commit and a trusted config."""
    repo = tmp_path / "repo"
    await _run_git(("init", "-b", "main", "repo"), tmp_path)
    await _run_git(("config", "user.name", "Test User"), repo)
    await _run_git(("config", "user.email", "test@example.com"), repo)
    (repo / "base.txt").write_text("base\n")
    await _run_git(("add", "-A"), repo)
    await _run_git(("commit", "-m", "base"), repo)
    return repo


def _poison(repo: Path, hook_name: str) -> None:
    """Write hostile hooks/config the way a sandboxed agent would."""
    hooks = repo / ".git" / "hooks"
    hooks.mkdir(exist_ok=True)
    hook = hooks / hook_name
    hook.write_text(f"#!/bin/sh\necho ran > {hook_name}-marker.txt\nexit 1\n")
    hook.chmod(0o755)
    (repo / ".gitattributes").write_text("* filter=evil\n")
    config = repo / ".git" / "config"
    config.write_text(
        config.read_text() + '[filter "evil"]\n\tclean = echo ran > filter-marker.txt\n'
    )


async def test_commit_all_never_executes_agent_controlled_git_code(
    tmp_path: Path,
) -> None:
    """Host-side commit must neutralize agent hooks and filters (P1 finding)."""
    repo = await _fresh_real_repo(tmp_path)
    _poison(repo, "pre-commit")
    (repo / "agent.txt").write_text("agent work\n")
    adapter = GitCommandLineRunner(SubprocessCommandRunner())
    info = await adapter.commit_all(
        workspace_path=str(repo), message="feat(gen-47): agent work"
    )
    assert info.committed is True
    assert not (repo / "pre-commit-marker.txt").exists()
    assert not (repo / "filter-marker.txt").exists()
    assert not (repo / ".git" / "hooks").exists()
    sanitized = (repo / ".git" / "config").read_text()
    assert "[filter" not in sanitized
    assert "user.name" not in sanitized


async def test_ensure_workspace_never_executes_agent_controlled_hooks(
    tmp_path: Path,
) -> None:
    """Existing-workspace ensure must sanitize hooks before checkout (P1)."""
    repo = await _fresh_real_repo(tmp_path)
    _poison(repo, "post-checkout")
    adapter = GitCommandLineRunner(SubprocessCommandRunner())
    status = await adapter.ensure_workspace(
        repository=REPO,
        base_branch="main",
        branch_name="feat/gen-47-new",
        workspace_path=str(repo),
    )
    assert status.existed is True
    assert status.branch_existed is False
    assert not (repo / "post-checkout-marker.txt").exists()
    assert not (repo / ".git" / "hooks").exists()
    sanitized = (repo / ".git" / "config").read_text()
    assert "[filter" not in sanitized


def test_sanitize_agent_git_metadata_strips_execution_vectors(tmp_path: Path) -> None:
    """Whitelist rewrite: hooks/filters/aliases/includes never survive."""
    repo = tmp_path / "repo"
    git_dir = repo / ".git"
    (git_dir / "hooks").mkdir(parents=True)
    (git_dir / "hooks" / "pre-commit").write_text("evil")
    (git_dir / "info").mkdir()
    (git_dir / "info" / "attributes").write_text("* filter=evil")
    (git_dir / "config.worktree").write_text("[core]\n\teditor = evil\n")
    (git_dir / "config").write_text(
        "[core]\n"
        "\trepositoryformatversion = 0\n"
        "\tbare = false\n"
        "\thooksPath = evil-hooks\n"
        "\tfsmonitor = evil-fsmonitor\n"
        "[extensions]\n"
        "\tworktreeConfig = true\n"
        "\tobjectFormat = sha1\n"
        '[remote "origin"]\n'
        "\turl = https://example.com/owner/repo.git\n"
        "\tpushurl = https://evil.example/push.git\n"
        "[alias]\n"
        "\tstatus = !evil\n"
        '[filter "evil"]\n'
        "\tclean = evil\n"
        "[include]\n"
        "\tpath = evil\n"
    )
    sanitize_agent_git_metadata(repo)
    assert not (git_dir / "hooks").exists()
    assert not (git_dir / "info" / "attributes").exists()
    assert not (git_dir / "config.worktree").exists()
    sanitized = (git_dir / "config").read_text()
    assert "hooksPath" not in sanitized
    assert "fsmonitor" not in sanitized
    assert "pushurl" not in sanitized
    assert "worktreeConfig" not in sanitized
    assert "[alias]" not in sanitized
    assert "[filter" not in sanitized
    assert "[include]" not in sanitized
    assert "repositoryformatversion = 0" in sanitized
    assert "objectformat = sha1" in sanitized
    assert '[remote "origin"]' in sanitized
    assert "https://example.com/owner/repo.git" in sanitized


def test_sanitize_agent_git_metadata_neutralizes_minimal_config(
    tmp_path: Path,
) -> None:
    """Nothing safe to keep leaves an empty config; file-shaped hooks go too."""
    repo = tmp_path / "repo"
    git_dir = repo / ".git"
    git_dir.mkdir(parents=True)
    (git_dir / "hooks").write_text("not a directory")
    (git_dir / "config").write_text("[alias]\n\tco = checkout\n")
    sanitize_agent_git_metadata(repo)
    assert not (git_dir / "hooks").exists()
    assert (git_dir / "config").read_text() == ""


def test_sanitize_agent_git_metadata_rejects_non_directory_git_dir(
    tmp_path: Path,
) -> None:
    """Fail closed: a .git file (worktree pointer) is an unsupported layout."""
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".git").write_text("gitdir: elsewhere\n")
    with pytest.raises(SCMUnavailable, match="unsupported git metadata layout"):
        sanitize_agent_git_metadata(repo)


def test_sanitize_agent_git_metadata_ignores_missing_git_dir(tmp_path: Path) -> None:
    """No .git at all: nothing to sanitize (git reports the missing repo)."""
    sanitize_agent_git_metadata(tmp_path)


def test_sanitize_agent_git_metadata_tolerates_malformed_config(tmp_path: Path) -> None:
    """Comments, blank lines and garbage lines are skipped, not fatal."""
    repo = tmp_path / "repo"
    git_dir = repo / ".git"
    git_dir.mkdir(parents=True)
    (git_dir / "config").write_text(
        "# agent note\n"
        "\n"
        "orphan line without section\n"
        "[core]\n"
        "bare = false\n"
        "dangling key line\n"
    )
    sanitize_agent_git_metadata(repo)
    sanitized = (git_dir / "config").read_text()
    assert "bare = false" in sanitized
    assert "agent note" not in sanitized
