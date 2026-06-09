from __future__ import annotations

from typing import Any

from mcp_servers.internal.adapters import InternalToolAdapter
from rootseeker.contracts.tool import ToolPermissionLevel, ToolScope, ToolSpec
from rootseeker.mcp_plane.registry import ToolRegistry
from rootseeker.service_catalog.memory_catalog import MemoryServiceCatalog

__all__ = ["register_internal_tools"]


def register_internal_tools(
    registry: ToolRegistry,
    *,
    adapter: InternalToolAdapter,
) -> MemoryServiceCatalog:
    """Register internal MCP handlers backed by an adapter."""

    def _invoke_catalog_resolve(args: dict[str, Any]) -> dict[str, Any]:
        tenant = str(args.get("tenant", "demo"))
        environment = str(args.get("environment", "prod"))
        service_name = str(args.get("service_name", "unknown"))
        entry = adapter.resolve_service(tenant, environment, service_name)
        return {"entry": entry.model_dump(mode="json")}

    def _invoke_catalog_log_sources(args: dict[str, Any]) -> dict[str, Any]:
        tenant = str(args.get("tenant", "demo"))
        environment = str(args.get("environment", "prod"))
        service_name = str(args.get("service_name", "unknown"))
        sources = adapter.get_log_sources(tenant, environment, service_name)
        return {"sources": sources, "service_name": service_name}

    def _invoke_log_by_trace(args: dict[str, Any]) -> dict[str, Any]:
        trace_id = str(args.get("trace_id", "trace-unknown"))
        service_name = str(args.get("service_name", "")) or None
        return adapter.query_logs_by_trace_id(trace_id, service_name=service_name)

    def _invoke_log_by_template(args: dict[str, Any]) -> dict[str, Any]:
        template_id = str(args.get("template_id", "tpl-unknown"))
        service_name = str(args.get("service_name", "")) or None
        return adapter.query_logs_by_template(template_id, service_name=service_name)

    def _invoke_trace_chain(args: dict[str, Any]) -> dict[str, Any]:
        trace_id = str(args.get("trace_id", "trace-unknown"))
        return adapter.get_trace_chain(trace_id)

    def _invoke_code_search(args: dict[str, Any]) -> dict[str, Any]:
        return adapter.search_code(str(args.get("query", "")))

    def _invoke_code_semantic_search(args: dict[str, Any]) -> dict[str, Any]:
        repo_name = args.get("repo_name")
        return adapter.semantic_search_code(
            str(args.get("query", "")),
            repo_name=str(repo_name) if repo_name else None,
            limit=int(args.get("limit", 10)),
        )

    def _invoke_code_read(args: dict[str, Any]) -> dict[str, Any]:
        return adapter.read_code(str(args.get("path", "README.md")))

    def _invoke_index_status(_args: dict[str, Any]) -> dict[str, Any]:
        return adapter.get_index_status()

    def _invoke_notify_send(args: dict[str, Any]) -> dict[str, Any]:
        channel = str(args.get("channel", "webhook"))
        message = str(args.get("message", ""))
        return adapter.send_notification(channel, message)

    def _repo_register(args: dict[str, Any]) -> dict[str, Any]:
        return adapter.repo_register(args)

    def _repo_sync(args: dict[str, Any]) -> dict[str, Any]:
        return adapter.repo_sync(args)

    def _repo_list(args: dict[str, Any]) -> dict[str, Any]:
        return adapter.repo_list(args)

    def _repo_get(args: dict[str, Any]) -> dict[str, Any]:
        return adapter.repo_get(args)

    def _repo_unregister(args: dict[str, Any]) -> dict[str, Any]:
        return adapter.repo_unregister(args)

    def _repo_sync_all(args: dict[str, Any]) -> dict[str, Any]:
        return adapter.repo_sync_all(args)

    def _repo_index_status(args: dict[str, Any]) -> dict[str, Any]:
        return adapter.repo_index_status(args)

    def _repo_semantic_search(args: dict[str, Any]) -> dict[str, Any]:
        return adapter.repo_semantic_search(args)

    def _lsp_references(args: dict[str, Any]) -> dict[str, Any]:
        return adapter.lsp_references(args)

    def _lsp_definition(args: dict[str, Any]) -> dict[str, Any]:
        return adapter.lsp_definition(args)

    def _lsp_hover(args: dict[str, Any]) -> dict[str, Any]:
        return adapter.lsp_hover(args)

    def _lsp_symbols(args: dict[str, Any]) -> dict[str, Any]:
        return adapter.lsp_symbols(args)

    internal = ToolScope.INTERNAL
    server = "internal"

    tools: list[tuple[ToolSpec, Any]] = [
        (
            ToolSpec(
                name="catalog.resolve_service",
                description="Resolve service catalog entry (internal adapter)",
                server_name=server,
                scope=internal,
                tags=["catalog"],
            ),
            _invoke_catalog_resolve,
        ),
        (
            ToolSpec(
                name="catalog.get_log_sources",
                description="List log sources for service (internal adapter)",
                server_name=server,
                scope=internal,
                tags=["catalog"],
            ),
            _invoke_catalog_log_sources,
        ),
        (
            ToolSpec(
                name="log.query_by_trace_id",
                description="Query logs by trace id (internal adapter)",
                server_name=server,
                scope=internal,
                tags=["log"],
            ),
            _invoke_log_by_trace,
        ),
        (
            ToolSpec(
                name="log.query_by_template",
                description="Query logs by template (internal adapter)",
                server_name=server,
                scope=internal,
                tags=["log"],
            ),
            _invoke_log_by_template,
        ),
        (
            ToolSpec(
                name="trace.get_chain",
                description="Fetch trace chain (internal adapter)",
                server_name=server,
                scope=internal,
                tags=["trace"],
            ),
            _invoke_trace_chain,
        ),
        (
            ToolSpec(
                name="code.search",
                description="Search code index (internal adapter)",
                server_name=server,
                scope=internal,
                tags=["code"],
            ),
            _invoke_code_search,
        ),
        (
            ToolSpec(
                name="code.semantic_search",
                description="Semantic search code chunks (Qdrant-backed internal adapter)",
                server_name=server,
                scope=internal,
                tags=["code"],
            ),
            _invoke_code_semantic_search,
        ),
        (
            ToolSpec(
                name="code.read",
                description="Read file from repo (internal adapter)",
                server_name=server,
                scope=internal,
                tags=["code"],
            ),
            _invoke_code_read,
        ),
        (
            ToolSpec(
                name="index.get_status",
                description="Indexing status (internal adapter)",
                server_name=server,
                scope=internal,
                tags=["index"],
            ),
            _invoke_index_status,
        ),
        (
            ToolSpec(
                name="notify.send",
                description="Send notification (internal adapter)",
                server_name=server,
                scope=internal,
                permission_level=ToolPermissionLevel.WRITE,
                tags=["notify"],
            ),
            _invoke_notify_send,
        ),
        (
            ToolSpec(
                name="repo.register",
                description="Register a code repository for indexing",
                server_name=server,
                scope=internal,
                permission_level=ToolPermissionLevel.WRITE,
                tags=["repo"],
            ),
            _repo_register,
        ),
        (
            ToolSpec(
                name="repo.sync",
                description="Sync repository (git clone/pull) and trigger indexing",
                server_name=server,
                scope=internal,
                permission_level=ToolPermissionLevel.WRITE,
                tags=["repo"],
            ),
            _repo_sync,
        ),
        (
            ToolSpec(
                name="repo.list",
                description="List all registered repositories",
                server_name=server,
                scope=internal,
                tags=["repo"],
            ),
            _repo_list,
        ),
        (
            ToolSpec(
                name="repo.get",
                description="Get repository details by name",
                server_name=server,
                scope=internal,
                tags=["repo"],
            ),
            _repo_get,
        ),
        (
            ToolSpec(
                name="repo.unregister",
                description="Unregister a repository from the sync manager",
                server_name=server,
                scope=internal,
                permission_level=ToolPermissionLevel.WRITE,
                tags=["repo"],
            ),
            _repo_unregister,
        ),
        (
            ToolSpec(
                name="repo.sync_all",
                description="Sync all registered repositories",
                server_name=server,
                scope=internal,
                permission_level=ToolPermissionLevel.WRITE,
                tags=["repo"],
            ),
            _repo_sync_all,
        ),
        (
            ToolSpec(
                name="repo.index_status",
                description="Get Zoekt/Qdrant index status for a repository",
                server_name=server,
                scope=internal,
                tags=["repo"],
            ),
            _repo_index_status,
        ),
        (
            ToolSpec(
                name="repo.semantic_search",
                description="Semantic search indexed repository chunks",
                server_name=server,
                scope=internal,
                tags=["repo", "code"],
            ),
            _repo_semantic_search,
        ),
        (
            ToolSpec(
                name="lsp.references",
                description="Find symbol references using LSP",
                server_name=server,
                scope=internal,
                tags=["lsp", "code"],
            ),
            _lsp_references,
        ),
        (
            ToolSpec(
                name="lsp.definition",
                description="Go to definition using LSP",
                server_name=server,
                scope=internal,
                tags=["lsp", "code"],
            ),
            _lsp_definition,
        ),
        (
            ToolSpec(
                name="lsp.hover",
                description="Get hover information using LSP",
                server_name=server,
                scope=internal,
                tags=["lsp", "code"],
            ),
            _lsp_hover,
        ),
        (
            ToolSpec(
                name="lsp.symbols",
                description="Get document symbols using LSP",
                server_name=server,
                scope=internal,
                tags=["lsp", "code"],
            ),
            _lsp_symbols,
        ),
    ]

    for spec, handler in tools:
        registry.register(spec, handler)

    mem = getattr(adapter, "catalog", None)
    if isinstance(mem, MemoryServiceCatalog):
        return mem
    return MemoryServiceCatalog.seeded_default()
