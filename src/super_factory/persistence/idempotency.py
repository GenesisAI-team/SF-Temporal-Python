"""In-process delivery deduplication for Linear webhooks (ADR-0006).

Fast best-effort idempotency at the edge: Linear retries the same delivery
(``Linear-Delivery``) across its retry schedule. The durable guarantee comes
from the Temporal workflow id reuse policy; this store avoids needless work
and stays small by dropping expired entries and never unbounded growth.
"""

import time


def _monotonic_now() -> float:
    """Isolated for tests."""
    return time.monotonic()


class InMemoryDeliveryDeduper:
    """Store of delivery ids claimed for a TTL (claims expire, then re-claim)."""

    def __init__(self, ttl_seconds: float) -> None:
        if ttl_seconds < 0:
            msg = "ttl_seconds must not be negative"
            raise ValueError(msg)
        self._ttl = ttl_seconds
        self._expires: dict[str, float] = {}

    def claim(self, delivery_id: str) -> bool:
        """Mark the delivery as in-flight; False when already claimed."""
        if not delivery_id or not delivery_id.strip():
            msg = "delivery_id must not be blank"
            raise ValueError(msg)
        now = _monotonic_now()
        self._drop_expired(now)
        delivery_id = delivery_id.strip()
        expires_at = self._expires.get(delivery_id)
        if expires_at is not None and expires_at > now:
            return False
        self._expires[delivery_id] = now + self._ttl
        return True

    def release(self, delivery_id: str) -> None:
        """Drop a claim after a failed outcome so retries can reprocess."""
        if not delivery_id or not delivery_id.strip():
            msg = "delivery_id must not be blank"
            raise ValueError(msg)
        self._drop_expired(_monotonic_now())
        self._expires.pop(delivery_id.strip(), None)

    def _drop_expired(self, now: float) -> None:
        if self._ttl == 0:
            self._expires.clear()
            return
        for delivery_id, expires_at in list(self._expires.items()):
            if expires_at <= now:
                del self._expires[delivery_id]
