"""Tests for SQLite storage implementations."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from rootseeker.contracts.case import CaseRecord, CaseStatus
from rootseeker.contracts.evidence import EvidencePack, RootCauseConclusion
from rootseeker.contracts.report import CaseReport
from rootseeker.contracts.task import TaskKind, TaskRecord, TaskStatus
from rootseeker.storage import (
    SqliteCaseStore,
    SqliteCheckpointStore,
    SqliteEvidenceStore,
    SqliteReplayStore,
    SqliteReportStore,
    SqliteTaskStore,
)


@pytest.fixture
def temp_db() -> Path:
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        yield Path(f.name)


def test_sqlite_case_store_put_and_get(temp_db: Path) -> None:
    store = SqliteCaseStore(db_path=temp_db)

    case = CaseRecord(
        case_id="test-case-1",
        title="Test Case",
        symptom="Test symptom",
        service_name="test-service",
        source="test",
        status=CaseStatus.COMPLETED,
    )

    store.put(case)
    retrieved = store.get("test-case-1")

    assert retrieved is not None
    assert retrieved.case_id == "test-case-1"
    assert retrieved.title == "Test Case"
    assert retrieved.status == CaseStatus.COMPLETED


def test_sqlite_case_store_not_found(temp_db: Path) -> None:
    store = SqliteCaseStore(db_path=temp_db)
    assert store.get("nonexistent") is None


def test_sqlite_evidence_store_put_and_get(temp_db: Path) -> None:
    store = SqliteEvidenceStore(db_path=temp_db)

    pack = EvidencePack(case_id="test-case-1", summary="Test evidence")
    store.put_pack(pack)

    retrieved = store.get_pack("test-case-1")

    assert retrieved is not None
    assert retrieved.case_id == "test-case-1"
    assert retrieved.summary == "Test evidence"


def test_sqlite_report_store_put_and_get(temp_db: Path) -> None:
    store = SqliteReportStore(db_path=temp_db)

    report = CaseReport(
        case_id="test-case-1",
        title="Test Report",
        summary="Test narrative",
        root_cause=RootCauseConclusion(
            title="root cause",
            narrative="details",
            confidence=0.8,
        ),
        evidence_item_ids=["ev-1"],
        metadata={"tenant": "demo"},
    )

    store.put(report)
    retrieved = store.get("test-case-1")

    assert retrieved is not None
    assert retrieved.case_id == "test-case-1"
    assert retrieved.title == "Test Report"
    assert retrieved.summary == "Test narrative"
    assert retrieved.root_cause is not None
    assert retrieved.root_cause.confidence == 0.8
    assert retrieved.evidence_item_ids == ["ev-1"]


def test_sqlite_task_store_put_and_get(temp_db: Path) -> None:
    store = SqliteTaskStore(db_path=temp_db)

    task = TaskRecord(
        task_id="task-1",
        kind=TaskKind.CASE_RUN,
        status=TaskStatus.PENDING,
        payload={"title": "Test"},
    )

    store.save(task)
    retrieved = store.get("task-1")

    assert retrieved is not None
    assert retrieved.task_id == "task-1"
    assert retrieved.kind == TaskKind.CASE_RUN
    assert retrieved.status == TaskStatus.PENDING


def test_sqlite_task_store_list_all(temp_db: Path) -> None:
    store = SqliteTaskStore(db_path=temp_db)

    for i in range(3):
        task = TaskRecord(
            task_id=f"task-{i}",
            kind=TaskKind.CASE_RUN,
            status=TaskStatus.PENDING,
            payload={},
        )
        store.save(task)

    all_tasks = store.list_all()
    assert len(all_tasks) == 3


def test_sqlite_checkpoint_store_save_and_get(temp_db: Path) -> None:
    store = SqliteCheckpointStore(db_path=temp_db)

    payload = {"case_id": "case-1", "status": "completed"}
    store.save("flow-1", payload)

    retrieved = store.get("flow-1")
    assert retrieved is not None
    assert retrieved["case_id"] == "case-1"

    record = store.get_record("flow-1")
    assert record is not None
    assert record.revision == 1


def test_sqlite_checkpoint_store_revision_increment(temp_db: Path) -> None:
    store = SqliteCheckpointStore(db_path=temp_db)

    store.save("flow-1", {"status": "running"})
    store.save("flow-1", {"status": "completed"})

    record = store.get_record("flow-1")
    assert record is not None
    assert record.revision == 2


def test_sqlite_checkpoint_store_list_records(temp_db: Path) -> None:
    store = SqliteCheckpointStore(db_path=temp_db)

    store.save("flow-1", {"case_id": "case-1", "status": "completed"})
    store.save("flow-2", {"case_id": "case-2", "status": "running"})

    records = store.list_records()
    assert len(records) == 2

    filtered = store.list_records(case_id="case-1")
    assert len(filtered) == 1


def test_sqlite_replay_store_save_and_get_case(temp_db: Path) -> None:
    store = SqliteReplayStore(db_path=temp_db)

    store.save_case("case-1", "suite-1", {"title": "Test Case"})

    case = store.get_case("case-1")
    assert case is not None
    assert case.case_id == "case-1"
    assert case.suite_name == "suite-1"


def test_sqlite_replay_store_list_cases(temp_db: Path) -> None:
    store = SqliteReplayStore(db_path=temp_db)

    store.save_case("case-1", "suite-1", {})
    store.save_case("case-2", "suite-1", {})
    store.save_case("case-3", "suite-2", {})

    all_cases = store.list_cases()
    assert len(all_cases) == 3

    suite1_cases = store.list_cases(suite_name="suite-1")
    assert len(suite1_cases) == 2


def test_sqlite_replay_store_save_result(temp_db: Path) -> None:
    store = SqliteReplayStore(db_path=temp_db)

    store.save_result(
        result_id="result-1",
        suite_name="suite-1",
        case_id="case-1",
        status="passed",
        metrics={"duration_ms": 100},
    )

    results = store.list_results()
    assert len(results) == 1
    assert results[0].status == "passed"


def test_sqlite_replay_store_clear_cases(temp_db: Path) -> None:
    store = SqliteReplayStore(db_path=temp_db)

    store.save_case("case-1", "suite-1", {})
    store.save_case("case-2", "suite-2", {})

    store.clear_cases(suite_name="suite-1")

    assert store.get_case("case-1") is None
    assert store.get_case("case-2") is not None
