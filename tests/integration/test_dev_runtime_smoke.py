from pathlib import Path

from rootseeker.analysis import build_case_report
from rootseeker.bootstrap import create_dev_runtime
from rootseeker.channel_routing import webhook_payload_to_case_create
from rootseeker.contracts.evidence import EvidencePack
from rootseeker.contracts.log_query import LogQueryResult
from rootseeker.contracts.tool import ToolCallRequest
from rootseeker.evidence import append_log_query_evidence


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def test_dev_runtime_catalog_tool_and_evidence_report() -> None:
    rt = create_dev_runtime(_repo_root())
    req = ToolCallRequest(
        case_id="c-int",
        step_id="s1",
        skill_name="base/default-log-triage",
        tool_name="catalog.resolve_service",
        arguments={"tenant": "demo", "environment": "prod", "service_name": "order-service"},
    )
    res = rt.gateway.invoke(req, plugin_id="builtin.service_catalog")
    assert res.ok
    assert rt.audit_log.count() >= 1

    pack = EvidencePack(case_id="c-int")
    lres = LogQueryResult(query_key="trace:t1", records=[])
    append_log_query_evidence(pack, tool_name="log.query_by_trace_id", result=lres)
    report = build_case_report(case_id="c-int", title="Smoke", pack=pack)
    assert report.case_id == "c-int"
    assert len(report.evidence_item_ids) == 1
    assert report.root_cause is not None


def test_webhook_to_case_create() -> None:
    payload = {
        "title": "5xx spike",
        "service_name": "api",
        "message": "error rate high",
        "source": "webhook",  # Use generic webhook channel
        "trace_id": "abc",
    }
    cr = webhook_payload_to_case_create(payload)
    assert cr.title == "5xx spike"
    assert cr.service_name == "api"
    assert cr.metadata.get("trace_id") == "abc"


def test_webhook_aliyun_channel() -> None:
    """Test that aliyun channel uses specialized normalizer."""
    payload = {
        "alertName": "HighCPU",
        "alertState": "ALARM",
        "instanceName": "api-server",
        "metricName": "cpu",
        "curValue": "95%",
        "source": "aliyun",
    }
    cr = webhook_payload_to_case_create(payload)
    assert "[Aliyun]" in cr.title
    assert cr.service_name == "api-server"
