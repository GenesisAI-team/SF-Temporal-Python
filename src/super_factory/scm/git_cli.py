"""Git CLI adapter for ``GitWorkspaces`` (GEN-47).

Idempotent workspace semantics:
- reuse an existing checkout (``existed=True``): create the branch when it is
  missing (e.g. previously unknown failure), reuse it when present;
- clone into a fresh workspace and branch from the base branch otherwise.

Security (P1 review finding): the workspace is agent-writable (mounted into
the sandbox), so its git metadata is untrusted. Before every host-side git
operation on an existing workspace the factory neutralizes execution vectors
it does not control: hooks are removed and ``.git/config`` is rewritten to a
whitelist (origin URL + inert core keys only). Decision: sanitize by
rewriting metadata rather than trusting per-operation flags — ``--no-verify``
covers commit only, not checkout/push/filters, and config whitelisting also
neutralizes ``core.hooksPath``/``fsmonitor``/aliases defined outside
``.git/hooks``.

Repository references (P1 review finding): the pipeline validates
``repository`` as an ``owner/name`` slug, but ``git clone`` treats a slug as a
filesystem path. Slugs are resolved to the configured Git transport URL before
cloning; real URLs, scp-like refs and local paths pass through untouched.

All commands run argv-style via the ``CommandRunner``; runner failures map
to ``SCMUnavailable`` (retryable). Never force-push.
"""

import contextlib
import os
import re
import shutil
from pathlib import Path

from super_factory.contracts.scm import CommitInfo, PushInfo, WorkspaceStatus
from super_factory.domain.repository_spec import is_valid_repository
from super_factory.process.ports import (
    CommandOutcome,
    CommandRequest,
    CommandRunner,
    ProcessLaunchError,
)
from super_factory.scm.ports import SCMUnavailable

_COMMAND_TIMEOUT_SECONDS = 120.0
_DEFAULT_REPOSITORY_URL_TEMPLATE = "https://github.com/{repository}.git"
_REPOSITORY_PLACEHOLDER = "{repository}"
_SCP_LIKE_SOURCE = re.compile(r"^[^/\s]+@[^/\s]+:")
_WINDOWS_DRIVE_PATH = re.compile(r"^[A-Za-z]:[\\/]")

_SAFE_CORE_KEYS = frozenset(
    {
        "repositoryformatversion",
        "bare",
        "logallrefupdates",
        "filemode",
        "ignorecase",
        "precomposeunicode",
    }
)
_SAFE_REMOTE_KEYS = frozenset({"url"})
_UNSAFE_EXTENSION_KEYS = frozenset({"worktreeconfig"})
_ORIGIN_SECTION = 'remote "origin"'


def sanitize_agent_git_metadata(workspace_path: str | Path) -> None:
    """Neutralize agent-controlled git execution vectors in a workspace.

    Removes ``.git/hooks`` (any hook could run arbitrary host code) and
    rewrites ``.git/config`` keeping only whitelisted, execution-inert keys,
    so filters/aliases/includes/``core.hooksPath``/``fsmonitor`` set by the
    agent can never spawn processes. The origin URL survives (a ``pushurl``
    override does not: it would redirect the publish). Fail-closed: a
    symlinked or file-shaped ``.git`` is rejected as an unsupported layout;
    a missing ``.git`` is a no-op (git reports the missing repository).
    """
    git_dir = Path(workspace_path) / ".git"
    if not git_dir.exists():
        return
    if git_dir.is_symlink() or not git_dir.is_dir():
        msg = f"unsupported git metadata layout in {workspace_path}"
        raise SCMUnavailable(msg)
    _remove_tree(git_dir / "hooks")
    _remove_tree(git_dir / "info" / "attributes")
    _remove_tree(git_dir / "config.worktree")
    config = git_dir / "config"
    if config.exists() or config.is_symlink():
        original = ""
        with contextlib.suppress(OSError):
            original = config.read_text(encoding="utf-8", errors="replace")
        _replace_config(config, _trusted_config_text(original))


def _remove_tree(target: Path) -> None:
    """Remove a directory tree, a plain file, or a symlink (never its target)."""
    if target.is_dir() and not target.is_symlink():
        shutil.rmtree(target)
        return
    target.unlink(missing_ok=True)


def _replace_config(config: Path, text: str) -> None:
    """Atomically replace the config file (a symlink is replaced, not followed)."""
    tmp = config.with_name("config.sanitize")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, config)


def _parse_config(text: str) -> dict[str, dict[str, str]]:
    """Parse git config text into ``{section: {key: value}}`` (names lowercased)."""
    sections: dict[str, dict[str, str]] = {}
    current: str | None = None
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith(("#", ";")):
            continue
        if line.startswith("[") and line.endswith("]"):
            current = line[1:-1].strip().lower()
            sections.setdefault(current, {})
            continue
        if current is None or "=" not in line:
            continue
        key, _, value = line.partition("=")
        sections[current][key.strip().lower()] = value.strip()
    return sections


def _trusted_config_text(original: str) -> str:
    """Rebuild config text keeping only execution-inert whitelisted keys."""
    sections = _parse_config(original)
    kept: list[tuple[str, dict[str, str]]] = [
        (
            "core",
            {
                key: value
                for key, value in sections.get("core", {}).items()
                if key in _SAFE_CORE_KEYS
            },
        ),
        (
            "extensions",
            {
                key: value
                for key, value in sections.get("extensions", {}).items()
                if key not in _UNSAFE_EXTENSION_KEYS
            },
        ),
        (
            _ORIGIN_SECTION,
            {
                key: value
                for key, value in sections.get(_ORIGIN_SECTION, {}).items()
                if key in _SAFE_REMOTE_KEYS
            },
        ),
    ]
    lines: list[str] = []
    for name, entries in kept:
        if not entries:
            continue
        lines.append(f"[{name}]")
        lines.extend(f"\t{key} = {value}" for key, value in entries.items())
    if not lines:
        return ""
    return "\n".join(lines) + "\n"


def resolve_clone_source(repository: str, url_template: str) -> str:
    """Turn an ``owner/name`` slug into the configured Git transport URL.

    ``git clone`` resolves a slug as a local path, never as a GitHub
    repository, so only a bare slug needs rewriting. A URL, an scp-like ref or
    a local path is already a usable clone source and passes through.
    """
    if _is_clone_source(repository) or not is_valid_repository(repository):
        return repository
    return url_template.format(repository=repository)


def _is_clone_source(repository: str) -> bool:
    """Return True when ``repository`` is already something git can clone."""
    if "://" in repository or _SCP_LIKE_SOURCE.match(repository):
        return True
    if repository.endswith(".git"):
        return True
    if repository.startswith((".", "~")) or "\\" in repository:
        return True
    return Path(repository).is_absolute() or bool(
        _WINDOWS_DRIVE_PATH.match(repository)
    )


class GitCommandLineRunner:
    """Real ``GitWorkspaces`` on top of the git CLI."""

    def __init__(
        self,
        command_runner: CommandRunner,
        *,
        user_name: str = "SF-Temporal-Python Factory",
        user_email: str = "factory@sf-temporal.local",
        repository_url_template: str = _DEFAULT_REPOSITORY_URL_TEMPLATE,
    ) -> None:
        if _REPOSITORY_PLACEHOLDER not in repository_url_template:
            msg = (
                "repository URL template must contain the "
                f"{_REPOSITORY_PLACEHOLDER} placeholder"
            )
            raise ValueError(msg)
        self._runner = command_runner
        self._user_name = user_name
        self._user_email = user_email
        self._repository_url_template = repository_url_template

    async def ensure_workspace(
        self, repository: str, base_branch: str, branch_name: str, workspace_path: str
    ) -> WorkspaceStatus:
        path = Path(workspace_path)
        git_dir = path / ".git"
        if path.exists() and not git_dir.exists():  # noqa: ASYNC240 -existence probe only
            msg = f"workspace path {workspace_path} exists without a git repository"
            raise SCMUnavailable(msg)
        if path.exists():  # noqa: ASYNC240
            sanitize_agent_git_metadata(path)
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
        clone_source = resolve_clone_source(repository, self._repository_url_template)
        clone = await self._git(
            ("clone", "--branch", base_branch, clone_source, str(path))
        )
        self._ensure_ok(clone, "clone")
        checkout = await self._git(("checkout", "-b", branch_name), str(path))
        self._ensure_ok(checkout, "checkout -b")
        return WorkspaceStatus(path=str(path), existed=False, branch_existed=False)

    async def commit_all(self, workspace_path: str, message: str) -> CommitInfo:
        sanitize_agent_git_metadata(workspace_path)
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
        sanitize_agent_git_metadata(workspace_path)
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
