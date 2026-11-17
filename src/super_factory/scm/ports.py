"""SCM ports (GEN-47): git workspaces and pull-request publication.

The publication phase never calls GitHub's API directly; it goes through
``GitWorkspaces`` (branch/commit/push) and ``PullRequestsService``
(find/open) so adapters are replaceable and tests stay hermetic.
"""

from typing import Protocol

from super_factory.contracts.scm import (
    CommitInfo,
    PullRequestRef,
    PushInfo,
    WorkspaceStatus,
)


class SCMUnavailable(RuntimeError):
    """The SCM layer failed transiently (missing binary, auth, outage)."""


class GitWorkspaces(Protocol):
    """Port over disposable git workspaces per run."""

    async def ensure_workspace(
        self, repository: str, base_branch: str, branch_name: str, workspace_path: str
    ) -> WorkspaceStatus:
        """Create or reuse a workspace checked out at the factory branch."""
        ...

    async def commit_all(self, workspace_path: str, message: str) -> CommitInfo:
        """Commit every pending change onto the factory branch."""
        ...

    async def push_branch(self, workspace_path: str, branch_name: str) -> PushInfo:
        """Push the factory branch (idempotent, no force)."""
        ...

    async def count_commits_ahead(self, workspace_path: str, base_branch: str) -> int:
        """Commits on the factory branch that are not on the base branch."""
        ...


class PullRequestsService(Protocol):
    """Port over the repository holder's pull requests (GitHub in H2)."""

    async def find_open(
        self, repository: str, head_branch: str
    ) -> PullRequestRef | None:
        """Existing open PR for a head branch, or None."""
        ...

    async def open(
        self,
        repository: str,
        base_branch: str,
        head_branch: str,
        title: str,
        body: str,
    ) -> PullRequestRef:
        """Open a pull request and return its reference."""
        ...
