from pathlib import Path

from rootseeker.bootstrap import create_dev_runtime
from rootseeker.contracts.task import TaskKind, TaskStatus
from rootseeker.task_runtime import TaskExecutor, TaskQueue, TaskStore, create_task_record


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def test_task_queue_push_pop() -> None:
    q = TaskQueue()
    q.push("a")
    assert len(q) == 1
    assert q.pop() == "a"
    assert q.pop() is None


def test_task_executor_case_run() -> None:
    runtime = create_dev_runtime(_repo_root())
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
    runtime = create_dev_runtime(_repo_root())
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


def test_task_executor_flow_resume_task() -> None:
    runtime = create_dev_runtime(_repo_root())
    store = TaskStore()

    run_task = create_task_record(
        kind=TaskKind.CASE_RUN,
        payload={
            "title": "resume-flow",
            "symptom": "latency high",
            "service_name": "order-service",
            "source": "task",
            "metadata": {"trace_id": "trace-resume-001"},
        },
    )
    store.save(run_task)
    executor = TaskExecutor(runtime, store)
    executor.execute(run_task.task_id)
    run_after = store.get(run_task.task_id)
    assert run_after is not None
    flow_run_id = str(run_after.payload.get("flow_run_id", ""))
    assert flow_run_id

    resume_task = create_task_record(
        kind=TaskKind.FLOW_RESUME,
        payload={
            "flow_run_id": flow_run_id,
            "force": False,
            "case_request": {
                "title": "resume-flow",
                "symptom": "latency high",
                "service_name": "order-service",
                "source": "task",
                "metadata": {"trace_id": "trace-resume-001"},
            },
        },
    )
    store.save(resume_task)
    executor.execute(resume_task.task_id)
    resume_after = store.get(resume_task.task_id)
    assert resume_after is not None
    assert resume_after.status == TaskStatus.COMPLETED
    assert resume_after.payload.get("resume_status") == "skipped_completed"


def test_task_executor_flow_step_task() -> None:
    """Test FLOW_STEP task executes from specific step index."""
    runtime = create_dev_runtime(_repo_root())
    store = TaskStore()

    # First run a case to create a checkpoint
    run_task = create_task_record(
        kind=TaskKind.CASE_RUN,
        payload={
            "title": "flow-step-test",
            "symptom": "db timeout",
            "service_name": "order-service",
            "source": "task",
            "metadata": {"trace_id": "trace-flow-step-001"},
        },
    )
    store.save(run_task)
    executor = TaskExecutor(runtime, store)
    executor.execute(run_task.task_id)
    run_after = store.get(run_task.task_id)
    assert run_after is not None
    flow_run_id = str(run_after.payload.get("flow_run_id", ""))
    assert flow_run_id

    # Now submit a FLOW_STEP task to resume from step 2
    step_task = create_task_record(
        kind=TaskKind.FLOW_STEP,
        payload={
            "flow_run_id": flow_run_id,
            "step_index": 2,
            "case_request": {
                "title": "flow-step-test",
                "symptom": "db timeout",
                "service_name": "order-service",
                "source": "task",
                "metadata": {"trace_id": "trace-flow-step-001"},
            },
        },
    )
    store.save(step_task)
    executor.execute(step_task.task_id)
    step_after = store.get(step_task.task_id)
    assert step_after is not None
    assert step_after.status == TaskStatus.COMPLETED
    assert step_after.payload.get("executed_step_index") == 2
