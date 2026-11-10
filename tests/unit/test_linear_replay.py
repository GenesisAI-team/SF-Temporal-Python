"""Tests for replay-staleness policy (GEN-38 H1).

Replay protection layer 2: a signed request whose body timestamp is outside
the tolerance window is rejected even though the signature matches.
"""

import pytest

from super_factory.integrations.linear.replay import is_stale_event

_NOW_MS = 1_500_000_000_000


@pytest.mark.parametrize(
    ("sent_ms", "tolerance_s", "expected"),
    [
        (_NOW_MS, 60, False),
        (_NOW_MS - 60_000, 60, False),
        (_NOW_MS - 60_001, 60, True),
        (_NOW_MS + 60_000, 60, False),
        (_NOW_MS + 60_001, 60, True),
        (_NOW_MS - 6 * 3_600_000, 60, True),
    ],
)
def test_staleness_boundary_behaviour(sent_ms: int, tolerance_s: int, expected: bool) -> None:
    assert is_stale_event(
        webhook_timestamp_ms=sent_ms,
        now_ms=_NOW_MS,
        tolerance_seconds=tolerance_s,
    ) is expected


def test_uptick_tolerance_allows_long_retry_windows() -> None:
    six_hours_ms = 6 * 3_600_000
    assert (
        is_stale_event(
            webhook_timestamp_ms=_NOW_MS - six_hours_ms,
            now_ms=_NOW_MS,
            tolerance_seconds=21_600,
        )
        is False
    )
