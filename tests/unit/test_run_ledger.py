"""Tests for the JSON-lines run ledger (GEN-47).

Acceptance: runs are recorded idempotently by run_key (retries never
duplicate), runs_for_issue filters per issue and survives process restarts,
and blank paths are rejected.
"""

from pathlib import Path

import pytest
from pydantic import ValidationError

from super_factory.contracts.run_ledger import PipelineRunRecord
from super_factory.persistence.run_ledger import JsonLinesRunLedger


def _record(
    run_key: str = "GEN-47-v1",
    issue_id: str = "GEN-47",
    **overrides: object,
) -> PipelineRunRecord:
    fields: dict[str, object] = {
        "run_key": run_key,
        "issue_id": issue_id,
        "spec_version": 1,
        "repository": "a/b",
        "branch_name": "feat/gen-47-task",
        "recorded_at": "2026-11-10T12:00:00+00:00",
        "outcome": "PREPARED",
        "pr_url": "",
    }
    fields.update(overrides)
    return PipelineRunRecord(**fields)


async def test_record_run_appends_and_is_idempotent(tmp_path: Path) -> None:
    ledger = JsonLinesRunLedger(tmp_path / "runs.jsonl")
    assert await ledger.record_run(_record()) is True
    assert await ledger.record_run(_record()) is False
    runs = await ledger.runs_for_issue("GEN-47")
    assert len(runs) == 1
    assert runs[0].run_key == "GEN-47-v1"
    assert runs[0].outcome == "PREPARED"
    lines = (tmp_path / "runs.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1


async def test_runs_for_issue_filters_other_issues(tmp_path: Path) -> None:
    ledger = JsonLinesRunLedger(tmp_path / "runs.jsonl")
    await ledger.record_run(_record())
    await ledger.record_run(_record(run_key="GEN-48-v1", issue_id="GEN-48"))
    assert [record.run_key for record in await ledger.runs_for_issue("GEN-47")] == ["GEN-47-v1"]
    assert [record.run_key for record in await ledger.runs_for_issue("GEN-48")] == ["GEN-48-v1"]
    assert await ledger.runs_for_issue("GEN-99") == ()


async def test_ledger_survives_restarts(tmp_path: Path) -> None:
    first = JsonLinesRunLedger(tmp_path / "runs.jsonl")
    await first.record_run(_record())
    second = JsonLinesRunLedger(tmp_path / "runs.jsonl")
    runs = await second.runs_for_issue("GEN-47")
    assert len(runs) == 1


async def test_ledger_fresh_file_has_no_runs(tmp_path: Path) -> None:
    ledger = JsonLinesRunLedger(tmp_path / "runs.jsonl")
    assert await ledger.runs_for_issue("GEN-47") == ()


def test_ledger_rejects_blank_paths(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="path must point to a file"):
        JsonLinesRunLedger("")


def test_ledger_record_validates_contract() -> None:
    valid: dict[str, object] = {
        "run_key": "GEN-47-v1",
        "issue_id": "GEN-47",
        "spec_version": 1,
        "repository": "a/b",
        "branch_name": "b",
        "recorded_at": "2026-11-10T12:00:00+00:00",
        "outcome": "PREPARED",
    }
    assert PipelineRunRecord(**valid).outcome == "PREPARED"
    for bad_fields in (
        {"run_key": "not-a-run-key"},
        {"issue_id": "ISS-7"},
        {"spec_version": 0},
        {"repository": "a b/c"},
        {"branch_name": " "},
        {"recorded_at": ""},
        {"outcome": " "},
    ):
        fields = dict(valid)
        fields.update(bad_fields)
        with pytest.raises(ValidationError):
            PipelineRunRecord(**fields)
