"""Temporal SDK adapter: unique durable start-or-recover of IssueWorkflow.

The FastAPI layer never imports the workflow classes directly; it consumes
this port. Idempotency is durable: the run id (``issue-<GEN-N>``) is stable
and ``REJECT_DUPLICATE`` guarantees a second event for the same issue
reuses/describes the same execution instead of starting a second one
(ADR-0006).
"""

from temporalio.client import Client
from temporalio.common import WorkflowIDReusePolicy
from temporalio.exceptions import WorkflowAlreadyStartedError

from super_factory.contracts.workflow_io import IssueWorkflowInput, WorkflowStartResult
from super_factory.temporal.workflows.issue import IssueWorkflow


class IssueWorkflowStarter:
    """Start-or-recover adapter bound to one Temporal client and task queue."""

    def __init__(self, client: Client, task_queue: str) -> None:
        self._client = client
        self._task_queue = task_queue

    @classmethod
    async def connect(
        cls, *, address: str, namespace: str, task_queue: str
    ) -> "IssueWorkflowStarter":
        """Connect a client and return the ready starter."""
        return cls(client=await Client.connect(address, namespace=namespace), task_queue=task_queue)

    async def start_or_recover(self, data: IssueWorkflowInput) -> WorkflowStartResult:
        """Create the issue run once; later deliveries recover the same run."""
        workflow_id = f"issue-{data.issue_id}"
        try:
            handle = await self._client.start_workflow(
                IssueWorkflow.run,
                data,
                id=workflow_id,
                task_queue=self._task_queue,
                id_reuse_policy=WorkflowIDReusePolicy.REJECT_DUPLICATE,
                memo={
                    "issue_id": data.issue_id,
                    "repository": data.repository,
                    "workflow_state": "PENDING",
                },
            )
            description = await handle.describe()
            started = True
        except WorkflowAlreadyStartedError:
            description = await self._client.get_workflow_handle(workflow_id).describe()
            started = False
        return WorkflowStartResult(
            workflow_id=workflow_id,
            run_id=description.run_id,
            started=started,
        )
