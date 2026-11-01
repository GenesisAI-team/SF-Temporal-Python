"""Tests for the approved task contract (TDD cycles C2-C3)."""

from typing import Any

import pytest
from pydantic import ValidationError

from super_factory.contracts.approved_task import ApprovedTaskSpec

VALID: dict[str, Any] = {
    "issue_id": "GEN-17",
    "spec_version": 1,
    "repository": "GenesisAI-team/SF-Temporal-Python",
    "base_branch": "main",
    "objective": "Bootstrap the software factory infrastructure.",
    "acceptance_criteria": ["Repo private", "uv sync --frozen passes"],
    "dependencies": [],
    "exclusions": ["No full factory"],
    "constraints": ["Temporal is the only orchestrator"],
}


def test_valid_spec_is_accepted() -> None:
    spec = ApprovedTaskSpec(**VALID)
    assert spec.issue_id == "GEN-17"
    assert spec.base_branch == "main"
    assert spec.acceptance_criteria == ["Repo private", "uv sync --frozen passes"]


@pytest.mark.parametrize("bad_id", ["gen-17", "GEN-1x", "17", "", "TICKET-1"])
def test_malformed_issue_id_is_rejected(bad_id: str) -> None:
    with pytest.raises(ValidationError, match="issue_id"):
        ApprovedTaskSpec(**{**VALID, "issue_id": bad_id})


def test_empty_acceptance_criteria_is_rejected() -> None:
    with pytest.raises(ValidationError, match="acceptance_criteria"):
        ApprovedTaskSpec(**{**VALID, "acceptance_criteria": []})


def test_blank_acceptance_criterion_is_rejected() -> None:
    with pytest.raises(ValidationError, match="acceptance_criteria"):
        ApprovedTaskSpec(**{**VALID, "acceptance_criteria": ["ok", "   "]})


def test_blank_exclusion_is_rejected() -> None:
    with pytest.raises(ValidationError, match="exclusions"):
        ApprovedTaskSpec(**{**VALID, "exclusions": ["  "]})


def test_repository_must_be_owner_slash_name() -> None:
    with pytest.raises(ValidationError, match="repository"):
        ApprovedTaskSpec(**{**VALID, "repository": "not-a-repo"})


def test_spec_version_must_be_positive() -> None:
    with pytest.raises(ValidationError, match="spec_version"):
        ApprovedTaskSpec(**{**VALID, "spec_version": 0})


def test_blank_objective_is_rejected() -> None:
    with pytest.raises(ValidationError, match="objective"):
        ApprovedTaskSpec(**{**VALID, "objective": "  "})


def test_dependency_ids_must_match_gen_format() -> None:
    with pytest.raises(ValidationError, match="dependencies"):
        ApprovedTaskSpec(**{**VALID, "dependencies": ["GEN-16", "bad-id"]})
