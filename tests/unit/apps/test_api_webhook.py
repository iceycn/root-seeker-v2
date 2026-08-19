from pathlib import Path

from fastapi.testclient import TestClient

from apps.api.main import create_app
from tests.support.stub_planner import IncidentNormalizePlanner


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def test_webhook_ok_true_when_planner_succeeds() -> None:
    app = create_app(_repo_root(), tool_planner=IncidentNormalizePlanner())
    client = TestClient(app)

    resp = client.post(
        "/webhook/webhook",
        json={
            "title": "Generic Alert",
            "message": "Service latency high",
            "service_name": "payment-service",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["case_id"]


def test_webhook_ok_false_when_planner_missing(monkeypatch) -> None:
    monkeypatch.setenv("ROOTSEEKER_LLM_ENABLED", "false")
    app = create_app(_repo_root())
    client = TestClient(app)

    resp = client.post(
        "/webhook/webhook",
        json={
            "title": "Planner missing",
            "message": "no llm",
            "service_name": "payment-service",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is False
    assert data["case_id"]
