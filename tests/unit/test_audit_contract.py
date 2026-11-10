"""Tests for the audit correlation contract (GEN-38 H1)."""

import pytest
from pydantic import ValidationError

from super_factory.contracts.audit import WorkflowRunCorrelation


def _entry(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "recorded_at": "2026-11-09T12:00:00.000000+00:00",
        "event_delivery_id": "234d1a4e-b617-4388-90fe-adc3633d6b72",
        "event_action": "update",
        "event_type": "Issue",
        "issue_id": "GEN-38",
        "repository": "GenesisAI-team/SF-Temporal-Python",
        "selection_outcome": "SELECTED",
        "workflow_state": "READY",
        "blocking_reasons": (),
        "workflow_id": "issue-GEN-38",
        "workflow_run_id": "0a8e4b4c-1111-2222-3333-444455556666",
    }
    base.update(overrides)
    return base


def test_correlation_accepts_full_record() -> None:
    entry = WorkflowRunCorrelation(**_entry())
    assert entry.issue_id == "GEN-38"
    assert entry.workflow_run_id is not None


def test_correlation_is_frozen() -> None:
    entry = WorkflowRunCorrelation(**_entry())
    with pytest.raises(ValidationError, match="frozen"):
        entry.issue_id = "GEN-99"  # type: ignore[misc]


@pytest.mark.parametrize(
    "blanked_field",
    ["recorded_at", "event_delivery_id", "event_action", "event_type", "issue_id", "repository"],
)
def test_correlation_requires_core_identifiers(blanked_field: str) -> None:
    with pytest.raises(ValidationError, match=blanked_field):
        WorkflowRunCorrelation(**_entry(**{blanked_field: "  "}))


@pytest.mark.parametrize(
    "nullable_field",
    ["workflow_id", "workflow_run_id"],
)
def test_correlation_allows_missing_workflow_ids_for_blocked_gates(nullable_field: str) -> None:
    entry = WorkflowRunCorrelation(**_entry(**{nullable_field: None}))
    assert getattr(entry, nullable_field) is None


def test_correlation_blocked_record_without_run() -> None:
    entry = WorkflowRunCorrelation(
        **_entry(
            selection_outcome="BLOCKED",
            workflow_state="-",
            workflow_id=None,
            workflow_run_id=None,
            blocking_reasons=("STATE_NOT_SELECTABLE: Done",),
        )
    )
    assert entry.blocking_reasons == ("STATE_NOT_SELECTABLE: Done",)
    assert entry.workflow_state == "-"


def test_correlation_rejects_reason_with_blank_entry() -> None:
    with pytest.raises(ValidationError, match="blocking_reasons"):
        WorkflowRunCorrelation(**_entry(blocking_reasons=("X: ok", "  ")))
