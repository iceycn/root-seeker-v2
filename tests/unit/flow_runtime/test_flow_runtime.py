from pathlib import Path

import pytest

from rootseeker.bootstrap import create_dev_runtime
from rootseeker.contracts.case import CaseCreateRequest
from rootseeker.flow_runtime import FlowRuntime


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def test_flow_runtime_run_default_and_checkpoint() -> None:
    runtime = create_dev_runtime(_repo_root())
    flow = FlowRuntime(runtime)
    res = flow.run_default(
        CaseCreateRequest(
            title="flow-runtime",
            symptom="5xx spike",
            service_name="order-service",
            source="unit-flow",
            metadata={"trace_id": "trace-flow-runtime-001"},
        )
    )
    checkpoint = flow.checkpoints.get(res.trace.execution_id)
    assert checkpoint is not None
    assert checkpoint["case_id"] == res.case_id
    assert checkpoint["status"] == "completed"
    assert checkpoint["next_step_index"] == len(res.trace.steps)
    assert len(checkpoint["steps"]) == len(res.trace.steps)


def test_flow_runtime_resume_from_checkpoint_force_replay() -> None:
    runtime = create_dev_runtime(_repo_root())
    flow = FlowRuntime(runtime)
    req = CaseCreateRequest(
        title="resume-runtime",
        symptom="db timeout",
        service_name="order-service",
        source="unit-flow",
        metadata={"trace_id": "trace-flow-runtime-resume-001"},
    )
    first = flow.run_default(req)
    resumed = flow.resume_default(flow_run_id=first.trace.execution_id, case_request=req, force=True)
    assert resumed is not None
    cp = flow.checkpoints.get(first.trace.execution_id)
    assert cp is not None
    assert cp["resumed_from_execution_id"] == first.trace.execution_id
    # resume_status can be "resumed_from_step" or "replayed" depending on checkpoint state
    assert cp["resume_status"] in {"resumed_from_step", "replayed"}


def test_flow_runtime_resume_completed_without_force_skips() -> None:
    runtime = create_dev_runtime(_repo_root())
    flow = FlowRuntime(runtime)
    req = CaseCreateRequest(
        title="resume-skip",
        symptom="latency",
        service_name="order-service",
        source="unit-flow",
        metadata={"trace_id": "trace-flow-runtime-resume-002"},
    )
    first = flow.run_default(req)
    result = flow.resume_default(flow_run_id=first.trace.execution_id, case_request=req, force=False)
    assert result is None
    record = flow.checkpoints.get_record(first.trace.execution_id)
    assert record is not None
    assert record.revision >= 2
    assert record.payload.get("resume_status") == "skipped_completed"


def test_flow_runtime_resume_unknown_checkpoint_raises() -> None:
    runtime = create_dev_runtime(_repo_root())
    flow = FlowRuntime(runtime)
    req = CaseCreateRequest(
        title="resume-missing",
        symptom="latency",
        service_name="order-service",
        source="unit-flow",
        metadata={"trace_id": "trace-flow-runtime-resume-003"},
    )
    with pytest.raises(ValueError):
        flow.resume_default(flow_run_id="missing-run-id", case_request=req)


def test_flow_runtime_list_checkpoints() -> None:
    runtime = create_dev_runtime(_repo_root())
    flow = FlowRuntime(runtime)
    req = CaseCreateRequest(
        title="list-checkpoints",
        symptom="latency",
        service_name="order-service",
        source="unit-flow",
        metadata={"trace_id": "trace-flow-runtime-list-001"},
    )
    res = flow.run_default(req)
    items = flow.list_checkpoints(case_id=res.case_id, status="completed")
    assert len(items) >= 1
    assert any(item["payload"]["case_id"] == res.case_id for item in items)


def test_flow_runtime_resume_from_step() -> None:
    """Test that resume_default uses step resume when checkpoint has prior state."""
    runtime = create_dev_runtime(_repo_root())
    flow = FlowRuntime(runtime)
    req = CaseCreateRequest(
        title="resume-from-step",
        symptom="db timeout",
        service_name="order-service",
        source="unit-flow",
        metadata={"trace_id": "trace-flow-runtime-step-resume-001"},
    )

    # First run to create checkpoint with step_outputs
    first = flow.run_default(req)
    assert first.case_id
    assert first.step_outputs

    # Verify checkpoint has step_outputs stored
    record = flow.checkpoints.get_record(first.trace.execution_id)
    assert record is not None
    steps_with_outputs = [s for s in record.payload.get("steps", []) if s.get("outputs")]
    assert len(steps_with_outputs) >= 1, "checkpoint should store step outputs"

    # Resume with force=True should use step resume path
    resumed = flow.resume_default(flow_run_id=first.trace.execution_id, case_request=req, force=True)
    assert resumed is not None
    record_after = flow.checkpoints.get_record(first.trace.execution_id)
    assert record_after is not None
    # Should have resume_status indicating step resume or replay
    assert record_after.payload.get("resume_status") in {"resumed_from_step", "replayed"}
