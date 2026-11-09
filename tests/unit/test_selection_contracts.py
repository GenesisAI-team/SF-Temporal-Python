"""Tests for cross-layer selection contracts (GEN-38 H1).

pydantic, frozen=True contracts live in ``contracts/``; the pure blocking
decision itself lives in ``domain/`` and is re-exported here for layering.
"""

import pytest
from pydantic import ValidationError

from super_factory.contracts.selection import (
    BlockingReason,
    IssueSelectionCriteria,
    IssueSelectionResult,
    IssueSnapshot,
    format_blocking_reasons,
)

REPO = "GenesisAI-team/SF-Temporal-Python"


def _criteria(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "selectable_states": ("Todo", "In Progress"),
        "allowed_repositories": (REPO,),
    }
    base.update(overrides)
    return base


def test_criteria_accepts_valid_configuration() -> None:
    criteria = IssueSelectionCriteria(**_criteria())
    assert criteria.selectable_states == ("Todo", "In Progress")
    assert criteria.allowed_repositories == (REPO,)


def test_criteria_is_frozen() -> None:
    criteria = IssueSelectionCriteria(**_criteria())
    with pytest.raises(ValidationError, match="frozen"):
        criteria.selectable_states = ("Done",)  # type: ignore[assignment,misc]


def test_criteria_rejects_empty_selectable_states() -> None:
    with pytest.raises(ValidationError, match="selectable_states"):
        IssueSelectionCriteria(**_criteria(selectable_states=()))


def test_criteria_rejects_blank_selectable_state() -> None:
    with pytest.raises(ValidationError, match="selectable_states"):
        IssueSelectionCriteria(**_criteria(selectable_states=("Todo", "   ")))


def test_criteria_rejects_malformed_repository() -> None:
    with pytest.raises(ValidationError, match="allowed_repositories"):
        IssueSelectionCriteria(**_criteria(allowed_repositories=("nope",)))


def test_criteria_permits_empty_allowlist_fail_closed() -> None:
    """An empty allowlist is valid config that blocks every repo decision later."""
    criteria = IssueSelectionCriteria(**_criteria(allowed_repositories=()))
    assert criteria.allowed_repositories == ()


def test_snapshot_accepts_parsed_issue() -> None:
    snapshot = IssueSnapshot(
        issue_id="GEN-38",
        title="H1 — webhook Linear",
        state="In Progress",
        labels=("Feature",),
    )
    assert snapshot.title == "H1 — webhook Linear"
    assert snapshot.labels == ("Feature",)


def test_snapshot_allows_unresolved_state_and_malformed_id() -> None:
    """Blank state / foreign issue ids are accepted data; the selector blocks them."""
    snapshot = IssueSnapshot(issue_id="ENG-417", title="t", state="", labels=())
    assert snapshot.state == ""
    assert snapshot.issue_id == "ENG-417"


def test_snapshot_is_frozen() -> None:
    snapshot = IssueSnapshot(issue_id="GEN-2", title="t", state="Todo", labels=())
    with pytest.raises(ValidationError, match="frozen"):
        snapshot.state = "Done"  # type: ignore[misc]


def test_domain_decision_types_re_exported_for_cross_layer_use() -> None:
    reason = BlockingReason(code="CODE", detail="d")
    result = IssueSelectionResult(approved=False, reasons=(reason,))
    assert format_blocking_reasons((reason,)) == "CODE: d"
    assert result.approved is False


def test_selection_result_cannot_carry_approved_with_reasons() -> None:
    """Domain invariant, re-exported via contracts: approved ⇒ no reasons."""
    reason = BlockingReason(code="CODE", detail="d")
    with pytest.raises(ValueError, match="approved"):
        IssueSelectionResult(approved=True, reasons=(reason,))
