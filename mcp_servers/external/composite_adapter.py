"""Composite adapter that delegates to production external adapters.

Combines SLS, Jaeger, Zoekt, RepoSyncService-backed repo tools, and channel notify.
When external services are not configured, sub-adapters return explicit errors
instead of synthetic records.

Environment variables for each sub-adapter:
- SLS: SLS_ACCESS_KEY_ID, SLS_ACCESS_KEY_SECRET, SLS_ENDPOINT, SLS_PROJECT, SLS_LOGSTORE
- Jaeger: JAEGER_ENDPOINT, JAEGER_TIMEOUT_SECONDS
- Zoekt: ZOEKT_ENDPOINT, ZOEKT_TIMEOUT_SECONDS
Notify: ROOTSEEKER_NOTIFY_DEFAULT_URL and/or ROOTSEEKER_NOTIFY_<CHANNEL>_URL (see notify_env).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from mcp_servers.external.jaeger_adapter import JaegerConfig, JaegerTraceAdapter
from mcp_servers.external.sls_adapter import SlsConfig, SlsLogAdapter
from mcp_servers.external.zoekt_adapter import ZoektCodeAdapter, ZoektConfig
from rootseeker.code_index.internal_repo_tools import (
    repo_get_tool,
    repo_index_status_tool,
    repo_list_tool,
    repo_register_tool,
    repo_semantic_search_tool,
    repo_sync_all_tool,
    repo_sync_tool,
    repo_unregister_tool,
)
from rootseeker.code_index.lsp_tools import (
    find_symbol_references,
    get_document_symbols,
    get_hover_info,
    go_to_definition,
)
from rootseeker.code_index.repo_sync import RepoSyncService
from rootseeker.contracts.service_catalog import ServiceCatalogEntry
from rootseeker.service_catalog.memory_catalog import MemoryServiceCatalog

__all__ = ["CompositeProductionAdapter", "ProductionConfig"]


@dataclass
class ProductionConfig:
    """Combined configuration for all production adapters."""

    sls: SlsConfig = field(default_factory=SlsConfig.from_env)
    jaeger: JaegerConfig = field(default_factory=JaegerConfig.from_env)
    zoekt: ZoektConfig = field(default_factory=ZoektConfig.from_env)

    @classmethod
    def from_env(cls) -> ProductionConfig:
        """Load all configurations from environment."""
        return cls(
            sls=SlsConfig.from_env(),
            jaeger=JaegerConfig.from_env(),
            zoekt=ZoektConfig.from_env(),
        )


@dataclass
class CompositeProductionAdapter:
    """Production adapter that delegates to external services and RepoSyncService."""

    config: ProductionConfig = field(default_factory=ProductionConfig.from_env)
    catalog: MemoryServiceCatalog = field(default_factory=MemoryServiceCatalog.seeded_default)
    repo_sync_service: RepoSyncService = field(default_factory=RepoSyncService)

    _sls: SlsLogAdapter = field(init=False, repr=False)
    _jaeger: JaegerTraceAdapter = field(init=False, repr=False)
    _zoekt: ZoektCodeAdapter = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._sls = SlsLogAdapter(config=self.config.sls)
        self._jaeger = JaegerTraceAdapter(config=self.config.jaeger)
        self._zoekt = ZoektCodeAdapter(config=self.config.zoekt)

    def resolve_service(
        self,
        tenant: str,
        environment: str,
        service_name: str,
    ) -> ServiceCatalogEntry:
        """Resolve service from catalog."""
        entry = self.catalog.resolve(tenant, environment, service_name)
        if entry is None:
            entry = ServiceCatalogEntry(
                tenant=tenant,
                environment=environment,
                service_name=service_name,
                display_name=service_name.title(),
                log_sources=[{"type": "sls", "source_id": f"log-{service_name}"}],
            )
        return entry

    def get_log_sources(
        self,
        tenant: str,
        environment: str,
        service_name: str,
    ) -> list[dict[str, Any]]:
        """Get log sources for service."""
        entry = self.catalog.resolve(tenant, environment, service_name)
        if entry is None:
            return [{"source_id": "sls-fallback", "type": "sls"}]
        return [dict(source) for source in entry.log_sources]

    def query_logs_by_trace_id(
        self,
        trace_id: str,
        service_name: str | None = None,
    ) -> dict[str, Any]:
        """Query logs by trace ID via SLS."""
        return self._sls.query_logs_by_trace_id(trace_id, service_name=service_name)

    def query_logs_by_template(
        self,
        template_id: str,
        service_name: str | None = None,
    ) -> dict[str, Any]:
        """Query logs by template via SLS."""
        return self._sls.query_logs_by_template(template_id, service_name=service_name)

    def get_trace_chain(self, trace_id: str) -> dict[str, Any]:
        """Get trace chain via Jaeger."""
        return self._jaeger.get_trace_chain(trace_id)

    def search_code(self, query: str) -> dict[str, Any]:
        """Search code via Zoekt."""
        return self._zoekt.search_code(query)

    def semantic_search_code(
        self,
        query: str,
        repo_name: str | None = None,
        limit: int = 10,
    ) -> dict[str, Any]:
        """Search code chunks via Qdrant-backed repo sync service."""
        return self.repo_sync_service.semantic_search(query=query, repo_name=repo_name, limit=limit)

    def read_code(self, path: str) -> dict[str, Any]:
        """Read file via Zoekt."""
        return self._zoekt.read_file(path)

    def get_index_status(self) -> dict[str, Any]:
        """Get index status via Zoekt."""
        return self._zoekt.get_index_status()

    def send_notification(self, channel: str, message: str) -> dict[str, Any]:
        from rootseeker.channel_routing.notify_dispatch import dispatch_env_resolved_notify

        return dispatch_env_resolved_notify(channel, message)

    def close(self) -> None:
        """Close all adapter connections."""
        self._sls.close()
        self._jaeger.close()
        self._zoekt.close()

    def repo_register(self, args: dict[str, Any]) -> dict[str, Any]:
        return repo_register_tool(self.repo_sync_service, args)

    def repo_sync(self, args: dict[str, Any]) -> dict[str, Any]:
        return repo_sync_tool(self.repo_sync_service, args)

    def repo_list(self, args: dict[str, Any]) -> dict[str, Any]:
        return repo_list_tool(self.repo_sync_service, args)

    def repo_get(self, args: dict[str, Any]) -> dict[str, Any]:
        return repo_get_tool(self.repo_sync_service, args)

    def repo_unregister(self, args: dict[str, Any]) -> dict[str, Any]:
        return repo_unregister_tool(self.repo_sync_service, args)

    def repo_sync_all(self, args: dict[str, Any]) -> dict[str, Any]:
        return repo_sync_all_tool(self.repo_sync_service, args)

    def repo_index_status(self, args: dict[str, Any]) -> dict[str, Any]:
        return repo_index_status_tool(self.repo_sync_service, args)

    def repo_semantic_search(self, args: dict[str, Any]) -> dict[str, Any]:
        return repo_semantic_search_tool(self.repo_sync_service, args)

    def lsp_references(self, args: dict[str, Any]) -> dict[str, Any]:
        return {
            "items": find_symbol_references(
                str(args.get("symbol", "")),
                file_path=args.get("file_path"),
                root_path=args.get("root_path"),
            )
        }

    def lsp_definition(self, args: dict[str, Any]) -> dict[str, Any]:
        return {
            "items": go_to_definition(
                str(args.get("file_path", "")),
                int(args.get("line", 0)),
                int(args.get("character", 0)),
                root_path=args.get("root_path"),
            )
        }

    def lsp_hover(self, args: dict[str, Any]) -> dict[str, Any]:
        return {
            "hover": get_hover_info(
                str(args.get("file_path", "")),
                int(args.get("line", 0)),
                int(args.get("character", 0)),
                root_path=args.get("root_path"),
            )
        }

    def lsp_symbols(self, args: dict[str, Any]) -> dict[str, Any]:
        return {
            "items": get_document_symbols(
                str(args.get("file_path", "")),
                root_path=args.get("root_path"),
            )
        }

    @classmethod
    def from_env(
        cls,
        catalog: MemoryServiceCatalog | None = None,
        repo_sync_service: RepoSyncService | None = None,
    ) -> CompositeProductionAdapter:
        """Create adapter from environment variables."""
        return cls(
            config=ProductionConfig.from_env(),
            catalog=catalog or MemoryServiceCatalog.seeded_default(),
            repo_sync_service=repo_sync_service or RepoSyncService(),
        )
