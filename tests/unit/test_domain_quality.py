"""Tests for the H3 domain rules: gates, independent review and repair (GEN-52).

Acceptance: the independent quality-gate suite is deterministic (tests, lint,
typecheck), the reviewer prompt states its independence and its verdict
format, review replies parse into findings deterministically, repair feedback
and repair audit ids are stable, and the agent prompt carries repair feedback
only when there are defects to repair.
"""

import pytest

from super_factory.domain.pipeline import build_agent_prompt, pr_body_for
from super_factory.domain.quality import (
    FINDING_DEFECT,
    FINDING_SPEC_DRIFT,
    REASON_REPAIR_BUDGET_EXHAUSTED,
    REASON_REVIEW_FAILED,
    REASON_REVIEW_REJECTED,
    REASON_SPEC_DRIFT,
    GateDefinition,
    build_reviewer_prompt,
    default_gate_suite,
    defect_feedback,
    gate_failure_feedback,
    has_spec_drift,
    parse_review_reply,
    repair_audit_delivery_id,
    review_failure_code_for,
    reviewer_approved,
    summarize_gate,
)


def test_h3_reason_and_finding_codes_are_stable_values() -> None:
    assert REASON_SPEC_DRIFT == "SPEC_DRIFT"
    assert REASON_REVIEW_REJECTED == "REVIEW_REJECTED"
    assert REASON_REVIEW_FAILED == "REVIEW_FAILED"
    assert REASON_REPAIR_BUDGET_EXHAUSTED == "REPAIR_BUDGET_EXHAUSTED"
    assert FINDING_DEFECT == "DEFECT"
    assert FINDING_SPEC_DRIFT == "SPEC_DRIFT"


def test_default_gate_suite_runs_the_repo_checks_independently() -> None:
    gates = default_gate_suite()
    assert [gate.name for gate in gates] == ["tests", "lint", "typecheck"]
    assert gates[0].steps == (("uv", "run", "pytest", "-q"),)
    assert gates[1].steps == (("uv", "run", "ruff", "check", "."),)
    assert gates[2].steps == (("uv", "run", "mypy", "src"),)


def test_gate_definition_rejects_blank_name_or_broken_steps() -> None:
    with pytest.raises(ValueError, match="name"):
        GateDefinition(name="  ", steps=(("uv",),))
    with pytest.raises(ValueError, match="steps"):
        GateDefinition(name="tests", steps=())
    with pytest.raises(ValueError, match="argv"):
        GateDefinition(name="tests", steps=((),))


def test_parse_review_reply_extracts_prefixed_findings() -> None:
    reply = (
        "prose analysis\n"
        "DEFECT: missing test for repair budget\n"
        "SPEC_DRIFT: touches the H1 selection flow\n"
    )
    assert parse_review_reply(reply) == (
        (FINDING_DEFECT, "missing test for repair budget"),
        (FINDING_SPEC_DRIFT, "touches the H1 selection flow"),
    )


def test_parse_review_reply_handles_blank_details_and_ignores_chatter() -> None:
    assert parse_review_reply("looked at the diff\nDEFECT:\nAPPROVED\n") == (
        (FINDING_DEFECT, "unspecified"),
    )
    assert parse_review_reply("") == ()
    assert parse_review_reply("all good") == ()


def test_reviewer_approved_requires_the_exact_verdict_line() -> None:
    assert reviewer_approved("looks good\nAPPROVED\n")
    assert reviewer_approved("APPROVED")
    assert not reviewer_approved("approved (lowercase)")
    assert not reviewer_approved("i would APPROVED this")


def test_has_spec_drift_and_failure_code_follow_findings() -> None:
    defects: tuple[tuple[str, str], ...] = ((FINDING_DEFECT, "a"),)
    drift: tuple[tuple[str, str], ...] = ((FINDING_DEFECT, "a"), (FINDING_SPEC_DRIFT, "b"))
    assert has_spec_drift(defects) is False
    assert has_spec_drift(drift) is True
    assert review_failure_code_for(defects) == REASON_REVIEW_REJECTED
    assert review_failure_code_for(drift) == REASON_SPEC_DRIFT


def test_defect_feedback_renders_every_finding() -> None:
    feedback = defect_feedback(((FINDING_DEFECT, "x"), (FINDING_SPEC_DRIFT, "y")))
    assert feedback == ("DEFECT: x", "SPEC_DRIFT: y")


def test_gate_failure_feedback_lists_only_failed_gates() -> None:
    feedback = gate_failure_feedback(
        (("tests", True, ""), ("lint", False, "ruff exited 1"), ("typecheck", False, ""))
    )
    assert feedback == (
        "quality gate lint failed: ruff exited 1",
        "quality gate typecheck failed: no output",
    )


def test_summarize_gate_renders_the_evidence_line() -> None:
    assert summarize_gate("tests", True, "") == "gate tests: PASSED"
    assert summarize_gate("lint", False, "ruff exited 1") == (
        "gate lint: FAILED (ruff exited 1)"
    )


def test_repair_audit_delivery_id_is_unique_per_attempt() -> None:
    first = repair_audit_delivery_id("d", "GEN-52-v1", 1)
    assert first == "d#GEN-52-v1#REPAIRING#1"
    assert repair_audit_delivery_id("d", "GEN-52-v1", 2) != first
    with pytest.raises(ValueError, match="attempt"):
        repair_audit_delivery_id("d", "GEN-52-v1", 0)
    with pytest.raises(ValueError, match="blank"):
        repair_audit_delivery_id("", "GEN-52-v1", 1)


def test_reviewer_prompt_states_independence_and_verdict_format() -> None:
    prompt = build_reviewer_prompt(
        objective="Add independent gates",
        acceptance_criteria=("gates run", "drift blocked"),
        base_branch="main",
        branch_name="feat/gen-52-gates",
        exclusions=("no new dependencies",),
        constraints=("no auto merge",),
        gate_summaries=("gate tests: PASSED",),
    )
    assert "independent reviewer" in prompt
    assert "You are NOT the implementer" in prompt
    assert "Add independent gates" in prompt
    assert "- gates run" in prompt
    assert "- drift blocked" in prompt
    assert "- no new dependencies" in prompt
    assert "- no auto merge" in prompt
    assert "gate tests: PASSED" in prompt
    assert "DEFECT:" in prompt
    assert "SPEC_DRIFT:" in prompt
    assert "APPROVED" in prompt
    assert "no network access" in prompt
    assert "do not modify anything" in prompt


def test_agent_prompt_includes_repair_feedback_when_defects_present() -> None:
    prompt = build_agent_prompt(
        objective="Add independent gates",
        acceptance_criteria=("gates run",),
        base_branch="main",
        branch_name="feat/gen-52-gates",
        defects=("DEFECT: missing test",),
    )
    assert "Repair feedback" in prompt
    assert "- DEFECT: missing test" in prompt


def test_agent_prompt_omits_repair_section_without_defects() -> None:
    prompt = build_agent_prompt(
        objective="Add independent gates",
        acceptance_criteria=("gates run",),
        base_branch="main",
        branch_name="feat/gen-52-gates",
    )
    assert "Repair feedback" not in prompt


def test_pr_body_includes_verified_evidence_when_gates_ran() -> None:
    body = pr_body_for(
        "GEN-52",
        "Add independent gates",
        ("criterion",),
        gate_summaries=("gate tests: PASSED", "gate lint: FAILED (ruff exited 1)"),
    )
    assert "## Verified evidence" in body
    assert "- gate tests: PASSED" in body
    assert "- gate lint: FAILED (ruff exited 1)" in body


def test_pr_body_omits_evidence_section_without_gates() -> None:
    body = pr_body_for("GEN-52", "Add independent gates", ("criterion",))
    assert "## Verified evidence" not in body
