"""Real adapter: asyncio subprocess runner for ``CommandRunner`` (GEN-47).

Single production gateway for external processes (docker, git, gh). Output
is bounded to 4000-char tails so durable state never balloons; launches
fail explicitly with ``ProcessLaunchError``; timeouts kill the process and
report ``timed_out`` outcomes.
"""

import asyncio
import contextlib

from super_factory.process.ports import (
    CommandOutcome,
    CommandRequest,
    ProcessLaunchError,
)

_TAIL_LIMIT = 4000


def _tail(text: str) -> str:
    """Keep the most recent output, bounded, with a truncation marker."""
    if len(text) > _TAIL_LIMIT:
        return f"…(truncated)\n{text[-_TAIL_LIMIT:]}"
    return text


class SubprocessCommandRunner:
    """Real ``CommandRunner`` on top of asyncio subprocesses."""

    async def run(self, request: CommandRequest) -> CommandOutcome:
        argv = list(request.argv)
        env = dict(request.env) if request.env is not None else None
        try:
            proc = await asyncio.create_subprocess_exec(
                *argv,
                cwd=request.cwd,
                env=env,
                stdin=asyncio.subprocess.PIPE if request.stdin else None,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except OSError as exc:
            raise ProcessLaunchError(
                f"cannot launch {argv[0]}: {type(exc).__name__}"
            ) from exc
        stdin: bytes | None = request.stdin.encode("utf-8") if request.stdin else None
        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(input=stdin), timeout=request.timeout_seconds
            )
        except TimeoutError:
            await self._terminate(proc)
            return CommandOutcome(
                exit_code=None,
                stdout_tail="",
                stderr_tail="",
                timed_out=True,
            )
        return CommandOutcome(
            exit_code=proc.returncode,
            stdout_tail=_tail(stdout.decode("utf-8", errors="replace")),
            stderr_tail=_tail(stderr.decode("utf-8", errors="replace")),
        )

    @staticmethod
    async def _terminate(proc: asyncio.subprocess.Process) -> None:
        with contextlib.suppress(ProcessLookupError):
            proc.kill()
        await proc.wait()
