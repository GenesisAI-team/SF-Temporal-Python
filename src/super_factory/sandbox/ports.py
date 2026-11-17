"""Sandbox ports: isolated, disposable execution runtimes (GEN-47).

The pipeline never executes agent work on the worker host. Every sandbox
session runs inside an ephemeral, restricted boundary provided by a
``SandboxRuntime``; the Docker adapter is the shipped implementation,
tests substitute fakes.
"""

from typing import Protocol

from super_factory.contracts.sandboxing import (
    SandboxCommand,
    SandboxCommandOutcome,
    SandboxInstance,
    SandboxSpec,
)


class SandboxUnavailable(RuntimeError):
    """The sandbox runtime is unreachable or transiently failed (retryable)."""


class SandboxCommandRejected(ValueError):
    """One sandbox command violated the safety deny list (never executed)."""

    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        self.detail = detail
        msg = f"command rejected by sandbox safety policy: {code} ({detail})"
        super().__init__(msg)


class SandboxRuntime(Protocol):
    """Port for ephemeral, isolation-bounded execution environments."""

    async def ensure_sandbox(self, spec: SandboxSpec) -> SandboxInstance:
        """Create (or reuse) the sandbox for one run specification."""
        ...

    async def run_in_sandbox(
        self, instance: SandboxInstance, command: SandboxCommand
    ) -> SandboxCommandOutcome:
        """Execute one command inside the sandbox and return its outcome."""
        ...

    async def cleanup(self, instance: SandboxInstance) -> None:
        """Dispose the sandbox (best effort, safe to call repeatedly)."""
        ...
