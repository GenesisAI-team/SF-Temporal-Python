"""Append-only JSON-lines audit ledger (ADR-0006).

There is no database in H1: the correlation between event, issue, repository
and workflow run is persisted as one JSON object per line. ``record`` is
idempotent per delivery id, so retries of the same delivery never duplicate
audit lines. PostgreSQL/Alembic replaces this in a later milestone without
changing the ``AuditSink`` port shape.
"""

import json
from pathlib import Path
from typing import Protocol

from super_factory.contracts.audit import WorkflowRunCorrelation


class AuditSink(Protocol):
    """Port for durable audit persistence."""

    async def record(self, entry: WorkflowRunCorrelation) -> None:
        """Persist one correlation entry, never twice for the same delivery."""
        ...


class JsonLinesAuditSink:
    """Filesystem ``AuditSink``: one JSON object per line."""

    def __init__(self, path: str | Path) -> None:
        if not Path(path).name:
            msg = "path must point to a file"
            raise ValueError(msg)
        self._path = Path(path)
        self._seen_deliveries: set[str] | None = None

    @property
    def path(self) -> Path:
        """Target ledger file."""
        return self._path

    async def record(self, entry: WorkflowRunCorrelation) -> None:
        """Append the entry unless its delivery id was already recorded."""
        seen = self._load_seen_deliveries()
        if entry.event_delivery_id in seen:
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("a", encoding="utf-8") as handle:
            handle.write(entry.model_dump_json())
            handle.write("\n")
        seen.add(entry.event_delivery_id)

    def _load_seen_deliveries(self) -> set[str]:
        if self._seen_deliveries is None:
            seen: set[str] = set()
            if self._path.exists():
                for line in self._path.read_text(encoding="utf-8").splitlines():
                    if line.strip():
                        item = json.loads(line)
                        seen.add(str(item.get("event_delivery_id", "")))
            self._seen_deliveries = seen
        return self._seen_deliveries
