from pathlib import Path

from rootseeker.bootstrap import create_dev_runtime
from rootseeker.contracts.case import CaseStatus, StepStatus
from tests.support.stub_internal_adapter import StubInternalToolAdapter


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def test_default_flow_closed_loop_from_alert_payload() -> None:
    runtime = create_dev_runtime(_repo_root())
    payload = {
        "title": "Order service 5xx spike",
        "service_name": "order-service",
        "message": "error ratio high in prod",
        "source": "aliyun-webhook",
        "trace_id": "trace-123",
        "tenant": "demo",
        "environment": "prod",
    }

    result = runtime.run_default_flow_from_payload(payload)

    assert result.case.status == CaseStatus.COMPLETED
    assert result.case.selected_skills == ["flows/default-log-triage"]
    assert result.case.steps
    assert all(step.status == StepStatus.COMPLETED for step in result.case.steps)
    assert result.tool_results
    required_tools = {
        "incident.normalize",
        "catalog.resolve_service",
        "catalog.get_log_sources",
        "log.query_by_trace_id",
        "log.query_by_template",
        "trace.get_chain",
        "index.get_status",
        "repo.list",
        "code.search",
        "code.read",
        "code.find_callers",
        "notify.send",
    }
    called_tools = {tr.tool_name for tr in result.tool_results if tr.ok}
    assert required_tools.issubset(called_tools)
    ordered_tools = [tr.tool_name for tr in result.tool_results]
    assert ordered_tools == [
        "incident.normalize",
        "catalog.resolve_service",
        "catalog.get_log_sources",
        "log.query_by_trace_id",
        "log.query_by_template",
        "trace.get_chain",
        "index.get_status",
        "repo.list",
        "code.search",
        "code.read",
        "code.find_callers",
        "notify.send",
    ]
    notify_result = result.tool_results[-1]
    assert notify_result.tool_name == "notify.send"
    assert "root_cause=" in str(notify_result.content.get("message", ""))
    assert "evidence=" in str(notify_result.content.get("message", ""))
    assert len(result.evidence_pack.items) >= 10
    assert result.report.case_id == result.case.case_id
    assert result.report.evidence_item_ids
    assert result.step_traces
    assert all("argument_source" in trace for trace in result.step_traces)

    audit_events = runtime.audit_log.list_events(case_id=result.case.case_id)
    assert audit_events
    assert all(evt.detail.get("skill_name") == "flows/default-log-triage" for evt in audit_events)
    assert all(evt.detail.get("plugin_id") == "builtin.default_log_triage_flow" for evt in audit_events)


def test_default_flow_reads_first_code_search_hit_when_available() -> None:
    runtime = create_dev_runtime(_repo_root(), internal_adapter=StubInternalToolAdapter.seeded_default())
    result = runtime.run_default_flow_from_payload(
        {
            "title": "Order service 5xx spike",
            "service_name": "order-service",
            "message": "error ratio high in prod",
            "source": "aliyun-webhook",
            "trace_id": "trace-123",
            "tenant": "demo",
            "environment": "prod",
        }
    )

    code_read_step = next(step for step in result.case.steps if step.step_id == "code-read")
    assert code_read_step.outputs["path"] == "stub.py"


def test_default_flow_uses_file_path_from_symptom_when_code_search_has_no_hits() -> None:
    runtime = create_dev_runtime(_repo_root())
    result = runtime.run_default_flow_from_payload(
        {
            "title": "Order service NPE",
            "service_name": "order-service",
            "message": "NullPointerException at FooService.java:42",
            "source": "aliyun-webhook",
            "trace_id": "trace-123",
            "tenant": "demo",
            "environment": "prod",
        }
    )

    code_read_step = next(step for step in result.case.steps if step.step_id == "code-read")
    assert code_read_step.outputs["path"] == "FooService.java"


def test_default_flow_runs_find_callers_when_call_chain_present() -> None:
    runtime = create_dev_runtime(_repo_root(), internal_adapter=StubInternalToolAdapter.seeded_default())
    stack = (
        "DuplicateKeyException\n"
        "at com.example.PopRecordService.insertPopRecordLogic(PopRecordService.java:60)\n"
        "at com.example.StudyProjectController.saveProgress(StudyProjectController.java:1132)\n"
    )
    result = runtime.run_default_flow_from_payload(
        {
            "title": "Training duplicate key",
            "service_name": "training-manage-api",
            "message": stack,
            "source": "aliyun-webhook",
            "trace_id": "trace-456",
            "tenant": "demo",
            "environment": "prod",
        }
    )

    find_callers_step = next(step for step in result.case.steps if step.step_id == "find-callers")
    assert find_callers_step.outputs.get("aligned")
    assert find_callers_step.outputs["aligned"]["fault_method"] == "PopRecordService.insertPopRecordLogic"
    assert find_callers_step.outputs["entrypoints"]
