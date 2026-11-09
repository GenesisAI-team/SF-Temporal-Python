"""Local smoke for the signed Linear webhook (GEN-38 H1).

Builds a representative Issue payload, signs it the way Linear does
(HMAC-SHA256 hex over the exact body, ``Linear-Signature``) and POSTs it to a
running endpoint. Prints the delivery id and the parsed response.

Usage:
    uv run python -m scripts.smoke_linear_webhook \
        --url http://localhost:8000/webhooks/linear \
        --secret "<webhook secret>" [--issue GEN-38] [--state Todo] \
        [--url-payload ...] (optionally repeat identical sends for duplicate case)
"""

import argparse
import asyncio
import hashlib
import hmac
import json
import sys
import time
import uuid

import httpx


def build_payload(issue_id: str, state: str, now_ms: int) -> bytes:
    payload = {
        "type": "Issue",
        "action": "update",
        "organizationId": "deno-org",
        "webhookId": "deno-webhook",
        "webhookTimestamp": now_ms,
        "url": f"https://linear.app/genesisnavarra/issue/{issue_id}/smoke",
        "data": {
            "id": str(uuid.uuid4()),
            "identifier": issue_id,
            "title": f"Smoke {issue_id}",
            "state": {"id": "state-id", "name": state, "type": "started"},
            "labels": [{"name": "Feature"}],
        },
    }
    return json.dumps(payload).encode("utf-8")


def sign(secret: str, body: bytes) -> str:
    return hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


async def send_once(
    client: httpx.AsyncClient,
    endpoint: str,
    secret: str,
    body: bytes,
    delivery_id: str,
) -> int:
    response = await client.post(
        endpoint,
        content=body,
        headers={
            "Content-Type": "application/json",
            "Linear-Signature": sign(secret, body),
            "Linear-Delivery": delivery_id,
            "Linear-Event": "Issue",
            "Linear-Timestamp": str(int(time.time() * 1000)),
        },
    )
    print(f"delivery={delivery_id} status={response.status_code} body={response.text}")
    return response.status_code


async def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Signed Linear webhook smoke.")
    parser.add_argument("--url", default="http://localhost:8000/webhooks/linear")
    parser.add_argument("--secret", required=True)
    parser.add_argument("--issue", default="GEN-38")
    parser.add_argument("--state", default="Todo")
    parser.add_argument("--repeat", type=int, default=1, help="resend same delivery n times")
    args = parser.parse_args(argv)

    body = build_payload(args.issue, args.state, int(time.time() * 1000))
    delivery_id = str(uuid.uuid4())
    async with httpx.AsyncClient(timeout=10) as client:
        for _ in range(max(args.repeat, 1)):
            await send_once(client, args.url, args.secret, body, delivery_id)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
