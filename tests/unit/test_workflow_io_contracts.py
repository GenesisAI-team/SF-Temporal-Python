"""Tests for the Temporal-boundary workflow I/O contracts (GEN-38 H1).

Plain frozen dataclasses: the Temporal default data converter supports
dataclasses (see temporalio 1.35); they must stay immutable and serializable.
"""

import dataclasses

import pytest

from super_factory.contracts.workflow_io import (
    IssueWorkflowInput,
    IssueWorkflowResult,
    SelectIssueResult,
)


def _input(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "issue_id": "GEN-38",
        "repository": "GenesisAI-team/SF-Temporal-Python",
        "issue_state": "Todo",
        "labels": ("Feature",),
        "title": "H1",
        "delivery_id": "234d1a4e-b617-4388-90fe-adc3633d6b72",
        "event_action": "update",
        "event_type": "Issue",
        "selectable_states": ("Todo", "In Progress"),
        "allowed_repositories": ("GenesisAI-team/SF-Temporal-Python",),
    }
    base.update(overrides)
    return base


@pytest.mark.parametrize("model", [IssueWorkflowInput, SelectIssueResult, IssueWorkflowResult])
def test_boundary_contracts_are_frozen_dataclasses(model: type) -> None:
    assert dataclasses.is_dataclass(model)
    assert model.__dataclass_params__.frozen is True  # type: ignore[union-attr]


def test_input_constructs_and_carries_all_fields() -> None:
    data = IssueWorkflowInput(**_input())
    assert data.issue_id == "GEN-38"
    assert data.selectable_states == ("Todo", "In Progress")
    assert data.labels == ("Feature",)


def test_result_immutable() -> None:
    result = IssueWorkflowResult(
        workflow_state="READY",
        issue_id="GEN-38",
        repository="GenesisAI-team/SF-Temporal-Python",
        blocking_reasons=(),
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.workflow_state = "BLOCKED"  # type: ignore[misc]


def test_select_issue_result_immutable() -> None:
    result = SelectIssueResult(approved=False, reasons=("STATE_NOT_SELECTABLE: Done",))
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.approved = True  # type: ignore[misc]
