"""Git CLI adapter for ``GitWorkspaces`` (GEN-47).

Idempotent workspace semantics:
- reuse an existing checkout (``existed=True``): create the branch when it is
  missing (e.g. previously unknown failure), reuse it when present;
- clone into a fresh workspace and branch from the base branch otherwise.

All commands run argv-style via the ``CommandRunner``; runner failures map
to ``SCMUnavailable`` (retryable). Never force-push.
"""

from pathlib import Path

from super_factory.contracts.scm import CommitInfo, PushInfo, WorkspaceStatus
from super_factory.process.ports import (
    CommandOutcome,
    CommandRequest,
    CommandRunner,
    ProcessLaunchError,
)
from super_factory.scm.ports import SCMUnavailable

_COMMAND_TIMEOUT_SECONDS = 120.0


class GitCommandLineRunner:
    """Real ``GitWorkspaces`` on top of the git CLI."""

    def __init__(
        self,
        command_runner: CommandRunner,
        *,
        user_name: str = "SF-Temporal-Python Factory",
        user_email: str = "factory@sf-temporal.local",
    ) -> None:
        self._runner = command_runner
        self._user_name = user_name
        self._user_email = user_email

    async def ensure_workspace(
        self, repository: str, base_branch: str, branch_name: str, workspace_path: str
    ) -> WorkspaceStatus:
        path = Path(workspace_path)
        git_dir = path / ".git"
        if path.exists() and not git_dir.exists():  # noqa: ASYNC240 -existence probe only
            msg = f"workspace path {workspace_path} exists without a git repository"
            raise SCMUnavailable(msg)
        if path.exists():  # noqa: ASYNC240
            probe = await self._git(("rev-parse", "--verify", branch_name), str(path))
            if probe.exit_code == 0:
                return WorkspaceStatus(
                    path=str(path), existed=True, branch_existed=True
                )
            checkout = await self._git(("checkout", "-b", branch_name), str(path))
            self._ensure_ok(checkout, "checkout -b")
            return WorkspaceStatus(
                path=str(path), existed=True, branch_existed=False
            )
        clone = await self._git(("clone", "--branch", base_branch, repository, str(path)))
        self._ensure_ok(clone, "clone")
        checkout = await self._git(("checkout", "-b", branch_name), str(path))
        self._ensure_ok(checkout, "checkout -b")
        return WorkspaceStatus(path=str(path), existed=False, branch_existed=False)

    async def commit_all(self, workspace_path: str, message: str) -> CommitInfo:
        status = await self._git(("status", "--porcelain"), workspace_path)
        self._ensure_ok(status, "status")
        if not status.stdout_tail.strip():
            return CommitInfo(committed=False, detail="working tree clean")
        staged = await self._git(("add", "-A"), workspace_path)
        self._ensure_ok(staged, "add")
        committed = await self._git(self._commit_argv(message), workspace_path)
        self._ensure_ok(committed, "commit")
        sha = await self._git(("rev-parse", "HEAD"), workspace_path)
        self._ensure_ok(sha, "rev-parse")
        files = sum(1 for line in status.stdout_tail.splitlines() if line.strip())
        return CommitInfo(
            committed=True, sha=sha.stdout_tail.strip(), files_committed=files
        )

    def _commit_argv(self, message: str) -> tuple[str, ...]:
        """Commit with an explicit identity (CI hosts have no global config)."""
        return (
            "-c",
            f"user.name={self._user_name}",
            "-c",
            f"user.email={self._user_email}",
            "commit",
            "-m",
            message,
        )

    async def push_branch(self, workspace_path: str, branch_name: str) -> PushInfo:
        pushed = await self._git(
            ("push", "-u", "origin", branch_name), workspace_path
        )
        self._ensure_ok(pushed, "push")
        return PushInfo(
            pushed=True,
            detail=pushed.stdout_tail.strip() or pushed.stderr_tail.strip(),
        )

    async def count_commits_ahead(self, workspace_path: str, base_branch: str) -> int:
        counted = await self._git(
            ("rev-list", "--count", f"{base_branch}..HEAD"), workspace_path
        )
        if counted.exit_code != 0:
            msg = f"git rev-list failed: {counted.stderr_tail.strip()}"
            raise SCMUnavailable(msg)
        return int(counted.stdout_tail.strip() or "0")

    async def _git(self, args: tuple[str, ...], cwd: str | None = None) -> CommandOutcome:
        request = CommandRequest(
            argv=("git", *args), cwd=cwd, timeout_seconds=_COMMAND_TIMEOUT_SECONDS
        )
        try:
            return await self._runner.run(request)
        except ProcessLaunchError as exc:
            raise SCMUnavailable(str(exc)) from exc

    @staticmethod
    def _ensure_ok(outcome: CommandOutcome, verb: str) -> None:
        if outcome.exit_code != 0:
            msg = f"git {verb} failed: {(outcome.stderr_tail or outcome.stdout_tail).strip()}"
            raise SCMUnavailable(msg)
