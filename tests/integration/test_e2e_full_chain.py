"""End-to-end integration test covering full chain with SQLite persistence."""

from __future__ import annotations

import tempfile
from pathlib import Path

from rootseeker.bootstrap import create_dev_runtime
from rootseeker.channel_routing import (
    ChannelRegistry,
    OutboundTarget,
    RecordingChannelAdapter,
    send_outbound_notification,
)
from rootseeker.contracts.case import CaseStatus, StepStatus
from rootseeker.storage import (
    SqliteCaseStore,
    SqliteCheckpointStore,
    SqliteEvidenceStore,
    SqliteReplayStore,
    SqliteReportStore,
    SqliteTaskStore,
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def test_e2e_full_chain_with_sqlite_persistence() -> None:
    """Complete E2E test: webhook → case → skill → evidence → report → notify with SQLite."""
    # Setup SQLite stores
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)

    case_store = SqliteCaseStore(db_path=db_path)
    evidence_store = SqliteEvidenceStore(db_path=db_path)
    report_store = SqliteReportStore(db_path=db_path)
    SqliteTaskStore(db_path=db_path)
    SqliteCheckpointStore(db_path=db_path)
    SqliteReplayStore(db_path=db_path)

    # Setup channel registry with in-memory recording adapter (tests only)
    channel_registry = ChannelRegistry()
    recording_adapter = RecordingChannelAdapter()
    channel_registry.register(recording_adapter)

    # Create dev runtime
    runtime = create_dev_runtime(_repo_root())

    # Inject SQLite stores (override in-memory)
    runtime.case_store = case_store
    runtime.evidence_store = evidence_store
    runtime.report_store = report_store

    # Simulate webhook payload
    payload = {
        "title": "E2E Test: Payment service timeout",
        "service_name": "payment-service",
        "message": "Connection timeout to database",
        "source": "webhook",
        "trace_id": "trace-e2e-001",
        "tenant": "acme",
        "environment": "prod",
        "severity": "critical",
        "team": "payment",
    }

    # Run default flow
    result = runtime.run_default_flow_from_payload(payload)

    # Verify case
    assert result.case.status == CaseStatus.COMPLETED
    assert result.case.selected_skills == ["base/default-log-triage"]
    assert result.case.service_name == "payment-service"
    assert all(step.status == StepStatus.COMPLETED for step in result.case.steps)

    # Verify SQLite persistence
    persisted_case = case_store.get(result.case.case_id)
    assert persisted_case is not None
    assert persisted_case.case_id == result.case.case_id
    assert persisted_case.title == payload["title"]
    assert persisted_case.status == CaseStatus.COMPLETED

    # Verify evidence
    assert len(result.evidence_pack.items) >= 8
    persisted_pack = evidence_store.get_pack(result.case.case_id)
    assert persisted_pack is not None
    assert persisted_pack.case_id == result.case.case_id
    assert len(persisted_pack.items) >= 8

    # Verify report
    assert result.report.case_id == result.case.case_id
    assert result.report.evidence_item_ids
    persisted_report = report_store.get(result.case.case_id)
    assert persisted_report is not None
    assert persisted_report.case_id == result.case.case_id
    assert persisted_report.title == payload["title"]

    # Send notification via channel registry
    target = OutboundTarget(
        channel="recording",
        endpoint="test://e2e-notification",
        team="payment",
        metadata={"tenant": "acme", "severity": "critical"},
    )
    notify_result = send_outbound_notification(
        target,
        f"Root cause identified for case {result.case.case_id}: {result.report.root_cause.title if result.report.root_cause else 'unknown'}",
        registry=channel_registry,
    )
    assert notify_result["ok"]
    assert notify_result["channel"] == "recording"

    # Verify notification was sent
    messages = recording_adapter.get_sent_messages()
    assert len(messages) == 1
    assert result.case.case_id in messages[0]["message"]

    # Verify audit trail
    audit_events = runtime.audit_log.list_events(case_id=result.case.case_id)
    assert audit_events
    assert all(evt.detail.get("skill_name") == "base/default-log-triage" for evt in audit_events)

    # Cleanup
    db_path.unlink(missing_ok=True)


def test_e2e_multi_channel_notification() -> None:
    """Test notification routing to multiple channels."""
    registry = ChannelRegistry()

    # Register multiple recording adapters shimmed as real channel names
    rec_feishu = RecordingChannelAdapter()
    rec_feishu._channel_name = "feishu"
    registry.register(rec_feishu)

    rec_slack = RecordingChannelAdapter()
    rec_slack._channel_name = "slack"
    registry.register(rec_slack)

    rec_wechat = RecordingChannelAdapter()
    rec_wechat._channel_name = "wechat_work"
    registry.register(rec_wechat)

    # Send to each channel
    channels = ["feishu", "slack", "wechat_work"]
    for channel in channels:
        target = OutboundTarget(
            channel=channel,
            endpoint=f"test://{channel}",
            team="platform",
        )
        result = send_outbound_notification(target, f"Alert via {channel}", registry=registry)
        assert result["ok"]
        assert result["channel"] == channel

    # Verify each adapter received message
    assert len(rec_feishu.get_sent_messages()) == 1
    assert len(rec_slack.get_sent_messages()) == 1
    assert len(rec_wechat.get_sent_messages()) == 1


def test_e2e_sqlite_task_and_checkpoint_persistence() -> None:
    """Test task and checkpoint persistence in SQLite."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)

    task_store = SqliteTaskStore(db_path=db_path)
    checkpoint_store = SqliteCheckpointStore(db_path=db_path)

    from rootseeker.contracts.task import TaskKind, TaskRecord, TaskStatus

    # Create and persist task
    task = TaskRecord(
        task_id="task-e2e-001",
        kind=TaskKind.CASE_RUN,
        case_id="case-e2e-001",
        status=TaskStatus.COMPLETED,
        payload={"test": "e2e"},
    )
    task_store.save(task)
    persisted_task = task_store.get("task-e2e-001")
    assert persisted_task is not None
    assert persisted_task.task_id == "task-e2e-001"
    assert persisted_task.kind == TaskKind.CASE_RUN
    assert persisted_task.status == TaskStatus.COMPLETED

    # Create and persist checkpoint
    checkpoint_store.save(
        "flow-e2e-001",
        {
            "case_id": "case-e2e-001",
            "flow_id": "builtin.default_log_triage_flow",
            "skill_slug": "base/default-log-triage",
            "step_index": 3,
            "status": "completed",
            "step_outputs": {"s1": {"result": "ok"}},
        },
    )
    persisted_cp = checkpoint_store.get("flow-e2e-001")
    assert persisted_cp is not None
    assert persisted_cp["case_id"] == "case-e2e-001"
    assert persisted_cp["step_index"] == 3

    # Cleanup
    db_path.unlink(missing_ok=True)
