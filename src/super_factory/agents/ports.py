"""Coding-agent ports (GEN-47).

``CodingAgent`` is the seam between the pipeline and any LLM coding agent
(Codex CLI in H2). Agents receive flattened, workflow-safe commands and
return records; transport-level outages surface as exceptions so Temporal's
retry policy handles them.
"""

from typing import Protocol

from super_factory.contracts.pipeline import AgentRunCommand, AgentRunRecord


class CodingAgent(Protocol):
    """Port for executing one approved coding task with an LLM agent."""

    async def run(self, command: AgentRunCommand) -> AgentRunRecord:
        """Execute the task and report the commands/tests/evidence trail."""
        ...
