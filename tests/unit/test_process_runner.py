"""Tests for the process-execution port + real subprocess runner (GEN-47).

Acceptance: the runner captures exit codes/stdout/stderr tails, enforces
timeouts (killed process, timed_out outcome), accepts cwd/env overrides and
fails explicitly (ProcessLaunchError) when the binary does not exist.
"""

import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

from super_factory.process.ports import (
    CommandOutcome,
    CommandRequest,
    ProcessLaunchError,
)
from super_factory.process.subprocess import SubprocessCommandRunner


@pytest.fixture
def runner() -> SubprocessCommandRunner:
    return SubprocessCommandRunner()


def _python(*code: str) -> tuple[str, str]:
    return (sys.executable, "-c", "; ".join(code))


async def test_runner_captures_exit_code_and_output(runner: SubprocessCommandRunner) -> None:
    argv = _python("print('out-ok')", "import sys; sys.stderr.write('err-ok')")
    outcome = await runner.run(CommandRequest(argv=argv, timeout_seconds=30))
    assert isinstance(outcome, CommandOutcome)
    assert outcome.exit_code == 0
    assert not outcome.timed_out
    assert "out-ok" in outcome.stdout_tail
    assert "err-ok" in outcome.stderr_tail


async def test_runner_reports_nonzero_exit_codes(runner: SubprocessCommandRunner) -> None:
    argv = _python("import sys; sys.exit(3)")
    outcome = await runner.run(CommandRequest(argv=argv, timeout_seconds=30))
    assert outcome.exit_code == 3


async def test_runner_times_out_and_kills(runner: SubprocessCommandRunner) -> None:
    argv = _python("import time; time.sleep(5)")
    outcome = await runner.run(CommandRequest(argv=argv, timeout_seconds=0.5))
    assert outcome.timed_out
    assert outcome.exit_code is None


async def test_runner_cwd_overrides_working_directory(
    runner: SubprocessCommandRunner, tmp_path: Path
) -> None:
    argv = _python("import os; print(os.path.basename(os.getcwd()))")
    outcome = await runner.run(CommandRequest(argv=argv, cwd=str(tmp_path), timeout_seconds=30))
    assert outcome.exit_code == 0
    assert tmp_path.name in outcome.stdout_tail


async def test_runner_rejects_blank_cwd(runner: SubprocessCommandRunner) -> None:
    with pytest.raises(ValidationError):
        CommandRequest(argv=("python",), cwd="   ")
    with pytest.raises(ValidationError):
        CommandRequest(argv=("python", "  "))


async def test_runner_truncates_long_output_to_bounded_tails(
    runner: SubprocessCommandRunner,
) -> None:
    argv = _python("print('x' * 6000)")
    outcome = await runner.run(CommandRequest(argv=argv, timeout_seconds=30))
    assert outcome.exit_code == 0
    assert "truncated" in outcome.stdout_tail
    assert len(outcome.stdout_tail) < 4500


async def test_runner_env_replaces_process_env(
    runner: SubprocessCommandRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SF_PROBE_FROM_PARENT", "parent-value")
    code = (
        "import os; "
        "print(os.environ.get('SF_PROBE_FROM_PARENT'), "
        "os.environ.get('SF_PROBE_ONLY_CHILD'))"
    )
    argv = _python(code)
    inherited = await runner.run(CommandRequest(argv=argv, timeout_seconds=30))
    assert "parent-value" in inherited.stdout_tail
    explicit = await runner.run(
        CommandRequest(
            argv=argv,
            env={"SF_PROBE_ONLY_CHILD": "child-value"},
            timeout_seconds=30,
        )
    )
    assert "SF_PROBE_FROM_PARENT" not in explicit.stdout_tail
    assert "child-value" in explicit.stdout_tail


async def test_runner_transports_stdin_payload(
    runner: SubprocessCommandRunner,
) -> None:
    argv = _python("import sys; print(sys.stdin.read().strip() + '-echoed')")
    outcome = await runner.run(
        CommandRequest(argv=argv, stdin="payload", timeout_seconds=30)
    )
    assert outcome.exit_code == 0
    assert "payload-echoed" in outcome.stdout_tail


async def test_runner_launch_failure_is_explicit(runner: SubprocessCommandRunner) -> None:
    with pytest.raises(ProcessLaunchError, match="cannot launch"):
        await runner.run(
            CommandRequest(
                argv=("definitely-missing-binary-xyz", "--version"), timeout_seconds=5
            )
        )
