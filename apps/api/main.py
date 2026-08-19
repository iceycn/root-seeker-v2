from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request, Response, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from rootseeker.agent_runtime.result import AgentRunResult
from apps.admin.config_store import build_admin_config_store
from rootseeker.bootstrap import DefaultFlowRunResult, DevRuntime, create_dev_runtime
from rootseeker.channel_routing import (
    ChannelMessage,
    build_channel_security_from_settings,
    ingest_channel_message,
    webhook_payload_to_case_create,
)
from rootseeker.contracts.tool import ToolCallRequest
from rootseeker.flow_runtime import FlowRuntime, build_execution_trace
from rootseeker.gateway import GatewayRequestFrame, GatewayResponseFrame, build_gateway_server
from rootseeker.gateway.ws_bridge import GatewayWsBridge
from rootseeker.gateway.websocket_transport import WebSocketTransport
from rootseeker.observability import build_runtime_health, render_prometheus_metrics


class RunCaseRequest(BaseModel):
    title: str = Field(min_length=1)
    symptom: str = Field(min_length=1)
    service_name: str = Field(min_length=1)
    source: str = Field(default="api", min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)
    use_agent: bool = False


class WebhookResponse(BaseModel):
    ok: bool
    case_id: str | None = None
    flow_run_id: str | None = None
    message: str = ""
    runner: str | None = None


class RegisterRepoRequest(BaseModel):
    """注册仓库请求"""

    name: str = Field(min_length=1, description="仓库名称")
    url: str = Field(min_length=1, description="Git 仓库 URL")
    branch: str = Field(default="main", description="默认分支")
    metadata: dict[str, Any] = Field(default_factory=dict, description="扩展元数据")


class SyncRepoRequest(BaseModel):
    """同步仓库请求"""

    trigger_index: bool = Field(default=True, description="是否触发索引")
    force_reclone: bool = Field(default=False, description="是否删除本地目录后重新 clone")


class RepoResponse(BaseModel):
    """仓库操作响应"""

    ok: bool
    message: str = ""
    repo: dict[str, Any] | None = None


class SyncRepoResponse(BaseModel):
    """同步仓库响应"""

    ok: bool
    repo_name: str
    message: str
    state: str
    zoekt_status: dict[str, Any] | None = None
    qdrant_status: dict[str, Any] | None = None
    gitnexus_status: dict[str, Any] | None = None


class ListRepoResponse(BaseModel):
    """仓库列表响应"""

    ok: bool
    repos: list[dict[str, Any]]
    total: int


class SemanticSearchRequest(BaseModel):
    query: str = Field(min_length=1, description="语义搜索查询")
    repo_name: str | None = Field(default=None, description="限定仓库名")
    limit: int = Field(default=10, ge=1, le=100, description="返回数量")


class FindCallersRequest(BaseModel):
    call_chain: list[str] = Field(default_factory=list, description="运行时调用链帧")
    class_name: str | None = Field(default=None, description="类名")
    method_name: str | None = Field(default=None, description="方法名")
    file_path: str | None = Field(default=None, description="文件路径")
    line: int | None = Field(default=None, description="行号")
    repo: str | None = Field(default=None, description="限定仓库")
    service_name: str | None = Field(default=None, description="服务名")
    max_depth: int = Field(default=3, ge=1, le=10, description="调用链追踪深度")
    limit: int = Field(default=20, ge=1, le=100, description="返回数量")
    prefer_graph: bool = Field(default=True, description="优先使用 GitNexus 知识图谱")


class GraphSymbolRequest(BaseModel):
    symbol: str = Field(min_length=1)
    direction: str = Field(default="upstream")
    repo: str | None = None
    file: str | None = None
    uid: str | None = None
    kind: str | None = None


class GraphQueryRequest(BaseModel):
    search_query: str | None = None
    query: str | None = None
    repo: str | None = None


class GraphCypherRequest(BaseModel):
    query: str = Field(min_length=1)
    repo: str | None = None


class GraphTraceRequest(BaseModel):
    source: str = Field(min_length=1)
    target: str = Field(min_length=1)
    repo: str | None = None


class CatalogResolveRequest(BaseModel):
    tenant: str = Field(default="demo", min_length=1)
    environment: str = Field(default="prod", min_length=1)
    service_name: str = Field(min_length=1)


class CatalogLogSourcesRequest(BaseModel):
    tenant: str = Field(default="demo", min_length=1)
    environment: str = Field(default="prod", min_length=1)
    service_name: str = Field(min_length=1)


class LogQueryByTraceRequest(BaseModel):
    trace_id: str = Field(min_length=1)
    service_name: str | None = None


class LogQueryByTemplateRequest(BaseModel):
    template_id: str = Field(min_length=1)
    service_name: str | None = None


class TraceChainRequest(BaseModel):
    trace_id: str = Field(min_length=1)


class CodeSearchRequest(BaseModel):
    query: str = Field(min_length=1)


class CodeReadRequest(BaseModel):
    path: str = Field(min_length=1)
    repo: str | None = None


class NotifySendRequest(BaseModel):
    channel: str = Field(min_length=1)
    message: str = Field(min_length=1)


class LspReferencesRequest(BaseModel):
    symbol: str = Field(min_length=1)


class LspPositionRequest(BaseModel):
    file_path: str = Field(min_length=1)
    line: int = Field(ge=1)
    character: int = Field(ge=0)


class LspSymbolsRequest(BaseModel):
    file_path: str = Field(min_length=1)


_API_REST_CASE_ID = "api-internal-rest"
_API_REST_STEP_ID = "route"
_API_REST_SKILL = "api.internal_gateway"
_REPO_CODE_INDEX_PLUGIN_ID = "builtin.code_index"
_PLUGIN_BY_TOOL_PREFIX = {
    "catalog": "builtin.service_catalog",
    "log": "builtin.log_query",
    "trace": "builtin.log_query",
    "notify": "builtin.notify",
}


def _plugin_id_for_tool(tool_name: str) -> str:
    prefix = tool_name.split(".", 1)[0]
    return _PLUGIN_BY_TOOL_PREFIX.get(prefix, _REPO_CODE_INDEX_PLUGIN_ID)


def _invoke_internal_tool(
    runtime: DevRuntime,
    tool_name: str,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    """REST 路由统一通过内置 MCP（McpGateway + internal ToolRegistry）执行。"""
    req = ToolCallRequest(
        case_id=_API_REST_CASE_ID,
        step_id=_API_REST_STEP_ID,
        skill_name=_API_REST_SKILL,
        tool_name=tool_name,
        arguments=arguments,
    )
    result = runtime.gateway.invoke(
        req,
        actor="rest-api",
        plugin_id=_plugin_id_for_tool(tool_name),
    )
    if not result.ok:
        msg = result.error.message if result.error else "tool invocation failed"
        raise HTTPException(status_code=500, detail=msg)
    return result.content


def _invoke_builtin_repo_tool(
    runtime: DevRuntime,
    tool_name: str,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    """仓库相关 REST 路由（兼容旧名，委托 _invoke_internal_tool）。"""
    return _invoke_internal_tool(runtime, tool_name, arguments)


def _agent_flow_run_id(result: AgentRunResult) -> str | None:
    if result.trace_id:
        return result.trace_id
    if result.attempts:
        return result.attempts[-1].flow_run_id
    return None


def _build_agent_api_response(runtime: DevRuntime, result: AgentRunResult) -> dict[str, Any]:
    case = runtime.case_store.get(result.case_id)
    report = runtime.report_store.get(result.case_id)
    pack = runtime.evidence_store.get_pack(result.case_id)
    return {
        "case_id": result.case_id,
        "status": result.status,
        "trace_id": result.trace_id,
        "attempt_count": len(result.attempts),
        "route_mode": result.metadata.get("route_mode"),
        "runner": "agent",
        "flow_run_id": _agent_flow_run_id(result),
        "case": case.model_dump(mode="json") if case is not None else None,
        "report": report.model_dump(mode="json") if report is not None else None,
        "evidence_count": len(pack.items) if pack is not None else 0,
        "attempts": [
            {
                "attempt_id": attempt.attempt_id,
                "status": attempt.status,
                "route_mode": attempt.route.mode,
                "tool_trace_count": len(attempt.tool_traces),
            }
            for attempt in result.attempts
        ],
    }


def _build_default_api_response(
    runtime: DevRuntime,
    flow_runtime: FlowRuntime,
    result: DefaultFlowRunResult,
) -> dict[str, Any]:
    case_payload = result.case.model_dump(mode="json")
    report_payload = result.report.model_dump(mode="json")
    trace = build_execution_trace(
        case_id=result.case.case_id,
        skill_slug=result.case.selected_skills[0] if result.case.selected_skills else "unknown",
        flow_id="builtin.default_log_triage_flow",
        case_steps=result.case.steps,
    )
    flow_runtime.checkpoints.save(
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
    return {
        "case": case_payload,
        "report": report_payload,
        "evidence_count": len(result.evidence_pack.items),
        "flow_run_id": trace.execution_id,
        "runner": "default_flow",
        "tool_results": [r.model_dump(mode="json") for r in result.tool_results],
    }


def create_app(repo_root: Path | None = None, *, tool_planner: Any = None) -> FastAPI:
    app = FastAPI(title="RootSeeker API", version="0.1.0")

    repo_root = Path(repo_root or Path.cwd())
    admin_store = build_admin_config_store(repo_root)
    runtime = create_dev_runtime(
        repo_root,
        node_role="api",
        mcp_extra_env=admin_store.mcp_runtime_env(),
        mcp_extra_env_provider=admin_store.mcp_runtime_env,
        tool_planner=tool_planner,
    )
    flow_runtime = FlowRuntime(runtime)

    # WebSocket Gateway (must be created before routes that flush broadcasts)
    ws_transport = WebSocketTransport()
    gateway_server = build_gateway_server(runtime)
    gateway_ws_bridge = GatewayWsBridge(gateway_server, ws_transport)

    def _forward_case_completed(payload: dict[str, Any]) -> None:
        case_id = str(payload.get("case_id", ""))
        if not case_id:
            return
        gateway_ws_bridge.publish(f"case.{case_id}", payload)

    runtime.event_bus.subscribe("case.completed", _forward_case_completed)

    @app.get("/system/presence")
    def list_system_presence() -> dict[str, Any]:
        nodes = runtime.presence_registry.list_nodes()
        return {
            "items": [
                {
                    "node_id": node.node_id,
                    "role": node.role,
                    "last_seen_at": node.last_seen_at.isoformat(),
                    "metadata": dict(node.metadata),
                }
                for node in nodes
            ],
            "total": len(nodes),
        }

    @app.get("/healthz")
    def healthz() -> dict[str, Any]:
        return build_runtime_health(runtime)

    @app.get("/readyz")
    def readyz() -> dict[str, Any]:
        return build_runtime_health(runtime)

    @app.get("/metrics")
    def metrics() -> Response:
        return Response(
            content=render_prometheus_metrics(runtime),
            media_type="text/plain; version=0.0.4; charset=utf-8",
        )

    @app.get("/skills")
    def list_skills() -> dict[str, list[dict[str, Any]]]:
        return {
            "items": [
                {
                    "slug": s.slug,
                    "name": s.name,
                    "version": s.version,
                    "source_kind": s.source_kind.value,
                }
                for s in runtime.skill_registry.list_skills()
            ]
        }

    @app.post("/cases/run-default")
    async def run_default_case(req: RunCaseRequest) -> dict[str, Any]:
        payload = req.model_dump(mode="json")
        flow_result = runtime.run_flow_from_payload(payload)
        await gateway_ws_bridge.flush_broadcasts()
        if isinstance(flow_result, AgentRunResult):
            return _build_agent_api_response(runtime, flow_result)
        return _build_default_api_response(runtime, flow_runtime, flow_result)

    @app.post("/cases/run-agent")
    async def run_agent_case(req: RunCaseRequest) -> dict[str, Any]:
        """Run a case through AgentRuntime (LLM tool plan with default-flow fallback)."""
        from rootseeker.contracts.case import CaseCreateRequest

        case_request = CaseCreateRequest.model_validate(req.model_dump(mode="json"))
        result = runtime.run_agent_from_case_request(case_request)
        await gateway_ws_bridge.flush_broadcasts()
        return _build_agent_api_response(runtime, result)

    @app.get("/cases/{case_id}")
    def get_case(case_id: str) -> dict[str, Any]:
        case = runtime.case_store.get(case_id)
        if case is None:
            raise HTTPException(status_code=404, detail="case not found")
        return case.model_dump(mode="json")

    @app.get("/reports/{case_id}")
    def get_report(case_id: str) -> dict[str, Any]:
        report = runtime.report_store.get(case_id)
        if report is None:
            raise HTTPException(status_code=404, detail="report not found")
        return report.model_dump(mode="json")

    @app.get("/evidence/{case_id}")
    def get_evidence(case_id: str) -> dict[str, Any]:
        pack = runtime.evidence_store.get_pack(case_id)
        if pack is None:
            raise HTTPException(status_code=404, detail="evidence not found")
        return pack.model_dump(mode="json")

    @app.get("/cases/{case_id}/audit")
    def get_case_audit(case_id: str, limit: int = 200) -> dict[str, Any]:
        events = runtime.audit_log.list_events(case_id=case_id, limit=limit)
        return {"items": [event.model_dump(mode="json") for event in events], "total": len(events)}

    @app.get("/flows/checkpoints")
    def list_flow_checkpoints(
        case_id: str | None = None,
        status: str | None = None,
        limit: int = 200,
    ) -> dict[str, Any]:
        items = flow_runtime.list_checkpoints(case_id=case_id, status=status, limit=limit)
        return {"items": items, "total": len(items)}

    @app.post("/webhook/{channel}", response_model=WebhookResponse)
    async def handle_webhook(channel: str, request: Request) -> WebhookResponse:
        """Handle incoming webhook from external alerting systems.

        This endpoint:
        1. Receives raw payload from external channel (aliyun/sls/prometheus/webhook)
        2. Normalizes via ingest_channel_message
        3. Triggers default flow
        4. Returns case_id and flow_run_id

        Supported channels:
        - webhook: Generic webhook with standard payload format
        - aliyun: Alibaba Cloud alert
        - sls: SLS alert
        - prometheus: Prometheus alertmanager webhook
        """
        try:
            payload = await request.json()
        except Exception:
            payload = {}

        # Add channel to payload for normalization
        payload["_channel"] = channel

        # Normalize through channel routing
        msg = ChannelMessage(
            channel=channel,
            payload=payload,
            headers=dict(request.headers),
            remote_ip=request.client.host if request.client else None,
        )
        try:
            normalized = ingest_channel_message(
                msg,
                security=build_channel_security_from_settings(),
            )
        except ValueError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc

        # Build CaseCreateRequest from normalized message
        metadata = dict(normalized.metadata)
        if normalized.trace_id:
            metadata["trace_id"] = normalized.trace_id
        metadata.setdefault("tenant", normalized.tenant)
        metadata.setdefault("environment", normalized.environment)
        metadata.setdefault("severity", normalized.severity)
        metadata.setdefault("team", normalized.team)

        from rootseeker.contracts.case import CaseCreateRequest

        case_request = CaseCreateRequest(
            title=normalized.title,
            symptom=normalized.symptom,
            service_name=normalized.service_name,
            source=channel,
            metadata=metadata,
        )

        flow_result = runtime.run_flow_from_case_request(
            case_request,
            use_agent=runtime._resolve_use_agent_from_payload(payload, case_request),
        )

        if isinstance(flow_result, AgentRunResult):
            flow_run_id = _agent_flow_run_id(flow_result)
            await gateway_ws_bridge.flush_broadcasts()
            ok = flow_result.status == "completed"
            return WebhookResponse(
                ok=ok,
                case_id=flow_result.case_id,
                flow_run_id=flow_run_id,
                runner="agent",
                message=f"Webhook processed via agent for channel: {channel}",
            )

        result = flow_result
        status = result.case.status.value
        trace = build_execution_trace(
            case_id=result.case.case_id,
            skill_slug=result.case.selected_skills[0] if result.case.selected_skills else "unknown",
            flow_id="builtin.default_log_triage_flow",
            case_steps=result.case.steps,
        )

        # Save checkpoint
        flow_runtime.checkpoints.save(
            trace.execution_id,
            {
                "case_id": result.case.case_id,
                "flow_id": trace.flow_id,
                "skill_slug": trace.skill_slug,
                "status": status,
                "next_step_index": len(trace.steps),
                "steps": [
                    {
                        "step_id": step.step_id,
                        "name": step.name,
                        "status": step.status.value,
                        "tool_name": step.tool_name,
                        "outputs": result.case.steps[idx].outputs
                        if idx < len(result.case.steps)
                        else {},
                    }
                    for idx, step in enumerate(trace.steps)
                ],
            },
        )

        await gateway_ws_bridge.flush_broadcasts()
        return WebhookResponse(
            ok=status == "completed",
            case_id=result.case.case_id,
            flow_run_id=trace.execution_id,
            runner="default_flow",
            message=f"Webhook processed successfully via channel: {channel}",
        )

    @app.websocket("/gateway/ws")
    async def gateway_websocket(websocket: WebSocket) -> None:
        """WebSocket endpoint for Gateway control plane.

        Protocol:
        - Client connects and receives connection_id
        - Client can subscribe to topics: {"frame_type": "subscribe", "topic": "case.{case_id}"}
        - Server broadcasts events: {"frame_type": "event", "topic": "...", "payload": {...}}
        - Heartbeat: server sends ping, client responds with pong
        """
        conn = await ws_transport.accept(websocket)
        connection_id = conn.connection_id
        gateway_ws_bridge.ensure_client(connection_id)

        # Send connection established message
        await websocket.send_json(
            {
                "frame_type": "connected",
                "connection_id": connection_id,
            }
        )

        # Start heartbeat task
        heartbeat_task = asyncio.create_task(ws_transport.heartbeat_loop(connection_id))

        try:
            while True:
                data = await websocket.receive_json()
                frame = await ws_transport.handle_message(connection_id, data)
                if isinstance(frame, GatewayRequestFrame):
                    response = gateway_server.handle_request(frame)
                    if frame.method == "gateway.publish" and response.ok:
                        topic = str(frame.params.get("topic", ""))
                        payload = frame.params.get("payload", {})
                        if topic and isinstance(payload, dict):
                            gateway_ws_bridge.queue_broadcast(topic, payload)
                    await gateway_ws_bridge.flush_broadcasts()
                    await websocket.send_json(response.model_dump(mode="json"))
                elif isinstance(frame, GatewayResponseFrame):
                    await websocket.send_json(frame.model_dump(mode="json"))
        except WebSocketDisconnect:
            pass
        except Exception:
            pass
        finally:
            heartbeat_task.cancel()
            gateway_ws_bridge.disconnect(connection_id)
            await ws_transport.close(connection_id, reason="disconnect")

    @app.get("/gateway/connections")
    def list_gateway_connections() -> dict[str, Any]:
        """List all active Gateway WebSocket connections."""
        connections = ws_transport.list_connections()
        return {
            "items": [
                {
                    "connection_id": c.connection_id,
                    "client_id": c.client_id,
                    "remote_addr": c.remote_addr,
                    "is_alive": c.is_alive,
                }
                for c in connections
            ],
            "total": len(connections),
        }

    # Internal tool HTTP bridge（供 HttpInternalToolAdapter 与远程进程转发）
    # ========================================

    @app.post("/catalog/resolve_service")
    def catalog_resolve_service(req: CatalogResolveRequest) -> dict[str, Any]:
        return _invoke_internal_tool(
            runtime,
            "catalog.resolve_service",
            req.model_dump(mode="json"),
        )

    @app.post("/catalog/get_log_sources")
    def catalog_get_log_sources(req: CatalogLogSourcesRequest) -> dict[str, Any]:
        return _invoke_internal_tool(
            runtime,
            "catalog.get_log_sources",
            req.model_dump(mode="json"),
        )

    @app.post("/log/query_by_trace_id")
    def log_query_by_trace_id(req: LogQueryByTraceRequest) -> dict[str, Any]:
        return _invoke_internal_tool(
            runtime,
            "log.query_by_trace_id",
            req.model_dump(mode="json", exclude_none=True),
        )

    @app.post("/log/query_by_template")
    def log_query_by_template(req: LogQueryByTemplateRequest) -> dict[str, Any]:
        return _invoke_internal_tool(
            runtime,
            "log.query_by_template",
            req.model_dump(mode="json", exclude_none=True),
        )

    @app.post("/trace/get_chain")
    def trace_get_chain(req: TraceChainRequest) -> dict[str, Any]:
        return _invoke_internal_tool(
            runtime,
            "trace.get_chain",
            req.model_dump(mode="json"),
        )

    @app.post("/code/search")
    def code_search(req: CodeSearchRequest) -> dict[str, Any]:
        return _invoke_internal_tool(runtime, "code.search", req.model_dump(mode="json"))

    @app.post("/code/read")
    def code_read(req: CodeReadRequest) -> dict[str, Any]:
        return _invoke_internal_tool(
            runtime,
            "code.read",
            req.model_dump(mode="json", exclude_none=True),
        )

    @app.post("/index/get_status")
    def index_get_status() -> dict[str, Any]:
        return _invoke_internal_tool(runtime, "index.get_status", {})

    @app.post("/notify/send")
    def notify_send(req: NotifySendRequest) -> dict[str, Any]:
        return _invoke_internal_tool(runtime, "notify.send", req.model_dump(mode="json"))

    @app.post("/lsp/references")
    def lsp_references(req: LspReferencesRequest) -> dict[str, Any]:
        return _invoke_internal_tool(
            runtime,
            "lsp.references",
            req.model_dump(mode="json"),
        )

    @app.post("/lsp/definition")
    def lsp_definition(req: LspPositionRequest) -> dict[str, Any]:
        return _invoke_internal_tool(
            runtime,
            "lsp.definition",
            req.model_dump(mode="json"),
        )

    @app.post("/lsp/hover")
    def lsp_hover(req: LspPositionRequest) -> dict[str, Any]:
        return _invoke_internal_tool(
            runtime,
            "lsp.hover",
            req.model_dump(mode="json"),
        )

    @app.post("/lsp/symbols")
    def lsp_symbols(req: LspSymbolsRequest) -> dict[str, Any]:
        return _invoke_internal_tool(
            runtime,
            "lsp.symbols",
            req.model_dump(mode="json"),
        )

    # Repository Management REST（薄封装：体内调用内置 MCP repo.* 工具，便于审计与策略统一）
    # ========================================

    @app.post("/repos", response_model=RepoResponse)
    def register_repo(req: RegisterRepoRequest) -> RepoResponse:
        """
        注册代码仓库

        - **name**: 仓库名称（唯一标识）
        - **url**: Git 仓库 URL
        - **branch**: 默认分支
        - **metadata**: 扩展元数据
        """
        content = _invoke_builtin_repo_tool(
            runtime,
            "repo.register",
            {
                "name": req.name,
                "url": req.url,
                "branch": req.branch,
                "metadata": req.metadata,
            },
        )
        if not content.get("ok"):
            raise HTTPException(
                status_code=400, detail=str(content.get("error", "register failed"))
            )

        return RepoResponse(
            ok=True,
            message=f"Repository '{req.name}' registered successfully",
            repo=content.get("repo"),
        )

    @app.get("/repos", response_model=ListRepoResponse)
    def list_repos(state: str | None = None) -> ListRepoResponse:
        """
        列出所有已注册的仓库

        - **state**: 可选，按状态过滤 (pending/syncing/indexing/completed/failed)
        """
        args: dict[str, Any] = {}
        if state:
            args["state"] = state
        content = _invoke_builtin_repo_tool(runtime, "repo.list", args)

        return ListRepoResponse(
            ok=bool(content.get("ok", True)),
            repos=list(content.get("repos", [])),
            total=int(content.get("total", 0)),
        )

    @app.get("/repos/{repo_name}", response_model=RepoResponse)
    def get_repo(repo_name: str) -> RepoResponse:
        """获取仓库详情"""
        content = _invoke_builtin_repo_tool(runtime, "repo.get", {"name": repo_name})
        if not content.get("ok"):
            raise HTTPException(status_code=404, detail=str(content.get("error", "not found")))

        return RepoResponse(
            ok=True,
            repo=content.get("repo"),
        )

    @app.delete("/repos/{repo_name}", response_model=RepoResponse)
    def unregister_repo(repo_name: str) -> RepoResponse:
        """注销仓库"""
        content = _invoke_builtin_repo_tool(runtime, "repo.unregister", {"name": repo_name})
        if not content.get("ok"):
            raise HTTPException(status_code=404, detail=str(content.get("message", "not found")))

        return RepoResponse(
            ok=True,
            message=str(content.get("message", "")),
        )

    @app.post("/repos/{repo_name}/sync", response_model=SyncRepoResponse)
    def sync_repo(repo_name: str, req: SyncRepoRequest) -> SyncRepoResponse:
        """
        同步仓库（Git clone/pull）并触发索引

        这是核心接口，执行以下操作：
        1. 如果仓库未克隆，执行 git clone
        2. 如果仓库已存在，执行 git pull
        3. 触发 Zoekt 代码索引
        4. （可选）触发 Qdrant 向量索引

        - **repo_name**: 仓库名称
        - **trigger_index**: 是否触发索引（默认 True）
        """
        content = _invoke_builtin_repo_tool(
            runtime,
            "repo.sync",
            {
                "name": repo_name,
                "trigger_index": req.trigger_index,
                "force_reclone": req.force_reclone,
            },
        )

        return SyncRepoResponse(
            ok=bool(content.get("ok", False)),
            repo_name=str(content.get("repo_name", repo_name)),
            message=str(content.get("message", "")),
            state=str(content.get("state", "")),
            zoekt_status=content.get("zoekt_status"),
            qdrant_status=content.get("qdrant_status"),
            gitnexus_status=content.get("gitnexus_status"),
        )

    @app.post("/repos/sync-all")
    def sync_all_repos(trigger_index: bool = True) -> dict[str, Any]:
        """同步所有已注册的仓库"""
        return _invoke_builtin_repo_tool(
            runtime,
            "repo.sync_all",
            {"trigger_index": trigger_index},
        )

    @app.post("/repos/sync-changed")
    def sync_changed_repos(trigger_index: bool = True) -> dict[str, Any]:
        """仅同步远端有变更的仓库，并对变更仓强制重建 GitNexus 图谱"""
        return _invoke_builtin_repo_tool(
            runtime,
            "repo.sync_changed",
            {"trigger_index": trigger_index},
        )

    @app.get("/repos/{repo_name}/index-status")
    def get_repo_index_status(repo_name: str) -> dict[str, Any]:
        """获取仓库的索引状态"""
        content = _invoke_builtin_repo_tool(
            runtime,
            "repo.index_status",
            {"name": repo_name},
        )
        if not content.get("ok"):
            raise HTTPException(status_code=400, detail=str(content.get("error", "failed")))
        return {
            "ok": True,
            "repo_name": content.get("repo_name", repo_name),
            "indexes": content.get("indexes", {}),
        }

    @app.post("/code/semantic-search")
    def semantic_search_code(req: SemanticSearchRequest) -> dict[str, Any]:
        """通过 Qdrant 对已索引代码块做语义搜索。"""
        content = _invoke_builtin_repo_tool(
            runtime,
            "repo.semantic_search",
            {"query": req.query, "repo_name": req.repo_name, "limit": req.limit},
        )
        if not content.get("ok"):
            raise HTTPException(
                status_code=400, detail=str(content.get("error", "semantic search failed"))
            )
        return content

    @app.post("/code/find_callers")
    def find_callers_code(req: FindCallersRequest) -> dict[str, Any]:
        """跨仓库静态调用链追踪，供 HTTP 内部适配器转发。"""
        content = _invoke_builtin_repo_tool(
            runtime,
            "code.find_callers",
            req.model_dump(mode="json", exclude_none=True),
        )
        return content

    @app.post("/graph/impact")
    def graph_impact(req: GraphSymbolRequest) -> dict[str, Any]:
        return _invoke_builtin_repo_tool(
            runtime, "graph.impact", req.model_dump(mode="json", exclude_none=True)
        )

    @app.post("/graph/context")
    def graph_context(req: GraphSymbolRequest) -> dict[str, Any]:
        return _invoke_builtin_repo_tool(
            runtime,
            "graph.context",
            {
                "symbol": req.symbol,
                "repo": req.repo,
                "file": req.file,
                "uid": req.uid,
            },
        )

    @app.post("/graph/query")
    def graph_query(req: GraphQueryRequest) -> dict[str, Any]:
        return _invoke_builtin_repo_tool(
            runtime, "graph.query", req.model_dump(mode="json", exclude_none=True)
        )

    @app.post("/graph/cypher")
    def graph_cypher(req: GraphCypherRequest) -> dict[str, Any]:
        return _invoke_builtin_repo_tool(
            runtime, "graph.cypher", req.model_dump(mode="json", exclude_none=True)
        )

    @app.post("/graph/trace")
    def graph_trace(req: GraphTraceRequest) -> dict[str, Any]:
        return _invoke_builtin_repo_tool(
            runtime, "graph.trace", req.model_dump(mode="json", exclude_none=True)
        )

    @app.post("/graph/list_repos")
    def graph_list_repos(limit: int | None = None, offset: int | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        if limit is not None:
            payload["limit"] = limit
        if offset is not None:
            payload["offset"] = offset
        return _invoke_builtin_repo_tool(runtime, "graph.list_repos", payload)

    @app.post("/graph/detect_changes")
    def graph_detect_changes(repo: str | None = None) -> dict[str, Any]:
        return _invoke_builtin_repo_tool(
            runtime, "graph.detect_changes", {"repo": repo} if repo else {}
        )

    app.state.runtime = runtime
    return app


app = create_app()
