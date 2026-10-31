"""Pure domain rules for task specifications (TDD cycles C2-C3)."""

import re

_ISSUE_ID_PATTERN = re.compile(r"^GEN-\d+$")


def is_valid_issue_id(issue_id: str) -> bool:
    """Return True when the identifier matches the GEN-N format."""
    return bool(_ISSUE_ID_PATTERN.match(issue_id))


def is_non_empty(value: str) -> bool:
    """Return True when value contains non-whitespace characters."""
    return bool(value.strip())


def all_non_empty(values: list[str]) -> bool:
    """Return True when every item in values is non-empty."""
    return all(is_non_empty(v) for v in values)
