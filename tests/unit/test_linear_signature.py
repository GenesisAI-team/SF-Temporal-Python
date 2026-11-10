"""Tests for Linear webhook signature verification (GEN-38 H1).

Linear sends the hex HMAC-SHA256 of the raw body with the signing secret in
``Linear-Signature`` (no prefix). Verification must itself be secret-free in
terms of logging and use constant-time comparison.
"""

import hashlib
import hmac

from super_factory.integrations.linear.signature import (
    LINEAR_SIGNATURE_HEADER,
    verify_linear_signature,
)

SECRET = "lin_wh_sample_secret_Yc3vT9qPk1x"
BODY = b'{"type": "Issue", "action": "update"}'


def _signature(body: bytes = BODY, secret: str = SECRET) -> str:
    return hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


def test_header_name_is_linear_signature() -> None:
    assert LINEAR_SIGNATURE_HEADER == "Linear-Signature"


def test_valid_signature_is_accepted() -> None:
    assert verify_linear_signature(secret=SECRET, body=BODY, signature=_signature()) is True


def test_uppercase_and_padded_signature_is_accepted() -> None:
    provided = f"  {_signature().upper()}  "
    assert verify_linear_signature(secret=SECRET, body=BODY, signature=provided) is True


def test_tampered_body_is_rejected() -> None:
    signature = _signature()
    other_body = BODY + b" "
    assert verify_linear_signature(secret=SECRET, body=other_body, signature=signature) is False


def test_wrong_secret_is_rejected() -> None:
    assert (
        verify_linear_signature(secret="other-secret", body=BODY, signature=_signature())
        is False
    )


def test_missing_signature_is_rejected() -> None:
    assert verify_linear_signature(secret=SECRET, body=BODY, signature=None) is False


def test_blank_signature_is_rejected() -> None:
    assert verify_linear_signature(secret=SECRET, body=BODY, signature="   ") is False


def test_non_hex_signature_is_rejected() -> None:
    assert (
        verify_linear_signature(
            secret=SECRET, body=BODY, signature="zz" * 32
        ) is False
    )


def test_empty_secret_fails_closed() -> None:
    assert verify_linear_signature(secret="", body=BODY, signature=_signature()) is False
