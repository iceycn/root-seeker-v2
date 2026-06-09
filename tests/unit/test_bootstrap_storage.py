from __future__ import annotations

from pathlib import Path

from rootseeker.bootstrap import create_dev_runtime
from rootseeker.contracts.case import CaseCreateRequest
from rootseeker.contracts.task import TaskKind, TaskStatus
from rootseeker.flow_runtime import FlowRuntime
from rootseeker.task_runtime import TaskRuntime


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def test_sqlite_runtime_persists_case_report_evidence_and_checkpoint(
    tmp_path: Path,
    monkeypatch,
) -> None:
    db_path = tmp_path / "rootseeker.db"
    monkeypatch.setenv("ROOTSEEKER_STORAGE_BACKEND", "sqlite")
    monkeypatch.setenv("ROOTSEEKER_SQLITE_DB_PATH", str(db_path))
    monkeypatch.setenv("ROOTSEEKER_LLM_ENABLED", "false")

    first_runtime = create_dev_runtime(_repo_root())
    flow = FlowRuntime(first_runtime)
    result = flow.run_default(
        CaseCreateRequest(
            title="sqlite runtime persistence",
            symptom="5xx spike",
            service_name="order-service",
            source="unit",
            metadata={"trace_id": "trace-sqlite-runtime-001"},
        )
    )

    second_runtime = create_dev_runtime(_repo_root())

    assert second_runtime.case_store.get(result.case_id) is not None
    assert second_runtime.report_store.get(result.case_id) is not None
    assert second_runtime.evidence_store.get_pack(result.case_id) is not None
    assert second_runtime.flow_checkpoint_store.get(result.trace.execution_id) is not None
    assert db_path.exists()


def test_sqlite_task_runtime_runs_pending_task_across_runtime_instances(
    tmp_path: Path,
    monkeypatch,
) -> None:
    db_path = tmp_path / "rootseeker.db"
    monkeypatch.setenv("ROOTSEEKER_STORAGE_BACKEND", "sqlite")
    monkeypatch.setenv("ROOTSEEKER_SQLITE_DB_PATH", str(db_path))
    monkeypatch.setenv("ROOTSEEKER_LLM_ENABLED", "false")

    first_task_runtime = TaskRuntime(create_dev_runtime(_repo_root()))
    submitted = first_task_runtime.submit(
        kind=TaskKind.CASE_RUN,
        payload={
            "title": "sqlite pending task",
            "symptom": "5xx spike",
            "service_name": "order-service",
            "source": "unit",
            "metadata": {"trace_id": "trace-sqlite-task-001"},
        },
    )

    second_task_runtime = TaskRuntime(create_dev_runtime(_repo_root()))
    executed = second_task_runtime.run_once()

    assert executed is not None
    assert executed.task_id == submitted.task_id
    assert executed.status == TaskStatus.COMPLETED
    assert executed.result_ref
    assert second_task_runtime.store.get(submitted.task_id) is not None
