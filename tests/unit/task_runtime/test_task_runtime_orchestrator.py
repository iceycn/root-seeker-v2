from pathlib import Path

from rootseeker.bootstrap import create_dev_runtime
from rootseeker.contracts.task import TaskKind, TaskStatus
from rootseeker.task_runtime import TaskRuntime


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def test_task_runtime_submit_and_run_once() -> None:
    runtime = create_dev_runtime(_repo_root())
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
    runtime = create_dev_runtime(_repo_root())
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


def test_task_runtime_submit_flow_resume_task_force_replay() -> None:
    runtime = create_dev_runtime(_repo_root())
    task_runtime = TaskRuntime(runtime)
    task_runtime.submit(
        kind=TaskKind.CASE_RUN,
        payload={
            "title": "runtime-resume",
            "symptom": "cpu high",
            "service_name": "order-service",
            "source": "task-runtime",
            "metadata": {"trace_id": "trace-task-runtime-resume-001"},
        },
    )
    run_executed = task_runtime.run_once()
    assert run_executed is not None
    flow_run_id = str(run_executed.payload.get("flow_run_id", ""))
    assert flow_run_id

    resume_task = task_runtime.submit(
        kind=TaskKind.FLOW_RESUME,
        payload={
            "flow_run_id": flow_run_id,
            "force": True,
            "case_request": {
                "title": "runtime-resume",
                "symptom": "cpu high",
                "service_name": "order-service",
                "source": "task-runtime",
                "metadata": {"trace_id": "trace-task-runtime-resume-001"},
            },
        },
    )
    resume_executed = task_runtime.run_once()
    assert resume_executed is not None
    assert resume_executed.task_id == resume_task.task_id
    assert resume_executed.status == TaskStatus.COMPLETED
    assert resume_executed.payload.get("resume_status") in {"resumed_from_step", "replayed"}
