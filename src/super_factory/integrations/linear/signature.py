"""Linear webhook adapter: signature verification (ADR-0007).

Linear signs each delivery with the hex HMAC-SHA256 of the exact raw body,
keyed with the webhook signing secret, in the ``Linear-Signature`` header.
Comparison is constant-time; secrets never leave this module's memory.
"""

import hashlib
import hmac

LINEAR_SIGNATURE_HEADER = "Linear-Signature"


def verify_linear_signature(
    *,
    secret: str,
    body: bytes,
    signature: str | None,
) -> bool:
    """Return True when ``signature`` matches HMAC-SHA256(secret, body) in hex.

    Fails closed: an empty secret or an absent/blank signature never passes.
    Casing and surrounding whitespace in the header are tolerated.
    """
    if not secret or not signature or not signature.strip():
        return False
    expected = hmac.new(
        secret.encode("utf-8"), body, hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(signature.strip().lower(), expected)
