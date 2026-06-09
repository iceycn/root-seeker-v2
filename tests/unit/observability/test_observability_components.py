from pathlib import Path

from rootseeker.agent_runtime import AgentRuntime
from rootseeker.bootstrap import create_dev_runtime
from rootseeker.observability import (
    DiagnosticCollector,
    StructuredLogger,
    build_runtime_health,
    redact_payload,
    render_prometheus_metrics,
)


def test_redaction_masks_sensitive_keys() -> None:
    payload = {
        "token": "abc",
        "nested": {"password": "123"},
        "authorization": "Bearer x.y.z",
    }
    redacted = redact_payload(payload)
    assert redacted["token"] == "[REDACTED]"
    assert redacted["nested"]["password"] == "[REDACTED]"
    assert redacted["authorization"] == "[REDACTED]"


def test_structured_logger_and_diagnostic() -> None:
    logger = StructuredLogger()
    diag = DiagnosticCollector(logger)
    logger.info("tool.called", {"api_key": "k"})
    diag.record("heartbeat", {"secret": "s"})
    records = logger.list_records()
    assert len(records) == 2
    assert records[0]["payload"]["api_key"] == "[REDACTED]"
    assert records[1]["event"] == "diagnostic.heartbeat"


def test_runtime_health_and_prometheus_metrics(monkeypatch) -> None:
    monkeypatch.setenv("ROOTSEEKER_LLM_ENABLED", "false")
    runtime = create_dev_runtime(Path(__file__).resolve().parents[3])
    health = build_runtime_health(runtime)
    assert health["status"] == "ok"
    assert health["components"]["skills"]["count"] >= 1
    assert health["components"]["tools"]["count"] >= 1

    metrics = render_prometheus_metrics(runtime)
    assert "rootseeker_up 1" in metrics
    assert "rootseeker_skills_total" in metrics
    assert 'rootseeker_component_up{component="tools",status="ok"} 1' in metrics


def test_prometheus_metrics_include_agent_tool_and_approval_activity(monkeypatch) -> None:
    monkeypatch.setenv("ROOTSEEKER_LLM_ENABLED", "false")
    runtime = create_dev_runtime(Path(__file__).resolve().parents[3])
    AgentRuntime(runtime).run_payload(
        {
            "title": "metrics activity case",
            "service_name": "order-service",
            "message": "error ratio high in prod",
            "source": "unit-metrics",
            "trace_id": "trace-metrics-001",
        }
    )
    approval = runtime.approval_store.create_manual(
        case_id="metrics-case",
        step_id="release-gate",
        tool_name="release.deploy",
        permission_level="admin",
        reason="metrics coverage",
    )
    runtime.approval_store.approve(approval.approval_id, actor="unit-test")

    metrics = render_prometheus_metrics(runtime)

    assert 'rootseeker_audit_events_total{action="agent.run.completed"} 1' in metrics
    assert (
        'rootseeker_agent_tool_events_total{tool_name="log.query_by_trace_id",ok="true",error_code=""}'
        in metrics
    )
    assert 'rootseeker_approvals_total{status="approved"} 1' in metrics
    assert 'rootseeker_approvals_total{status="pending"} 0' in metrics
