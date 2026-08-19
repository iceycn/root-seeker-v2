from pathlib import Path

from rootseeker.bootstrap import create_dev_runtime
from rootseeker.contracts.task import TaskKind, TaskStatus
from rootseeker.task_runtime import TaskRuntime
from tests.support.stub_planner import IncidentNormalizePlanner


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _runtime():
    return create_dev_runtime(_repo_root(), tool_planner=IncidentNormalizePlanner())


def test_task_runtime_submit_and_run_once() -> None:
    runtime = _runtime()
    task_runtime = TaskRuntime(runtime)
    task = task_runtime.submit(
        kind=TaskKind.CASE_RUN,
        payload={
            "title": "runtime-task",
            "symptom": "cpu high",
            "service_name": "order-service",
            "source": "task-runtime",
            "metadata": {"trace_id": "trace-task-runtime-001"},
        },
    )
    executed = task_runtime.run_once()
    assert executed is not None
    assert executed.task_id == task.task_id
    assert executed.status == TaskStatus.COMPLETED


def test_task_runtime_submit_cron_task() -> None:
    runtime = _runtime()
    task_runtime = TaskRuntime(runtime)
    task = task_runtime.submit(
        kind=TaskKind.CRON,
        payload={"suite_name": "cron-default-flow", "repeat_each": 1},
    )
    executed = task_runtime.run_once()
    assert executed is not None
    assert executed.task_id == task.task_id
    assert executed.status == TaskStatus.COMPLETED
    assert isinstance(executed.payload.get("report_gate_passed"), bool)
    assert isinstance(executed.payload.get("report_release_allowed"), bool)
    assert isinstance(executed.payload.get("deployment_decision"), dict)
