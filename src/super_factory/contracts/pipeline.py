"""H2 pipeline-plane contracts (GEN-47).

Frozen plain dataclasses: these types cross the Temporal activity boundary
endpoint -> activity -> workflow, so they follow the H1 rule of dataclasses
for the workflow plane (the default Temporal data converter serializes
dataclasses natively) while Pydantic contracts handle validation.
Every outcome contract carries the fail-fast ok/failed axis: an ok object
carries the payload, a failure object always carries a ``failure_code`` and
``failure_detail`` from the stable domain reason codes
(``super_factory.domain.pipeline``).
"""

from dataclasses import dataclass

from super_factory.domain.pipeline import is_valid_run_key, run_key_for
from super_factory.domain.task_spec import all_non_empty, is_non_empty, is_valid_issue_id


@dataclass(frozen=True)
class PlanRunCommand:
    """Input of ``plan_run_activity``: what is being planned and where."""

    issue_id: str
    repository: str
    base_branch: str
    title: str


@dataclass(frozen=True)
class TaskSpecQuery:
    """Query to the ``TaskSpecSource`` port inside the planning activity."""

    issue_id: str
    repository: str
    base_branch: str
    title: str


@dataclass(frozen=True)
class TaskPlan:
    """Output of the planning phase: approved spec + deterministic names.

    ``ok=True`` carries the flattened approved specification (dataclass
    plane) plus the deterministic ``run_key``/``branch_name``. ``ok=False``
    carries ``failure_code``/``failure_detail`` instead.
    """

    ok: bool
    issue_id: str = ""
    spec_version: int = 0
    objective: str = ""
    acceptance_criteria: tuple[str, ...] = ()
    dependencies: tuple[str, ...] = ()
    exclusions: tuple[str, ...] = ()
    constraints: tuple[str, ...] = ()
    run_key: str = ""
    branch_name: str = ""
    failure_code: str = ""
    failure_detail: str = ""

    def __post_init__(self) -> None:
        if self.ok:
            ok_spec = (
                is_valid_issue_id(self.issue_id)
                and self.spec_version >= 1
                and is_non_empty(self.objective)
                and all_non_empty(list(self.acceptance_criteria))
            )
            if not ok_spec:
                msg = "ok plans must carry the full approved specification"
                raise ValueError(msg)
            if not is_valid_run_key(self.run_key):
                msg = "ok plans must carry a valid run key (GEN-N-vM)"
                raise ValueError(msg)
            if self.run_key != run_key_for(self.issue_id, self.spec_version):
                msg = "run_key must be derived from issue_id and spec_version"
                raise ValueError(msg)
            if not self.branch_name.strip():
                msg = "ok plans must carry a branch name"
                raise ValueError(msg)
            return
        if not (self.failure_code and self.failure_detail):
            msg = "failure plans must carry failure_code and failure_detail"
            raise ValueError(msg)


@dataclass(frozen=True)
class PrepareRunCommand:
    """Input of ``prepare_run_activity``: workspace + budget + ledger bookkeeping."""

    issue_id: str
    repository: str
    spec_version: int
    run_key: str
    branch_name: str
    base_branch: str


@dataclass(frozen=True)
class RunPreparation:
    """Output of the preparation phase."""

    ok: bool
    workspace_path: str = ""
    branch_existed: bool = False
    budget_remaining: int = 0
    failure_code: str = ""
    failure_detail: str = ""

    def __post_init__(self) -> None:
        if self.ok:
            if not self.workspace_path.strip():
                msg = "ok preparations must carry the workspace_path"
                raise ValueError(msg)
            if self.failure_code:
                msg = "ok preparations must not carry a failure code"
                raise ValueError(msg)
            return
        if not (self.failure_code and self.failure_detail):
            msg = "failure preparations must carry failure_code and failure_detail"
            raise ValueError(msg)


@dataclass(frozen=True)
class AgentRunCommand:
    """Input of ``run_coding_agent_activity`` (spec flattened for the workflow)."""

    issue_id: str
    repository: str
    spec_version: int
    run_key: str
    branch_name: str
    base_branch: str
    objective: str
    acceptance_criteria: tuple[str, ...]
    exclusions: tuple[str, ...]
    constraints: tuple[str, ...]
    dependencies: tuple[str, ...]
    workspace_path: str


@dataclass(frozen=True)
class AgentRunRecord:
    """Output of the implementation phase (commands/tests/evidence trail)."""

    completed: bool
    commands: tuple[str, ...] = ()
    evidence: tuple[str, ...] = ()
    failure_code: str = ""
    failure_detail: str = ""

    def __post_init__(self) -> None:
        if self.completed and self.failure_code:
            msg = "completed runs must not carry a failure_code"
            raise ValueError(msg)
        if not self.completed and not (self.failure_code and self.failure_detail):
            msg = "failed runs must carry failure_code and failure_detail"
            raise ValueError(msg)


@dataclass(frozen=True)
class VerificationCommand:
    """Input of ``verify_run_activity``."""

    issue_id: str
    run_key: str
    workspace_path: str
    acceptance_criteria: tuple[str, ...]


@dataclass(frozen=True)
class VerificationOutcome:
    """Output of the verification phase."""

    passed: bool
    commands: tuple[str, ...] = ()
    evidence: tuple[str, ...] = ()
    failure_code: str = ""
    failure_detail: str = ""

    def __post_init__(self) -> None:
        if self.passed:
            return
        if not (self.failure_code and self.failure_detail):
            msg = "failed verifications must carry failure_code and failure_detail"
            raise ValueError(msg)


@dataclass(frozen=True)
class PublishCommand:
    """Input of ``publish_pr_activity``."""

    issue_id: str
    repository: str
    run_key: str
    branch_name: str
    base_branch: str
    workspace_path: str
    objective: str
    acceptance_criteria: tuple[str, ...]
    linear_url_template: str


@dataclass(frozen=True)
class PublicationOutcome:
    """Output of the publication phase (no duplicates: reuse existing PRs)."""

    published: bool
    pr_url: str = ""
    pr_number: int | None = None
    updated_existing: bool = False
    failure_code: str = ""
    failure_detail: str = ""

    def __post_init__(self) -> None:
        if self.published:
            if not self.pr_url.strip() or self.pr_number is None:
                msg = "published outcomes must carry pr_url and pr_number"
                raise ValueError(msg)
            return
        if self.updated_existing:
            msg = "failed publications must not set updated_existing"
            raise ValueError(msg)
        if not (self.failure_code and self.failure_detail):
            msg = "failed publications must carry failure_code and failure_detail"
            raise ValueError(msg)
