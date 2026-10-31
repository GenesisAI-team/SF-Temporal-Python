"""Logical task queue names for the Software Factory (GEN-17).

Workers are separated by concern so coding/verification can scale and be
locked down independently of orchestration (ADR-0004).
"""

TASK_QUEUE_ORCHESTRATION = "factory-orchestration"
TASK_QUEUE_CODING = "factory-coding"
TASK_QUEUE_VERIFICATION = "factory-verification"
TASK_QUEUE_INTEGRATIONS = "factory-integrations"

ALL_TASK_QUEUES: tuple[str, ...] = (
    TASK_QUEUE_ORCHESTRATION,
    TASK_QUEUE_CODING,
    TASK_QUEUE_VERIFICATION,
    TASK_QUEUE_INTEGRATIONS,
)
