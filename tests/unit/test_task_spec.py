"""Tests for pure domain rules (TDD cycles C2-C3)."""

import pytest

from super_factory.domain.task_spec import all_non_empty, is_non_empty, is_valid_issue_id


@pytest.mark.parametrize(("value", "expected"), [
    ("GEN-17", True),
    ("GEN-1", True),
    ("GEN-123", True),
    ("gen-17", False),
    ("GEN-1x", False),
    ("17", False),
    ("", False),
    ("GEN-", False),
    (" GEN-17 ", False),
])
def test_is_valid_issue_id(value: str, expected: bool) -> None:
    assert is_valid_issue_id(value) is expected


@pytest.mark.parametrize(("value", "expected"), [
    ("objective", True),
    ("  spaced  ", True),
    ("", False),
    ("   ", False),
])
def test_is_non_empty(value: str, expected: bool) -> None:
    assert is_non_empty(value) is expected


def test_all_non_empty_rejects_blank_members() -> None:
    assert all_non_empty(["a", " b "]) is True
    assert all_non_empty(["a", "  "]) is False
    assert all_non_empty([]) is True
