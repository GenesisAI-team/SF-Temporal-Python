"""Tests for pure repository-validation rules (GEN-38 H1)."""

import pytest

from super_factory.domain.repository_spec import is_valid_repository


@pytest.mark.parametrize(
    "repository",
    [
        "GenesisAI-team/SF-Temporal-Python",
        "owner/repo",
        "owner/repo.name",
    ],
)
def test_valid_repositories_are_accepted(repository: str) -> None:
    assert is_valid_repository(repository) is True


@pytest.mark.parametrize(
    "repository",
    [
        "",
        "not-a-repo",
        "a/b/c",
        "/name",
        "owner/",
        "owner/na me",
        "ow ner/name",
        "owner /name",
        "owner/ name",
        "owner/na\tme",
    ],
)
def test_invalid_repositories_are_rejected(repository: str) -> None:
    assert is_valid_repository(repository) is False
