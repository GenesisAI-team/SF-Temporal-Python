"""Independent-review ports (GEN-52): the reviewer separate from the implementer.

``IndependentReviewer`` is the seam between the pipeline and any reviewer
agent (Codex CLI in a separate sandbox session for the shipped adapter).
Unlike the coding agent, the reviewer never modifies the workspace: it
contrasts the produced changes with the approved criteria and answers in the
strict verdict format. Transport-level outages surface as exceptions so
Temporal's retry policy handles them.
"""

from typing import Protocol

from super_factory.contracts.quality import ReviewCommand, ReviewOutcome


class ReviewerUnavailable(RuntimeError):
    """The review runtime is unavailable (retryable technical)."""


class IndependentReviewer(Protocol):
    """Port that reviews the run independently of the implementer agent."""

    async def review(self, command: ReviewCommand) -> ReviewOutcome:
        """Return the review outcome (approved / findings / failed)."""
        ...
