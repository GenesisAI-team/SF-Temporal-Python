"""Signed Linear webhook endpoint (GEN-38 H1, see ADR-0007).

Pipeline per request: verify HMAC signature -> validate envelope -> reject
stale events (replay) -> claim the delivery id (idempotency) -> ignore
non-Issue events -> apply selection criteria (blocked candidates are audited
without a run) -> create/recover the unique IssueWorkflow run -> audit the
correlation. Secrets come only from settings and are never logged.
"""

import asyncio
import hashlib
import logging
import time
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from super_factory.config.settings import get_settings, parse_selectable_states
from super_factory.contracts.audit import WorkflowRunCorrelation
from super_factory.contracts.selection import IssueSelectionCriteria
from super_factory.contracts.workflow_io import IssueWorkflowInput
from super_factory.domain.issue_selection import (
    evaluate_issue_selection,
    format_blocking_reason,
)
from super_factory.integrations.linear.models import (
    parse_linear_webhook,
    to_issue_snapshot,
)
from super_factory.integrations.linear.replay import is_stale_event
from super_factory.integrations.linear.signature import (
    LINEAR_SIGNATURE_HEADER,
    verify_linear_signature,
)
from super_factory.integrations.temporal_sdk.starter import IssueWorkflowStarter
from super_factory.persistence.audit import AuditSink, JsonLinesAuditSink
from super_factory.persistence.idempotency import InMemoryDeliveryDeduper

router = APIRouter(tags=["webhooks"])

logger = logging.getLogger(__name__)

_starter: IssueWorkflowStarter | None = None
_starter_lock = asyncio.Lock()
_deduper: InMemoryDeliveryDeduper | None = None
_audit: AuditSink | None = None


def get_webhook_secret() -> str:
    """Signature secret, only provided through settings (SF_* env)."""
    return get_settings().linear_webhook_secret


def get_deduper() -> InMemoryDeliveryDeduper:
    """Process-wide delivery dedupe store (lazy singleton)."""
    global _deduper
    if _deduper is None:
        _deduper = InMemoryDeliveryDeduper(
            ttl_seconds=get_settings().linear_dedupe_ttl_seconds
        )
    return _deduper


def get_audit_sink() -> AuditSink:
    """Process-wide audit sink (lazy singleton)."""
    global _audit
    if _audit is None:
        _audit = JsonLinesAuditSink(get_settings().audit_log_path)
    return _audit


async def get_starter() -> IssueWorkflowStarter:
    """Lazy singleton starter connected to the configured Temporal server.

    Transport failures map to HTTP 503 so Linear retries later; the singleton
    stays unbound and the next request re-attempts the connection.
    """
    global _starter
    if _starter is None:
        async with _starter_lock:
            if _starter is None:
                settings = get_settings()
                try:
                    _starter = await IssueWorkflowStarter.connect(
                        address=settings.temporal_address,
                        namespace=settings.temporal_namespace,
                        task_queue=settings.temporal_task_queue,
                    )
                except (RuntimeError, OSError) as exc:
                    logger.warning("temporal server unavailable: %s", type(exc).__name__)
                    msg = "temporal server unavailable"
                    raise HTTPException(status_code=503, detail=msg) from exc
    return _starter


async def get_starter_resolver() -> Callable[[], Awaitable[IssueWorkflowStarter]]:
    """Returns the lazy starter factory; resolved only when a run is needed.

    Keeping the Temporal connection out of the per-request dependency graph
    means rejected/blocked/duplicate events are processed even during a
    Temporal outage (they are audited, then answered with 200).
    """
    return get_starter


def _identifier_or_dash(value: str) -> str:
    return value.strip() or "-"


@router.post("/webhooks/linear")
async def linear_webhook(
    request: Request,
    starter_factory: Callable[[], Awaitable[IssueWorkflowStarter]] = Depends(get_starter_resolver),
    deduper: InMemoryDeliveryDeduper = Depends(get_deduper),
    audit: AuditSink = Depends(get_audit_sink),
    secret: str = Depends(get_webhook_secret),
) -> JSONResponse:
    """Accept signed Linear events; ack quickly, never duplicate work."""
    body = await request.body()
    if not secret:
        return JSONResponse(
            status_code=503, content={"detail": "webhook secret not configured"}
        )
    if not verify_linear_signature(
        secret=secret,
        body=body,
        signature=request.headers.get(LINEAR_SIGNATURE_HEADER),
    ):
        logger.warning("linear webhook rejected: invalid signature")
        return JSONResponse(status_code=401, content={"detail": "invalid signature"})

    try:
        payload = parse_linear_webhook(body)
    except ValidationError:
        logger.warning("linear webhook rejected: invalid payload")
        return JSONResponse(status_code=400, content={"detail": "invalid payload"})

    settings = get_settings()
    if is_stale_event(
        webhook_timestamp_ms=payload.webhook_timestamp,
        now_ms=int(time.time() * 1000),
        tolerance_seconds=settings.linear_timestamp_tolerance_seconds,
    ):
        logger.warning("linear webhook rejected: stale event replayed")
        return JSONResponse(status_code=400, content={"detail": "stale event rejected"})

    delivery_id = _delivery_id(request, body)
    if not deduper.claim(delivery_id):
        logger.info("linear webhook duplicate delivery ignored")
        return JSONResponse(status_code=200, content={"status": "duplicate"})

    if payload.type != "Issue":
        logger.info("linear webhook ignored non-issue event type=%s", payload.type)
        return JSONResponse(status_code=200, content={"status": "ignored"})

    snapshot = to_issue_snapshot(payload)
    recorded_at = datetime.now(tz=UTC).isoformat()
    try:
        criteria = IssueSelectionCriteria(
            selectable_states=parse_selectable_states(settings.linear_selectable_states),
            allowed_repositories=(
                (settings.linear_target_repository.strip(),)
                if settings.linear_target_repository.strip()
                else ()
            ),
        )
    except (ValidationError, ValueError):
        deduper.release(delivery_id)
        logger.error("linear webhook rejected: invalid configuration")
        return JSONResponse(
            status_code=500, content={"detail": "invalid configuration"}
        )

    decision = evaluate_issue_selection(
        issue_id=snapshot.issue_id,
        issue_state=snapshot.state,
        repository=settings.linear_target_repository,
        selectable_states=criteria.selectable_states,
        allowed_repositories=criteria.allowed_repositories,
    )
    reasons = tuple(format_blocking_reason(reason) for reason in decision.reasons)
    if not decision.approved:
        await audit.record(
            WorkflowRunCorrelation(
                recorded_at=recorded_at,
                event_delivery_id=delivery_id,
                event_action=payload.action,
                event_type=payload.type,
                issue_id=_identifier_or_dash(snapshot.issue_id),
                repository=_identifier_or_dash(settings.linear_target_repository),
                selection_outcome="BLOCKED",
                workflow_state="-",
                blocking_reasons=reasons,
            )
        )
        logger.info("linear webhook blocked issue=%s", snapshot.issue_id)
        return JSONResponse(
            status_code=200, content={"status": "blocked", "reasons": list(reasons)}
        )

    try:
        starter = await starter_factory()
        run = await starter.start_or_recover(
            IssueWorkflowInput(
                issue_id=snapshot.issue_id,
                repository=settings.linear_target_repository,
                issue_state=snapshot.state,
                labels=snapshot.labels,
                title=snapshot.title,
                delivery_id=delivery_id,
                event_action=payload.action,
                event_type=payload.type,
                selectable_states=criteria.selectable_states,
                allowed_repositories=criteria.allowed_repositories,
            )
        )
    except HTTPException:
        deduper.release(delivery_id)
        logger.warning("linear webhook: temporal server unavailable")
        raise
    except Exception:
        deduper.release(delivery_id)
        logger.exception("linear webhook: issue workflow dispatch failed")
        return JSONResponse(
            status_code=500, content={"detail": "workflow dispatch failed"}
        )

    await audit.record(
        WorkflowRunCorrelation(
            recorded_at=recorded_at,
            event_delivery_id=delivery_id,
            event_action=payload.action,
            event_type=payload.type,
            issue_id=snapshot.issue_id,
            repository=settings.linear_target_repository,
            selection_outcome="SELECTED",
            workflow_state="READY",
            blocking_reasons=(),
            workflow_id=run.workflow_id,
            workflow_run_id=run.run_id,
        )
    )
    logger.info(
        "linear webhook started run=%s issue=%s recovered=%s",
        run.workflow_id,
        snapshot.issue_id,
        not run.started,
    )
    return JSONResponse(
        status_code=200,
        content={
            "status": "accepted" if run.started else "recovered",
            "workflow_id": run.workflow_id,
            "run_id": run.run_id,
        },
    )


def _delivery_id(request: Request, body: bytes) -> str:
    """Linear-Delivery header when present; content hash as stable fallback."""
    header_delivery = request.headers.get("Linear-Delivery")
    if header_delivery and header_delivery.strip():
        return header_delivery.strip()
    return hashlib.sha256(body).hexdigest()
