from __future__ import annotations

from pathlib import Path

from rootseeker.bootstrap import create_dev_runtime
from rootseeker.contracts.case import CaseCreateRequest
from rootseeker.contracts.replay import ReplayCaseSpec, ReplayRunSnapshot
from rootseeker.storage.sqlite_replay_history import SqliteReplayHistoryStore
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


def test_create_dev_runtime_wires_guards_and_replay_store(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("ROOTSEEKER_STORAGE_BACKEND", "memory")

    runtime = create_dev_runtime(_repo_root())

    assert runtime.network_guard is not None
    assert runtime.exec_approval_guard is not None
    assert runtime.replay_store is not None
    assert runtime.event_bus is not None
    assert runtime.presence_registry is not None
    assert runtime.node_id


def test_create_dev_runtime_registers_presence_with_node_role() -> None:
    runtime = create_dev_runtime(_repo_root(), node_role="api")
    nodes = runtime.presence_registry.list_nodes()
    assert len(nodes) == 1
    assert nodes[0].node_id == runtime.node_id
    assert nodes[0].role == "api"


def test_run_agent_from_case_request_publishes_case_completed_event() -> None:
    from rootseeker.contracts.case import CaseCreateRequest

    runtime = create_dev_runtime(_repo_root())
    received: list[dict[str, object]] = []
    runtime.event_bus.subscribe("case.completed", received.append)

    runtime.run_agent_from_case_request(
        CaseCreateRequest(
            title="agent event test",
            symptom="timeout",
            service_name="demo-svc",
            source="unit",
        )
    )

    assert len(received) == 1
    assert received[0]["runner"] == "agent"
    assert received[0]["case_id"]


def test_run_default_flow_publishes_case_completed_event() -> None:
    from rootseeker.contracts.case import CaseCreateRequest

    runtime = create_dev_runtime(_repo_root())
    received: list[dict[str, object]] = []
    runtime.event_bus.subscribe("case.completed", received.append)

    runtime.run_default_flow_from_case_request(
        CaseCreateRequest(
            title="event test",
            symptom="timeout",
            service_name="demo-svc",
            source="unit",
        )
    )

    assert len(received) == 1
    assert received[0]["case_id"]
    assert received[0]["status"]


def test_sqlite_replay_history_store_persists_across_instances(tmp_path: Path) -> None:
    db_path = tmp_path / "replay.db"
    case = ReplayCaseSpec(
        replay_id="rp-test-1",
        name="test replay",
        alert_payload={"title": "t", "service_name": "svc"},
        case_request=CaseCreateRequest(
            title="t",
            symptom="s",
            service_name="svc",
            source="unit",
        ),
    )
    run = ReplayRunSnapshot(
        replay_id="rp-test-1",
        run_id="run-1",
        case_id="case-1",
        skill_name="flows/default-log-triage",
        flow_plugin_id="builtin.default_log_triage_flow",
        passed=True,
        metrics={"duration_ms": 12.0},
    )

    first = SqliteReplayHistoryStore(db_path)
    first.upsert_case(case)
    first.add_run(run)

    second = SqliteReplayHistoryStore(db_path)

    assert second.get_case("rp-test-1") is not None
    assert len(second.get_runs("rp-test-1")) == 1
