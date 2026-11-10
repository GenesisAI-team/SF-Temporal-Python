"""Planning ports (GEN-47): resolve the human-approved task specification.

The default H2 state is an explicit failure (``UnavailableSpecSource``): the
pipeline never invents approval criteria. Operators configure
``SF_TASK_SPEC_PATH`` (an approved ``ApprovedTaskSpec`` JSON payload,
e.g. produced by the planning step that consumes the approved Linear issue)
to enable real PR production locally.
"""

import json
from pathlib import Path
from typing import Protocol

from pydantic import ValidationError

from super_factory.contracts.approved_task import ApprovedTaskSpec
from super_factory.contracts.pipeline import TaskSpecQuery


class SpecSourceUnavailable(RuntimeError):
    """The approved specification could not be resolved (configuration)."""


class TaskSpecSource(Protocol):
    """Port that maps an approved issue into its ``ApprovedTaskSpec``."""

    async def resolve(self, query: TaskSpecQuery) -> ApprovedTaskSpec:
        """Return the human-approved spec or raise ``SpecSourceUnavailable``."""
        ...


class UnavailableSpecSource:
    """Shipped default: fail loudly, never simulate approval."""

    async def resolve(self, query: TaskSpecQuery) -> ApprovedTaskSpec:
        msg = "no task spec source is configured (set SF_TASK_SPEC_PATH)"
        raise SpecSourceUnavailable(msg)


class StaticFileSpecSource:
    """Reads one approved spec from a JSON file (operator-managed input)."""

    def __init__(self, path: str | Path) -> None:
        candidate = Path(path)
        if not candidate.name:
            msg = "path must point to a file"
            raise ValueError(msg)
        if not candidate.name.strip():
            msg = "path must be non-blank"
            raise ValueError(msg)
        self._path = candidate

    @property
    def path(self) -> Path:
        """Approved-spec file path."""
        return self._path

    async def resolve(self, query: TaskSpecQuery) -> ApprovedTaskSpec:
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise SpecSourceUnavailable(f"task spec file unreadable: {exc}") from exc
        try:
            spec = ApprovedTaskSpec.model_validate(raw)
        except ValidationError as exc:
            raise SpecSourceUnavailable(
                "task spec file is not a valid ApprovedTaskSpec"
            ) from exc
        if spec.issue_id != query.issue_id:
            raise SpecSourceUnavailable(
                f"task spec file targets {spec.issue_id}, expected {query.issue_id}"
            )
        if spec.repository != query.repository:
            raise SpecSourceUnavailable(
                f"task spec file targets repository {spec.repository}, "
                f"expected {query.repository}"
            )
        return spec
