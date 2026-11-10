"""Verification ports (GEN-47): the independent test-run gate.

A PR is only published after the pipeline's own verification step executes
the test suite inside the sandbox. ``VerificationRunner`` is the seam; the
shipped adapter reuses the sandbox runtime (Docker), tests substitute fakes.
"""

from typing import Protocol

from super_factory.contracts.pipeline import VerificationCommand, VerificationOutcome


class VerificationUnavailable(RuntimeError):
    """The verification runtime is unavailable (retryable technical)."""


class VerificationRunner(Protocol):
    """Port that re-runs the task's tests independently of the agent."""

    async def run(self, command: VerificationCommand) -> VerificationOutcome:
        """Return the verification outcome (passed/failed with reasons)."""
        ...
