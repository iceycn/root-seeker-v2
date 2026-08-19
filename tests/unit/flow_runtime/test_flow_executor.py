from pathlib import Path

from rootseeker.bootstrap import create_dev_runtime
from rootseeker.contracts.case import CaseCreateRequest
from rootseeker.flow_runtime import FlowCheckpointStore, FlowExecutor, build_execution_trace
from tests.support.stub_planner import IncidentNormalizePlanner


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _runtime():
    return create_dev_runtime(_repo_root(), tool_planner=IncidentNormalizePlanner())


def test_flow_executor_default() -> None:
    runtime = _runtime()
    req = CaseCreateRequest(
        title="x",
        symptom="y",
        service_name="order-service",
        source="unit",
        metadata={"trace_id": "t1"},
    )
    res = FlowExecutor(runtime).execute_default(req)
    assert res.case_id
    assert res.trace.flow_id == "builtin.default_log_triage_flow"
    assert all(step.step_id for step in res.trace.steps)
    assert all(
        step.status.value in {"completed", "failed", "pending", "running", "skipped"}
        for step in res.trace.steps
    )


def test_checkpoint_and_trace_builder() -> None:
    cp = FlowCheckpointStore()
    cp.save("run-1", {"state": "ok"})
    assert cp.get("run-1") == {"state": "ok"}
    cp.save("run-1", {"state": "ok2"})
    record = cp.get_record("run-1")
    assert record is not None
    assert record.revision == 2
    trace = build_execution_trace(case_id="c1", skill_slug="s1", flow_id="f1", step_names=["a", "b"])
    assert len(trace.steps) == 2


def test_flow_executor_has_no_step_checkpoint_api() -> None:
    assert not hasattr(FlowExecutor, "execute_from_checkpoint")
