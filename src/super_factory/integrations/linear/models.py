"""Linear webhook payload adapter: envelope parsing and issue snapshots.

Envelope shape follows the documented Linear webhook contract
(``type``/``action``/``webhookTimestamp`` plus a serialized entity in
``data``); unknown vendor fields are ignored. The Issue snapshot mapping is
deliberately tolerant: missing state objects or identifiers surface as blank
values that the pure selector blocks with auditable reasons.
"""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from super_factory.contracts.selection import IssueSnapshot


def _blankable(value: str) -> str:
    return value.strip()


class LinearWebhookEnvelope(BaseModel):
    """Validated webhook envelope common to all Linear event streams."""

    model_config = ConfigDict(extra="allow", str_strip_whitespace=True)

    type: str
    action: str
    webhook_timestamp: int = Field(alias="webhookTimestamp")
    data: dict[str, Any] = {}

    @field_validator("type", "action")
    @classmethod
    def _check_non_blank(cls, value: str) -> str:
        return _blankable(value)


def parse_linear_webhook(raw: bytes) -> LinearWebhookEnvelope:
    """Parse the raw body into the webhook envelope, rejecting invalid input."""
    return LinearWebhookEnvelope.model_validate_json(raw)


class _StateRef(BaseModel):
    model_config = ConfigDict(extra="allow", str_strip_whitespace=True)

    name: str = ""


class _LabelRef(BaseModel):
    model_config = ConfigDict(extra="allow", str_strip_whitespace=True)

    name: str = ""


class _IssueData(BaseModel):
    model_config = ConfigDict(extra="allow", str_strip_whitespace=True)

    identifier: str = ""
    title: str = ""
    state: _StateRef | None = None
    labels: tuple[_LabelRef, ...] = ()


def to_issue_snapshot(payload: LinearWebhookEnvelope) -> IssueSnapshot:
    """Extract the single-issue snapshot used for selection decisions."""
    issue_data = _IssueData.model_validate(payload.data)
    state_name = issue_data.state.name if issue_data.state is not None else ""
    labels = tuple(_blankable(label.name) for label in issue_data.labels if _blankable(label.name))
    return IssueSnapshot(
        issue_id=issue_data.identifier,
        title=issue_data.title,
        state=state_name,
        labels=labels,
    )
