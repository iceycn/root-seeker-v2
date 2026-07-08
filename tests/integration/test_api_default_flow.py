from pathlib import Path

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
