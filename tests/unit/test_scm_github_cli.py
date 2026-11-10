"""Tests for the GitHub CLI pull-request adapter (GEN-47) with a scripted runner.

Acceptance: open PRs are found by head branch (no duplicates created),
creations are parsed from the CLI output, and gh failures surface as
SCMUnavailable with the detail tail.
"""

import json

import pytest

from super_factory.contracts.scm import PullRequestRef
from super_factory.process.ports import ProcessLaunchError
from super_factory.scm.github_cli import GhCliPullRequests
from super_factory.scm.ports import SCMUnavailable
from tests.unit.command_runner_stubs import ScriptedRunner

REPO = "GenesisAI-team/SF-Temporal-Python"
HEAD = "feat/gen-47-h2"


def _list_payload() -> str:
    return json.dumps(
        [
            {
                "number": 9,
                "url": f"https://github.com/{REPO}/pull/9",
                "headRefName": HEAD,
                "baseRefName": "main",
            }
        ]
    )


async def test_find_open_returns_existing_pull_request() -> None:
    runner = ScriptedRunner().on(("gh", "pr", "list"), stdout_tail=_list_payload())
    adapter = GhCliPullRequests(runner)
    ref = await adapter.find_open(repository=REPO, head_branch=HEAD)
    assert ref == PullRequestRef(
        number=9,
        url=f"https://github.com/{REPO}/pull/9",
        head_branch=HEAD,
        base_branch="main",
    )
    argv = list(runner.requests[0].argv)
    assert argv[:2] == ["gh", "pr"]
    assert "--head" in argv and HEAD in argv
    assert "--state" in argv and "open" in argv


async def test_find_open_returns_none_when_absent() -> None:
    runner = ScriptedRunner().on(("gh", "pr", "list"), stdout_tail="[]")
    adapter = GhCliPullRequests(runner)
    assert await adapter.find_open(repository=REPO, head_branch=HEAD) is None


async def test_find_open_surfaces_gh_failures() -> None:
    runner = ScriptedRunner().on(
        ("gh", "pr", "list"), exit_code=4, stderr_tail="token missing"
    )
    adapter = GhCliPullRequests(runner)
    with pytest.raises(SCMUnavailable, match="token missing"):
        await adapter.find_open(repository=REPO, head_branch=HEAD)


async def test_find_open_surfaces_broken_json() -> None:
    runner = ScriptedRunner().on(("gh", "pr", "list"), stdout_tail="not json")
    adapter = GhCliPullRequests(runner)
    with pytest.raises(SCMUnavailable, match="parse"):
        await adapter.find_open(repository=REPO, head_branch=HEAD)


async def test_open_creates_and_parses_pull_request() -> None:
    runner = ScriptedRunner().on(
        ("gh", "pr", "create"),
        stdout_tail=f"Created\nhttps://github.com/{REPO}/pull/12\n",
    )
    adapter = GhCliPullRequests(runner)
    ref = await adapter.open(
        repository=REPO,
        base_branch="main",
        head_branch=HEAD,
        title="feat(gen-47): H2",
        body="PR body\n",
    )
    assert ref == PullRequestRef(
        number=12,
        url=f"https://github.com/{REPO}/pull/12",
        head_branch=HEAD,
        base_branch="main",
    )
    argv = list(runner.requests[0].argv)
    for flag, value in (
        ("--repo", REPO),
        ("--base", "main"),
        ("--head", HEAD),
        ("--title", "feat(gen-47): H2"),
        ("--body", "PR body\n"),
    ):
        assert flag in argv
        assert argv[argv.index(flag) + 1] == value


async def test_open_surfaces_failures() -> None:
    runner = ScriptedRunner().on(
        ("gh", "pr", "create"), exit_code=1, stderr_tail="gh never authenticated"
    )
    adapter = GhCliPullRequests(runner)
    with pytest.raises(SCMUnavailable, match="never authenticated"):
        await adapter.open(
            repository=REPO,
            base_branch="main",
            head_branch=HEAD,
            title="t",
            body="b",
        )


async def test_open_surfaces_unparsable_output() -> None:
    runner = ScriptedRunner().on(("gh", "pr", "create"), stdout_tail="weird\n")
    adapter = GhCliPullRequests(runner)
    with pytest.raises(SCMUnavailable, match="URL"):
        await adapter.open(
            repository=REPO, base_branch="main", head_branch=HEAD, title="t", body="b"
        )


async def test_gh_launch_failures_map_to_scm_unavailable() -> None:
    class _BrokenRunner(ScriptedRunner):
        async def run(self, request: object) -> object:
            raise ProcessLaunchError("cannot launch gh: FileNotFoundError")

    adapter = GhCliPullRequests(_BrokenRunner())
    with pytest.raises(SCMUnavailable, match="cannot launch"):
        await adapter.find_open(repository=REPO, head_branch=HEAD)
