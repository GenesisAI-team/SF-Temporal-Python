"""Pure rules that decide whether an approved Linear issue enters the factory.

The selector is deterministic and deliberately dumb: it maps (issue snapshot,
selection criteria) to an accept/blocked decision plus persisted blocking
reasons. Eligibility rules live here so contracts, the API gate and the
workflow activity share one source of truth (clean architecture).
"""

from dataclasses import dataclass

from super_factory.domain.repository_spec import is_valid_repository
from super_factory.domain.task_spec import is_valid_issue_id

REASON_ISSUE_ID_MALFORMED = "ISSUE_ID_MALFORMED"
REASON_STATE_UNRESOLVED = "STATE_UNRESOLVED"
REASON_STATE_NOT_SELECTABLE = "STATE_NOT_SELECTABLE"
REASON_REPOSITORY_UNRESOLVED = "REPOSITORY_UNRESOLVED"
REASON_REPOSITORY_MALFORMED = "REPOSITORY_MALFORMED"
REASON_REPOSITORY_NOT_ALLOWED = "REPOSITORY_NOT_ALLOWED"


@dataclass(frozen=True)
class BlockingReason:
    """Why a candidate issue was not selected (machine-readable code + detail)."""

    code: str
    detail: str


@dataclass(frozen=True)
class IssueSelectionResult:
    """Outcome of applying selection criteria to a candidate issue.

    Invariant: an approved decision carries no blocking reasons.
    """

    approved: bool
    reasons: tuple[BlockingReason, ...]

    def __post_init__(self) -> None:
        if self.approved and self.reasons:
            msg = "approved decisions cannot carry blocking reasons"
            raise ValueError(msg)


def format_blocking_reason(reason: BlockingReason) -> str:
    """One blocking reason as the stable ``code: detail`` string."""
    return f"{reason.code}: {reason.detail}"


def format_blocking_reasons(reasons: tuple[BlockingReason, ...]) -> str:
    """Serialize reasons for audit/memo storage: ``"code: detail; ..."``."""
    return "; ".join(format_blocking_reason(reason) for reason in reasons)


def evaluate_issue_selection(
    *,
    issue_id: str,
    issue_state: str,
    repository: str,
    selectable_states: tuple[str, ...],
    allowed_repositories: tuple[str, ...],
) -> IssueSelectionResult:
    """Return the selection decision for one candidate issue.

    Accumulates every blocking reason so operators get the full diagnosis;
    an issue is approved only when no reason applies.
    """
    reasons: list[BlockingReason] = []
    if not is_valid_issue_id(issue_id):
        reasons.append(BlockingReason(code=REASON_ISSUE_ID_MALFORMED, detail=issue_id))

    state = issue_state.strip()
    if not state:
        reasons.append(BlockingReason(code=REASON_STATE_UNRESOLVED, detail=issue_state))
    elif state not in selectable_states:
        reasons.append(
            BlockingReason(code=REASON_STATE_NOT_SELECTABLE, detail=issue_state)
        )

    repository_stripped = repository.strip()
    if not repository_stripped:
        reasons.append(BlockingReason(code=REASON_REPOSITORY_UNRESOLVED, detail=repository))
    elif not is_valid_repository(repository_stripped):
        reasons.append(
            BlockingReason(code=REASON_REPOSITORY_MALFORMED, detail=repository_stripped)
        )
    elif repository_stripped not in allowed_repositories:
        reasons.append(
            BlockingReason(code=REASON_REPOSITORY_NOT_ALLOWED, detail=repository_stripped)
        )

    return IssueSelectionResult(approved=not reasons, reasons=tuple(reasons))
