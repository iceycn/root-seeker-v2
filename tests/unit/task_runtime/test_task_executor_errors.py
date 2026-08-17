from pathlib import Path
from unittest.mock import patch

import pytest

from rootseeker.bootstrap import create_dev_runtime
from rootseeker.contracts.task import TaskKind, TaskStatus
from rootseeker.task_runtime import TaskExecutor, TaskStore, create_task_record


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def test_task_executor_marks_failed_when_flow_raises() -> None:
    runtime = create_dev_runtime(_repo_root())
    store = TaskStore()
    task = create_task_record(
        kind=TaskKind.CASE_RUN,
        payload={
            "title": "boom",
            "symptom": "y",
            "service_name": "order-service",
            "source": "task",
            "metadata": {},
        },
    )
    store.save(task)
    executor = TaskExecutor(runtime, store)

    with patch.object(
        executor._flow_runtime,
        "run_default",
        side_effect=RuntimeError("flow exploded"),
    ):
        with pytest.raises(RuntimeError, match="flow exploded"):
            executor.execute(task.task_id)

    after = store.get(task.task_id)
    assert after is not None
    assert after.status == TaskStatus.FAILED
    assert after.error is not None
    assert after.error.get("type") == "RuntimeError"
    assert "flow exploded" in str(after.error.get("reason", ""))
