"""Tests for the coverage policy gate (TDD cycle C10)."""

from scripts.check_coverage import DEFAULT_POLICY, evaluate

CORE = "src/super_factory/domain/task_spec.py"
IMPORTANT = "src/super_factory/api/routes/health.py"


def _file_entry(
    percent_lines: float,
    percent_branches: float,
    num_statements: int = 10,
    num_branches: int = 5,
) -> dict[str, object]:
    covered_lines = round(num_statements * percent_lines / 100)
    covered_branches = round(num_branches * percent_branches / 100)
    return {
        "summary": {
            "num_statements": num_statements,
            "covered_lines": covered_lines,
            "num_branches": num_branches,
            "covered_branches": covered_branches,
        }
    }


def _report(files: dict[str, dict[str, object]]) -> dict[str, object]:
    return {"files": files}


def test_core_file_below_100_lines_is_violation() -> None:
    violations = evaluate(_report({CORE: _file_entry(90.0, 100.0)}))
    assert any("lines" in v and CORE in v for v in violations)


def test_core_file_below_100_branches_is_violation() -> None:
    violations = evaluate(_report({CORE: _file_entry(100.0, 75.0)}))
    assert any("branch" in v and CORE in v for v in violations)


def test_core_file_missing_from_report_is_violation() -> None:
    violations = evaluate(_report({}))
    assert any("not measured" in v and CORE in v for v in violations)


def test_core_file_at_100_passes() -> None:
    violations = evaluate(_report({CORE: _file_entry(100.0, 100.0)}))
    assert not any(CORE in v for v in violations)


def test_important_file_at_80_passes() -> None:
    violations = evaluate(_report({IMPORTANT: _file_entry(80.0, 80.0)}))
    assert not any(IMPORTANT in v for v in violations)


def test_important_file_below_80_is_violation() -> None:
    violations = evaluate(_report({IMPORTANT: _file_entry(70.0, 100.0)}))
    assert any(IMPORTANT in v for v in violations)


def test_important_file_missing_is_violation() -> None:
    violations = evaluate(_report({}))
    assert any("not measured" in v and IMPORTANT in v for v in violations)


def test_default_policy_has_three_tiers() -> None:
    assert set(DEFAULT_POLICY) == {"core", "important"}
    assert DEFAULT_POLICY["core"]["lines"] == 100.0
    assert DEFAULT_POLICY["core"]["branches"] == 100.0
    assert DEFAULT_POLICY["important"]["lines"] == 80.0
