"""H3 quality/review contracts (GEN-52).

Frozen plain dataclasses (workflow plane, ADR-0008 convention): these types
cross the Temporal activity boundary. The ok/failed axis follows
``contracts/pipeline.py``: an ok object carries the payload, a failure
object always carries ``failure_code``/``failure_detail`` from the stable
reason codes of ``super_factory.domain.quality``.
"""

from dataclasses import dataclass

from super_factory.domain.pipeline import is_valid_run_key
from super_factory.domain.quality import (
    FINDING_DEFECT,
    FINDING_SPEC_DRIFT,
    REASON_REVIEW_FAILED,
    REASON_REVIEW_REJECTED,
    REASON_SPEC_DRIFT,
)
from super_factory.domain.task_spec import (
    all_non_empty,
    is_non_empty,
    is_valid_issue_id,
)


@dataclass(frozen=True)
class GateOutcome:
    """Outcome of one independent quality gate (all of its steps)."""

    gate: str
    passed: bool
    commands: tuple[str, ...] = ()
    evidence: tuple[str, ...] = ()
    failure_code: str = ""
    failure_detail: str = ""

    def __post_init__(self) -> None:
        if not self.gate.strip():
            msg = "gate name must not be blank"
            raise ValueError(msg)
        if self.passed:
            if self.failure_code or self.failure_detail:
                msg = "ok gate outcomes must not carry failure codes"
                raise ValueError(msg)
            return
        if not (self.failure_code and self.failure_detail):
            msg = "failed gate outcomes must carry failure_code and failure_detail"
            raise ValueError(msg)


@dataclass(frozen=True)
class ReviewFinding:
    """One finding of the independent reviewer (defect or scope drift)."""

    kind: str
    detail: str

    def __post_init__(self) -> None:
        if self.kind not in (FINDING_DEFECT, FINDING_SPEC_DRIFT):
            msg = "finding kind must be DEFECT or SPEC_DRIFT"
            raise ValueError(msg)
        if not self.detail.strip():
            msg = "finding detail must not be blank"
            raise ValueError(msg)


@dataclass(frozen=True)
class ReviewCommand:
    """Input of ``review_run_activity``: what the reviewer judges and where."""

    issue_id: str
    run_key: str
    workspace_path: str
    branch_name: str
    base_branch: str
    objective: str
    acceptance_criteria: tuple[str, ...]
    exclusions: tuple[str, ...] = ()
    constraints: tuple[str, ...] = ()
    gate_summaries: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not is_valid_issue_id(self.issue_id):
            msg = f"issue_id {self.issue_id!r} must match the GEN-N format"
            raise ValueError(msg)
        if not is_valid_run_key(self.run_key):
            msg = f"run_key {self.run_key!r} must match GEN-N-vM"
            raise ValueError(msg)
        if not self.workspace_path.strip():
            msg = "workspace_path must not be blank"
            raise ValueError(msg)
        if not (self.branch_name.strip() and self.base_branch.strip()):
            msg = "branch names must not be blank"
            raise ValueError(msg)
        if not is_non_empty(self.objective):
            msg = "objective must not be blank"
            raise ValueError(msg)
        if not self.acceptance_criteria or not all_non_empty(
            list(self.acceptance_criteria)
        ):
            msg = "acceptance_criteria must be non-empty and without blanks"
            raise ValueError(msg)
        if not all_non_empty(list(self.exclusions)) or not all_non_empty(
            list(self.constraints)
        ):
            msg = "exclusions/constraints must not contain blank items"
            raise ValueError(msg)
        if not all_non_empty(list(self.gate_summaries)):
            msg = "gate_summaries must not contain blank items"
            raise ValueError(msg)


@dataclass(frozen=True)
class ReviewOutcome:
    """Output of the independent review phase.

    ``approved=True`` is clean (no findings, no failure). ``approved=False``
    carries exactly one of: ``SPEC_DRIFT`` (with ``spec_drift=True`` and at
    least one drift finding), ``REVIEW_REJECTED`` (defect findings only,
    repairable) or ``REVIEW_FAILED`` (verdictless review, not repairable).
    """

    approved: bool
    findings: tuple[ReviewFinding, ...] = ()
    spec_drift: bool = False
    failure_code: str = ""
    failure_detail: str = ""

    def __post_init__(self) -> None:
        if self.approved:
            if self.findings or self.spec_drift or self.failure_code or self.failure_detail:
                msg = "approved reviews must be clean"
                raise ValueError(msg)
            return
        if not (self.failure_code and self.failure_detail):
            msg = "rejected reviews must carry failure_code and failure_detail"
            raise ValueError(msg)
        if self.spec_drift != (self.failure_code == REASON_SPEC_DRIFT):
            msg = "SPEC_DRIFT flag must pair with the SPEC_DRIFT failure code"
            raise ValueError(msg)
        if self.failure_code == REASON_SPEC_DRIFT:
            if not any(finding.kind == FINDING_SPEC_DRIFT for finding in self.findings):
                msg = "SPEC_DRIFT outcomes must carry at least one SPEC_DRIFT finding"
                raise ValueError(msg)
        elif self.failure_code == REASON_REVIEW_REJECTED:
            if not self.findings or any(
                finding.kind != FINDING_DEFECT for finding in self.findings
            ):
                msg = (
                    "REVIEW_REJECTED must carry findings and they must all be DEFECT "
                    "(SPEC_DRIFT requires its own code)"
                )
                raise ValueError(msg)
        elif self.failure_code == REASON_REVIEW_FAILED and self.findings:
            msg = "REVIEW_FAILED must be verdictless (no findings)"
            raise ValueError(msg)
