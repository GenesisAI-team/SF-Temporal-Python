"""Tests for the in-process delivery deduplication store (GEN-38 H1)."""

import pytest

import super_factory.persistence.idempotency as idempotency
from super_factory.persistence.idempotency import InMemoryDeliveryDeduper


def test_first_claim_succeeds_then_duplicates_fail() -> None:
    deduper = InMemoryDeliveryDeduper(ttl_seconds=3600)
    assert deduper.claim("d-1") is True
    assert deduper.claim("d-1") is False
    assert deduper.claim("d-2") is True


def test_release_allows_reclaim() -> None:
    deduper = InMemoryDeliveryDeduper(ttl_seconds=3600)
    assert deduper.claim("d-1") is True
    deduper.release("d-1")
    assert deduper.claim("d-1") is True


def test_release_of_unknown_delivery_is_harmless() -> None:
    deduper = InMemoryDeliveryDeduper(ttl_seconds=3600)
    deduper.release("unknown")


def test_expired_delivery_can_be_claimed_again(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(idempotency, "_monotonic_now", lambda: 1000.0)
    deduper = InMemoryDeliveryDeduper(ttl_seconds=600)
    assert deduper.claim("d-1") is True
    assert deduper.claim("d-1") is False
    monkeypatch.setattr(idempotency, "_monotonic_now", lambda: 1601.0)
    assert deduper.claim("d-1") is True


def test_zero_ttl_degrades_to_no_deduplication() -> None:
    deduper = InMemoryDeliveryDeduper(ttl_seconds=0)
    assert deduper.claim("d-1") is True
    assert deduper.claim("d-1") is True


def test_negative_ttl_is_rejected() -> None:
    with pytest.raises(ValueError, match="ttl_seconds"):
        InMemoryDeliveryDeduper(ttl_seconds=-1)


def test_blank_delivery_id_is_rejected() -> None:
    deduper = InMemoryDeliveryDeduper(ttl_seconds=600)
    with pytest.raises(ValueError, match="delivery_id"):
        deduper.claim("   ")
