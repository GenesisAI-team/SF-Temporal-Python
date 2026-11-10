"""Direct tests for the webhook provider singletons (GEN-38 H1).

The endpoint tests override these deps with fakes; here we prove the lazy
production wiring itself: single construction, env-driven configuration and
no repeat connects.
"""

import asyncio

import pytest

import super_factory.api.webhooks.linear as webhook_module
from super_factory.integrations.temporal_sdk.starter import IssueWorkflowStarter
from super_factory.persistence.audit import JsonLinesAuditSink


@pytest.fixture
def _reset_providers():
    webhook_module._deduper = None
    webhook_module._audit = None
    webhook_module._starter = None
    try:
        yield
    finally:
        webhook_module._deduper = None
        webhook_module._audit = None
        webhook_module._starter = None


def test_deduper_and_audit_singletons_build_once_from_settings(
    tmp_path, monkeypatch: pytest.MonkeyPatch, _reset_providers
) -> None:
    monkeypatch.setenv("SF_LINEAR_DEDUPE_TTL_SECONDS", "777")
    monkeypatch.setenv("SF_AUDIT_LOG_PATH", str(tmp_path / "audit.jsonl"))

    dedup_a = webhook_module.get_deduper()
    dedup_b = webhook_module.get_deduper()
    audit_a = webhook_module.get_audit_sink()
    audit_b = webhook_module.get_audit_sink()

    assert dedup_a is dedup_b
    assert dedup_a._ttl == 777
    assert audit_a is audit_b
    assert isinstance(audit_a, JsonLinesAuditSink)
    assert audit_a.path == tmp_path / "audit.jsonl"


async def test_starter_singleton_connects_exactly_once(
    monkeypatch: pytest.MonkeyPatch, _reset_providers
) -> None:
    connects: list[tuple[str, str, str]] = []

    async def fake_connect(**kwargs: str) -> IssueWorkflowStarter:
        connects.append((kwargs["address"], kwargs["namespace"], kwargs["task_queue"]))
        return IssueWorkflowStarter(client=None, task_queue=kwargs["task_queue"])  # type: ignore[arg-type]

    monkeypatch.setattr(webhook_module.IssueWorkflowStarter, "connect", fake_connect)
    monkeypatch.setenv("SF_TEMPORAL_ADDRESS", "temporal-test:7233")
    monkeypatch.setenv("SF_TEMPORAL_NAMESPACE", "default")
    monkeypatch.setenv("SF_TEMPORAL_TASK_QUEUE", "factory-orchestration")

    first, second = await asyncio.gather(
        webhook_module.get_starter(), webhook_module.get_starter()
    )

    assert len(connects) == 1
    assert connects[0] == ("temporal-test:7233", "default", "factory-orchestration")
    assert first is second


async def test_starter_unavailable_maps_to_503(
    monkeypatch: pytest.MonkeyPatch, _reset_providers
) -> None:
    from fastapi import HTTPException

    async def failing_connect(**kwargs: str) -> IssueWorkflowStarter:
        raise RuntimeError("Failed client connect")

    monkeypatch.setattr(webhook_module.IssueWorkflowStarter, "connect", failing_connect)

    with pytest.raises(HTTPException) as http_error:
        await webhook_module.get_starter()
    assert http_error.value.status_code == 503
    assert "temporal" in http_error.value.detail.lower()
    # the singleton stays unbound; a later call retries the connect
    assert webhook_module._starter is None
