from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from apps.admin.main import create_app


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


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


def test_admin_builtin_skill_content_returns_standard_skill_md() -> None:
    client = TestClient(create_app(_repo_root()))

    response = client.get("/api/skills/base/default-log-triage/content")

    assert response.status_code == 200
    data = response.json()
    assert data["skill_md"].startswith("---\nname: Default log triage\n")
    assert "rootseeker-skill-spec" not in data["skill_md"]
    assert "\"slug\"" not in data["skill_md"]
    assert data["runtime_spec"]["slug"] == "base/default-log-triage"
    assert "flows/default-log-triage" in data["rootseeker_skill_yaml"]
    assert "tool_parameters" in data
    assert len(data["tool_parameters"]) > 0
    first_tool = data["tool_parameters"][0]
    assert "tool_name" in first_tool
    assert "parameters_schema" in first_tool


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


def test_admin_import_local_repo(tmp_path: Path) -> None:
    client = TestClient(create_app(tmp_path))
    local_repo = tmp_path / "local-repo"
    (local_repo / ".git").mkdir(parents=True)

    response = client.post(
        "/api/repos/import-local",
        json={"path": str(local_repo), "branch": "main"},
    )

    assert response.status_code == 200
    assert response.json()["ok"] is True
    repos = client.get("/api/repos").json()["repos"]
    assert repos[0]["name"] == "local-repo"
    assert repos[0]["local_path"] == str(local_repo.resolve())
    assert repos[0]["metadata"]["source"] == "local"


def test_admin_repo_remote_config_masks_token(tmp_path: Path) -> None:
    client = TestClient(create_app(tmp_path))

    response = client.post(
        "/api/repo-remotes",
        json={
            "name": "github-main",
            "provider": "github",
            "base_url": "https://github.com",
            "token": "ghp_secret1234",
        },
    )

    assert response.status_code == 200
    payload = response.json()["remote"]
    assert payload["token"] == ""
    assert payload["has_token"] is True
    assert payload["masked_token"].endswith("1234")
    listed = client.get("/api/repo-remotes").json()["items"][0]
    assert listed["token"] == ""
    assert listed["has_token"] is True


def test_admin_repo_remote_fills_default_base_url(tmp_path: Path) -> None:
    client = TestClient(create_app(tmp_path))

    response = client.post(
        "/api/repo-remotes",
        json={"name": "yunxiao-main", "provider": "yunxiao", "token": "yx-token", "owner": "org-1"},
    )

    assert response.status_code == 200
    assert response.json()["remote"]["base_url"] == "https://openapi-rdc.aliyuncs.com"


def test_admin_repo_remote_normalizes_generic_to_custom(tmp_path: Path) -> None:
    client = TestClient(create_app(tmp_path))

    response = client.post(
        "/api/repo-remotes",
        json={"name": "custom-main", "provider": "generic", "base_url": "https://git.example.com"},
    )

    assert response.status_code == 200
    assert response.json()["remote"]["provider"] == "custom"


def test_admin_discover_requires_existing_repo_remote(tmp_path: Path) -> None:
    client = TestClient(create_app(tmp_path))

    response = client.post("/api/repos/discover", json={"remote_name": "missing"})

    assert response.status_code == 404


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
    assert item["flow_run_id"].startswith("exec-")
    assert item["evidence_count"] >= 0
    assert item["evidence_summary"] == "default flow evidence"
    assert len(item["evidence_items"]) == item["evidence_count"]
    assert item["tool_results"]

    fresh = TestClient(create_app(tmp_path))
    history = fresh.get("/api/error-chat").json()
    assert history["total"] == 1
    assert history["items"][0]["case"]["case_id"] == item["case"]["case_id"]
    assert history["items"][0]["flow_run_id"] == item["flow_run_id"]
    assert history["items"][0]["evidence_items"] == item["evidence_items"]
