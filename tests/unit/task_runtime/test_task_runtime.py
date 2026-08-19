from pathlib import Path

from rootseeker.bootstrap import create_dev_runtime
from rootseeker.contracts.task import TaskKind, TaskStatus
from rootseeker.task_runtime import TaskExecutor, TaskQueue, TaskStore, create_task_record
from tests.support.stub_planner import IncidentNormalizePlanner


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _runtime():
    return create_dev_runtime(_repo_root(), tool_planner=IncidentNormalizePlanner())


def test_task_queue_push_pop() -> None:
    q = TaskQueue()
    q.push("a")
    assert len(q) == 1
    assert q.pop() == "a"
    assert q.pop() is None


def test_task_executor_case_run() -> None:
    runtime = _runtime()
    store = TaskStore()
    task = create_task_record(
        kind=TaskKind.CASE_RUN,
        payload={
            "title": "x",
            "symptom": "y",
            "service_name": "order-service",
            "source": "task",
            "metadata": {"trace_id": "t1"},
        },
    )
    store.save(task)
    TaskExecutor(runtime, store).execute(task.task_id)
    after = store.get(task.task_id)
    assert after is not None
    assert after.status == TaskStatus.COMPLETED
    assert after.result_ref
    assert after.payload.get("flow_run_id")


def test_task_executor_cron_replay_task() -> None:
    runtime = _runtime()
    store = TaskStore()
    task = create_task_record(
        kind=TaskKind.CRON,
        payload={"suite_name": "cron-default-flow", "repeat_each": 1},
    )
    store.save(task)
    TaskExecutor(runtime, store).execute(task.task_id)
    after = store.get(task.task_id)
    assert after is not None
    assert after.status == TaskStatus.COMPLETED
    assert after.result_ref
    assert isinstance(after.payload.get("report_gate_passed"), bool)
    assert isinstance(after.payload.get("report_release_allowed"), bool)
    assert isinstance(after.payload.get("deployment_decision"), dict)


def test_task_kind_has_no_yaml_step_resume_members() -> None:
    assert not hasattr(TaskKind, "FLOW_RESUME")
    assert not hasattr(TaskKind, "FLOW_STEP")
