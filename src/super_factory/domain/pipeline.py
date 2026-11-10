"""Domain rules for the H2 PR-production pipeline (GEN-47).

Pure functions only: deterministic naming and text builders consumed by the
pipeline activities. No I/O, no clocks, no framework imports.
"""

import re
import unicodedata

from super_factory.domain.task_spec import is_valid_issue_id

REASON_SPEC_SOURCE_UNAVAILABLE = "SPEC_SOURCE_UNAVAILABLE"
REASON_BUDGET_EXHAUSTED = "BUDGET_EXHAUSTED"
REASON_AGENT_FAILED = "AGENT_FAILED"
REASON_AGENT_BLOCKED = "AGENT_BLOCKED"
REASON_CHANGES_EMPTY = "CHANGES_EMPTY"
REASON_VERIFICATION_FAILED = "VERIFICATION_FAILED"
REASON_PUBLISH_FAILED = "PUBLISH_FAILED"

_BRANCH_PREFIX = "feat/"
_MAX_SLUG_LENGTH = 48
_DEFAULT_SLUG = "task"

_RUN_KEY_PATTERN = re.compile(r"^GEN-\d+-v\d+$")

_LINEAR_URL_TEMPLATE = "https://linear.app/genesisnavarra/issue/{issue_id}"


def run_key_for(issue_id: str, spec_version: int) -> str:
    """Deterministic run key: ``GEN-N-vM`` (one run per issue/spec version)."""
    if not is_valid_issue_id(issue_id):
        msg = f"issue_id {issue_id!r} must match the GEN-N format"
        raise ValueError(msg)
    if spec_version < 1:
        msg = "spec_version must be >= 1"
        raise ValueError(msg)
    return f"{issue_id}-v{spec_version}"


def is_valid_run_key(run_key: str) -> bool:
    """Return True for ``GEN-N-vM`` run keys."""
    return bool(_RUN_KEY_PATTERN.match(run_key))


def slugify(text: str) -> str:
    """ASCII, lowercase, dash-separated slug safe for git branch names."""
    decomposed = unicodedata.normalize("NFKD", text)
    ascii_only = decomposed.encode("ascii", "ignore").decode("ascii")
    lowered = ascii_only.lower()
    slug = re.sub(r"[^a-z0-9]+", "-", lowered)
    slug = re.sub(r"-+", "-", slug).strip("-")
    if not slug:
        return _DEFAULT_SLUG
    return slug[:_MAX_SLUG_LENGTH].rstrip("-")


def branch_name_for(issue_id: str, title: str) -> str:
    """Deterministic factory branch: ``feat/GEN-N-slug`` per repo conventions."""
    if not is_valid_issue_id(issue_id):
        msg = f"issue_id {issue_id!r} must match the GEN-N format"
        raise ValueError(msg)
    slug = slugify(title)
    return f"{_BRANCH_PREFIX}{issue_id.lower()}-{slug}"


def _short_objective(objective: str, limit: int = 72) -> str:
    collapsed = " ".join(objective.split())
    if len(collapsed) <= limit:
        return collapsed
    return collapsed[: limit - 1].rstrip() + "\u2026"


def pr_title_for(issue_id: str, objective: str) -> str:
    """Classic conventional-commit style PR title."""
    scope = issue_id.lower()
    return f"feat({scope}): {_short_objective(objective)}"


def commit_message_for(issue_id: str, objective: str) -> str:
    """Commit message produced on the factory branch."""
    return pr_title_for(issue_id, objective)


def linear_issue_url(
    issue_id: str, template: str = _LINEAR_URL_TEMPLATE
) -> str:
    """Link the produced PR back to its Linear issue."""
    if not is_valid_issue_id(issue_id):
        msg = f"issue_id {issue_id!r} must match the GEN-N format"
        raise ValueError(msg)
    if "{issue_id}" not in template:
        msg = "template must contain the {issue_id} placeholder"
        raise ValueError(msg)
    return template.format(issue_id=issue_id)


def pr_body_for(
    issue_id: str,
    objective: str,
    acceptance_criteria: tuple[str, ...],
    linear_template: str = _LINEAR_URL_TEMPLATE,
) -> str:
    """PR body linking the Linear issue and listing the accepted criteria."""
    lines: list[str] = [
        pr_title_for(issue_id, objective),
        "",
        f"**Linear issue:** {linear_issue_url(issue_id, linear_template)}",
        "",
        "## Acceptance criteria",
        "",
    ]
    lines.extend(f"- [x] {criterion}" for criterion in acceptance_criteria)
    lines.extend(
        (
            "",
            "---",
            "Produced automatically by the SF-Temporal-Python Software Factory "
            f"(run for {issue_id}). Human review required before merge.",
        )
    )
    return "\n".join(lines)


def build_agent_prompt(
    objective: str,
    acceptance_criteria: tuple[str, ...],
    base_branch: str,
    branch_name: str,
) -> str:
    """Deterministic prompt for the coding agent executed inside the sandbox."""
    criteria_lines = "\n".join(f"- {criterion}" for criterion in acceptance_criteria)
    return (
        "You are the coding agent of the SF-Temporal-Python Software Factory.\n"
        "Working directory: /workspace (repository mounted read-write).\n"
        f"Implement the task on the current branch ({branch_name}), based on "
        f"{base_branch}.\n"
        "\n"
        "Objective:\n"
        f"{objective.strip()}\n"
        "\n"
        "Acceptance criteria:\n"
        f"{criteria_lines}\n"
        "\n"
        "Hard rules:\n"
        "- The sandbox has no network access and receives no credentials.\n"
        "- Never read, modify or commit .env, credentials, tokens or secrets.\n"
        "- Run and pass the project tests before finishing.\n"
        "- Commit your changes with a clear conventional-commit message; "
        "never push to remotes.\n"
        "- Do not modify files outside /workspace."
    )


def pipeline_audit_delivery_id(delivery_id: str, run_key: str, phase: str) -> str:
    """Stable, per-phase audit id so retries never duplicate audit lines."""
    for part in (delivery_id, run_key, phase):
        if not part.strip():
            msg = "audit id parts must not be blank"
            raise ValueError(msg)
    return f"{delivery_id}#{run_key}#{phase}"
