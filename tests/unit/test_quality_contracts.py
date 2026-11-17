"""Contract tests for the H3 quality/review boundary types (GEN-52).

Acceptance: gate outcomes, review findings, review commands and review
outcomes validate themselves exactly like the H2 outcome contracts (ok axis
carries payload, failure axis carries stable code + detail), the verification
outcome can carry per-gate evidence, and the agent/publish commands carry the
new optional repair/evidence fields.
"""

import pytest

from super_factory.contracts.pipeline import AgentRunCommand, PublishCommand, VerificationOutcome
from super_factory.contracts.quality import (
    GateOutcome,
    ReviewCommand,
    ReviewFinding,
    ReviewOutcome,
)
from super_factory.domain.quality import (
    FINDING_DEFECT,
    FINDING_SPEC_DRIFT,
    REASON_GATE_FAILED,
    REASON_REVIEW_FAILED,
    REASON_REVIEW_REJECTED,
    REASON_SPEC_DRIFT,
)


def test_gate_outcome_carries_independent_evidence() -> None:
    outcome = GateOutcome(
        gate="tests",
        passed=True,
        commands=("uv run pytest -q",),
        evidence=("1 passed",),
    )
    assert outcome.gate == "tests"
    assert outcome.passed


def test_gate_outcome_passed_must_not_carry_failure_codes() -> None:
    with pytest.raises(ValueError, match="ok"):
        GateOutcome(gate="tests", passed=True, failure_code=REASON_GATE_FAILED)


def test_gate_outcome_failed_requires_code_and_detail() -> None:
    with pytest.raises(ValueError, match="failure_code"):
        GateOutcome(gate="tests", passed=False)
    with pytest.raises(ValueError, match="failure_detail"):
        GateOutcome(gate="tests", passed=False, failure_code=REASON_GATE_FAILED)


def test_gate_outcome_rejects_blank_gate_name() -> None:
    with pytest.raises(ValueError, match="gate"):
        GateOutcome(gate="  ", passed=True)


def test_review_finding_validates_kind_and_detail() -> None:
    assert ReviewFinding(kind=FINDING_DEFECT, detail="x").detail == "x"
    with pytest.raises(ValueError, match="kind"):
        ReviewFinding(kind="NOTE", detail="x")
    with pytest.raises(ValueError, match="detail"):
        ReviewFinding(kind=FINDING_DEFECT, detail="  ")


def test_review_command_validates_approved_scope_shape() -> None:
    command = ReviewCommand(
        issue_id="GEN-52",
        run_key="GEN-52-v1",
        workspace_path="/ws",
        branch_name="feat/gen-52-gates",
        base_branch="main",
        objective="Add gates",
        acceptance_criteria=("gates run",),
        exclusions=(),
        constraints=("no auto merge",),
        gate_summaries=("gate tests: PASSED",),
    )
    assert command.run_key == "GEN-52-v1"
    with pytest.raises(ValueError, match="GEN-N"):
        ReviewCommand(
            issue_id="BAD",
            run_key="GEN-52-v1",
            workspace_path="/ws",
            branch_name="b",
            base_branch="main",
            objective="o",
            acceptance_criteria=("c",),
        )
    with pytest.raises(ValueError, match="run_key"):
        ReviewCommand(
            issue_id="GEN-52",
            run_key="nope",
            workspace_path="/ws",
            branch_name="b",
            base_branch="main",
            objective="o",
            acceptance_criteria=("c",),
        )
    with pytest.raises(ValueError, match="objective"):
        ReviewCommand(
            issue_id="GEN-52",
            run_key="GEN-52-v1",
            workspace_path="/ws",
            branch_name="b",
            base_branch="main",
            objective="   ",
            acceptance_criteria=("c",),
        )
    with pytest.raises(ValueError, match="acceptance_criteria"):
        ReviewCommand(
            issue_id="GEN-52",
            run_key="GEN-52-v1",
            workspace_path="/ws",
            branch_name="b",
            base_branch="main",
            objective="o",
            acceptance_criteria=(),
        )
    with pytest.raises(ValueError, match="workspace_path"):
        ReviewCommand(
            issue_id="GEN-52",
            run_key="GEN-52-v1",
            workspace_path="  ",
            branch_name="b",
            base_branch="main",
            objective="o",
            acceptance_criteria=("c",),
        )
    with pytest.raises(ValueError, match="branch names"):
        ReviewCommand(
            issue_id="GEN-52",
            run_key="GEN-52-v1",
            workspace_path="/ws",
            branch_name=" ",
            base_branch="main",
            objective="o",
            acceptance_criteria=("c",),
        )
    with pytest.raises(ValueError, match="exclusions"):
        ReviewCommand(
            issue_id="GEN-52",
            run_key="GEN-52-v1",
            workspace_path="/ws",
            branch_name="b",
            base_branch="main",
            objective="o",
            acceptance_criteria=("c",),
            exclusions=("  ",),
        )
    with pytest.raises(ValueError, match="exclusions"):
        ReviewCommand(
            issue_id="GEN-52",
            run_key="GEN-52-v1",
            workspace_path="/ws",
            branch_name="b",
            base_branch="main",
            objective="o",
            acceptance_criteria=("c",),
            constraints=("  ",),
        )
    with pytest.raises(ValueError, match="gate_summaries"):
        ReviewCommand(
            issue_id="GEN-52",
            run_key="GEN-52-v1",
            workspace_path="/ws",
            branch_name="b",
            base_branch="main",
            objective="o",
            acceptance_criteria=("c",),
            gate_summaries=(" ",),
        )


def test_review_outcome_approved_is_clean() -> None:
    outcome = ReviewOutcome(approved=True)
    assert outcome.approved
    assert outcome.findings == ()


def test_review_outcome_approved_must_not_carry_findings_or_failures() -> None:
    with pytest.raises(ValueError, match="approved"):
        ReviewOutcome(approved=True, findings=(ReviewFinding(FINDING_DEFECT, "x"),))
    with pytest.raises(ValueError, match="approved"):
        ReviewOutcome(approved=True, spec_drift=True)
    with pytest.raises(ValueError, match="approved"):
        ReviewOutcome(approved=True, failure_code=REASON_REVIEW_FAILED, failure_detail="d")


def test_review_outcome_rejected_carries_defects() -> None:
    outcome = ReviewOutcome(
        approved=False,
        findings=(ReviewFinding(FINDING_DEFECT, "missing test"),),
        failure_code=REASON_REVIEW_REJECTED,
        failure_detail="DEFECT: missing test",
    )
    assert not outcome.approved
    assert not outcome.spec_drift


def test_review_outcome_rejected_requires_code_detail_and_findings() -> None:
    with pytest.raises(ValueError, match="failure_code"):
        ReviewOutcome(approved=False)
    with pytest.raises(ValueError, match="findings"):
        ReviewOutcome(
            approved=False,
            failure_code=REASON_REVIEW_REJECTED,
            failure_detail="d",
        )


def test_review_outcome_review_rejected_forbids_drift_findings() -> None:
    with pytest.raises(ValueError, match="SPEC_DRIFT"):
        ReviewOutcome(
            approved=False,
            findings=(
                ReviewFinding(FINDING_DEFECT, "x"),
                ReviewFinding(FINDING_SPEC_DRIFT, "y"),
            ),
            failure_code=REASON_REVIEW_REJECTED,
            failure_detail="d",
        )


def test_review_outcome_spec_drift_requires_drift_finding_and_code() -> None:
    outcome = ReviewOutcome(
        approved=False,
        findings=(
            ReviewFinding(FINDING_DEFECT, "x"),
            ReviewFinding(FINDING_SPEC_DRIFT, "exclusion violated"),
        ),
        spec_drift=True,
        failure_code=REASON_SPEC_DRIFT,
        failure_detail="SPEC_DRIFT: exclusion violated",
    )
    assert outcome.spec_drift
    with pytest.raises(ValueError, match="SPEC_DRIFT"):
        ReviewOutcome(
            approved=False,
            findings=(ReviewFinding(FINDING_SPEC_DRIFT, "y"),),
            failure_code=REASON_REVIEW_REJECTED,
            failure_detail="d",
        )
    with pytest.raises(ValueError, match="SPEC_DRIFT"):
        ReviewOutcome(
            approved=False,
            findings=(ReviewFinding(FINDING_DEFECT, "y"),),
            spec_drift=True,
            failure_code=REASON_SPEC_DRIFT,
            failure_detail="d",
        )
    with pytest.raises(ValueError, match="SPEC_DRIFT"):
        ReviewOutcome(
            approved=False,
            findings=(ReviewFinding(FINDING_SPEC_DRIFT, "y"),),
            failure_code=REASON_SPEC_DRIFT,
            failure_detail="d",
        )
    with pytest.raises(ValueError, match="finding"):
        ReviewOutcome(
            approved=False,
            spec_drift=True,
            failure_code=REASON_SPEC_DRIFT,
            failure_detail="d",
        )


def test_review_outcome_review_failed_is_verdictless() -> None:
    outcome = ReviewOutcome(
        approved=False,
        failure_code=REASON_REVIEW_FAILED,
        failure_detail="reviewer produced no verdict",
    )
    assert outcome.failure_code == REASON_REVIEW_FAILED
    with pytest.raises(ValueError, match="findings"):
        ReviewOutcome(
            approved=False,
            findings=(ReviewFinding(FINDING_DEFECT, "x"),),
            failure_code=REASON_REVIEW_FAILED,
            failure_detail="d",
        )


def test_verification_outcome_carries_gate_evidence() -> None:
    gates = (
        GateOutcome(gate="tests", passed=True, commands=("uv run pytest -q",)),
        GateOutcome(
            gate="lint",
            passed=False,
            failure_code=REASON_GATE_FAILED,
            failure_detail="ruff",
        ),
    )
    outcome = VerificationOutcome(
        passed=False,
        gates=gates,
        failure_code="VERIFICATION_FAILED",
        failure_detail="lint: ruff",
    )
    assert outcome.gates[1].failure_code == REASON_GATE_FAILED
    assert VerificationOutcome(passed=True).gates == ()


def test_agent_run_command_carries_optional_repair_defects() -> None:
    command = _agent_command(defects=("DEFECT: missing test",))
    assert command.defects == ("DEFECT: missing test",)
    assert _agent_command().defects == ()
    with pytest.raises(ValueError, match="defects"):
        _agent_command(defects=("  ",))


def test_publish_command_carries_gate_evidence_summaries() -> None:
    command = _publish_command(gate_summaries=("gate tests: PASSED",))
    assert command.gate_summaries == ("gate tests: PASSED",)
    with pytest.raises(ValueError, match="gate_summaries"):
        _publish_command(gate_summaries=("  ",))


def _agent_command(**overrides: object) -> AgentRunCommand:
    fields: dict[str, object] = {
        "issue_id": "GEN-52",
        "repository": "a/b",
        "spec_version": 1,
        "run_key": "GEN-52-v1",
        "branch_name": "feat/gen-52-gates",
        "base_branch": "main",
        "objective": "Add gates",
        "acceptance_criteria": ("gates run",),
        "exclusions": (),
        "constraints": (),
        "dependencies": (),
        "workspace_path": "/ws/gen-52-v1",
    }
    fields.update(overrides)
    return AgentRunCommand(**fields)  # type: ignore[arg-type]


def _publish_command(**overrides: object) -> PublishCommand:
    fields: dict[str, object] = {
        "issue_id": "GEN-52",
        "repository": "a/b",
        "run_key": "GEN-52-v1",
        "branch_name": "feat/gen-52-gates",
        "base_branch": "main",
        "workspace_path": "/ws",
        "objective": "Add gates",
        "acceptance_criteria": ("gates run",),
        "linear_url_template": "https://linear.app/genesisnavarra/issue/{issue_id}",
    }
    fields.update(overrides)
    return PublishCommand(**fields)  # type: ignore[arg-type]
