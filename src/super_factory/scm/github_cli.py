"""GitHub CLI adapter for ``PullRequestsService`` (GEN-47).

Uses the ``gh`` CLI via the ``CommandRunner`` port so production only
configures authentication and tests stay hermetic. find_open() enables the
no-duplicate-PR guarantee; open() parses the created URL.
"""

import json
import re
from typing import Any, cast

from pydantic import ValidationError

from super_factory.contracts.scm import PullRequestRef
from super_factory.process.ports import (
    CommandOutcome,
    CommandRequest,
    CommandRunner,
    ProcessLaunchError,
)
from super_factory.scm.ports import SCMUnavailable

_COMMAND_TIMEOUT_SECONDS = 120.0
_URL_PATTERN = re.compile(r"https://\S+/pull/(\d+)")


class GhCliPullRequests:
    """Real ``PullRequestsService`` on top of the gh CLI."""

    def __init__(self, command_runner: CommandRunner) -> None:
        self._runner = command_runner

    async def find_open(
        self, repository: str, head_branch: str
    ) -> PullRequestRef | None:
        outcome = await self._gh(
            (
                "pr",
                "list",
                "--repo",
                repository,
                "--head",
                head_branch,
                "--state",
                "open",
                "--json",
                "number,url,headRefName,baseRefName",
            )
        )
        if outcome.exit_code != 0:
            msg = f"gh pr list failed: {outcome.stderr_tail.strip()}"
            raise SCMUnavailable(msg)
        try:
            raw = json.loads(outcome.stdout_tail or "[]")
        except json.JSONDecodeError as exc:
            msg = "cannot parse gh pr list output"
            raise SCMUnavailable(msg) from exc
        entries = cast("list[dict[str, Any]]", raw)
        if not entries:
            return None
        first = entries[0]
        try:
            return PullRequestRef(
                number=int(first["number"]),
                url=str(first["url"]),
                head_branch=str(first["headRefName"]),
                base_branch=str(first["baseRefName"]),
            )
        except (KeyError, TypeError, ValueError, ValidationError) as exc:
            msg = "cannot parse gh pr list entry"
            raise SCMUnavailable(msg) from exc

    async def open(
        self,
        repository: str,
        base_branch: str,
        head_branch: str,
        title: str,
        body: str,
    ) -> PullRequestRef:
        outcome = await self._gh(
            (
                "pr",
                "create",
                "--repo",
                repository,
                "--base",
                base_branch,
                "--head",
                head_branch,
                "--title",
                title,
                "--body",
                body,
            )
        )
        if outcome.exit_code != 0:
            msg = f"gh pr create failed: {outcome.stderr_tail.strip()}"
            raise SCMUnavailable(msg)
        match = _URL_PATTERN.search(outcome.stdout_tail)
        if match is None:
            msg = "cannot parse PR URL from gh output"
            raise SCMUnavailable(msg)
        return PullRequestRef(
            number=int(match.group(1)),
            url=match.group(0),
            head_branch=head_branch,
            base_branch=base_branch,
        )

    async def _gh(self, args: tuple[str, ...]) -> CommandOutcome:
        request = CommandRequest(argv=("gh", *args), timeout_seconds=_COMMAND_TIMEOUT_SECONDS)
        try:
            return await self._runner.run(request)
        except ProcessLaunchError as exc:
            raise SCMUnavailable(str(exc)) from exc
