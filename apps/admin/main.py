from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

import httpx
from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from apps.admin.config_store import AdminConfigStore
from apps.admin.error_history import ErrorChatHistoryStore, build_error_history_store
from rootseeker.analysis.llm_report import LlmReportConfig, OpenAICompatibleReportClient
from rootseeker.bootstrap import DevRuntime, create_dev_runtime
from rootseeker.contracts.repository import RepositoryRef
from rootseeker.contracts.service_catalog import ServiceCatalogEntry
from rootseeker.contracts.skill import SkillSourceKind, SkillSpec
from rootseeker.contracts.tool import ToolCallRequest
from rootseeker.flow_runtime import build_execution_trace
from rootseeker.skill_system.parser import ROOTSEEKER_SKILL_SPEC_FILENAME

ADMIN_CASE_ID = "admin-console"
ADMIN_STEP_ID = "admin-route"
ADMIN_SKILL = "admin.console"
CODE_INDEX_PLUGIN_ID = "builtin.code_index"

BUILTIN_AI_PROVIDERS: list[dict[str, Any]] = [
    {
        "name": "jdcloud",
        "provider_type": "openai_compatible",
        "base_url": "https://modelservice.jdcloud.com/v1",
        "model": "GLM-5",
        "embedding_model": "",
        "embedding_dimension": 1536,
        "enabled": False,
        "builtin": True,
        "api_key_url": "https://modelservice.jdcloud.com/",
        "metadata": {"display_name": "京东云", "models": ["GLM-5", "Kimi-K2.5"]},
    },
    {
        "name": "deepseek",
        "provider_type": "openai_compatible",
        "base_url": "https://api.deepseek.com/v1",
        "model": "deepseek-chat",
        "embedding_model": "",
        "embedding_dimension": 1536,
        "enabled": False,
        "builtin": True,
        "api_key_url": "https://platform.deepseek.com/api_keys",
        "metadata": {
            "display_name": "深度求索 (DeepSeek)",
            "models": ["deepseek-chat", "deepseek-reasoner", "deepseek-v4-pro", "deepseek-v4-flash"],
        },
    },
    {
        "name": "zhipu",
        "provider_type": "openai_compatible",
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "model": "glm-4-plus",
        "embedding_model": "",
        "embedding_dimension": 1536,
        "enabled": False,
        "builtin": True,
        "api_key_url": "https://open.bigmodel.cn/usercenter/apikeys",
        "metadata": {"display_name": "智谱 AI", "models": ["glm-4-plus", "glm-4-air", "glm-4-flash"]},
    },
    {
        "name": "moonshot",
        "provider_type": "openai_compatible",
        "base_url": "https://api.moonshot.cn/v1",
        "model": "moonshot-v1-8k",
        "embedding_model": "",
        "embedding_dimension": 1536,
        "enabled": False,
        "builtin": True,
        "api_key_url": "https://platform.moonshot.cn/console/api-keys",
        "metadata": {
            "display_name": "月之暗面 (Moonshot)",
            "models": ["moonshot-v1-8k", "moonshot-v1-32k", "moonshot-v1-128k"],
        },
    },
    {
        "name": "silicon",
        "provider_type": "openai_compatible",
        "base_url": "https://api.siliconflow.cn/v1",
        "model": "deepseek-ai/DeepSeek-V3",
        "embedding_model": "",
        "embedding_dimension": 1536,
        "enabled": False,
        "builtin": True,
        "api_key_url": "https://cloud.siliconflow.cn/account/ak",
        "metadata": {
            "display_name": "硅基流动 (SiliconFlow)",
            "models": ["deepseek-ai/DeepSeek-V3", "deepseek-ai/DeepSeek-R1", "Qwen/Qwen2.5-72B-Instruct"],
        },
    },
    {
        "name": "modelscope",
        "provider_type": "openai_compatible",
        "base_url": "https://api-inference.modelscope.cn/v1",
        "model": "Qwen/Qwen2.5-72B-Instruct",
        "embedding_model": "",
        "embedding_dimension": 1536,
        "enabled": False,
        "builtin": True,
        "api_key_url": "https://modelscope.cn/my/myaccesstoken",
        "metadata": {
            "display_name": "魔搭 (ModelScope)",
            "models": ["Qwen/Qwen2.5-72B-Instruct", "deepseek-ai/DeepSeek-R1"],
        },
    },
    {
        "name": "minimax",
        "provider_type": "openai_compatible",
        "base_url": "https://api.minimax.chat/v1",
        "model": "MiniMax-M2.7",
        "embedding_model": "",
        "embedding_dimension": 1536,
        "enabled": False,
        "builtin": True,
        "api_key_url": "https://platform.minimaxi.com/user-center/basic-information/interface-key",
        "metadata": {"display_name": "MiniMax", "models": ["MiniMax-M2.7"]},
    },
    {
        "name": "dashscope",
        "provider_type": "openai_compatible",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "model": "qwen-max",
        "embedding_model": "text-embedding-v3",
        "embedding_dimension": 1024,
        "enabled": False,
        "builtin": True,
        "api_key_url": "https://bailian.console.aliyun.com/",
        "metadata": {"display_name": "百炼 (DashScope)", "models": ["qwen-max", "qwen-plus", "qwen-turbo"]},
    },
    {
        "name": "volces",
        "provider_type": "openai_compatible",
        "base_url": "https://ark.cn-beijing.volces.com/api/v3",
        "model": "",
        "embedding_model": "",
        "embedding_dimension": 1536,
        "enabled": False,
        "builtin": True,
        "api_key_url": "https://console.volcengine.com/ark",
        "metadata": {"display_name": "火山引擎", "models": ["doubao-pro", "doubao-lite"]},
    },
    {
        "name": "mimo",
        "provider_type": "openai_compatible",
        "base_url": "https://api.mimo.mi.com/v1",
        "model": "mimo-vl",
        "embedding_model": "",
        "embedding_dimension": 1536,
        "enabled": False,
        "builtin": True,
        "api_key_url": "https://platform.mimo.mi.com/",
        "metadata": {"display_name": "小米 MiMo", "models": ["mimo-vl", "mimo-reasoner"]},
    },
    {
        "name": "tencent-token-plan",
        "provider_type": "openai_compatible",
        "base_url": "https://api.lkeap.cloud.tencent.com/v1",
        "model": "",
        "embedding_model": "",
        "embedding_dimension": 1536,
        "enabled": False,
        "builtin": True,
        "api_key_url": "https://cloud.tencent.com/product/lkeap",
        "metadata": {"display_name": "腾讯云 Token Plan", "models": []},
    },
    {
        "name": "tencent-coding-plan",
        "provider_type": "openai_compatible",
        "base_url": "https://api.lkeap.cloud.tencent.com/v1",
        "model": "",
        "embedding_model": "",
        "embedding_dimension": 1536,
        "enabled": False,
        "builtin": True,
        "api_key_url": "https://cloud.tencent.com/product/lkeap",
        "metadata": {"display_name": "腾讯云 Coding Plan", "models": []},
    },
]


class AdminRegisterRepoRequest(BaseModel):
    name: str = Field(min_length=1)
    url: str | None = None
    branch: str = "main"
    local_path: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class AdminImportLocalRepoRequest(BaseModel):
    path: str = Field(min_length=1)
    name: str | None = None
    branch: str = "main"
    trigger_index: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class AdminDiscoverReposRequest(BaseModel):
    provider: str = Field(default="github")
    base_url: str = ""
    token: str = ""
    owner: str = ""
    api_path: str = ""
    query: str = ""
    page: int = Field(default=1, ge=1)
    per_page: int = Field(default=50, ge=1, le=100)


class AdminRepoRemoteRequest(BaseModel):
    name: str = Field(min_length=1)
    provider: str = Field(default="github")
    base_url: str = ""
    token: str = ""
    owner: str = ""
    api_path: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class AdminDiscoverReposFromRemoteRequest(BaseModel):
    remote_name: str = Field(min_length=1)
    owner: str = ""
    api_path: str = ""
    query: str = ""
    page: int = Field(default=1, ge=1)
    per_page: int = Field(default=50, ge=1, le=100)


class AdminSyncRepoRequest(BaseModel):
    trigger_index: bool = True


class AdminSemanticSearchRequest(BaseModel):
    query: str = Field(min_length=1)
    repo_name: str | None = None
    limit: int = Field(default=10, ge=1, le=100)


class AdminServiceCatalogUpsertRequest(BaseModel):
    tenant: str = Field(default="demo", min_length=1)
    environment: str = Field(default="prod", min_length=1)
    service_name: str = Field(min_length=1)
    display_name: str | None = None
    owner_team: str = ""
    language: str = ""
    runtime: str = ""
    repositories: list[dict[str, Any]] = Field(default_factory=list)
    log_sources: list[dict[str, Any]] = Field(default_factory=list)
    trace_sources: list[dict[str, Any]] = Field(default_factory=list)
    enabled_skills: list[str] = Field(default_factory=list)
    enabled_tools: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class AdminSettingsUpdateRequest(BaseModel):
    settings: dict[str, Any] = Field(default_factory=dict)


class AdminEnvVarRequest(BaseModel):
    key: str = Field(min_length=1)
    value: str = ""
    secret: bool = False
    scope: str = "runtime"


class AdminSkillUpsertRequest(BaseModel):
    spec: SkillSpec


class AdminQuickSkillRequest(BaseModel):
    name: str = Field(min_length=1)
    slug: str = Field(min_length=1)
    description: str = ""
    tags: str = ""
    triggers: str = ""
    required_tools: str = ""


class AdminAiProviderRequest(BaseModel):
    name: str = Field(min_length=1)
    provider_type: str = Field(default="openai_compatible")
    base_url: str = ""
    api_key: str = ""
    model: str = ""
    embedding_model: str = ""
    embedding_dimension: int = 1536
    enabled: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)


class AdminCallbackRequest(BaseModel):
    name: str = Field(min_length=1)
    channel: str = Field(default="webhook")
    url: str = Field(min_length=1)
    enabled: bool = True
    team: str = "default"
    secret: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class AdminErrorChatSubmitRequest(BaseModel):
    content: str = Field(min_length=1)
    service_name: str = "order-service"
    environment: str = "prod"
    severity: str = "error"
    trace_id: str = "trace-admin-error-chat"


ADMIN_STATIC_HTML = Path(__file__).with_name("static") / "admin.html"
ADMIN_WEB_DIST = Path(__file__).parents[1] / "admin-web" / "dist"
ADMIN_WEB_INDEX = ADMIN_WEB_DIST / "index.html"


def _invoke_admin_tool(runtime: DevRuntime, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    req = ToolCallRequest(
        case_id=ADMIN_CASE_ID,
        step_id=ADMIN_STEP_ID,
        skill_name=ADMIN_SKILL,
        tool_name=tool_name,
        arguments=arguments,
    )
    result = runtime.gateway.invoke(req, actor="admin", plugin_id=CODE_INDEX_PLUGIN_ID)
    if not result.ok:
        msg = result.error.message if result.error else "tool invocation failed"
        raise HTTPException(status_code=500, detail=msg)
    return result.content


def _load_admin_config(runtime: DevRuntime, store: AdminConfigStore) -> None:
    for repo in store.list_repos():
        runtime.gateway.invoke(
            ToolCallRequest(
                case_id=ADMIN_CASE_ID,
                step_id="load-config",
                skill_name=ADMIN_SKILL,
                tool_name="repo.register",
                arguments={
                    "name": repo.name,
                    "url": repo.url,
                    "branch": repo.default_branch or "main",
                    "metadata": repo.metadata,
                },
            ),
            actor="admin-config-loader",
            plugin_id=CODE_INDEX_PLUGIN_ID,
        )
    for entry in store.list_catalog():
        runtime.service_catalog.upsert(entry)
    for skill in store.list_skills():
        skill.source_kind = SkillSourceKind.CUSTOM
        runtime.skill_registry.upsert(skill)


def _builtin_skill_dir(config_root: Path, slug: str) -> Path:
    parts = [part for part in slug.split("/") if part]
    if not parts or any(part in {".", ".."} for part in parts):
        raise HTTPException(status_code=400, detail="invalid skill slug")
    return config_root / "skills" / "builtin" / Path(*parts)


def _read_skill_references(skill_dir: Path) -> list[dict[str, str]]:
    references_dir = skill_dir / "references"
    if not references_dir.is_dir():
        return []
    refs: list[dict[str, str]] = []
    for path in sorted(references_dir.glob("*.md")):
        refs.append(
            {
                "path": str(path.relative_to(skill_dir)),
                "title": path.stem,
                "content": path.read_text(encoding="utf-8"),
            }
        )
    return refs


def _join_url(base_url: str, path: str) -> str:
    return f"{base_url.rstrip('/')}/{path.lstrip('/')}"


def _normalize_repo_provider(provider: str) -> str:
    value = provider.lower().strip()
    if value == "codeup":
        return "yunxiao"
    if value == "generic":
        return "custom"
    return value or "github"


def _default_repo_base_url(provider: str) -> str:
    provider = _normalize_repo_provider(provider)
    if provider == "github":
        return "https://github.com"
    if provider == "gitee":
        return "https://gitee.com"
    if provider == "yunxiao":
        return "https://openapi-rdc.aliyuncs.com"
    return ""


def _repo_api_base(provider: str, base_url: str) -> str:
    provider = _normalize_repo_provider(provider)
    base = (base_url or _default_repo_base_url(provider)).rstrip("/")
    if provider == "github":
        if "api.github.com" in base:
            return base
        if base in {"https://github.com", "http://github.com"}:
            return "https://api.github.com"
        return _join_url(base, "api/v3")
    if provider == "gitee":
        return base if "/api/" in base else _join_url(base, "api/v5")
    if provider == "yunxiao":
        return "https://openapi-rdc.aliyuncs.com/oapi/v1/codeup"
    return base


def _repo_api_path(req: AdminDiscoverReposRequest) -> str:
    provider = _normalize_repo_provider(req.provider)
    if req.api_path:
        return req.api_path
    if provider == "github":
        return f"/orgs/{req.owner}/repos" if req.owner else "/user/repos"
    if provider == "gitee":
        return f"/orgs/{req.owner}/repos" if req.owner else "/user/repos"
    if provider == "yunxiao":
        if not req.owner:
            raise HTTPException(status_code=400, detail="organizationId is required for Yunxiao Codeup")
        return f"/organizations/{req.owner}/repositories"
    raise HTTPException(status_code=400, detail="api_path is required for this provider")


def _repo_auth_headers(provider: str, token: str) -> dict[str, str]:
    provider = _normalize_repo_provider(provider)
    headers = {"Accept": "application/json"}
    if not token:
        return headers
    if provider == "yunxiao":
        headers["x-yunxiao-token"] = token
        return headers
    if provider == "github":
        headers["Authorization"] = f"Bearer {token}"
    else:
        headers["Authorization"] = f"Bearer {token}"
        headers["PRIVATE-TOKEN"] = token
    return headers


def _extract_repo_items(data: Any) -> list[Any]:
    if isinstance(data, list):
        return data
    if not isinstance(data, dict):
        return []
    for key in ("repositories", "repos", "items", "data", "list"):
        value = data.get(key)
        if isinstance(value, list):
            return value
        if isinstance(value, dict):
            nested = _extract_repo_items(value)
            if nested:
                return nested
    return []


def _normalize_remote_repo(provider: str, item: Any) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None
    name = item.get("name") or item.get("path") or item.get("repoName")
    if not name:
        return None
    clone_url = (
        item.get("clone_url")
        or item.get("httpUrlToRepo")
        or item.get("http_url_to_repo")
        or item.get("html_url")
        or item.get("web_url")
        or item.get("webUrl")
        or item.get("ssh_url_to_repo")
        or item.get("sshUrlToRepo")
        or item.get("ssh_url")
    )
    ssh_url = item.get("ssh_url") or item.get("ssh_url_to_repo") or item.get("sshUrlToRepo")
    namespace = item.get("namespace")
    if isinstance(namespace, dict):
        namespace_name = namespace.get("path") or namespace.get("name")
    else:
        namespace_name = None
    full_name = (
        item.get("full_name")
        or item.get("fullName")
        or item.get("pathWithNamespace")
        or item.get("nameWithNamespace")
        or item.get("path_with_namespace")
    )
    if not full_name and namespace_name:
        full_name = f"{namespace_name}/{name}"
    return {
        "provider": provider,
        "name": str(name),
        "full_name": str(full_name or name),
        "clone_url": str(clone_url or ""),
        "ssh_url": str(ssh_url or ""),
        "web_url": str(item.get("html_url") or item.get("web_url") or ""),
        "default_branch": str(item.get("default_branch") or item.get("defaultBranch") or "main"),
        "private": bool(item.get("private") or item.get("visibility") == "private"),
        "raw": item,
    }


def _discover_remote_repos(req: AdminDiscoverReposRequest) -> dict[str, Any]:
    provider = _normalize_repo_provider(req.provider)
    base = _repo_api_base(provider, req.base_url)
    url = _join_url(base, _repo_api_path(req))
    params: dict[str, Any] = {"page": req.page, "per_page": req.per_page}
    if provider == "gitee" and req.token:
        params["access_token"] = req.token
    if provider == "yunxiao":
        params = {"page": req.page, "perPage": req.per_page}
    with httpx.Client(timeout=10.0) as client:
        response = client.get(url, headers=_repo_auth_headers(provider, req.token), params=params)
        response.raise_for_status()
        data = response.json()
    repos = [
        repo
        for repo in (_normalize_remote_repo(provider, item) for item in _extract_repo_items(data))
        if repo is not None
    ]
    query = req.query.strip().lower()
    if query:
        repos = [
            repo
            for repo in repos
            if query in str(repo.get("name", "")).lower() or query in str(repo.get("full_name", "")).lower()
        ]
    return {"ok": True, "provider": provider, "url": url, "repos": repos, "total": len(repos)}


def _mask_secret(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 8:
        return f"{value[:2]}******"
    return f"{value[:3]}******{value[-4:]}"


def _public_repo_remote(remote: dict[str, Any]) -> dict[str, Any]:
    payload = dict(remote)
    token = str(payload.get("token") or "")
    payload["token"] = ""
    payload["masked_token"] = _mask_secret(token)
    payload["has_token"] = bool(token)
    return payload


def _discover_repos_from_remote(store: AdminConfigStore, req: AdminDiscoverReposFromRemoteRequest) -> dict[str, Any]:
    remote = next((item for item in store.list_repo_remotes() if item.get("name") == req.remote_name), None)
    if remote is None:
        raise HTTPException(status_code=404, detail="repo remote not found")
    discover_req = AdminDiscoverReposRequest(
        provider=str(remote.get("provider") or "github"),
        base_url=str(remote.get("base_url") or ""),
        token=str(remote.get("token") or ""),
        owner=req.owner or str(remote.get("owner") or ""),
        api_path=req.api_path or str(remote.get("api_path") or ""),
        query=req.query,
        page=req.page,
        per_page=req.per_page,
    )
    return _discover_remote_repos(discover_req)


def _configured_ai_provider(store: AdminConfigStore) -> dict[str, Any] | None:
    settings = store.get_settings()
    default_name = settings.get("ROOTSEEKER_DEFAULT_AI_PROVIDER")
    providers_by_name = {item.get("name"): item for item in store.list_ai_providers()}
    if default_name and default_name in providers_by_name:
        return providers_by_name[default_name]
    for item in store.list_ai_providers():
        if item.get("api_key") and item.get("base_url"):
            return item
    return None


def _configured_ai_model(store: AdminConfigStore, provider: dict[str, Any]) -> str:
    return str(
        store.get_settings().get("ROOTSEEKER_DEFAULT_AI_MODEL")
        or provider.get("model")
        or (provider.get("metadata", {}).get("models") or [""])[0]
    )


def _has_ready_ai_provider(store: AdminConfigStore) -> bool:
    provider = _configured_ai_provider(store)
    if provider is None:
        return False
    return bool(str(provider.get("base_url") or "").strip() and str(provider.get("api_key") or "").strip() and _configured_ai_model(store, provider))


def _run_llm_analysis(
    *,
    store: AdminConfigStore,
    content: str,
    flow_result: Any,
) -> dict[str, Any]:
    provider = _configured_ai_provider(store)
    if provider is None:
        return {"ok": False, "skipped": True, "reason": "no configured AI provider"}
    base_url = str(provider.get("base_url") or "").rstrip("/")
    api_key = str(provider.get("api_key") or "")
    model = _configured_ai_model(store, provider)
    if not base_url or not api_key or not model:
        return {"ok": False, "skipped": True, "reason": "AI provider missing base_url/api_key/model"}
    config = LlmReportConfig(
        base_url=base_url,
        api_key=api_key,
        model=str(model),
        provider_name=str(provider.get("name") or provider.get("provider_type") or "admin"),
        timeout_seconds=60.0,
        temperature=0.2,
    )

    evidence_preview = [
        item.model_dump(mode="json")
        for item in flow_result.evidence_pack.items[:8]
    ]
    messages = [
        {
            "role": "system",
            "content": (
                "你是 RootSeeker 错误排查助手。请基于用户提交的错误信息、排查流程产生的 "
                "case/report/evidence，给出简洁的根因判断、排查证据和下一步建议。"
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                {
                    "error": content,
                    "case": flow_result.case.model_dump(mode="json"),
                    "report": flow_result.report.model_dump(mode="json"),
                    "evidence_preview": evidence_preview,
                },
                ensure_ascii=False,
            ),
        },
    ]
    result = OpenAICompatibleReportClient(config).complete(messages)
    return result.to_payload(include_content=True, include_raw=True)


def _run_and_store_llm_analysis(
    *,
    store: AdminConfigStore,
    history_store: ErrorChatHistoryStore,
    item_id: str,
    content: str,
    flow_result: Any,
) -> None:
    ai_analysis = _run_llm_analysis(store=store, content=content, flow_result=flow_result)
    history_store.update(item_id, {"ai_analysis": ai_analysis})


def _save_default_flow_checkpoint(runtime: DevRuntime, result: Any) -> str:
    trace = build_execution_trace(
        case_id=result.case.case_id,
        skill_slug=result.case.selected_skills[0] if result.case.selected_skills else "unknown",
        flow_id="builtin.default_log_triage_flow",
        case_steps=result.case.steps,
    )
    runtime.flow_checkpoint_store.save(
        trace.execution_id,
        {
            "case_id": result.case.case_id,
            "flow_id": trace.flow_id,
            "skill_slug": trace.skill_slug,
            "status": "completed",
            "next_step_index": len(trace.steps),
            "steps": [
                {
                    "step_id": step.step_id,
                    "name": step.name,
                    "status": step.status.value,
                    "tool_name": step.tool_name,
                }
                for step in trace.steps
            ],
        },
    )
    return trace.execution_id


def create_app(repo_root: Path | None = None) -> FastAPI:
    app = FastAPI(title="RootSeeker Admin", version="0.1.0")
    config_root = Path(repo_root or Path.cwd())
    runtime_root = config_root if (config_root / "plugins" / "builtin").exists() else Path.cwd()
    runtime = create_dev_runtime(runtime_root)
    store = AdminConfigStore(config_root / "data" / "admin" / "config.json")
    history_store = build_error_history_store(config_root)
    _load_admin_config(runtime, store)

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/")
    @app.get("/admin")
    @app.get("/models")
    @app.get("/advanced-settings")
    @app.get("/skills")
    @app.get("/repos")
    @app.get("/catalog")
    @app.get("/plugins")
    @app.get("/callbacks")
    @app.get("/semantic-search")
    @app.get("/error-chat")
    @app.get("/overview")
    def admin_page() -> FileResponse:
        if ADMIN_WEB_INDEX.exists():
            return FileResponse(ADMIN_WEB_INDEX)
        return FileResponse(ADMIN_STATIC_HTML)

    @app.get("/assets/{path:path}")
    def admin_assets(path: str) -> FileResponse:
        target = ADMIN_WEB_DIST / "assets" / path
        if not target.exists():
            raise HTTPException(status_code=404, detail="asset not found")
        return FileResponse(target)

    @app.get("/api/status")
    def status() -> dict[str, Any]:
        return {
            "health": {"status": "ok"},
            "skills_total": len(runtime.skill_registry.list_skills()),
            "plugins_total": len(runtime.plugin_registry.list_plugins()),
            "repos": _invoke_admin_tool(runtime, "repo.list", {}),
            "index": _invoke_admin_tool(runtime, "index.get_status", {}),
            "catalog": {"total": len(runtime.service_catalog.list_entries())},
            "config_path": str(store.path),
        }

    @app.get("/api/settings")
    def get_settings() -> dict[str, Any]:
        return {"settings": store.get_settings(), "config_path": str(store.path)}

    @app.put("/api/settings")
    def update_settings(req: AdminSettingsUpdateRequest) -> dict[str, Any]:
        return {"ok": True, "settings": store.update_settings(req.settings), "config_path": str(store.path)}

    @app.get("/api/env-vars")
    def list_env_vars() -> dict[str, Any]:
        items = store.list_env_vars()
        return {
            "items": [
                {**item, "masked_value": "******" if item.get("secret") and item.get("value") else item.get("value", "")}
                for item in items
            ],
            "total": len(items),
        }

    @app.post("/api/env-vars")
    def upsert_env_var(req: AdminEnvVarRequest) -> dict[str, Any]:
        store.upsert_env_var(req.key, req.value, secret=req.secret, scope=req.scope)
        return {"ok": True, "item": req.model_dump(mode="json")}

    @app.delete("/api/env-vars/{key}")
    def delete_env_var(key: str) -> dict[str, Any]:
        store.delete_env_var(key)
        return {"ok": True, "key": key}

    @app.get("/api/ai-providers")
    def list_ai_providers() -> dict[str, Any]:
        settings = store.get_settings()
        configured_by_name = {item.get("name"): item for item in store.list_ai_providers()}
        items: list[dict[str, Any]] = []
        for provider in BUILTIN_AI_PROVIDERS:
            merged = dict(provider)
            if provider["name"] in configured_by_name:
                configured = configured_by_name[provider["name"]]
                metadata = dict(provider.get("metadata", {}))
                metadata.update(configured.get("metadata", {}))
                merged.update(configured)
                merged["metadata"] = metadata
                merged["builtin"] = True
            items.append(merged)
        for provider in store.list_ai_providers():
            if provider.get("name") not in {item["name"] for item in BUILTIN_AI_PROVIDERS}:
                items.append(provider)
        return {
            "items": items,
            "total": len(items),
            "default_provider": settings.get("ROOTSEEKER_DEFAULT_AI_PROVIDER"),
            "default_model": settings.get("ROOTSEEKER_DEFAULT_AI_MODEL"),
        }

    @app.post("/api/ai-providers")
    def upsert_ai_provider(req: AdminAiProviderRequest) -> dict[str, Any]:
        payload = req.model_dump(mode="json")
        store.upsert_ai_provider(payload)
        settings: dict[str, Any] = {}
        if req.provider_type in {"openai_compatible", "http"}:
            settings["ROOTSEEKER_LLM_ENABLED"] = True
            settings["ROOTSEEKER_LLM_PROVIDER_NAME"] = req.name
            if req.base_url:
                settings["ROOTSEEKER_LLM_BASE_URL"] = req.base_url
                settings["ROOTSEEKER_EMBEDDING_BASE_URL"] = req.base_url
            if req.api_key:
                settings["ROOTSEEKER_LLM_API_KEY"] = req.api_key
                settings["ROOTSEEKER_EMBEDDING_API_KEY"] = req.api_key
            if req.model:
                settings["ROOTSEEKER_LLM_MODEL"] = req.model
            if req.embedding_model:
                settings["ROOTSEEKER_EMBEDDING_MODEL"] = req.embedding_model
                settings["ROOTSEEKER_EMBEDDING_PROVIDER"] = "openai_compatible"
            settings["ROOTSEEKER_EMBEDDING_DIMENSION"] = req.embedding_dimension
        if settings:
            store.update_settings(settings)
        return {"ok": True, "provider": payload, "settings": store.get_settings()}

    @app.post("/api/ai-providers/{name}/default")
    def set_default_ai_provider(name: str) -> dict[str, Any]:
        known = {item["name"] for item in BUILTIN_AI_PROVIDERS} | {
            str(item.get("name")) for item in store.list_ai_providers()
        }
        if name not in known:
            raise HTTPException(status_code=404, detail=f"AI provider not found: {name}")
        settings = store.set_default_ai_provider(name)
        return {"ok": True, "default_provider": name, "settings": settings}

    @app.post("/api/ai-providers/{name}/models/{model:path}/switch")
    def switch_default_ai_model(name: str, model: str) -> dict[str, Any]:
        known = {item["name"] for item in BUILTIN_AI_PROVIDERS} | {
            str(item.get("name")) for item in store.list_ai_providers()
        }
        if name not in known:
            raise HTTPException(status_code=404, detail=f"AI provider not found: {name}")
        settings = store.set_default_ai_model(name, model)
        return {"ok": True, "default_provider": name, "default_model": model, "settings": settings}

    @app.delete("/api/ai-providers/{name}")
    def delete_ai_provider(name: str) -> dict[str, Any]:
        store.delete_ai_provider(name)
        return {"ok": True, "name": name}

    @app.post("/api/ai-providers/{name}/test")
    def test_ai_provider(name: str) -> dict[str, Any]:
        provider = next((item for item in store.list_ai_providers() if item.get("name") == name), None)
        if provider is None:
            raise HTTPException(status_code=404, detail=f"AI provider not found: {name}")
        base_url = str(provider.get("base_url") or "").rstrip("/")
        if not base_url:
            return {"ok": False, "name": name, "error": "base_url is empty"}
        headers = {}
        api_key = str(provider.get("api_key") or "")
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        try:
            started = time.perf_counter()
            with httpx.Client(timeout=10.0, trust_env=False) as client:
                response = client.get(f"{base_url}/models", headers=headers)
                if response.status_code == 404:
                    response = client.get(base_url, headers=headers)
                elapsed_ms = int((time.perf_counter() - started) * 1000)
                return {
                    "ok": 200 <= response.status_code < 500,
                    "name": name,
                    "display_name": provider.get("metadata", {}).get("display_name") or name,
                    "response_ms": elapsed_ms,
                    "status_code": response.status_code,
                    "body_preview": response.text[:500],
                }
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "name": name, "error": str(exc)}

    @app.get("/api/callbacks")
    def list_callbacks() -> dict[str, Any]:
        items = store.list_callbacks()
        return {"items": items, "total": len(items)}

    @app.post("/api/callbacks")
    def upsert_callback(req: AdminCallbackRequest) -> dict[str, Any]:
        payload = req.model_dump(mode="json")
        store.upsert_callback(payload)
        env_key_by_channel = {
            "webhook": "ROOTSEEKER_NOTIFY_WEBHOOK_URL",
            "feishu": "ROOTSEEKER_NOTIFY_FEISHU_URL",
            "dingtalk": "ROOTSEEKER_NOTIFY_DINGTALK_URL",
            "wechat_work": "ROOTSEEKER_NOTIFY_WECHAT_WORK_URL",
            "slack": "ROOTSEEKER_NOTIFY_SLACK_URL",
            "discord": "ROOTSEEKER_NOTIFY_DISCORD_URL",
        }
        settings: dict[str, Any] = {
            "ROOTSEEKER_NOTIFY_TEAM": req.team,
            "ROOTSEEKER_NOTIFY_DEFAULT_URL": req.url,
        }
        channel_key = env_key_by_channel.get(req.channel)
        if channel_key:
            settings[channel_key] = req.url
        if req.secret:
            settings[f"ROOTSEEKER_NOTIFY_{req.channel.upper()}_SECRET"] = req.secret
        store.update_settings(settings)
        return {"ok": True, "callback": payload, "settings": store.get_settings()}

    @app.delete("/api/callbacks/{name}")
    def delete_callback(name: str) -> dict[str, Any]:
        store.delete_callback(name)
        return {"ok": True, "name": name}

    @app.post("/api/callbacks/{name}/test")
    def test_callback(name: str) -> dict[str, Any]:
        callback = next((item for item in store.list_callbacks() if item.get("name") == name), None)
        if callback is None:
            raise HTTPException(status_code=404, detail=f"callback not found: {name}")
        url = str(callback.get("url") or "")
        if not url:
            return {"ok": False, "name": name, "error": "url is empty"}
        try:
            with httpx.Client(timeout=10.0, trust_env=False) as client:
                response = client.post(
                    url,
                    json={
                        "source": "rootseeker-admin",
                        "event": "callback.test",
                        "message": "RootSeeker callback test",
                    },
                )
                return {
                    "ok": 200 <= response.status_code < 500,
                    "name": name,
                    "status_code": response.status_code,
                    "body_preview": response.text[:500],
                }
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "name": name, "error": str(exc)}

    @app.get("/api/error-chat")
    def list_error_chat() -> dict[str, Any]:
        items = history_store.list_items()
        return {"items": items, "total": len(items)}

    @app.post("/api/error-chat")
    def submit_error_chat(req: AdminErrorChatSubmitRequest, background_tasks: BackgroundTasks) -> dict[str, Any]:
        started = time.perf_counter()
        result = runtime.run_default_flow_from_payload(
            {
                "title": "错误排查请求",
                "service_name": req.service_name,
                "message": req.content,
                "source": "admin-error-chat",
                "tenant": "demo",
                "environment": req.environment,
                "severity": req.severity,
                "team": "default",
                "trace_id": req.trace_id,
            }
        )
        flow_elapsed_ms = int((time.perf_counter() - started) * 1000)
        flow_run_id = _save_default_flow_checkpoint(runtime, result)
        if _has_ready_ai_provider(store):
            ai_analysis = {"ok": False, "pending": True, "reason": "AI analysis is running"}
        else:
            ai_analysis = _run_llm_analysis(store=store, content=req.content, flow_result=result)
        item = history_store.append(
            {
                "role": "user",
                "content": req.content,
                "request": req.model_dump(mode="json"),
                "case": result.case.model_dump(mode="json"),
                "report": result.report.model_dump(mode="json"),
                "flow_run_id": flow_run_id,
                "evidence_count": len(result.evidence_pack.items),
                "evidence_summary": result.evidence_pack.summary,
                "evidence_items": [evidence.model_dump(mode="json") for evidence in result.evidence_pack.items],
                "flow_elapsed_ms": flow_elapsed_ms,
                "ai_analysis": ai_analysis,
                "tool_results": [tool.model_dump(mode="json") for tool in result.tool_results],
            }
        )
        if ai_analysis.get("pending"):
            background_tasks.add_task(
                _run_and_store_llm_analysis,
                store=store,
                history_store=history_store,
                item_id=str(item["id"]),
                content=req.content,
                flow_result=result,
            )
        return {"ok": True, "item": item}

    @app.delete("/api/error-chat")
    def clear_error_chat() -> dict[str, Any]:
        history_store.clear()
        return {"ok": True}

    @app.get("/api/skills")
    def list_skills() -> dict[str, Any]:
        items = [skill.model_dump(mode="json") for skill in runtime.skill_registry.list_skills()]
        return {"items": items, "total": len(items)}

    @app.get("/api/skills/{slug:path}/content")
    def get_skill_content(slug: str) -> dict[str, Any]:
        skill = runtime.skill_registry.get(slug)
        if skill is None:
            raise HTTPException(status_code=404, detail="skill not found")
        if skill.source_kind != SkillSourceKind.BUILTIN:
            return {
                "slug": slug,
                "source_kind": skill.source_kind.value,
                "skill_md": "",
                "runtime_spec": skill.model_dump(mode="json"),
            }
        skill_dir = _builtin_skill_dir(config_root, slug)
        skill_path = skill_dir / "SKILL.md"
        sidecar_path = skill_dir / ROOTSEEKER_SKILL_SPEC_FILENAME
        if not skill_path.exists():
            raise HTTPException(status_code=404, detail="SKILL.md not found")
        return {
            "slug": slug,
            "source_kind": skill.source_kind.value,
            "skill_md": skill_path.read_text(encoding="utf-8"),
            "rootseeker_skill_yaml": sidecar_path.read_text(encoding="utf-8") if sidecar_path.exists() else "",
            "references": _read_skill_references(skill_dir),
            "runtime_spec": skill.model_dump(mode="json"),
        }

    @app.get("/api/skills/{slug:path}")
    def get_skill(slug: str) -> dict[str, Any]:
        skill = runtime.skill_registry.get(slug)
        if skill is None:
            raise HTTPException(status_code=404, detail="skill not found")
        return skill.model_dump(mode="json")

    @app.put("/api/skills")
    def upsert_skill(req: AdminSkillUpsertRequest) -> dict[str, Any]:
        skill = req.spec
        skill.source_kind = SkillSourceKind.CUSTOM
        runtime.skill_registry.upsert(skill)
        store.upsert_skill(skill)
        return {"ok": True, "skill": skill.model_dump(mode="json")}

    @app.post("/api/skills/quick")
    def upsert_quick_skill(req: AdminQuickSkillRequest) -> dict[str, Any]:
        skill = SkillSpec(
            name=req.name,
            slug=req.slug,
            description=req.description,
            tags=[item.strip() for item in req.tags.split(",") if item.strip()],
            triggers=[item.strip() for item in req.triggers.split(",") if item.strip()],
            required_tools=[item.strip() for item in req.required_tools.split(",") if item.strip()],
            steps=[],
            source_kind=SkillSourceKind.CUSTOM,
            version="0.1.0",
            metadata={},
        )
        runtime.skill_registry.upsert(skill)
        store.upsert_skill(skill)
        return {"ok": True, "skill": skill.model_dump(mode="json")}

    @app.delete("/api/skills/{slug:path}")
    def delete_skill(slug: str) -> dict[str, Any]:
        removed = runtime.skill_registry.unregister(slug)
        store.delete_skill(slug)
        return {"ok": removed, "slug": slug}

    @app.get("/api/plugins")
    def list_plugins() -> dict[str, Any]:
        items = [plugin.model_dump(mode="json") for plugin in runtime.plugin_registry.list_plugins()]
        return {"items": items, "total": len(items)}

    @app.get("/api/tools")
    def list_tools() -> dict[str, Any]:
        items = [spec.model_dump(mode="json") for spec in runtime.tool_registry.list_specs()]
        return {"items": items, "total": len(items)}

    @app.get("/api/repos")
    def list_repos(state: str | None = None) -> dict[str, Any]:
        return _invoke_admin_tool(runtime, "repo.list", {"state": state} if state else {})

    @app.get("/api/repo-remotes")
    def list_repo_remotes() -> dict[str, Any]:
        items = [_public_repo_remote(item) for item in store.list_repo_remotes()]
        return {"items": items, "total": len(items)}

    @app.post("/api/repo-remotes")
    def upsert_repo_remote(req: AdminRepoRemoteRequest) -> dict[str, Any]:
        existing = next((item for item in store.list_repo_remotes() if item.get("name") == req.name), {})
        token = req.token or str(existing.get("token") or "")
        payload = req.model_dump(mode="json")
        payload["provider"] = _normalize_repo_provider(str(payload.get("provider") or "github"))
        payload["base_url"] = payload.get("base_url") or _default_repo_base_url(str(payload["provider"]))
        remote = store.upsert_repo_remote({**payload, "token": token})
        return {"ok": True, "remote": _public_repo_remote(remote)}

    @app.delete("/api/repo-remotes/{name}")
    def delete_repo_remote(name: str) -> dict[str, Any]:
        store.delete_repo_remote(name)
        return {"ok": True, "name": name}

    @app.post("/api/repos/discover")
    def discover_repos(req: AdminDiscoverReposFromRemoteRequest) -> dict[str, Any]:
        try:
            return _discover_repos_from_remote(store, req)
        except httpx.HTTPStatusError as e:
            raise HTTPException(status_code=e.response.status_code, detail=e.response.text) from e
        except httpx.HTTPError as e:
            raise HTTPException(status_code=502, detail=str(e)) from e

    @app.post("/api/repos")
    def register_repo(req: AdminRegisterRepoRequest) -> dict[str, Any]:
        result = _invoke_admin_tool(
            runtime,
            "repo.register",
            {
                "name": req.name,
                "url": req.url,
                "branch": req.branch,
                "local_path": req.local_path,
                "metadata": req.metadata,
            },
        )
        repo_payload = result.get("repo")
        if isinstance(repo_payload, dict):
            store.upsert_repo(RepositoryRef.model_validate(repo_payload))
        return result

    @app.post("/api/repos/import-local")
    def import_local_repo(req: AdminImportLocalRepoRequest) -> dict[str, Any]:
        local_path = Path(req.path).expanduser().resolve()
        if not local_path.is_dir():
            raise HTTPException(status_code=400, detail="local path is not a directory")
        if not (local_path / ".git").exists():
            raise HTTPException(status_code=400, detail="local path is not a git repository")
        name = req.name or local_path.name
        metadata = {"source": "local", **req.metadata}
        result = _invoke_admin_tool(
            runtime,
            "repo.register",
            {
                "name": name,
                "url": None,
                "branch": req.branch,
                "local_path": str(local_path),
                "metadata": metadata,
            },
        )
        repo_payload = result.get("repo")
        if isinstance(repo_payload, dict):
            store.upsert_repo(RepositoryRef.model_validate(repo_payload))
        if req.trigger_index:
            sync_result = _invoke_admin_tool(runtime, "repo.sync", {"name": name, "trigger_index": True})
            return {"ok": bool(result.get("ok")) and bool(sync_result.get("ok")), "repo": repo_payload, "sync": sync_result}
        return result

    @app.get("/api/repos/{repo_name}")
    def get_repo(repo_name: str) -> dict[str, Any]:
        return _invoke_admin_tool(runtime, "repo.get", {"name": repo_name})

    @app.delete("/api/repos/{repo_name}")
    def unregister_repo(repo_name: str) -> dict[str, Any]:
        result = _invoke_admin_tool(runtime, "repo.unregister", {"name": repo_name})
        store.delete_repo(repo_name)
        return result

    @app.post("/api/repos/{repo_name}/sync")
    def sync_repo(repo_name: str, req: AdminSyncRepoRequest) -> dict[str, Any]:
        return _invoke_admin_tool(runtime, "repo.sync", {"name": repo_name, "trigger_index": req.trigger_index})

    @app.get("/api/repos/{repo_name}/index-status")
    def repo_index_status(repo_name: str) -> dict[str, Any]:
        return _invoke_admin_tool(runtime, "repo.index_status", {"name": repo_name})

    @app.post("/api/code/semantic-search")
    def semantic_search(req: AdminSemanticSearchRequest) -> dict[str, Any]:
        return _invoke_admin_tool(
            runtime,
            "repo.semantic_search",
            {"query": req.query, "repo_name": req.repo_name, "limit": req.limit},
        )

    @app.get("/api/catalog")
    def list_catalog() -> dict[str, Any]:
        items = [entry.model_dump(mode="json") for entry in runtime.service_catalog.list_entries()]
        return {"items": items, "total": len(items)}

    @app.post("/api/catalog")
    def upsert_catalog(req: AdminServiceCatalogUpsertRequest) -> dict[str, Any]:
        entry = ServiceCatalogEntry(
            tenant=req.tenant,
            environment=req.environment,
            service_name=req.service_name,
            display_name=req.display_name or req.service_name,
            owner_team=req.owner_team,
            language=req.language,
            runtime=req.runtime,
            repositories=req.repositories,
            log_sources=req.log_sources,
            trace_sources=req.trace_sources,
            enabled_skills=req.enabled_skills,
            enabled_tools=req.enabled_tools,
            metadata=req.metadata,
        )
        runtime.service_catalog.upsert(entry)
        store.upsert_catalog(entry)
        return {"ok": True, "entry": entry.model_dump(mode="json")}

    @app.delete("/api/catalog/{tenant}/{environment}/{service_name}")
    def delete_catalog(tenant: str, environment: str, service_name: str) -> dict[str, Any]:
        store.delete_catalog(tenant, environment, service_name)
        # Runtime catalog is in-memory; rebuild deletion by replacing with config-backed entries.
        runtime.service_catalog.remove(tenant, environment, service_name)
        return {"ok": True, "tenant": tenant, "environment": environment, "service_name": service_name}

    app.state.runtime = runtime
    return app


app = create_app()


def main() -> int:
    import uvicorn

    host = os.getenv("ADMIN_HOST", "127.0.0.1")
    port = int(os.getenv("ADMIN_PORT", "8010"))
    uvicorn.run("apps.admin.main:app", host=host, port=port, reload=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
