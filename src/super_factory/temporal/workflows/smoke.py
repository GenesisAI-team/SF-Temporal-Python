"""SmokeWorkflow: minimal deterministic orchestration demo (GEN-17 bootstrap).

NOT the future IssueWorkflow (H1). Its only purpose is to prove that the
Temporal stack (client, worker, activities, replay) works end to end.
"""

from datetime import timedelta

from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    from super_factory.temporal.activities.smoke import EchoInput, echo_activity


@workflow.defn(name="SmokeWorkflow")
class SmokeWorkflow:
    """Run two echo activities sequentially and return their results."""

    @workflow.run
    async def run(self, message: str) -> list[str]:
        workflow_id = workflow.info().workflow_id
        results: list[str] = []
        for step in ("preflight", "record"):
            result = await workflow.execute_activity(
                echo_activity,
                EchoInput(workflow_id=workflow_id, step=step, message=message),
                start_to_close_timeout=timedelta(seconds=10),
            )
            results.append(result)
        return results
