from pathlib import Path

from rootseeker.bootstrap import create_dev_runtime
from rootseeker.contracts.case import CaseCreateRequest
from rootseeker.flow_runtime import FlowCheckpointStore, FlowExecutor, build_execution_trace


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def test_flow_executor_default() -> None:
    runtime = create_dev_runtime(_repo_root())
    req = CaseCreateRequest(
        title="x",
        symptom="y",
        service_name="order-service",
        source="unit",
        metadata={"trace_id": "t1"},
    )
    res = FlowExecutor(runtime).execute_default(req)
    assert res.case_id
    assert res.trace.steps
    assert res.trace.flow_id == "builtin.default_log_triage_flow"
    assert all(step.step_id for step in res.trace.steps)
    assert all(step.status.value in {"completed", "failed", "pending", "running", "skipped"} for step in res.trace.steps)
    assert res.step_outputs, "step_outputs should be populated"


def test_flow_executor_execute_from_checkpoint() -> None:
    runtime = create_dev_runtime(_repo_root())
    req = CaseCreateRequest(
        title="resume-test",
        symptom="latency spike",
        service_name="order-service",
        source="unit-resume",
        metadata={"trace_id": "trace-resume-001"},
    )
    executor = FlowExecutor(runtime)

    # First run to get initial state
    first = executor.execute_default(req)
    assert first.case_id
    assert len(first.trace.steps) >= 1
    assert first.step_outputs

    # Simulate resuming from step 2 (skip first 2 steps)
    prior_outputs = {
        step.step_id: {"prior": "output"}
        for step in first.trace.steps[:2]
    }
    resumed = executor.execute_from_checkpoint(
        req,
        start_from_step_index=2,
        prior_step_outputs=prior_outputs,
        prior_case_id=first.case_id,
    )
    assert resumed.case_id == first.case_id, "should reuse prior case_id"
    assert resumed.trace.steps
    assert resumed.step_outputs


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
