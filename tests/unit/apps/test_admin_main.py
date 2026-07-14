from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

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

    response = client.get("/api/skills/flows/default-log-triage/content")

    assert response.status_code == 200
    data = response.json()
    assert data["skill_md"].startswith("---\nname: Default log triage\n")
    assert "rootseeker-skill-spec" not in data["skill_md"]
    assert "\"slug\"" not in data["skill_md"]
    assert data["runtime_spec"]["slug"] == "flows/default-log-triage"
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
        json={
            "name": "yunxiao-main",
            "provider": "yunxiao",
            "token": "yx-token",
            "owner": "org-1",
            "git_username": "clone-user",
        },
    )

    assert response.status_code == 200
    assert response.json()["remote"]["base_url"] == "https://openapi-rdc.aliyuncs.com"
    assert response.json()["remote"]["git_username"] == "clone-user"


def test_admin_repo_remote_normalizes_generic_to_custom(tmp_path: Path) -> None:
    client = TestClient(create_app(tmp_path))

    response = client.post(
        "/api/repo-remotes",
        json={"name": "custom-main", "provider": "generic", "base_url": "https://git.example.com"},
    )

    assert response.status_code == 200
    assert response.json()["remote"]["provider"] == "custom"


def test_admin_yunxiao_repo_api_path_supports_region_and_central_editions() -> None:
    from apps.admin.main import AdminDiscoverReposRequest, _repo_api_path

    region_req = AdminDiscoverReposRequest(provider="yunxiao", owner="")
    central_req = AdminDiscoverReposRequest(provider="yunxiao", owner="org-1")

    assert _repo_api_path(region_req) == "/repositories"
    assert _repo_api_path(central_req) == "/organizations/org-1/repositories"


def test_admin_yunxiao_repository_detail_path() -> None:
    from apps.admin.main import _yunxiao_repository_detail_path

    assert _yunxiao_repository_detail_path("", 2813489) == "/repositories/2813489"
    assert (
        _yunxiao_repository_detail_path("org-1", "org-1/DemoRepo")
        == "/organizations/org-1/repositories/org-1%2FDemoRepo"
    )


def test_admin_enrich_yunxiao_repo_merges_default_branch_and_clone_url() -> None:
    from apps.admin.main import _enrich_yunxiao_repo

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, str]:
            return {
                "defaultBranch": "master",
                "httpUrlToRepo": "https://codeup.aliyun.com/org/repo.git",
                "webUrl": "https://codeup.aliyun.com/org/repo",
            }

    class FakeClient:
        pass

    repo = {
        "name": "repo",
        "full_name": "org/repo",
        "clone_url": "",
        "default_branch": "",
        "raw": {"id": 2813489, "pathWithNamespace": "org/repo"},
    }

    with patch("apps.admin.main.get_with_retry", return_value=FakeResponse()):
        enriched = _enrich_yunxiao_repo(
            repo,
            base="https://openapi-rdc.aliyuncs.com/oapi/v1/codeup",
            owner="org-1",
            token="pt-token",
            client=FakeClient(),  # type: ignore[arg-type]
        )

    assert enriched["default_branch"] == "master"
    assert enriched["clone_url"] == "https://codeup.aliyun.com/org/repo.git"
    assert "raw" in enriched


def test_admin_discover_yunxiao_uses_list_payload_without_enrichment() -> None:
    from apps.admin.main import AdminDiscoverReposRequest, _discover_remote_repos

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, list[dict[str, str]]]:
            return {
                "repositories": [
                    {
                        "id": 2813489,
                        "name": "repo",
                        "pathWithNamespace": "org/repo",
                        "httpUrlToRepo": "https://codeup.aliyun.com/org/repo.git",
                        "webUrl": "https://codeup.aliyun.com/org/repo",
                        "defaultBranch": "master",
                        "visibility": "private",
                    }
                ]
            }

    req = AdminDiscoverReposRequest(
        provider="yunxiao",
        token="pt-token",
        owner="org-1",
        page=1,
        per_page=50,
    )

    with patch("apps.admin.main.get_with_retry", return_value=FakeResponse()) as get_with_retry_mock:
        with patch("apps.admin.main._enrich_yunxiao_repos_parallel") as enrich_mock:
            result = _discover_remote_repos(req)

    enrich_mock.assert_not_called()
    assert get_with_retry_mock.call_count == 1
    assert result["total"] == 1
    assert result["repos"][0]["clone_url"] == "https://codeup.aliyun.com/org/repo.git"
    assert result["repos"][0]["full_name"] == "org/repo"
    assert result["repos"][0]["default_branch"] == "master"
    assert "raw" not in result["repos"][0]


def test_admin_discover_yunxiao_enriches_when_list_lacks_clone_url() -> None:
    from apps.admin.main import AdminDiscoverReposRequest, _discover_remote_repos

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, list[dict[str, str]]]:
            return {
                "repositories": [
                    {
                        "id": 2813489,
                        "name": "repo",
                        "pathWithNamespace": "org/repo",
                        "webUrl": "https://codeup.aliyun.com/org/repo",
                        "visibility": "private",
                    }
                ]
            }

    req = AdminDiscoverReposRequest(
        provider="yunxiao",
        token="pt-token",
        owner="org-1",
        page=1,
        per_page=50,
    )

    with patch("apps.admin.main.get_with_retry", return_value=FakeResponse()):
        with patch(
            "apps.admin.main._enrich_yunxiao_repos_parallel",
            return_value=[
                {
                    "provider": "yunxiao",
                    "name": "repo",
                    "full_name": "org/repo",
                    "clone_url": "https://codeup.aliyun.com/org/repo.git",
                    "ssh_url": "",
                    "web_url": "https://codeup.aliyun.com/org/repo",
                    "default_branch": "master",
                    "private": True,
                    "raw": {"id": 2813489},
                }
            ],
        ) as enrich_mock:
            result = _discover_remote_repos(req)

    enrich_mock.assert_called_once()
    assert result["repos"][0]["clone_url"] == "https://codeup.aliyun.com/org/repo.git"
    assert result["repos"][0]["default_branch"] == "master"


def test_admin_public_discovered_repo_strips_raw_payload() -> None:
    from apps.admin.main import _public_discovered_repo

    payload = _public_discovered_repo({"name": "demo", "default_branch": "master", "raw": {"id": 1}})
    assert "raw" not in payload
    assert payload["default_branch"] == "master"


def test_admin_annotate_discovered_repo_import_status_matches_full_name_and_url() -> None:
    from rootseeker.contracts.repository import RepositoryRef, RepoSyncState, RepoSyncStatus

    from apps.admin.main import _annotate_discovered_repos_import_status

    registered = [
        RepositoryRef(
            name="org__repo",
            url="https://codeup.aliyun.com/org/repo.git",
            default_branch="main",
            sync_status=RepoSyncStatus(state=RepoSyncState.COMPLETED),
            metadata={"full_name": "org/repo", "source": "remote"},
        )
    ]
    repos = [
        {
            "full_name": "org/repo",
            "clone_url": "https://codeup.aliyun.com/org/repo.git",
            "provider": "yunxiao",
        },
        {
            "full_name": "org/other",
            "clone_url": "https://codeup.aliyun.com/org/other.git",
            "provider": "yunxiao",
        },
    ]

    annotated = _annotate_discovered_repos_import_status(repos, registered)

    assert annotated[0]["imported"] is True
    assert annotated[0]["registered_name"] == "org__repo"
    assert annotated[0]["sync_state"] == "completed"
    assert annotated[0]["reimportable"] is False
    assert annotated[1]["imported"] is False


def test_admin_annotate_discovered_repo_marks_failed_as_reimportable() -> None:
    from rootseeker.contracts.repository import RepositoryRef, RepoSyncState, RepoSyncStatus

    from apps.admin.main import _annotate_discovered_repos_import_status

    registered = [
        RepositoryRef(
            name="org__repo",
            url="https://codeup.aliyun.com/org/repo.git",
            default_branch="main",
            sync_status=RepoSyncStatus(state=RepoSyncState.FAILED, error_message="clone failed"),
            metadata={"full_name": "org/repo", "source": "remote"},
        )
    ]
    repos = [{"full_name": "org/repo", "clone_url": "https://codeup.aliyun.com/org/repo.git", "provider": "yunxiao"}]

    annotated = _annotate_discovered_repos_import_status(repos, registered)

    assert annotated[0]["imported"] is True
    assert annotated[0]["sync_state"] == "failed"
    assert annotated[0]["reimportable"] is True


def test_admin_discover_requires_existing_repo_remote(tmp_path: Path) -> None:
    client = TestClient(create_app(tmp_path))

    response = client.post("/api/repos/discover", json={"remote_name": "missing"})

    assert response.status_code == 404


def test_admin_discover_from_remote_prefers_request_owner_over_remote_default(tmp_path: Path) -> None:
    from apps.admin.main import AdminDiscoverReposFromRemoteRequest, _discover_repos_from_remote
    from apps.admin.config_store import AdminConfigStore

    store = AdminConfigStore(tmp_path / "admin" / "config.json")
    store.upsert_repo_remote(
        {
            "name": "yx-main",
            "provider": "yunxiao",
            "token": "yx-token",
            "owner": "org-default",
            "base_url": "https://openapi-rdc.aliyuncs.com",
        }
    )
    req = AdminDiscoverReposFromRemoteRequest(
        remote_name="yx-main",
        owner="",  # Region edition: empty owner must not be overwritten
        page=1,
        per_page=20,
    )

    with patch("apps.admin.main._discover_remote_repos") as discover_mock:
        discover_mock.return_value = {"repos": [], "total": 0}
        _discover_repos_from_remote(store, req)

    called = discover_mock.call_args.args[0]
    assert called.owner == ""
    assert called.provider == "yunxiao"

    req_override = AdminDiscoverReposFromRemoteRequest(
        remote_name="yx-main",
        owner="org-override",
        page=1,
        per_page=20,
    )
    with patch("apps.admin.main._discover_remote_repos") as discover_mock:
        discover_mock.return_value = {"repos": [], "total": 0}
        _discover_repos_from_remote(store, req_override)
    assert discover_mock.call_args.args[0].owner == "org-override"


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


def test_build_llm_error_chat_payload_stays_under_kimi_limit() -> None:
    import json
    from types import SimpleNamespace

    from apps.admin.main import KIMI_MESSAGE_BYTE_LIMIT, _build_llm_error_chat_payload

    huge = "x" * 20000
    steps = [
        {
            "step_id": f"step-{index}",
            "name": f"step-{index}",
            "tool_name": "log.query",
            "status": "completed",
            "inputs": {"query": huge},
            "outputs": {"lines": [huge]},
        }
        for index in range(12)
    ]
    evidence_items = [
        {
            "item_id": f"ev-{index}",
            "type": "log",
            "source": "tool",
            "content": huge,
        }
        for index in range(8)
    ]

    def _evidence_namespace(item: dict[str, Any]) -> SimpleNamespace:
        return SimpleNamespace(model_dump=lambda mode="json", payload=item: payload)

    flow_result = SimpleNamespace(
        case=SimpleNamespace(
            model_dump=lambda mode="json": {
                "case_id": "case-huge",
                "title": "huge case",
                "selected_skills": ["flows/default-log-triage"],
                "symptom": huge,
                "steps": steps,
            }
        ),
        report=SimpleNamespace(
            model_dump=lambda mode="json": {
                "summary": "rule summary",
                "root_cause": {
                    "title": "candidate",
                    "narrative": huge,
                    "confidence": 0.5,
                    "contributing_factors": ["factor"],
                },
                "metadata": {},
            }
        ),
        evidence_pack=SimpleNamespace(
            items=[_evidence_namespace(item) for item in evidence_items]
        ),
    )

    payload = _build_llm_error_chat_payload(content=huge, flow_result=flow_result)
    serialized = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    assert len(serialized) <= KIMI_MESSAGE_BYTE_LIMIT
    assert "call_chain" in payload
    assert payload["case"]["step_count"] == 12
    assert "inputs" not in payload["case"]["steps"][0]


def test_build_llm_error_chat_payload_hard_truncates_when_still_over_limit() -> None:
    import json
    from types import SimpleNamespace

    from apps.admin.main import _build_llm_error_chat_payload

    huge = "x" * 50000
    flow_result = SimpleNamespace(
        case=SimpleNamespace(
            model_dump=lambda mode="json": {
                "case_id": "case-hard",
                "title": "hard truncate",
                "selected_skills": ["flows/default-log-triage"],
                "symptom": huge,
                "steps": [],
            }
        ),
        report=SimpleNamespace(
            model_dump=lambda mode="json": {
                "summary": huge,
                "root_cause": {"title": "x", "narrative": huge, "confidence": 0.1},
                "metadata": {},
            }
        ),
        evidence_pack=SimpleNamespace(items=[]),
    )

    payload = _build_llm_error_chat_payload(
        content=huge,
        flow_result=flow_result,
        byte_limit=8_000,
    )
    serialized = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    assert len(serialized) <= 8_000
    assert payload.get("truncation", {}).get("reason") in {"payload_too_large", "payload_hard_truncated"}
