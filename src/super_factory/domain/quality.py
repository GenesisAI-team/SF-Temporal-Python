"""Domain rules for the H3 quality gates, independent review and repair (GEN-52).

Pure functions only (same discipline as ``domain/pipeline.py``): the
independent gate-suite definition, the reviewer verdict parsing, the repair
feedback rendering and the per-attempt repair audit ids. No I/O, no clocks,
no framework imports.
"""

from dataclasses import dataclass

REASON_GATE_FAILED = "GATE_FAILED"
REASON_SPEC_DRIFT = "SPEC_DRIFT"
REASON_REVIEW_REJECTED = "REVIEW_REJECTED"
REASON_REVIEW_FAILED = "REVIEW_FAILED"
REASON_REPAIR_BUDGET_EXHAUSTED = "REPAIR_BUDGET_EXHAUSTED"

FINDING_DEFECT = "DEFECT"
FINDING_SPEC_DRIFT = "SPEC_DRIFT"

_DEFECT_PREFIX = "DEFECT:"
_DRIFT_PREFIX = "SPEC_DRIFT:"
_VERDICT_LINE = "APPROVED"
_UNSPECIFIED_DETAIL = "unspecified"


@dataclass(frozen=True)
class GateDefinition:
    """One independent quality gate: a name plus its ordered argv steps."""

    name: str
    steps: tuple[tuple[str, ...], ...]

    def __post_init__(self) -> None:
        if not self.name.strip():
            msg = "gate name must not be blank"
            raise ValueError(msg)
        if not self.steps:
            msg = "gate steps must not be empty"
            raise ValueError(msg)
        for step in self.steps:
            if not step or any(not item.strip() for item in step):
                msg = "gate steps must be non-empty argv without blank items"
                raise ValueError(msg)


def default_gate_suite() -> tuple[GateDefinition, ...]:
    """The repository's own checks as independent gates (no shell chaining)."""
    return (
        GateDefinition(name="tests", steps=(("uv", "run", "pytest", "-q"),)),
        GateDefinition(name="lint", steps=(("uv", "run", "ruff", "check", "."),)),
        GateDefinition(name="typecheck", steps=(("uv", "run", "mypy", "src"),)),
    )


def summarize_gate(name: str, passed: bool, failure_detail: str) -> str:
    """One-line gate evidence summary for review context and the PR body."""
    if passed:
        return f"gate {name}: PASSED"
    detail = failure_detail.strip() or "no output"
    return f"gate {name}: FAILED ({detail})"


def gate_failure_feedback(
    gates: tuple[tuple[str, bool, str], ...],
) -> tuple[str, ...]:
    """Repair feedback lines for every failed gate: (name, passed, failure_detail)."""
    return tuple(
        f"quality gate {name} failed: {detail.strip() or 'no output'}"
        for name, passed, detail in gates
        if not passed
    )


def parse_review_reply(reply: str) -> tuple[tuple[str, str], ...]:
    """Deterministic findings: one (kind, detail) pair per prefixed line, in order.

    ``DEFECT:``/``SPEC_DRIFT:`` prefixed lines become findings; every other
    line is reviewer chatter. A prefixed line without detail reports
    ``unspecified`` so the finding can never be silently dropped.
    """
    findings: list[tuple[str, str]] = []
    for line in reply.splitlines():
        stripped = line.strip()
        if stripped.startswith(_DEFECT_PREFIX):
            kind = FINDING_DEFECT
            detail = stripped[len(_DEFECT_PREFIX) :].strip()
        elif stripped.startswith(_DRIFT_PREFIX):
            kind = FINDING_SPEC_DRIFT
            detail = stripped[len(_DRIFT_PREFIX) :].strip()
        else:
            continue
        findings.append((kind, detail or _UNSPECIFIED_DETAIL))
    return tuple(findings)


def reviewer_approved(reply: str) -> bool:
    """True only when some line is exactly the APPROVED verdict."""
    return any(line.strip() == _VERDICT_LINE for line in reply.splitlines())


def has_spec_drift(findings: tuple[tuple[str, str], ...]) -> bool:
    """True when any finding reports a scope drift."""
    return any(kind == FINDING_SPEC_DRIFT for kind, _ in findings)


def review_failure_code_for(findings: tuple[tuple[str, str], ...]) -> str:
    """SPEC_DRIFT takes precedence over plain REVIEW_REJECTED defects."""
    if has_spec_drift(findings):
        return REASON_SPEC_DRIFT
    return REASON_REVIEW_REJECTED


def defect_feedback(findings: tuple[tuple[str, str], ...]) -> tuple[str, ...]:
    """Repair feedback lines for review findings."""
    return tuple(f"{kind}: {detail}" for kind, detail in findings)


def repair_audit_delivery_id(delivery_id: str, run_key: str, attempt: int) -> str:
    """Stable per-attempt repair audit id so retries never duplicate lines."""
    for part in (delivery_id, run_key):
        if not part.strip():
            msg = "audit id parts must not be blank"
            raise ValueError(msg)
    if attempt < 1:
        msg = "attempt must be >= 1"
        raise ValueError(msg)
    return f"{delivery_id}#{run_key}#REPAIRING#{attempt}"


def _render_bullets(title: str, items: tuple[str, ...]) -> str:
    """Render a titled bullet list, or ``""`` when there is nothing to list."""
    if not items:
        return ""
    lines = "\n".join(f"- {item}" for item in items)
    return f"{title}:\n{lines}"


def build_reviewer_prompt(
    objective: str,
    acceptance_criteria: tuple[str, ...],
    base_branch: str,
    branch_name: str,
    exclusions: tuple[str, ...] = (),
    constraints: tuple[str, ...] = (),
    gate_summaries: tuple[str, ...] = (),
) -> str:
    """Deterministic prompt for the independent reviewer session.

    The reviewer judges the produced changes against the approved scope
    (objective, criteria, exclusions, constraints) plus the evidence of the
    independently executed quality gates, and answers in the strict verdict
    format parsed by :func:`parse_review_reply`.
    """
    criteria_lines = "\n".join(f"- {criterion}" for criterion in acceptance_criteria)
    scope_block = "".join(
        f"\n{section}\n"
        for section in (
            _render_bullets("Exclusions (violations are SPEC_DRIFT)", exclusions),
            _render_bullets("Constraints (violations are SPEC_DRIFT)", constraints),
            _render_bullets(
                "Quality gates already executed independently", gate_summaries
            ),
        )
        if section
    )
    return (
        "You are the independent reviewer of the SF-Temporal-Python Software Factory.\n"
        "You are NOT the implementer: judge the changes with the approved scope only.\n"
        "Working directory: /workspace (repository mounted read-only for review).\n"
        f"Review the changes on the current branch ({branch_name}) against "
        f"{base_branch} (inspect the diff and the changed files).\n"
        "\n"
        "Objective:\n"
        f"{objective.strip()}\n"
        "\n"
        "Approved acceptance criteria:\n"
        f"{criteria_lines}\n"
        f"{scope_block}"
        "\n"
        "Verdict format (exactly one of):\n"
        "- APPROVED (a single line with only this word, when everything matches)\n"
        "- DEFECT: <detail> (one line per implementation defect)\n"
        "- SPEC_DRIFT: <detail> (one line per change outside or against the approved scope)\n"
        "\n"
        "Hard rules:\n"
        "- The sandbox has no network access and receives no credentials.\n"
        "- Never read, modify or commit .env, credentials, tokens or secrets.\n"
        "- do not modify anything: report, never fix.\n"
    )
