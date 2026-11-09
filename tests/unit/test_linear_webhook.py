"""Tests for the signed Linear webhook endpoint (GEN-38 H1).

Covers: signature rejection (401), payload validation (400), replay-window
rejection (400), delivery idempotency (duplicate), non-Issue ignoring,
blocked selection with audit, accepted/recovered unique runs, configuration
failure (500), secret absence (503) and secret-free logs.
"""

import hashlib
import hmac
import json
import logging
import time
from pathlib import Path
from typing import Any, cast

import httpx
import pytest
from fastapi import FastAPI

from super_factory.api.app import create_app
from super_factory.api.webhooks.linear import (
    get_audit_sink,
    get_deduper,
    get_starter,
    get_webhook_secret,
)
from super_factory.contracts.workflow_io import IssueWorkflowInput, WorkflowStartResult
from super_factory.persistence.audit import JsonLinesAuditSink
from super_factory.persistence.idempotency import InMemoryDeliveryDeduper

SECRET = "lin_wh_sample_secret_Yc3vT9qPk1x"
REPO = "GenesisAI-team/SF-Temporal-Python"
BASE_URL = "http://test"


class FakeStarter:
    """Records start inputs; optional failure/recovered modes."""

    def __init__(self, *, raises: bool = False, started: bool = True) -> None:
        self.calls: list[IssueWorkflowInput] = []
        self._raises = raises
        self._started = started

    async def start_or_recover(self, data: IssueWorkflowInput) -> WorkflowStartResult:
        self.calls.append(data)
        if self._raises:
            msg = "boom"
            raise RuntimeError(msg)
        return WorkflowStartResult(
            workflow_id=f"issue-{data.issue_id}",
            run_id="run-1",
            started=self._started,
        )


@pytest.fixture
def h1_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SF_LINEAR_TARGET_REPOSITORY", REPO)
    monkeypatch.setenv("SF_LINEAR_SELECTABLE_STATES", "Todo,In Progress")
    monkeypatch.setenv("SF_LINEAR_TIMESTAMP_TOLERANCE_SECONDS", "60")


def _app(
    tmp_path: Path, starter: FakeStarter | None = None, *, secret: str | None = SECRET
) -> FastAPI:
    app = create_app()
    app.dependency_overrides[get_webhook_secret] = lambda: secret or ""
    dedupe_store = InMemoryDeliveryDeduper(ttl_seconds=3600)
    app.dependency_overrides[get_deduper] = lambda: dedupe_store
    app.dependency_overrides[get_audit_sink] = lambda: JsonLinesAuditSink(tmp_path / "audit.jsonl")
    app.dependency_overrides[get_starter] = lambda: cast(Any, starter or FakeStarter())
    return app


def _signed(body: bytes, secret: str = SECRET) -> str:
    return hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


def _payload_dict(issue_id: str = "GEN-38", state: str = "Todo") -> dict[str, Any]:
    return {
        "type": "Issue",
        "action": "update",
        "organizationId": "dc844923-f9a4-40a3-825c-dea7747e57d6",
        "webhookId": "000042e3-d123-4980-b49f-8e140eef9329",
        "webhookTimestamp": int(time.time() * 1000),
        "url": "https://linear.app/genesisnavarra/issue/GEN-38/sf",
        "data": {
            "id": "539068e2-ae88-4d09-bd75-22eb4a59612f",
            "identifier": issue_id,
            "title": "H1",
            "state": {"id": "f62890cb", "name": state, "type": "started"},
            "labels": [{"name": "Feature"}],
        },
    }


def _fresh_body() -> bytes:
    return json.dumps(_payload_dict()).encode("utf-8")


async def _post(
    app: FastAPI,
    body: bytes,
    *,
    sign: bool = True,
    secret: str = SECRET,
    headers: dict[str, str] | None = None,
) -> httpx.Response:
    request_headers = {"Content-Type": "application/json"}
    if headers:
        request_headers.update(headers)
    if sign:
        request_headers["Linear-Signature"] = _signed(body, secret)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as client:
        return await client.post("/webhooks/linear", content=body, headers=request_headers)


async def test_missing_signature_is_rejected(
    tmp_path: Path, h1_env: None
) -> None:
    response = await _post(_app(tmp_path), _fresh_body(), sign=False)
    assert response.status_code == 401


async def test_invalid_signature_is_rejected(
    tmp_path: Path, h1_env: None
) -> None:
    body = _fresh_body()
    response = await _post(
        _app(tmp_path), body, sign=False, headers={"Linear-Signature": "deadbeef" * 8}
    )
    assert response.status_code == 401
    assert "invalid" in response.json()["detail"].lower()


async def test_underconfigured_secret_fails_closed_to_503(
    tmp_path: Path, h1_env: None
) -> None:
    response = await _post(_app(tmp_path, secret=""), _fresh_body())
    assert response.status_code == 503
    assert "not configured" in response.json()["detail"]


async def test_unparseable_payload_is_rejected_with_400(
    tmp_path: Path, h1_env: None
) -> None:
    response = await _post(_app(tmp_path), b"{not json")
    assert response.status_code == 400
    assert "invalid payload" in response.json()["detail"]


async def test_stale_signed_payload_is_rejected_with_400(
    tmp_path: Path, h1_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SF_LINEAR_TIMESTAMP_TOLERANCE_SECONDS", "0")
    stale = _payload_dict()
    stale["webhookTimestamp"] = int(time.time() * 1000) - 10_000
    response = await _post(_app(tmp_path), json.dumps(stale).encode("utf-8"))
    assert response.status_code == 400
    assert "stale" in response.json()["detail"].lower()


async def test_duplicate_delivery_is_acknowledged_once(
    tmp_path: Path, h1_env: None
) -> None:
    starter = FakeStarter()
    app = _app(tmp_path, starter)
    body = _fresh_body()
    first = await _post(app, body)
    second = await _post(app, body)
    assert first.json()["status"] == "accepted"
    assert second.json()["status"] == "duplicate"
    assert len(starter.calls) == 1


async def test_non_issue_event_is_ignored(
    tmp_path: Path, h1_env: None
) -> None:
    starter = FakeStarter()
    comment = _payload_dict()
    comment["type"] = "Comment"
    comment["action"] = "create"
    response = await _post(_app(tmp_path, starter), json.dumps(comment).encode("utf-8"))
    assert response.json()["status"] == "ignored"
    assert starter.calls == []


async def test_done_issue_is_blocked_with_audited_reasons(
    tmp_path: Path, h1_env: None
) -> None:
    starter = FakeStarter()
    done = _payload_dict(issue_id="GEN-38", state="Done")
    response = await _post(_app(tmp_path, starter), json.dumps(done).encode("utf-8"))
    assert response.json() == {
        "status": "blocked",
        "reasons": ["STATE_NOT_SELECTABLE: Done"],
    }
    assert starter.calls == []
    entry = _single_audit_line(tmp_path / "audit.jsonl")
    assert entry["selection_outcome"] == "BLOCKED"
    assert entry["workflow_state"] == "-"
    assert entry["workflow_id"] is None
    assert entry["workflow_run_id"] is None


async def test_foreign_issue_identifier_is_blocked(
    tmp_path: Path, h1_env: None
) -> None:
    starter = FakeStarter()
    foreign = _payload_dict(issue_id="ENG-417")
    response = await _post(_app(tmp_path, starter), json.dumps(foreign).encode("utf-8"))
    body = response.json()
    assert body["status"] == "blocked"
    assert "ISSUE_ID_MALFORMED: ENG-417" in body["reasons"]


async def test_blank_target_repository_blocks_everything(
    tmp_path: Path, h1_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SF_LINEAR_TARGET_REPOSITORY", "")
    starter = FakeStarter()
    fresh = json.dumps(_payload_dict(issue_id="GEN-77")).encode("utf-8")
    response = await _post(_app(tmp_path, starter), fresh)
    assert response.json() == {
        "status": "blocked",
        "reasons": ["REPOSITORY_UNRESOLVED"],
    }
    assert starter.calls == []


async def test_accepted_event_starts_unique_run_and_audits(
    tmp_path: Path, h1_env: None
) -> None:
    starter = FakeStarter()
    response = await _post(_app(tmp_path, starter), _fresh_body())
    body = response.json()
    assert body == {
        "status": "accepted",
        "workflow_id": "issue-GEN-38",
        "run_id": "run-1",
    }
    assert len(starter.calls) == 1
    call = starter.calls[0]
    assert call.issue_id == "GEN-38"
    assert call.repository == REPO
    assert call.issue_state == "Todo"
    assert call.labels == ("Feature",)
    assert call.selectable_states == ("Todo", "In Progress")
    entry = _single_audit_line(tmp_path / "audit.jsonl")
    assert entry["selection_outcome"] == "SELECTED"
    assert entry["workflow_id"] == "issue-GEN-38"
    assert entry["workflow_run_id"] == "run-1"
    assert entry["workflow_state"] == "READY"


async def test_already_running_event_reports_recovered(
    tmp_path: Path, h1_env: None
) -> None:
    app = _app(tmp_path, FakeStarter(started=False))
    response = await _post(app, _fresh_body())
    assert response.json()["status"] == "recovered"


async def test_malformed_target_repository_fails_closed_on_500(
    tmp_path: Path, h1_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SF_LINEAR_TARGET_REPOSITORY", "not-a-repo")
    starter = FakeStarter()
    response = await _post(_app(tmp_path, starter), _fresh_body())
    assert response.status_code == 500
    assert response.json()["detail"] == "invalid configuration"
    assert starter.calls == []


async def test_workflow_dispatch_failure_returns_500(
    tmp_path: Path, h1_env: None
) -> None:
    starter = FakeStarter(raises=True)
    dispatch = json.dumps(_payload_dict(issue_id="GEN-91")).encode("utf-8")
    response = await _post(_app(tmp_path, starter), dispatch)
    assert response.status_code == 500
    assert response.json()["detail"] == "workflow dispatch failed"
    assert starter.calls


async def test_logs_never_contain_the_secret(
    tmp_path: Path, h1_env: None, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.DEBUG):
        await _post(_app(tmp_path), _fresh_body())
        await _post(_app(tmp_path), b"{bogus")
        await _post(_app(tmp_path), _fresh_body(), sign=False, secret="another-secret")
    assert SECRET not in caplog.text
    assert "lin_wh" not in caplog.text
    assert "another-secret" not in caplog.text


def _single_audit_line(path: Path) -> dict[str, Any]:
    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    return json.loads(lines[0])
