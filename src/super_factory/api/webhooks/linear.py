"""Linear webhook endpoint (not implemented until H1 — returns 501)."""

from fastapi import APIRouter, Response

router = APIRouter(tags=["webhooks"])


@router.post("/webhooks/linear")
def linear_webhook(response: Response) -> dict[str, str]:
    """Placeholder for the signed Linear webhook (implemented in H1).

    Deliberately returns 501 instead of pretending to succeed.
    """
    response.status_code = 501
    return {"detail": "Linear webhook not implemented (H1)"}
