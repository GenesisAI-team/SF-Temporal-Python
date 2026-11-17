"""Tests for the independent reviewer adapter (GEN-52).

Acceptance: the reviewer runs a separate sandbox session (never the
implementer's), parses its reply into findings deterministically, fails
closed (no verdict => REVIEW_FAILED), reports spec drift and plain defects
differently, propagates sandbox unavailability for retries, and cleans up
the sandbox on every path.
"""

import pytest

from super_factory.contracts.quality import ReviewCommand, ReviewFinding
from super_factory.contracts.sandboxing import (
    SandboxCommand,
    SandboxCommandOutcome,
    SandboxInstance,
    SandboxSpec,
)
from super_factory.domain.quality import (
    FINDING_DEFECT,
    FINDING_SPEC_DRIFT,
    REASON_REVIEW_FAILED,
    REASON_REVIEW_REJECTED,
    REASON_SPEC_DRIFT,
)
from super_factory.review.sandbox import SandboxReviewer
from super_factory.sandbox.ports import SandboxCommandRejected, SandboxUnavailable


class FakeSandboxRuntime:
    def __init__(self) -> None:
        self.started_specs: list[SandboxSpec] = []
        self.commands: list[SandboxCommand] = []
        self.cleaned: list[str] = []
        self.raise_on_start: Exception | None = None
        self.raise_on_run: Exception | None = None
        self.outcome = SandboxCommandOutcome(exit_code=0, output_tail="APPROVED")

    async def ensure_sandbox(self, spec: SandboxSpec) -> SandboxInstance:
        if self.raise_on_start is not None:
            raise self.raise_on_start
        self.started_specs.append(spec)
        return SandboxInstance(id=f"factory-sandbox-{spec.run_key.lower()}")

    async def run_in_sandbox(
        self, instance: SandboxInstance, command: SandboxCommand
    ) -> SandboxCommandOutcome:
        if self.raise_on_run is not None:
            raise self.raise_on_run
        self.commands.append(command)
        return self.outcome

    async def cleanup(self, instance: SandboxInstance) -> None:
        self.cleaned.append(instance.id)


def _command(**overrides: object) -> ReviewCommand:
    fields: dict[str, object] = {
        "issue_id": "GEN-52",
        "run_key": "GEN-52-v1",
        "workspace_path": "/ws/gen-52-v1",
        "branch_name": "feat/gen-52-gates",
        "base_branch": "main",
        "objective": "Add independent gates",
        "acceptance_criteria": ("gates run", "drift blocked"),
        "exclusions": (),
        "constraints": (),
        "gate_summaries": ("gate tests: PASSED",),
    }
    fields.update(overrides)
    return ReviewCommand(**fields)  # type: ignore[arg-type]


async def test_clean_reply_approves() -> None:
    sandbox = FakeSandboxRuntime()
    sandbox.outcome = SandboxCommandOutcome(exit_code=0, output_tail="reviewed\nAPPROVED\n")
    outcome = await SandboxReviewer(sandbox).review(_command())
    assert outcome.approved
    assert outcome.findings == ()
    assert not outcome.spec_drift
    assert outcome.failure_code == ""
    assert sandbox.cleaned == ["factory-sandbox-gen-52-v1"]
    launched = sandbox.commands[0]
    assert launched.argv == ("codex", "exec")
    assert "independent reviewer" in (launched.stdin_payload or "")
    assert "gates run" in (launched.stdin_payload or "")
    assert "gate tests: PASSED" in (launched.stdin_payload or "")


async def test_defect_findings_reject_without_drift() -> None:
    sandbox = FakeSandboxRuntime()
    sandbox.outcome = SandboxCommandOutcome(
        exit_code=0, output_tail="DEFECT: missing test for budget\n"
    )
    outcome = await SandboxReviewer(sandbox).review(_command())
    assert not outcome.approved
    assert not outcome.spec_drift
    assert outcome.failure_code == REASON_REVIEW_REJECTED
    assert outcome.findings == (ReviewFinding(FINDING_DEFECT, "missing test for budget"),)
    assert len(sandbox.cleaned) == 1


async def test_drift_findings_report_spec_drift() -> None:
    sandbox = FakeSandboxRuntime()
    sandbox.outcome = SandboxCommandOutcome(
        exit_code=0, output_tail="SPEC_DRIFT: rewrote the H1 webhook\n"
    )
    outcome = await SandboxReviewer(sandbox).review(_command())
    assert not outcome.approved
    assert outcome.spec_drift
    assert outcome.failure_code == REASON_SPEC_DRIFT
    assert outcome.findings == (ReviewFinding(FINDING_SPEC_DRIFT, "rewrote the H1 webhook"),)


async def test_mixed_findings_take_drift_precedence() -> None:
    sandbox = FakeSandboxRuntime()
    sandbox.outcome = SandboxCommandOutcome(
        exit_code=0,
        output_tail="DEFECT: style\nSPEC_DRIFT: touches exclusions\n",
    )
    outcome = await SandboxReviewer(sandbox).review(_command())
    assert outcome.spec_drift
    assert outcome.failure_code == REASON_SPEC_DRIFT
    assert len(outcome.findings) == 2


async def test_findings_win_even_next_to_an_approved_line() -> None:
    sandbox = FakeSandboxRuntime()
    sandbox.outcome = SandboxCommandOutcome(
        exit_code=0, output_tail="APPROVED\nDEFECT: forgot one test\n"
    )
    outcome = await SandboxReviewer(sandbox).review(_command())
    assert not outcome.approved
    assert outcome.failure_code == REASON_REVIEW_REJECTED


async def test_verdictless_reply_fails_closed() -> None:
    sandbox = FakeSandboxRuntime()
    sandbox.outcome = SandboxCommandOutcome(exit_code=0, output_tail="looks mostly fine")
    outcome = await SandboxReviewer(sandbox).review(_command())
    assert not outcome.approved
    assert outcome.failure_code == REASON_REVIEW_FAILED
    assert "no verdict" in outcome.failure_detail
    assert outcome.findings == ()


async def test_failed_session_reports_review_failed_honestly() -> None:
    sandbox = FakeSandboxRuntime()
    sandbox.outcome = SandboxCommandOutcome(exit_code=7, output_tail="reviewer crashed")
    outcome = await SandboxReviewer(sandbox).review(_command())
    assert not outcome.approved
    assert outcome.failure_code == REASON_REVIEW_FAILED
    assert "reviewer crashed" in outcome.failure_detail
    assert len(sandbox.cleaned) == 1


async def test_timeout_reports_review_failed() -> None:
    sandbox = FakeSandboxRuntime()
    sandbox.outcome = SandboxCommandOutcome(exit_code=None, output_tail="", timed_out=True)
    outcome = await SandboxReviewer(sandbox).review(_command())
    assert not outcome.approved
    assert outcome.failure_code == REASON_REVIEW_FAILED
    assert "timed out" in outcome.failure_detail


async def test_sandbox_command_rejection_is_a_failed_review_with_cleanup() -> None:
    sandbox = FakeSandboxRuntime()
    sandbox.raise_on_run = SandboxCommandRejected("FORBIDDEN_COMMAND", "rm -rf /")
    outcome = await SandboxReviewer(sandbox).review(_command())
    assert not outcome.approved
    assert outcome.failure_code == REASON_REVIEW_FAILED
    assert "FORBIDDEN_COMMAND" in outcome.failure_detail
    assert len(sandbox.cleaned) == 1


async def test_sandbox_unavailability_propagates_for_retries() -> None:
    sandbox = FakeSandboxRuntime()
    sandbox.raise_on_start = SandboxUnavailable("docker down")
    with pytest.raises(SandboxUnavailable, match="docker down"):
        await SandboxReviewer(sandbox).review(_command())
    assert sandbox.cleaned == []


async def test_reviewer_starts_read_only_workspace_sandbox() -> None:
    """GEN-52: the review sandbox mounts the workspace read-only, so a
    reviewer edit can never alter the artifact that gets published."""
    sandbox = FakeSandboxRuntime()
    sandbox.outcome = SandboxCommandOutcome(exit_code=0, output_tail="APPROVED\n")
    await SandboxReviewer(sandbox).review(_command())
    assert len(sandbox.started_specs) == 1
    spec = sandbox.started_specs[0]
    assert spec.workspace_read_only is True
