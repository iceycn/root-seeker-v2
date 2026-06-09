from pathlib import Path

from rootseeker.bootstrap import create_dev_runtime
from rootseeker.contracts.case import CaseStatus, StepStatus


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
    assert result.case.selected_skills == ["base/default-log-triage"]
    assert result.case.steps
    assert all(step.status == StepStatus.COMPLETED for step in result.case.steps)
    assert result.tool_results
    required_tools = {
        "catalog.resolve_service",
        "catalog.get_log_sources",
        "log.query_by_trace_id",
        "log.query_by_template",
        "trace.get_chain",
        "code.search",
        "code.read",
        "index.get_status",
        "notify.send",
    }
    called_tools = {tr.tool_name for tr in result.tool_results if tr.ok}
    assert required_tools.issubset(called_tools)
    ordered_tools = [tr.tool_name for tr in result.tool_results]
    assert ordered_tools == [
        "catalog.resolve_service",
        "catalog.get_log_sources",
        "log.query_by_trace_id",
        "log.query_by_template",
        "trace.get_chain",
        "code.search",
        "code.read",
        "index.get_status",
        "notify.send",
    ]
    notify_result = result.tool_results[-1]
    assert notify_result.tool_name == "notify.send"
    assert "root_cause=" in str(notify_result.content.get("message", ""))
    assert "evidence=" in str(notify_result.content.get("message", ""))
    assert len(result.evidence_pack.items) >= 8
    assert result.report.case_id == result.case.case_id
    assert result.report.evidence_item_ids

    audit_events = runtime.audit_log.list_events(case_id=result.case.case_id)
    assert audit_events
    assert all(evt.detail.get("skill_name") == "base/default-log-triage" for evt in audit_events)
    assert all(evt.detail.get("plugin_id") == "builtin.default_log_triage_flow" for evt in audit_events)
