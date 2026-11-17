"""Independent review adapter (GEN-52): reviewer session inside the sandbox.

Runs a separate reviewer session (``codex exec``, prompt via stdin) in its
own ephemeral sandbox after the implementer's session. The reviewer's reply
is parsed deterministically by ``domain.quality`` into findings; anything
without a clean verdict fails closed as ``REVIEW_FAILED``. Nothing is
simulated: without a reviewer-capable sandbox image the review fails
honestly.
"""

import contextlib

from super_factory.contracts.quality import ReviewCommand, ReviewFinding, ReviewOutcome
from super_factory.contracts.sandboxing import SandboxCommand, SandboxInstance, SandboxSpec
from super_factory.domain.quality import (
    REASON_REVIEW_FAILED,
    build_reviewer_prompt,
    defect_feedback,
    has_spec_drift,
    parse_review_reply,
    review_failure_code_for,
    reviewer_approved,
)
from super_factory.sandbox.ports import (
    SandboxCommandRejected,
    SandboxRuntime,
    SandboxUnavailable,
)

_DEFAULT_PROGRAM = "codex"
_DEFAULT_SANDBOX_IMAGE = "python:3.12-slim"
_DEFAULT_COMMAND_TIMEOUT_SECONDS = 600.0


async def _best_effort_cleanup(sandbox: SandboxRuntime, instance: SandboxInstance) -> None:
    """Cleanup must never mask the real outcome."""
    with contextlib.suppress(RuntimeError, OSError):
        await sandbox.cleanup(instance)


class SandboxReviewer:
    """Real ``IndependentReviewer`` executing the reviewer inside a sandbox."""

    def __init__(
        self,
        sandbox_runtime: SandboxRuntime,
        *,
        program: str = _DEFAULT_PROGRAM,
        sandbox_image: str = _DEFAULT_SANDBOX_IMAGE,
        command_timeout_seconds: float = _DEFAULT_COMMAND_TIMEOUT_SECONDS,
    ) -> None:
        self._sandbox = sandbox_runtime
        self._program = program
        self._sandbox_image = sandbox_image
        self._command_timeout_seconds = command_timeout_seconds

    @property
    def sandbox_image(self) -> str:
        """Sandbox image used for review sessions (ops configurable)."""
        return self._sandbox_image

    async def review(self, command: ReviewCommand) -> ReviewOutcome:
        spec = SandboxSpec(
            run_key=command.run_key,
            workspace_path=command.workspace_path,
            image=self._sandbox_image,
            command_timeout_seconds=int(self._command_timeout_seconds),
        )
        instance = await self._sandbox.ensure_sandbox(spec)
        prompt = build_reviewer_prompt(
            objective=command.objective,
            acceptance_criteria=command.acceptance_criteria,
            base_branch=command.base_branch,
            branch_name=command.branch_name,
            exclusions=command.exclusions,
            constraints=command.constraints,
            gate_summaries=command.gate_summaries,
        )
        launched = SandboxCommand(
            argv=(self._program, "exec"),
            stdin_payload=prompt,
            timeout_seconds=self._command_timeout_seconds,
        )
        try:
            outcome = await self._sandbox.run_in_sandbox(instance, launched)
        except SandboxCommandRejected as rejected:
            await _best_effort_cleanup(self._sandbox, instance)
            return ReviewOutcome(
                approved=False,
                failure_code=REASON_REVIEW_FAILED,
                failure_detail=f"{rejected.code}: {rejected.detail}",
            )
        except SandboxUnavailable:
            await _best_effort_cleanup(self._sandbox, instance)
            raise
        await _best_effort_cleanup(self._sandbox, instance)
        reply = outcome.output_tail
        findings = parse_review_reply(reply)
        failed = outcome.timed_out or outcome.exit_code is None or outcome.exit_code != 0
        if failed:
            detail = reply.strip() or (
                "reviewer session timed out"
                if outcome.timed_out
                else f"reviewer session exit={outcome.exit_code}"
            )
            return ReviewOutcome(
                approved=False, failure_code=REASON_REVIEW_FAILED, failure_detail=detail
            )
        if findings:
            drift = has_spec_drift(findings)
            code = review_failure_code_for(findings)
            return ReviewOutcome(
                approved=False,
                findings=tuple(
                    ReviewFinding(kind=kind, detail=detail) for kind, detail in findings
                ),
                spec_drift=drift,
                failure_code=code,
                failure_detail="; ".join(defect_feedback(findings)),
            )
        if not reviewer_approved(reply):
            return ReviewOutcome(
                approved=False,
                failure_code=REASON_REVIEW_FAILED,
                failure_detail="reviewer produced no verdict",
            )
        return ReviewOutcome(approved=True)
