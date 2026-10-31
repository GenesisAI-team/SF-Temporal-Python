"""Coverage policy gate: per-file thresholds, no global averages (GEN-14/GEN-17).

Reads the JSON report produced by `coverage json` and fails when a CORE file
is not at 100% lines AND branches, or an IMPORTANT file is below 80%, or a
critical file was never measured (hidden files are treated as violations).

Usage:
    uv run coverage run -m pytest && uv run coverage json -o coverage.json
    uv run python -m scripts.check_coverage
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

_SRC = "src/super_factory/"

Policy = dict[str, dict[str, float]]

DEFAULT_POLICY: Policy = {
    "core": {
        "lines": 100.0,
        "branches": 100.0,
    },
    "important": {
        "lines": 80.0,
        "branches": 80.0,
    },
}

CORE_FILES: tuple[str, ...] = (
    f"{_SRC}domain/task_spec.py",
    f"{_SRC}contracts/approved_task.py",
    f"{_SRC}temporal/workflows/smoke.py",
)

IMPORTANT_FILES: tuple[str, ...] = (
    f"{_SRC}config/settings.py",
    f"{_SRC}api/app.py",
    f"{_SRC}api/routes/health.py",
    f"{_SRC}api/webhooks/linear.py",
    f"{_SRC}temporal/activities/smoke.py",
    f"{_SRC}temporal/workers/factory_worker.py",
)


def _find_entry(files: dict[str, Any], rel_path: str) -> dict[str, Any] | None:
    """Locate a file entry by posix-relative suffix (report paths vary by OS)."""
    wanted = rel_path.replace("\\", "/")
    for key, entry in files.items():
        normalized = key.replace("\\", "/")
        if normalized.endswith(wanted):
            return entry
    return None


def _percentages(entry: dict[str, Any]) -> tuple[float, float]:
    """Return (lines_pct, branches_pct) computed from raw counts.

    Uses counts instead of percentage fields so the gate does not depend on
    coverage.py's JSON schema naming. A file with zero branches has vacuous
    branch coverage (100%).
    """
    summary: dict[str, Any] = entry.get("summary", {})
    num_statements = int(summary.get("num_statements", 0))
    covered_lines = int(summary.get("covered_lines", 0))
    num_branches = int(summary.get("num_branches", 0))
    covered_branches = int(summary.get("covered_branches", 0))

    lines_pct = (covered_lines / num_statements * 100) if num_statements else 100.0
    branches_pct = (covered_branches / num_branches * 100) if num_branches else 100.0
    return lines_pct, branches_pct


def evaluate(
    report: dict[str, Any],
    policy: Policy = DEFAULT_POLICY,
    core_files: tuple[str, ...] = CORE_FILES,
    important_files: tuple[str, ...] = IMPORTANT_FILES,
) -> list[str]:
    """Return a list of policy violations (empty when the report is compliant)."""
    violations: list[str] = []
    files: dict[str, Any] = report.get("files", {})

    tiers: list[tuple[str, tuple[str, ...]]] = [
        ("core", core_files),
        ("important", important_files),
    ]
    for tier, paths in tiers:
        thresholds = policy[tier]
        for rel_path in paths:
            entry = _find_entry(files, rel_path)
            if entry is None:
                violations.append(f"{rel_path}: [{tier}] file not measured (hidden?)")
                continue
            pct_lines, pct_branches = _percentages(entry)
            if pct_lines < thresholds["lines"]:
                violations.append(
                    f"{rel_path}: [{tier}] lines {pct_lines:.1f}% < {thresholds['lines']:.0f}%"
                )
            if pct_branches < thresholds["branches"]:
                violations.append(
                    f"{rel_path}: [{tier}] branches {pct_branches:.1f}% "
                    f"< {thresholds['branches']:.0f}%"
                )
    return violations


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Per-file coverage policy gate.")
    parser.add_argument(
        "--coverage-file",
        default="coverage.json",
        help="Path to the JSON report from `coverage json`",
    )
    args = parser.parse_args(argv)

    path = Path(args.coverage_file)
    if not path.exists():
        print(f"coverage file not found: {path}", file=sys.stderr)
        return 2

    report: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    violations = evaluate(report)
    if violations:
        print("COVERAGE POLICY VIOLATIONS:", file=sys.stderr)
        for violation in violations:
            print(f"  - {violation}", file=sys.stderr)
        return 1

    print("coverage policy OK (per-file 100/80)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
