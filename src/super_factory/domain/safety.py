"""Pure command-safety rules for the H2 sandbox and agent path (GEN-47).

The sandbox blocks commands with destructive or credential-threatening
effects before execution. The guard is a pure deny-list over the command
text (token-aware) so both the Docker adapter and any future runtime share
one source of truth.
"""

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class ForbiddenCommand:
    """One matched dangerous command pattern."""

    code: str
    detail: str


_PATTERNS: tuple[tuple[str, str], ...] = (
    (
        "DESTRUCTIVE_REMOVAL",
        r"rm\s+-\w*[rf]\w*\s+(/|~|~/*|\*|\./\*)",
    ),
    (
        "GIT_FORCE_PUSH",
        r"git\s+push\s+.*(-f\b|--force\b|--force-with-lease\b)",
    ),
    (
        "PRIVILEGE_ESCALATION",
        r"(^|[\s;|&])(sudo|su)\b",
    ),
    (
        "HOST_POWER_CONTROL",
        r"\b(shutdown|reboot|poweroff|halt)\b",
    ),
    (
        "FILESYSTEM_FORMAT",
        r"\bmkfs(\.\w+)?\b",
    ),
    (
        "RAW_DEVICE_WRITE",
        r"\bdd\b[^\n]*\bof=/dev/",
    ),
    (
        "PERMISSION_OPEN",
        r"chmod\s+777\s+(/|\*|~)",
    ),
    (
        "REMOTE_CODE_EXECUTION",
        r"\b(curl|wget)\b[^\n|]*\|\s*(sudo\s+)?((ba|z)?sh|python)\b",
    ),
    (
        "FORK_BOMB",
        r":[(]\s*[)]\s*[{][^}]*[}]\s*[;]?\s*:",
    ),
    (
        "MOUNT_MANIPULATION",
        r"(^|[\s;|&])(u?mount)\b",
    ),
)

_COMPILED: tuple[tuple[str, re.Pattern[str]], ...] = tuple(
    (code, re.compile(pattern)) for code, pattern in _PATTERNS
)


def find_forbidden_command(command: str | tuple[str, ...]) -> ForbiddenCommand | None:
    """Return the first matched dangerous pattern, or None when clean.

    Tuple commands are joined with spaces before scanning; compound commands
    that chain several steps through shell operators are scanned in full.
    """
    joined = " ".join(command) if isinstance(command, tuple) else command
    if not joined.strip():
        return None
    for code, compiled in _COMPILED:
        if compiled.search(joined):
            return ForbiddenCommand(code=code, detail=code)
    return None
