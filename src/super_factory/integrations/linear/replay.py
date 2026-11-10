"""Linear replay-staleness policy (ADR-0007).

Layer 2 of replay protection: a request whose signed body timestamp is
outside the tolerance window is rejected even though the signature matches.
Tolerance is configurable so deployments can accept Linear's documented
retry schedule (1 minute, 1 hour, 6 hours) at the price of a wider window.
"""


def is_stale_event(*, webhook_timestamp_ms: int, now_ms: int, tolerance_seconds: int) -> bool:
    """Return True when the body timestamp is outside the tolerance window."""
    return abs(now_ms - webhook_timestamp_ms) > tolerance_seconds * 1000
