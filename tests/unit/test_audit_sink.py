"""Tests for the JSON-lines audit sink (GEN-38 H1)."""

import json
from pathlib import Path

import pytest

from super_factory.contracts.audit import WorkflowRunCorrelation
from super_factory.persistence.audit import JsonLinesAuditSink

BASE = "GenesisAI-team/SF-Temporal-Python"


def _entry(delivery_id: str, **overrides: object) -> WorkflowRunCorrelation:
    fields: dict[str, object] = {
        "recorded_at": "2026-11-09T12:00:00.000+00:00",
        "event_delivery_id": delivery_id,
        "event_action": "update",
        "event_type": "Issue",
        "issue_id": "GEN-38",
        "repository": BASE,
        "selection_outcome": "SELECTED",
        "workflow_state": "READY",
        "blocking_reasons": (),
        "workflow_id": "issue-GEN-38",
        "workflow_run_id": "0a8e4b4c-1111-2222-3333-444455556666",
    }
    fields.update(overrides)
    return WorkflowRunCorrelation(**fields)


async def test_record_appends_json_lines(tmp_path: Path) -> None:
    path = tmp_path / "audit" / "nested" / "events.jsonl"
    sink = JsonLinesAuditSink(path)
    await sink.record(_entry("d-1"))
    await sink.record(_entry("d-2"))
    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    first = json.loads(lines[0])
    assert first["event_delivery_id"] == "d-1"
    assert first["issue_id"] == "GEN-38"
    assert first["repository"] == BASE


async def test_record_is_idempotent_per_delivery(tmp_path: Path) -> None:
    path = tmp_path / "audit.jsonl"
    sink = JsonLinesAuditSink(path)
    await sink.record(_entry("d-1"))
    await sink.record(
        _entry("d-1", recorded_at="2026-11-09T12:05:00.000+00:00", workflow_id="other")
    )
    assert len(path.read_text(encoding="utf-8").splitlines()) == 1


async def test_record_allows_new_deliveries_after_deduped_one(tmp_path: Path) -> None:
    sink = JsonLinesAuditSink(tmp_path / "audit.jsonl")
    await sink.record(_entry("d-blocked", selection_outcome="BLOCKED", workflow_state="-"))
    await sink.record(_entry("d-2"))
    lines = (tmp_path / "audit.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["selection_outcome"] == "BLOCKED"


async def test_record_dedupes_against_restart(tmp_path: Path) -> None:
    path = tmp_path / "audit.jsonl"
    sink = JsonLinesAuditSink(path)
    await sink.record(_entry("d-1"))
    reopened = JsonLinesAuditSink(path)
    await reopened.record(_entry("d-1"))
    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1


def test_sink_rejects_blank_path() -> None:
    with pytest.raises(ValueError, match="path"):
        JsonLinesAuditSink("")
