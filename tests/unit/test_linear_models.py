"""Tests for the Linear webhook payload adapter (parse + issue snapshot)."""

import json

import pytest
from pydantic import ValidationError

from super_factory.contracts.selection import IssueSnapshot
from super_factory.integrations.linear.models import (
    parse_linear_webhook,
    to_issue_snapshot,
)

DELIVERY_TIMESTAMP_MS = 1767225600000


def _payload_dict(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "type": "Issue",
        "action": "update",
        "createdAt": "2026-01-01T12:00:00.000Z",
        "url": "https://linear.app/genesisnavarra/issue/GEN-38/sf",
        "organizationId": "dc844923-f9a4-40a3-825c-dea7747e57d6",
        "webhookId": "000042e3-d123-4980-b49f-8e140eef9329",
        "webhookTimestamp": DELIVERY_TIMESTAMP_MS,
        "actor": {"id": "b5ea5f1f", "type": "user", "name": "Orbit"},
        "updatedFrom": {"stateId": "a9b8c7d6"},
        "data": {
            "id": "539068e2-ae88-4d09-bd75-22eb4a59612f",
            "identifier": "GEN-38",
            "title": "H1 - webhook Linear y seleccion durable",
            "state": {"id": "f62890cb", "name": "In Progress", "type": "started"},
            "labels": [{"id": "c7e6a373", "name": "Feature"}],
            "priority": 3,
            "teamId": "d432eff4",
        },
    }
    base.update(overrides)
    return base


def _encode(data: dict[str, object]) -> bytes:
    return json.dumps(data).encode("utf-8")


def test_parse_accepts_documented_envelope() -> None:
    payload = parse_linear_webhook(_encode(_payload_dict()))
    assert payload.type == "Issue"
    assert payload.action == "update"
    assert payload.webhook_timestamp == DELIVERY_TIMESTAMP_MS


def test_parse_requires_type_action_and_timestamp() -> None:
    for removed in ("type", "action", "webhookTimestamp"):
        minimal = _payload_dict()
        minimal.pop(removed)
        with pytest.raises(ValidationError, match=removed):
            parse_linear_webhook(_encode(minimal))


def test_parse_rejects_invalid_json() -> None:
    with pytest.raises(ValidationError, match="json"):
        parse_linear_webhook(b"{not json")


def test_parse_rejects_non_object_root() -> None:
    with pytest.raises(ValidationError):
        parse_linear_webhook(_encode(["array"]))


def test_snapshot_maps_identifier_title_state_labels() -> None:
    payload = parse_linear_webhook(_encode(_payload_dict()))
    snapshot = to_issue_snapshot(payload)
    assert snapshot == IssueSnapshot(
        issue_id="GEN-38",
        title="H1 - webhook Linear y seleccion durable",
        state="In Progress",
        labels=("Feature",),
    )


def test_snapshot_defaults_to_blank_state_when_state_object_absent() -> None:
    data = _payload_dict()
    data["data"] = {k: v for k, v in data["data"].items() if k != "state"}  # type: ignore[union-attr]
    snapshot = to_issue_snapshot(parse_linear_webhook(_encode(data)))
    assert snapshot.state == ""
    assert snapshot.issue_id == "GEN-38"


def test_snapshot_ignores_unnamed_labels() -> None:
    data = _payload_dict()
    data["data"] = {  # type: ignore[assignment]
        **data["data"],  # type: ignore[arg-type]
        "labels": [
            {"id": "x1"},
            {"name": "Bug"},
            {"name": "  "},
        ],
    }
    assert to_issue_snapshot(parse_linear_webhook(_encode(data))).labels == ("Bug",)


def test_snapshot_handles_missing_data_object() -> None:
    minimal = _payload_dict()
    minimal["data"] = {}
    snapshot = to_issue_snapshot(parse_linear_webhook(_encode(minimal)))
    assert snapshot.issue_id == ""
    assert snapshot.state == ""
    assert snapshot.labels == ()
