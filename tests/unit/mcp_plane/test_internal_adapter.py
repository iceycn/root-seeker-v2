from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from mcp_servers.internal.handlers import register_internal_tools
from rootseeker.contracts.service_catalog import ServiceCatalogEntry
from rootseeker.contracts.tool import ToolCallRequest
from rootseeker.mcp_plane import McpGateway, PolicyGuard, ToolRegistry
from rootseeker.observability.audit import InMemoryAuditLog


@dataclass
class FixedAdapter:
    def resolve_service(self, tenant: str, environment: str, service_name: str) -> ServiceCatalogEntry:
        return ServiceCatalogEntry(
            tenant=tenant,
            environment=environment,
            service_name=service_name,
            display_name="fixed",
            log_sources=[{"type": "fixed", "source_id": "ls-1"}],
        )

    def get_log_sources(self, tenant: str, environment: str, service_name: str) -> list[dict[str, Any]]:
        return [{"type": "fixed", "source_id": "ls-1"}]

    def query_logs_by_trace_id(self, trace_id: str, service_name: str | None = None) -> dict[str, Any]:
        return {"query_key": f"trace:{trace_id}", "records": [], "truncated": False}

    def query_logs_by_template(self, template_id: str, service_name: str | None = None) -> dict[str, Any]:
        return {"query_key": f"tpl:{template_id}", "records": [], "truncated": False}

    def get_trace_chain(self, trace_id: str) -> dict[str, Any]:
        return {"trace_id": trace_id, "spans": []}

    def search_code(self, query: str) -> dict[str, Any]:
        return {"query": query, "hits": []}

    def read_code(self, path: str, repo: str | None = None) -> dict[str, Any]:
        return {"path": path, "content": ""}

    def get_index_status(self) -> dict[str, Any]:
        return {"ready": True, "indexes": []}

    def send_notification(self, channel: str, message: str) -> dict[str, Any]:
        return {"channel": channel, "message": message, "status": "sent"}

    def repo_register(self, args: dict[str, Any]) -> dict[str, Any]:
        return {"ok": False, "error": "repo tools not wired in FixedAdapter"}

    def repo_sync(self, args: dict[str, Any]) -> dict[str, Any]:
        return {"ok": False, "error": "repo tools not wired in FixedAdapter"}

    def repo_list(self, args: dict[str, Any]) -> dict[str, Any]:
        return {"ok": True, "repos": [], "total": 0}

    def repo_get(self, args: dict[str, Any]) -> dict[str, Any]:
        return {"ok": False, "error": "not found"}

    def repo_unregister(self, args: dict[str, Any]) -> dict[str, Any]:
        return {"ok": False, "message": "not found"}

    def repo_sync_all(self, args: dict[str, Any]) -> dict[str, Any]:
        return {"ok": True, "total": 0, "results": []}

    def repo_index_status(self, args: dict[str, Any]) -> dict[str, Any]:
        return {"ok": False, "error": "not wired"}


def test_register_internal_tools_with_custom_adapter() -> None:
    reg = ToolRegistry()
    register_internal_tools(reg, adapter=FixedAdapter())
    gw = McpGateway(reg, PolicyGuard(), InMemoryAuditLog())
    req = ToolCallRequest(
        case_id="c1",
        step_id="s1",
        skill_name="base/default-log-triage",
        tool_name="catalog.resolve_service",
        arguments={"tenant": "t1", "environment": "prod", "service_name": "svc-a"},
    )
    res = gw.invoke(req)
    assert res.ok
    assert res.content["entry"]["display_name"] == "fixed"
