from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from apps.admin.main import create_app


def test_admin_health_status_and_page(tmp_path: Path) -> None:
    client = TestClient(create_app(tmp_path))

    health = client.get("/healthz")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"

    page = client.get("/admin")
    assert page.status_code == 200
    assert '<div id="root">' in page.text
    assert "/assets/" in page.text

    status = client.get("/api/status")
    assert status.status_code == 200
    assert "skills_total" in status.json()


def test_admin_repo_register_and_list(tmp_path: Path) -> None:
    client = TestClient(create_app(tmp_path))

    response = client.post(
        "/api/repos",
        json={"name": "repo-admin", "url": "https://example.invalid/repo.git", "branch": "main"},
    )
    assert response.status_code == 200
    assert response.json()["ok"] is True

    repos = client.get("/api/repos")
    assert repos.status_code == 200
    assert repos.json()["total"] == 1


def test_admin_catalog_upsert_and_list(tmp_path: Path) -> None:
    client = TestClient(create_app(tmp_path))

    response = client.post(
        "/api/catalog",
        json={"service_name": "billing-service", "display_name": "Billing Service"},
    )
    assert response.status_code == 200
    assert response.json()["entry"]["service_name"] == "billing-service"

    catalog = client.get("/api/catalog")
    assert catalog.status_code == 200
    assert any(item["service_name"] == "billing-service" for item in catalog.json()["items"])


def test_admin_config_persists_repo_catalog_skill_and_settings(tmp_path: Path) -> None:
    client = TestClient(create_app(tmp_path))
    client.post(
        "/api/repos",
        json={"name": "repo-admin", "url": "https://example.invalid/repo.git", "branch": "main"},
    )
    client.post(
        "/api/catalog",
        json={"service_name": "billing-service", "display_name": "Billing Service"},
    )
    client.put("/api/settings", json={"settings": {"theme": "dark"}})
    env_result = client.post(
        "/api/env-vars",
        json={"key": "OPENAI_API_KEY", "value": "sk-test", "secret": True, "scope": "mcp"},
    )
    assert env_result.status_code == 200
    client.post(
        "/api/ai-providers",
        json={
            "name": "openai-main",
            "provider_type": "openai_compatible",
            "base_url": "https://api.example.com/v1",
            "api_key": "sk-test",
            "model": "gpt-test",
            "embedding_model": "emb-test",
            "embedding_dimension": 1536,
        },
    )
    client.post("/api/ai-providers/openai-main/default")
    switch = client.post("/api/ai-providers/openai-main/models/gpt-test/switch")
    assert switch.status_code == 200
    ai_test = client.post("/api/ai-providers/openai-main/test")
    assert ai_test.status_code == 200
    client.post(
        "/api/callbacks",
        json={
            "name": "ops-webhook",
            "channel": "webhook",
            "url": "https://hooks.example.com/rootseeker",
            "team": "ops",
        },
    )
    cb_test = client.post("/api/callbacks/ops-webhook/test")
    assert cb_test.status_code == 200
    client.put(
        "/api/skills",
        json={
            "spec": {
                "name": "Custom Skill",
                "slug": "custom/admin",
                "description": "admin configured",
                "tags": ["custom"],
                "triggers": [],
                "required_tools": [],
                "steps": [],
                "source_kind": "custom",
                "version": "0.1.0",
                "metadata": {},
            }
        },
    )
    quick = client.post(
        "/api/skills/quick",
        json={"name": "Quick Skill", "slug": "custom/quick", "tags": "a,b"},
    )
    assert quick.status_code == 200

    fresh = TestClient(create_app(tmp_path))

    assert fresh.get("/api/repos").json()["total"] == 1
    assert any(
        item["service_name"] == "billing-service"
        for item in fresh.get("/api/catalog").json()["items"]
    )
    assert fresh.get("/api/settings").json()["settings"]["theme"] == "dark"
    settings = fresh.get("/api/settings").json()["settings"]
    assert settings["ROOTSEEKER_DEFAULT_AI_PROVIDER"] == "openai-main"
    assert settings["ROOTSEEKER_DEFAULT_AI_MODEL"] == "gpt-test"
    assert settings["ROOTSEEKER_LLM_ENABLED"] is True
    assert settings["ROOTSEEKER_LLM_PROVIDER_NAME"] == "openai-main"
    assert settings["OPENAI_API_KEY"] == "sk-test"
    env_vars = fresh.get("/api/env-vars").json()
    assert env_vars["items"][0]["masked_value"] == "******"
    assert settings["ROOTSEEKER_NOTIFY_WEBHOOK_URL"] == "https://hooks.example.com/rootseeker"
    providers = fresh.get("/api/ai-providers").json()
    assert providers["total"] >= 6
    assert any(item["name"] == "openai-main" for item in providers["items"])
    assert fresh.get("/api/callbacks").json()["total"] == 1
    assert fresh.get("/api/skills/custom/admin").status_code == 200
    assert fresh.get("/api/skills/custom/quick").status_code == 200


def test_admin_error_chat_runs_default_flow_and_persists_history(tmp_path: Path) -> None:
    client = TestClient(create_app(tmp_path))

    response = client.post("/api/error-chat", json={"content": "NullPointerException at Foo.java:12"})

    assert response.status_code == 200
    item = response.json()["item"]
    assert item["content"] == "NullPointerException at Foo.java:12"
    assert item["case"]["case_id"].startswith("case-")
    assert "report" in item
    assert item["evidence_count"] >= 0

    fresh = TestClient(create_app(tmp_path))
    history = fresh.get("/api/error-chat").json()
    assert history["total"] == 1
    assert history["items"][0]["case"]["case_id"] == item["case"]["case_id"]
