"""Tests for the FastAPI application (TDD cycles C5-C6)."""

import httpx

from super_factory.api.app import create_app


async def _request(method: str, url: str, **kwargs: object) -> httpx.Response:  # type: ignore[typeddict-item]
    transport = httpx.ASGITransport(app=create_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.request(method, url, **kwargs)  # type: ignore[arg-type]


async def test_healthz_returns_ok() -> None:
    response = await _request("GET", "/healthz")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "super-factory"


async def test_linear_webhook_returns_501_not_implemented() -> None:
    response = await _request("POST", "/webhooks/linear", json={"type": "Issue"})
    assert response.status_code == 501
    body = response.json()
    assert "not implemented" in body["detail"].lower()
    assert "h1" in body["detail"].lower()


async def test_unknown_route_returns_404() -> None:
    response = await _request("GET", "/does-not-exist")
    assert response.status_code == 404


def test_app_title_is_super_factory() -> None:
    app = create_app()
    assert app.title == "Super Factory"
