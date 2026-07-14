"""Prove every HttpInternalToolAdapter method hits the expected HTTP route."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from mcp_servers.internal.adapters import HttpInternalToolAdapter
from mcp_servers.internal.handlers import register_internal_tools
from rootseeker.contracts.tool import ToolCallRequest
from rootseeker.mcp_plane import McpGateway, PolicyGuard, ToolRegistry
from rootseeker.observability.audit import InMemoryAuditLog


class RecordingTransport(httpx.BaseTransport):
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict[str, Any]]] = []

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        body: dict[str, Any] = {}
        if request.content:
            raw = request.content.decode("utf-8")
            if raw:
                body = json.loads(raw)
        path = request.url.path
        self.calls.append((request.method, path, body))
        if path == "/catalog/resolve_service":
            return httpx.Response(
                200,
                json={
                    "entry": {
                        "tenant": body.get("tenant", "demo"),
                        "environment": body.get("environment", "prod"),
                        "service_name": body.get("service_name", "svc"),
                        "display_name": "HTTP",
                        "log_sources": [{"source_id": "http-log", "type": "http"}],
                        "repositories": [],
                        "trace_sources": [],
                        "metadata": {},
                    }
                },
            )
        if path == "/catalog/get_log_sources":
            return httpx.Response(200, json={"sources": [{"source_id": "http-log", "type": "http"}]})
        if path == "/code/find_callers":
            return httpx.Response(200, json={"static_callers": [], "timeout_hint": True})
        return httpx.Response(200, json={"ok": True, "path": path, "method": request.method})


@pytest.fixture
def transport() -> RecordingTransport:
    return RecordingTransport()


@pytest.fixture
def adapter(transport: RecordingTransport) -> HttpInternalToolAdapter:
    return HttpInternalToolAdapter(base_url="https://example.internal", transport=transport)


def test_http_adapter_every_method_hits_expected_route(
    adapter: HttpInternalToolAdapter,
    transport: RecordingTransport,
) -> None:
    expectations: list[tuple[str, Any, tuple, dict, str, str]] = [
        ("resolve_service", adapter.resolve_service, ("demo", "prod", "svc"), {}, "POST", "/catalog/resolve_service"),
        ("get_log_sources", adapter.get_log_sources, ("demo", "prod", "svc"), {}, "POST", "/catalog/get_log_sources"),
        ("query_logs_by_trace_id", adapter.query_logs_by_trace_id, ("t1",), {"service_name": "svc"}, "POST", "/log/query_by_trace_id"),
        ("query_logs_by_template", adapter.query_logs_by_template, ("tpl",), {}, "POST", "/log/query_by_template"),
        ("get_trace_chain", adapter.get_trace_chain, ("t1",), {}, "POST", "/trace/get_chain"),
        ("search_code", adapter.search_code, ("Foo",), {}, "POST", "/code/search"),
        ("semantic_search_code", adapter.semantic_search_code, ("Foo",), {"repo_name": "r", "limit": 3}, "POST", "/code/semantic-search"),
        ("read_code", adapter.read_code, ("a.py",), {"repo": "r"}, "POST", "/code/read"),
        ("find_callers", adapter.find_callers, ({"call_chain": ["A.b"]},), {}, "POST", "/code/find_callers"),
        ("get_index_status", adapter.get_index_status, (), {}, "POST", "/index/get_status"),
        ("send_notification", adapter.send_notification, ("webhook", "hi"), {}, "POST", "/notify/send"),
        ("repo_register", adapter.repo_register, ({"name": "r", "url": "https://x/r.git"},), {}, "POST", "/repos"),
        ("repo_sync", adapter.repo_sync, ({"name": "r", "force_reclone": True},), {}, "POST", "/repos/r/sync"),
        ("repo_list", adapter.repo_list, ({},), {}, "GET", "/repos"),
        ("repo_get", adapter.repo_get, ({"name": "r"},), {}, "GET", "/repos/r"),
        ("repo_unregister", adapter.repo_unregister, ({"name": "r"},), {}, "DELETE", "/repos/r"),
        ("repo_sync_all", adapter.repo_sync_all, ({"trigger_index": False},), {}, "POST", "/repos/sync-all"),
        ("repo_index_status", adapter.repo_index_status, ({"name": "r"},), {}, "GET", "/repos/r/index-status"),
        ("repo_semantic_search", adapter.repo_semantic_search, ({"query": "q"},), {}, "POST", "/code/semantic-search"),
        ("lsp_references", adapter.lsp_references, ({"symbol": "S"},), {}, "POST", "/lsp/references"),
        ("lsp_definition", adapter.lsp_definition, ({"file_path": "a.py", "line": 1, "character": 0},), {}, "POST", "/lsp/definition"),
        ("lsp_hover", adapter.lsp_hover, ({"file_path": "a.py", "line": 1, "character": 0},), {}, "POST", "/lsp/hover"),
        ("lsp_symbols", adapter.lsp_symbols, ({"file_path": "a.py"},), {}, "POST", "/lsp/symbols"),
    ]

    for name, method, args, kwargs, http_method, path in expectations:
        transport.calls.clear()
        method(*args, **kwargs)
        assert transport.calls, f"{name} made no HTTP call"
        got_method, got_path, _body = transport.calls[-1]
        assert got_method == http_method, name
        assert got_path == path, f"{name}: expected {path}, got {got_path}"


def test_http_adapter_find_callers_uses_extended_timeout(adapter: HttpInternalToolAdapter) -> None:
    assert adapter.find_callers_timeout_seconds == 120.0
    result = adapter.find_callers({"call_chain": ["A.b (A.java:1)"]})
    assert result["timeout_hint"] is True


def test_gateway_with_http_adapter_invokes_all_non_incident_tools(
    adapter: HttpInternalToolAdapter,
    transport: RecordingTransport,
) -> None:
    registry = ToolRegistry()
    register_internal_tools(registry, adapter=adapter)
    gw = McpGateway(registry, PolicyGuard(deny_write=False), InMemoryAuditLog())

    cases: list[tuple[str, dict[str, Any], str]] = [
        ("catalog.resolve_service", {"tenant": "demo", "environment": "prod", "service_name": "svc"}, "/catalog/resolve_service"),
        ("catalog.get_log_sources", {"tenant": "demo", "environment": "prod", "service_name": "svc"}, "/catalog/get_log_sources"),
        ("log.query_by_trace_id", {"trace_id": "t"}, "/log/query_by_trace_id"),
        ("log.query_by_template", {"template_id": "tpl"}, "/log/query_by_template"),
        ("trace.get_chain", {"trace_id": "t"}, "/trace/get_chain"),
        ("code.search", {"query": "x"}, "/code/search"),
        ("code.semantic_search", {"query": "x"}, "/code/semantic-search"),
        ("code.read", {"path": "a.py"}, "/code/read"),
        ("code.find_callers", {"call_chain": []}, "/code/find_callers"),
        ("index.get_status", {}, "/index/get_status"),
        ("notify.send", {"channel": "webhook", "message": "m"}, "/notify/send"),
        ("repo.register", {"name": "r", "url": "https://x/r.git"}, "/repos"),
        ("repo.sync", {"name": "r"}, "/repos/r/sync"),
        ("repo.list", {}, "/repos"),
        ("repo.get", {"name": "r"}, "/repos/r"),
        ("repo.unregister", {"name": "r"}, "/repos/r"),
        ("repo.sync_all", {}, "/repos/sync-all"),
        ("repo.index_status", {"name": "r"}, "/repos/r/index-status"),
        ("repo.semantic_search", {"query": "q"}, "/code/semantic-search"),
        ("lsp.references", {"symbol": "S"}, "/lsp/references"),
        ("lsp.definition", {"file_path": "a.py", "line": 1, "character": 0}, "/lsp/definition"),
        ("lsp.hover", {"file_path": "a.py", "line": 1, "character": 0}, "/lsp/hover"),
        ("lsp.symbols", {"file_path": "a.py"}, "/lsp/symbols"),
    ]

    for tool_name, arguments, expected_path in cases:
        transport.calls.clear()
        req = ToolCallRequest(
            case_id="c",
            step_id="s",
            skill_name="flows/default-log-triage",
            tool_name=tool_name,
            arguments=arguments,
        )
        result = gw.invoke(req, actor="unit-test")
        assert result.ok, f"{tool_name}: {result.error}"
        assert any(path == expected_path for _m, path, _b in transport.calls), (
            f"{tool_name} did not hit {expected_path}; calls={transport.calls}"
        )
