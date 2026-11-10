"""Tests for the selection activity (GEN-38 H1).

The activity applies the pure selector to the workflow input; it has no I/O
and returns formatted reasons for the audit trail.
"""

from super_factory.contracts.workflow_io import IssueWorkflowInput, SelectIssueResult
from super_factory.temporal.activities.selection import select_issue_activity

REPO = "GenesisAI-team/SF-Temporal-Python"
DELIVERY = "234d1a4e-b617-4388-90fe-adc3633d6b72"


def _input(**overrides: object) -> IssueWorkflowInput:
    fields: dict[str, object] = {
        "issue_id": "GEN-38",
        "repository": REPO,
        "issue_state": "Todo",
        "labels": ("Feature",),
        "title": "H1",
        "delivery_id": DELIVERY,
        "event_action": "update",
        "event_type": "Issue",
        "selectable_states": ("Todo", "In Progress"),
        "allowed_repositories": (REPO,),
    }
    fields.update(overrides)
    return IssueWorkflowInput(**fields)


async def test_selects_when_all_criteria_pass() -> None:
    result = await select_issue_activity(_input())
    assert result == SelectIssueResult(approved=True, reasons=())


async def test_blocks_done_issue_with_state_reason() -> None:
    result = await select_issue_activity(_input(issue_state="Done"))
    assert result.approved is False
    assert result.reasons == ("STATE_NOT_SELECTABLE: Done",)


async def test_blocks_foreign_issue_identifier() -> None:
    result = await select_issue_activity(_input(issue_id="ENG-417"))
    assert result.approved is False
    assert result.reasons == ("ISSUE_ID_MALFORMED: ENG-417",)


async def test_blocks_repository_not_in_criteria() -> None:
    result = await select_issue_activity(
        _input(repository="owner/elsewhere", allowed_repositories=(REPO,))
    )
    assert result.approved is False
    assert result.reasons == ("REPOSITORY_NOT_ALLOWED: owner/elsewhere",)


async def test_reasons_preserve_selection_state() -> None:
    result = await select_issue_activity(_input(issue_id="", issue_state="Done"))
    assert len(result.reasons) == 2
    assert result.reasons[0].startswith("ISSUE_ID_MALFORMED")
    assert result.reasons[1].startswith("STATE_NOT_SELECTABLE")
