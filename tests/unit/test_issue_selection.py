"""Tests for pure issue-selection rules (GEN-38 H1).

The selector is deterministic: it maps a Linear issue snapshot + selection
criteria to an accept/blocked decision with persisted blocking reasons.
"""

import dataclasses

import pytest

from super_factory.domain.issue_selection import (
    REASON_ISSUE_ID_MALFORMED,
    REASON_REPOSITORY_MALFORMED,
    REASON_REPOSITORY_NOT_ALLOWED,
    REASON_REPOSITORY_UNRESOLVED,
    REASON_STATE_NOT_SELECTABLE,
    REASON_STATE_UNRESOLVED,
    BlockingReason,
    evaluate_issue_selection,
    format_blocking_reason,
    format_blocking_reasons,
)

TARGET_REPOSITORY = "GenesisAI-team/SF-Temporal-Python"
SELECTABLE = ("Todo", "In Progress")
ALLOWED = (TARGET_REPOSITORY,)


def _evaluate(
    issue_id: str = "GEN-38",
    issue_state: str = "Todo",
    repository: str = TARGET_REPOSITORY,
    selectable_states: tuple[str, ...] = SELECTABLE,
    allowed_repositories: tuple[str, ...] = ALLOWED,
) -> object:
    return evaluate_issue_selection(
        issue_id=issue_id,
        issue_state=issue_state,
        repository=repository,
        selectable_states=selectable_states,
        allowed_repositories=allowed_repositories,
    )


@pytest.mark.parametrize("state", ["Todo", "In Progress"])
def test_selectable_state_is_approved(state: str) -> None:
    result = _evaluate(issue_state=state)
    assert result.approved is True  # type: ignore[union-attr]
    assert result.reasons == ()  # type: ignore[union-attr]


@pytest.mark.parametrize("state", ["Done", "Canceled", "Backlog", "In Review", "Triage"])
def test_non_selectable_state_is_blocked_with_reason(state: str) -> None:
    result = _evaluate(issue_state=state)
    assert result.approved is False  # type: ignore[union-attr]
    codes = [r.code for r in result.reasons]  # type: ignore[union-attr]
    assert codes == [REASON_STATE_NOT_SELECTABLE]


@pytest.mark.parametrize("state", ["", "   "])
def test_blank_state_is_blocked_as_unresolved(state: str) -> None:
    result = _evaluate(issue_state=state)
    assert result.approved is False  # type: ignore[union-attr]
    assert [r.code for r in result.reasons] == [REASON_STATE_UNRESOLVED]  # type: ignore[union-attr]


@pytest.mark.parametrize("issue_id", ["GEN-1", "GEN-1234"])
def test_valid_issue_id_does_not_block(issue_id: str) -> None:
    assert _evaluate(issue_id=issue_id).approved is True  # type: ignore[union-attr]


@pytest.mark.parametrize("issue_id", ["ENG-417", "gen-38", "17", ""])
def test_malformed_issue_id_is_blocked(issue_id: str) -> None:
    result = _evaluate(issue_id=issue_id)
    assert result.approved is False  # type: ignore[union-attr]
    codes = [r.code for r in result.reasons]  # type: ignore[union-attr]
    assert REASON_ISSUE_ID_MALFORMED in codes


def test_blank_repository_is_blocked_as_unresolved() -> None:
    result = _evaluate(repository="")
    assert result.approved is False  # type: ignore[union-attr]
    assert [r.code for r in result.reasons] == [REASON_REPOSITORY_UNRESOLVED]  # type: ignore[union-attr]


@pytest.mark.parametrize("repository", ["nope", "a/b/c", "owner/"])
def test_malformed_repository_is_blocked(repository: str) -> None:
    result = _evaluate(repository=repository)
    assert result.approved is False  # type: ignore[union-attr]
    codes = [r.code for r in result.reasons]  # type: ignore[union-attr]
    assert codes == [REASON_REPOSITORY_MALFORMED]


def test_repository_outside_allowlist_is_blocked() -> None:
    result = _evaluate(
        repository="owner/other",
        allowed_repositories=(TARGET_REPOSITORY,),
    )
    assert result.approved is False  # type: ignore[union-attr]
    assert [r.code for r in result.reasons] == [REASON_REPOSITORY_NOT_ALLOWED]  # type: ignore[union-attr]


def test_reasons_accumulate_for_multiple_failures() -> None:
    result = _evaluate(
        issue_id="ENG-5",
        issue_state="Done",
        repository="owner/other",
    )
    assert result.approved is False  # type: ignore[union-attr]
    codes = {r.code for r in result.reasons}  # type: ignore[union-attr]
    assert {
        REASON_ISSUE_ID_MALFORMED,
        REASON_STATE_NOT_SELECTABLE,
        REASON_REPOSITORY_NOT_ALLOWED,
    } == codes


def test_blocking_reason_is_immutable() -> None:
    reason = BlockingReason(code="X", detail="y")
    with pytest.raises(dataclasses.FrozenInstanceError):
        reason.code = "Y"  # type: ignore[misc]


def test_format_blocking_reason_without_detail_omits_separator() -> None:
    reason = BlockingReason(code=REASON_REPOSITORY_UNRESOLVED, detail="   ")
    assert format_blocking_reason(reason) == REASON_REPOSITORY_UNRESOLVED


def test_format_blocking_reason_joins_code_and_detail() -> None:
    reasons = (
        BlockingReason(code=REASON_STATE_NOT_SELECTABLE, detail="Done"),
        BlockingReason(code=REASON_REPOSITORY_NOT_ALLOWED, detail="owner/other"),
    )
    assert (
        format_blocking_reasons(reasons)
        == f"{REASON_STATE_NOT_SELECTABLE}: Done; {REASON_REPOSITORY_NOT_ALLOWED}: owner/other"
    )


def test_format_empty_reasons_serializes_to_empty_string() -> None:
    """Approved decisions leave no reason text in memo/audit sinks."""
    assert format_blocking_reasons(()) == ""
