from pathlib import Path

import hashlib
import hmac

from fastapi.testclient import TestClient

from apps.api.main import create_app


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def test_api_run_default_flow_and_query_report() -> None:
    app = create_app(_repo_root())
    client = TestClient(app)

    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
    assert r.json()["components"]["skills"]["count"] >= 1
    assert r.json()["components"]["presence"]["count"] >= 1

    presence = client.get("/system/presence")
    assert presence.status_code == 200
    assert presence.json()["total"] >= 1
    assert presence.json()["items"][0]["role"] == "api"

    ready = client.get("/readyz")
    assert ready.status_code == 200
    assert ready.json()["status"] == "ok"

    metrics = client.get("/metrics")
    assert metrics.status_code == 200
    assert "rootseeker_up 1" in metrics.text

    skills = client.get("/skills")
    assert skills.status_code == 200
    slugs = {x["slug"] for x in skills.json()["items"]}
    assert "flows/default-log-triage" in slugs

    run = client.post(
        "/cases/run-default",
        json={
            "title": "API 5xx spike",
            "symptom": "error ratio high",
            "service_name": "order-service",
            "source": "api-test",
            "metadata": {"trace_id": "trace-api-1", "tenant": "demo", "environment": "prod"},
        },
    )
    assert run.status_code == 200
    payload = run.json()
    case_id = payload["case"]["case_id"]
    flow_run_id = payload["flow_run_id"]
    assert payload["case"]["status"] == "completed"
    assert payload["report"]["case_id"] == case_id
    assert payload["evidence_count"] >= 8
    assert isinstance(flow_run_id, str) and flow_run_id

    case_resp = client.get(f"/cases/{case_id}")
    assert case_resp.status_code == 200
    assert case_resp.json()["case_id"] == case_id

    report_resp = client.get(f"/reports/{case_id}")
    assert report_resp.status_code == 200
    assert report_resp.json()["case_id"] == case_id

    evidence_resp = client.get(f"/evidence/{case_id}")
    assert evidence_resp.status_code == 200
    evidence_payload = evidence_resp.json()
    assert evidence_payload["case_id"] == case_id
    assert len(evidence_payload["items"]) >= 8

    audit_resp = client.get(f"/cases/{case_id}/audit")
    assert audit_resp.status_code == 200
    audit_payload = audit_resp.json()
    assert audit_payload["total"] >= 1
    assert any(item["detail"].get("plugin_id") == "builtin.default_log_triage_flow" for item in audit_payload["items"])

    checkpoints_resp = client.get(f"/flows/checkpoints?case_id={case_id}")
    assert checkpoints_resp.status_code == 200
    cp_payload = checkpoints_resp.json()
    assert cp_payload["total"] >= 1
    assert any(item["flow_run_id"] == flow_run_id for item in cp_payload["items"])


def test_api_run_agent_case(monkeypatch) -> None:
    monkeypatch.setenv("ROOTSEEKER_LLM_ENABLED", "false")
    app = create_app(_repo_root())
    client = TestClient(app)

    response = client.post(
        "/cases/run-agent",
        json={
            "title": "Agent API case",
            "symptom": "error ratio high",
            "service_name": "order-service",
            "source": "api-agent-test",
            "metadata": {"trace_id": "trace-agent-api-1"},
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "completed"
    assert payload["case_id"].startswith("case-")
    assert payload["attempt_count"] >= 1
    assert payload["route_mode"] == "rule_flow"
    assert payload["case"] is not None
    assert payload["report"] is not None
    assert payload["evidence_count"] >= 1


def test_api_run_default_with_use_agent_flag(monkeypatch) -> None:
    monkeypatch.setenv("ROOTSEEKER_LLM_ENABLED", "false")
    app = create_app(_repo_root())
    client = TestClient(app)

    response = client.post(
        "/cases/run-default",
        json={
            "title": "Agent via run-default",
            "symptom": "error ratio high",
            "service_name": "order-service",
            "source": "api-test",
            "use_agent": True,
            "metadata": {"trace_id": "trace-run-default-agent-1"},
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["runner"] == "agent"
    assert payload["case_id"].startswith("case-")


def test_api_webhook_with_use_agent_flag(monkeypatch) -> None:
    monkeypatch.setenv("ROOTSEEKER_LLM_ENABLED", "false")
    app = create_app(_repo_root())
    client = TestClient(app)

    resp = client.post(
        "/webhook/webhook",
        json={
            "title": "Agent Webhook",
            "message": "Service latency high",
            "service_name": "payment-service",
            "use_agent": True,
            "trace_id": "trace-webhook-agent-001",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["runner"] == "agent"
    assert data["case_id"]


def test_api_webhook_rejects_invalid_signature(monkeypatch) -> None:
    secret = "integration-test-secret"
    monkeypatch.setenv("ROOTSEEKER_WEBHOOK_SIGNING_SECRET", secret)
    app = create_app(_repo_root())
    client = TestClient(app)
    payload = {
        "title": "Signed Alert",
        "message": "error",
        "service_name": "order-service",
        "_channel": "webhook",
    }

    resp = client.post("/webhook/webhook", json=payload, headers={"x-signature": "bad"})
    assert resp.status_code == 403

    expected = hmac.new(
        secret.encode("utf-8"),
        str(sorted(payload.items())).encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    ok = client.post(
        "/webhook/webhook",
        json=payload,
        headers={"x-signature": expected},
    )
    assert ok.status_code == 200
    assert ok.json()["ok"] is True


def test_api_webhook_generic_channel() -> None:
    """Test generic webhook channel."""
    app = create_app(_repo_root())
    client = TestClient(app)

    resp = client.post(
        "/webhook/webhook",
        json={
            "title": "Generic Alert",
            "message": "Service latency high",
            "service_name": "payment-service",
            "tenant": "acme",
            "environment": "prod",
            "severity": "critical",
            "team": "payment",
            "trace_id": "trace-webhook-001",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["case_id"]
    assert data["flow_run_id"]


def test_api_webhook_aliyun_channel() -> None:
    """Test Alibaba Cloud alert webhook."""
    app = create_app(_repo_root())
    client = TestClient(app)

    resp = client.post(
        "/webhook/aliyun",
        json={
            "alertName": "HighCPUUsage",
            "alertState": "ALARM",
            "curValue": "95%",
            "instanceName": "order-service-prod",
            "metricName": "cpu_utilization",
            "namespace": "acs_ecs",
            "tenant": "acme",
            "environment": "prod",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["case_id"]


def test_api_webhook_sls_channel() -> None:
    """Test SLS alert webhook."""
    app = create_app(_repo_root())
    client = TestClient(app)

    resp = client.post(
        "/webhook/sls",
        json={
            "alertName": "ErrorLogSpike",
            "project": "my-project",
            "logstore": "app-logs",
            "query": "level:ERROR",
            "count": 150,
            "message": "Error count exceeded threshold",
            "tenant": "acme",
            "environment": "prod",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["case_id"]


def test_api_webhook_prometheus_channel() -> None:
    """Test Prometheus Alertmanager webhook."""
    app = create_app(_repo_root())
    client = TestClient(app)

    resp = client.post(
        "/webhook/prometheus",
        json={
            "status": "firing",
            "alerts": [
                {
                    "status": "firing",
                    "labels": {
                        "alertname": "HighRequestLatency",
                        "service": "api-gateway",
                        "tenant": "acme",
                        "environment": "prod",
                    },
                    "annotations": {
                        "summary": "Request latency > 500ms",
                        "description": "P99 latency is 850ms",
                    },
                }
            ],
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["case_id"]
