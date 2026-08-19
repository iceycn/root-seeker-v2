from pathlib import Path

from rootseeker.bootstrap import create_dev_runtime
from rootseeker.contracts.case import CaseCreateRequest
from rootseeker.flow_runtime import FlowRuntime
from tests.support.stub_planner import IncidentNormalizePlanner


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _runtime():
    return create_dev_runtime(_repo_root(), tool_planner=IncidentNormalizePlanner())


def test_flow_runtime_run_default_and_checkpoint() -> None:
    runtime = _runtime()
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


def test_flow_runtime_list_checkpoints() -> None:
    runtime = _runtime()
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


def test_flow_runtime_has_no_yaml_step_resume() -> None:
    runtime = _runtime()
    flow = FlowRuntime(runtime)
    assert not hasattr(flow, "resume_default")
