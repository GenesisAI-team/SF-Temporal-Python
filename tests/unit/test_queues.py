"""Tests for task queue constants (TDD cycle C9)."""

from super_factory.temporal.workers.queues import (
    ALL_TASK_QUEUES,
    TASK_QUEUE_CODING,
    TASK_QUEUE_INTEGRATIONS,
    TASK_QUEUE_ORCHESTRATION,
    TASK_QUEUE_VERIFICATION,
)


def test_four_task_queues_are_defined() -> None:
    assert ALL_TASK_QUEUES == (
        "factory-orchestration",
        "factory-coding",
        "factory-verification",
        "factory-integrations",
    )


def test_task_queue_constants_match_expected_names() -> None:
    assert TASK_QUEUE_ORCHESTRATION == "factory-orchestration"
    assert TASK_QUEUE_CODING == "factory-coding"
    assert TASK_QUEUE_VERIFICATION == "factory-verification"
    assert TASK_QUEUE_INTEGRATIONS == "factory-integrations"


def test_task_queues_are_unique() -> None:
    assert len(set(ALL_TASK_QUEUES)) == 4
