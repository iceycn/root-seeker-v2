"""In-memory stubs for catalog / logs / traces / code — unit tests only (no production services)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from rootseeker.code_index.internal_repo_tools import (
    repo_get_tool,
    repo_index_status_tool,
    repo_list_tool,
    repo_register_tool,
    repo_sync_all_tool,
    repo_sync_tool,
    repo_unregister_tool,
)
from rootseeker.code_index.repo_sync import RepoSyncService
from rootseeker.contracts.service_catalog import ServiceCatalogEntry
from rootseeker.service_catalog.memory_catalog import MemoryServiceCatalog


@dataclass
class StubInternalToolAdapter:
    """Synthetic internal-tool responses for fast tests; outbound notify uses ``dispatch_env_resolved_notify``."""

    catalog: MemoryServiceCatalog
    repo_sync_service: RepoSyncService = field(default_factory=RepoSyncService)

    @classmethod
    def seeded_default(cls) -> StubInternalToolAdapter:
        return cls(catalog=MemoryServiceCatalog.seeded_default())

    def resolve_service(self, tenant: str, environment: str, service_name: str) -> ServiceCatalogEntry:
        entry = self.catalog.resolve(tenant, environment, service_name)
        if entry is None:
            entry = ServiceCatalogEntry(
                tenant=tenant,
                environment=environment,
                service_name=service_name,
                display_name=service_name.title(),
                log_sources=[{"type": "stub", "source_id": f"log-{service_name}"}],
            )
        return entry

    def get_log_sources(self, tenant: str, environment: str, service_name: str) -> list[dict[str, Any]]:
        entry = self.catalog.resolve(tenant, environment, service_name)
        if entry is None:
            return [{"source_id": "stub-fallback", "type": "stub"}]
        return [dict(source) for source in entry.log_sources]

    def query_logs_by_trace_id(self, trace_id: str, service_name: str | None = None) -> dict[str, Any]:
        service = service_name or "unknown"
        return {
            "query_key": f"trace:{trace_id}",
            "records": [{"message": f"stub log line from {service}", "trace_id": trace_id}],
            "truncated": False,
        }

    def query_logs_by_template(self, template_id: str, service_name: str | None = None) -> dict[str, Any]:
        service = service_name or "unknown"
        return {
            "query_key": f"tpl:{template_id}",
            "records": [{"message": f"stub template hit for {service}", "template_id": template_id}],
            "truncated": False,
        }

    def get_trace_chain(self, trace_id: str) -> dict[str, Any]:
        return {"trace_id": trace_id, "spans": [{"span_id": "s1", "operation": "stub-span"}]}

    def search_code(self, query: str) -> dict[str, Any]:
        return {"query": query, "hits": [{"path": "stub.py", "line_start": 1, "snippet": "# stub"}]}

    def read_code(self, path: str, repo: str | None = None) -> dict[str, Any]:
        return {"path": path, "repo": repo, "content": "# stub file content\n"}

    def find_callers(self, args: dict[str, Any]) -> dict[str, Any]:
        call_chain = args.get("call_chain") if isinstance(args.get("call_chain"), list) else []
        aligned_path = [
            str(item).split(" (", 1)[0]
            for item in call_chain
            if str(item).strip()
        ]
        entrypoints: list[dict[str, Any]] = []
        for frame in reversed(call_chain):
            summary = str(frame).split(" (", 1)[0]
            if "." not in summary:
                continue
            class_name, method_name = summary.split(".", 1)
            if class_name.endswith("Controller"):
                entrypoints.append(
                    {
                        "type": "http",
                        "class_name": class_name,
                        "method_name": method_name,
                        "mapping": "/stub",
                    }
                )
                break
        target = None
        if call_chain:
            first = str(call_chain[0])
            summary = first.split(" (", 1)[0]
            if "." in summary:
                class_name, method_name = summary.split(".", 1)
                target = {"class_name": class_name, "method_name": method_name, "summary": first}
        return {
            "target": target,
            "runtime_chain": call_chain,
            "static_callers": [],
            "aligned": {
                "matched": bool(aligned_path),
                "aligned_path": aligned_path,
                "fault_method": aligned_path[0] if aligned_path else None,
                "entry_method": aligned_path[-1] if aligned_path else None,
            },
            "entrypoints": entrypoints,
            "queries": [],
            "notes": "stub",
        }

    def get_index_status(self) -> dict[str, Any]:
        return {"ready": True, "indexes": [{"name": "stub-zoekt", "ready": True}]}

    def send_notification(self, channel: str, message: str) -> dict[str, Any]:
        from rootseeker.channel_routing.notify_dispatch import dispatch_env_resolved_notify

        return dispatch_env_resolved_notify(channel, message)

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
