from pathlib import Path

from rootseeker.bootstrap import create_dev_runtime
from rootseeker.contracts.case import CaseStatus
from tests.support.stub_planner import IncidentNormalizePlanner


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def test_default_flow_runs_agent_playbook_without_yaml_stepper() -> None:
    import rootseeker.skill_runtime as sr

    runtime = create_dev_runtime(_repo_root(), tool_planner=IncidentNormalizePlanner())
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

    assert not hasattr(sr, "execute_skill_flow")
    assert result.case.status == CaseStatus.COMPLETED
    assert result.case.selected_skills == ["default-log-triage"]
    assert result.report.case_id == result.case.case_id
    called_tools = [tr.tool_name for tr in result.tool_results if tr.ok]
    assert "incident.normalize" in called_tools or any(
        step.tool_name == "incident.normalize" or step.action == "incident.normalize"
        for step in result.case.steps
    )
