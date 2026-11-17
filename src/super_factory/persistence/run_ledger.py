"""Run-ledger port + JSON-lines adapter (GEN-47).

The ledger is the durable budget guard for issue runs: one record per
``run_key`` (``GEN-N-vM``), idempotent by key, readable across worker
restarts. PostgreSQL replaces the JSON lines later without changing the
port shape.
"""

from pathlib import Path
from typing import Protocol

from super_factory.contracts.run_ledger import PipelineRunRecord


class PipelineRunLedger(Protocol):
    """Port for durable per-issue run bookkeeping."""

    async def runs_for_issue(self, issue_id: str) -> tuple[PipelineRunRecord, ...]:
        """All recorded runs of an issue (append order)."""
        ...

    async def record_run(self, record: PipelineRunRecord) -> bool:
        """Record one run; False when the run_key already exists."""
        ...


class JsonLinesRunLedger:
    """Filesystem ``PipelineRunLedger``: one JSON object per line."""

    def __init__(self, path: str | Path) -> None:
        if not Path(path).name:
            msg = "path must point to a file"
            raise ValueError(msg)
        self._path = Path(path)

    @property
    def path(self) -> Path:
        """Target ledger file."""
        return self._path

    async def runs_for_issue(self, issue_id: str) -> tuple[PipelineRunRecord, ...]:
        records = self._load()
        return tuple(record for record in records if record.issue_id == issue_id)

    async def record_run(self, record: PipelineRunRecord) -> bool:
        records = self._load()
        if any(existing.run_key == record.run_key for existing in records):
            return False
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("a", encoding="utf-8") as handle:
            handle.write(record.model_dump_json())
            handle.write("\n")
        return True

    def _load(self) -> list[PipelineRunRecord]:
        if not self._path.exists():
            return []
        records: list[PipelineRunRecord] = []
        for line in self._path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                records.append(PipelineRunRecord.model_validate_json(line))
        return records
