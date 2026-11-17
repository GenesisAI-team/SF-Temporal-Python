"""Tests for the planning port + shipped task-spec sources (GEN-47).

Acceptance: the default state of H2 is an explicit unavailability (no
simulation, ADR overview rule); a static approved-spec file resolves into a
validated ApprovedTaskSpec when it matches the query and fails closed with
``SpecSourceUnavailable`` otherwise.
"""

import json
from pathlib import Path

import pytest

from super_factory.contracts.approved_task import ApprovedTaskSpec
from super_factory.contracts.pipeline import TaskSpecQuery
from super_factory.planning.ports import (
    SpecSourceUnavailable,
    StaticFileSpecSource,
    UnavailableSpecSource,
)


def _query(issue_id: str = "GEN-47", repository: str = "a/b") -> TaskSpecQuery:
    return TaskSpecQuery(
        issue_id=issue_id, repository=repository, base_branch="main", title="title"
    )


def _spec_payload(**overrides: object) -> dict[str, object]:
    data: dict[str, object] = {
        "issue_id": "GEN-47",
        "spec_version": 1,
        "repository": "a/b",
        "base_branch": "main",
        "objective": "H2 pipeline",
        "acceptance_criteria": ["criterion one", "criterion two"],
    }
    data.update(overrides)
    return data


async def test_unavailable_spec_source_fails_explicitly() -> None:
    source = UnavailableSpecSource()
    with pytest.raises(SpecSourceUnavailable, match="no task spec source"):
        await source.resolve(_query())


async def test_static_file_source_resolves_approved_spec(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "spec.json"
    path.write_text(json.dumps(_spec_payload()), encoding="utf-8")
    monkeypatch.setattr(StaticFileSpecSource, "READ_CHUNK", 4096, raising=False)
    source = StaticFileSpecSource(path)
    spec = await source.resolve(_query())
    assert isinstance(spec, ApprovedTaskSpec)
    assert spec.issue_id == "GEN-47"
    assert spec.objective == "H2 pipeline"
    assert spec.acceptance_criteria == ["criterion one", "criterion two"]


async def test_static_file_source_fails_when_file_missing(tmp_path: Path) -> None:
    source = StaticFileSpecSource(tmp_path / "missing.json")
    with pytest.raises(SpecSourceUnavailable, match="unreadable"):
        await source.resolve(_query())


async def test_static_file_source_fails_on_invalid_payload(tmp_path: Path) -> None:
    path = tmp_path / "spec.json"
    path.write_text(json.dumps({"issue_id": "GEN-47"}), encoding="utf-8")
    source = StaticFileSpecSource(path)
    with pytest.raises(SpecSourceUnavailable, match="valid ApprovedTaskSpec"):
        await source.resolve(_query())


async def test_static_file_source_fails_on_issue_mismatch(tmp_path: Path) -> None:
    path = tmp_path / "spec.json"
    path.write_text(
        json.dumps(_spec_payload(issue_id="GEN-48")), encoding="utf-8"
    )
    source = StaticFileSpecSource(path)
    with pytest.raises(SpecSourceUnavailable, match="targets GEN-48"):
        await source.resolve(_query())


async def test_static_file_source_fails_on_repository_mismatch(tmp_path: Path) -> None:
    path = tmp_path / "spec.json"
    path.write_text(
        json.dumps(_spec_payload(repository="other/repo")), encoding="utf-8"
    )
    source = StaticFileSpecSource(path)
    with pytest.raises(SpecSourceUnavailable, match="repository"):
        await source.resolve(_query())


def test_static_file_source_requires_blank_free_path(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="non-blank"):
        StaticFileSpecSource("   ")
    assert StaticFileSpecSource(tmp_path / "spec.json").path == tmp_path / "spec.json"
