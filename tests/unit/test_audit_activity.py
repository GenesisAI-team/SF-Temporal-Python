"""Tests for the audit-recording activity (GEN-38 H1).

The activity translates the workflow context into a ``WorkflowRunCorrelation``
and delegates persistence to the ``AuditSink`` port (injected by
``get_audit_sink``, overridable in tests and wiring).
"""

import json
from pathlib import Path
from typing import Any

from super_factory.persistence.audit import JsonLinesAuditSink
from super_factory.temporal.activities.audit import (
    RecordAuditInput,
    get_audit_sink,
    record_audit_activity,
    set_audit_sink,
)

REPO = "GenesisAI-team/SF-Temporal-Python"


def _record(**overrides: object) -> RecordAuditInput:
    fields: dict[str, object] = {
        "delivery_id": "234d1a4e-b617-4388-90fe-adc3633d6b72",
        "event_action": "update",
        "event_type": "Issue",
        "issue_id": "GEN-38",
        "repository": REPO,
        "workflow_id": "issue-GEN-38",
        "workflow_run_id": "0a8e4b4c-1111-2222-3333-444455556666",
        "selection_outcome": "SELECTED",
        "workflow_state": "READY",
        "blocking_reasons": (),
    }
    fields.update(overrides)
    return RecordAuditInput(**fields)


def _patch_sink(monkeypatch: Any, tmp_path: Path) -> Path:
    ledger = tmp_path / "audit.jsonl"
    sink = JsonLinesAuditSink(ledger)
    monkeypatch.setattr(
        "super_factory.temporal.activities.audit.get_audit_sink", lambda: sink
    )
    return ledger


async def test_record_audit_appends_correlation(
    tmp_path: Path, monkeypatch: Any
) -> None:
    ledger = _patch_sink(monkeypatch, tmp_path)
    await record_audit_activity(_record())
    lines = ledger.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    entry = json.loads(lines[0])
    assert entry["issue_id"] == "GEN-38"
    assert entry["repository"] == REPO
    assert entry["workflow_id"] == "issue-GEN-38"
    assert entry["workflow_run_id"].startswith("0a8e4b4c")
    assert entry["workflow_state"] == "READY"
    assert entry["recorded_at"], "recorded_at must be stamped by the activity"
    assert entry["blocking_reasons"] == []


async def test_record_audit_blocked_state(
    tmp_path: Path, monkeypatch: Any
) -> None:
    ledger = _patch_sink(monkeypatch, tmp_path)
    await record_audit_activity(
        _record(
            selection_outcome="BLOCKED",
            workflow_state="BLOCKED",
            blocking_reasons=("STATE_NOT_SELECTABLE: Done",),
        )
    )
    entry = json.loads(ledger.read_text(encoding="utf-8").splitlines()[0])
    assert entry["workflow_state"] == "BLOCKED"
    assert entry["blocking_reasons"] == ["STATE_NOT_SELECTABLE: Done"]


async def test_record_audit_is_idempotent_per_delivery(
    tmp_path: Path, monkeypatch: Any
) -> None:
    ledger = _patch_sink(monkeypatch, tmp_path)
    await record_audit_activity(_record())
    await record_audit_activity(_record())
    assert len(ledger.read_text(encoding="utf-8").splitlines()) == 1


def test_get_audit_sink_builds_singleton_from_settings(
    tmp_path: Path, monkeypatch: Any
) -> None:
    set_audit_sink(None)
    try:
        monkeypatch.setenv("SF_AUDIT_LOG_PATH", str(tmp_path / "audit.jsonl"))
        first = get_audit_sink()
        second = get_audit_sink()
        assert first is second
        assert isinstance(first, JsonLinesAuditSink)
        assert first.path == Path(tmp_path / "audit.jsonl")
    finally:
        set_audit_sink(None)


def test_set_audit_sink_seam_replaces_the_sink() -> None:
    class _StubSink:
        pass

    stub = _StubSink()
    set_audit_sink(stub)
    try:
        assert get_audit_sink() is stub
    finally:
        set_audit_sink(None)
