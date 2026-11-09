"""Audit-recording activity: persist issue/repository/run correlation (H1).

Effect-free on the workflow plane: the only I/O is the audit sink call. The
sink port is resolved through ``get_audit_sink`` so tests and deployments can
substitute implementations without touching the workflow.
"""

from dataclasses import dataclass
from datetime import UTC, datetime

from temporalio import activity

from super_factory.config.settings import Settings, get_settings
from super_factory.contracts.audit import WorkflowRunCorrelation
from super_factory.persistence.audit import AuditSink, JsonLinesAuditSink

_sink: AuditSink | None = None


@dataclass(frozen=True)
class RecordAuditInput:
    """Audit command built deterministically by ``IssueWorkflow``."""

    delivery_id: str
    event_action: str
    event_type: str
    issue_id: str
    repository: str
    workflow_id: str
    workflow_run_id: str
    selection_outcome: str
    workflow_state: str
    blocking_reasons: tuple[str, ...]


def get_audit_sink() -> AuditSink:
    """Return the process-wide audit sink (built once from settings)."""
    global _sink
    if _sink is None:
        settings: Settings = get_settings()
        _sink = JsonLinesAuditSink(settings.audit_log_path)
    return _sink


def set_audit_sink(sink: AuditSink | None) -> None:
    """Replace the process-wide sink (wiring/testing seam)."""
    global _sink
    _sink = sink


@activity.defn(name="record_audit_activity")
async def record_audit_activity(record: RecordAuditInput) -> None:
    """Write one correlation line; idempotent per delivery via the sink."""
    entry = WorkflowRunCorrelation(
        recorded_at=datetime.now(tz=UTC).isoformat(),
        event_delivery_id=record.delivery_id,
        event_action=record.event_action,
        event_type=record.event_type,
        issue_id=record.issue_id,
        repository=record.repository,
        selection_outcome=record.selection_outcome,
        workflow_state=record.workflow_state,
        blocking_reasons=record.blocking_reasons,
        workflow_id=record.workflow_id,
        workflow_run_id=record.workflow_run_id,
    )
    await get_audit_sink().record(entry)
