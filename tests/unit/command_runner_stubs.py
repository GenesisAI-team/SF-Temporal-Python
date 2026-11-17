"""Shared command-runner stubs for adapter tests (unit, GEN-47)."""

from super_factory.process.ports import CommandOutcome, CommandRequest


class ScriptedRunner:
    """CommandRunner double: matches argv prefixes to scripted outcomes.

    Prefixes are matched left-to-right against ``request.argv`` so tests can
    discriminate docker run/exec, git verbs and gh subcommands without
    asserting full command lines. All requests are recorded in order.
    """

    def __init__(self) -> None:
        self.requests: list[CommandRequest] = []
        self.script: dict[tuple[str, ...], CommandOutcome] = {}
        self.stdin_seen: list[str | None] = []

    def on(
        self,
        prefix: tuple[str, ...],
        *,
        exit_code: int = 0,
        stdout_tail: str = "",
        stderr_tail: str = "",
        timed_out: bool = False,
    ) -> "ScriptedRunner":
        self.script[prefix] = CommandOutcome(
            exit_code=exit_code,
            stdout_tail=stdout_tail,
            stderr_tail=stderr_tail,
            timed_out=timed_out,
        )
        return self

    async def run(self, request: CommandRequest) -> CommandOutcome:
        self.requests.append(request)
        self.stdin_seen.append(request.stdin)
        for prefix, outcome in self.script.items():
            if tuple(request.argv[: len(prefix)]) == prefix:
                return outcome
        return CommandOutcome(exit_code=0)
