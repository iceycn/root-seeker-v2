from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

import httpx

from rootseeker.contracts.service_catalog import ServiceCatalogEntry

__all__ = ["HttpInternalToolAdapter", "InternalToolAdapter"]


class InternalToolAdapter(Protocol):
    def resolve_service(
        self, tenant: str, environment: str, service_name: str
    ) -> ServiceCatalogEntry: ...

    def get_log_sources(
        self, tenant: str, environment: str, service_name: str
    ) -> list[dict[str, Any]]: ...

    def query_logs_by_trace_id(
        self, trace_id: str, service_name: str | None = None
    ) -> dict[str, Any]: ...

    def query_logs_by_template(
        self, template_id: str, service_name: str | None = None
    ) -> dict[str, Any]: ...

    def get_trace_chain(self, trace_id: str) -> dict[str, Any]: ...

    def search_code(self, query: str) -> dict[str, Any]: ...

    def semantic_search_code(
        self, query: str, repo_name: str | None = None, limit: int = 10
    ) -> dict[str, Any]: ...

    def read_code(self, path: str, repo: str | None = None) -> dict[str, Any]: ...

    def find_callers(self, args: dict[str, Any]) -> dict[str, Any]: ...

    def graph_impact(self, args: dict[str, Any]) -> dict[str, Any]: ...

    def graph_context(self, args: dict[str, Any]) -> dict[str, Any]: ...

    def graph_query(self, args: dict[str, Any]) -> dict[str, Any]: ...

    def graph_cypher(self, args: dict[str, Any]) -> dict[str, Any]: ...

    def graph_trace(self, args: dict[str, Any]) -> dict[str, Any]: ...

    def graph_list_repos(self, args: dict[str, Any]) -> dict[str, Any]: ...

    def graph_detect_changes(self, args: dict[str, Any]) -> dict[str, Any]: ...

    def get_index_status(self) -> dict[str, Any]: ...

    def send_notification(self, channel: str, message: str) -> dict[str, Any]: ...

    # Repo operations
    def repo_register(self, args: dict[str, Any]) -> dict[str, Any]: ...

    def repo_sync(self, args: dict[str, Any]) -> dict[str, Any]: ...

    def repo_list(self, args: dict[str, Any]) -> dict[str, Any]: ...

    def repo_get(self, args: dict[str, Any]) -> dict[str, Any]: ...

    def repo_unregister(self, args: dict[str, Any]) -> dict[str, Any]: ...

    def repo_sync_all(self, args: dict[str, Any]) -> dict[str, Any]: ...

    def repo_sync_changed(self, args: dict[str, Any]) -> dict[str, Any]: ...

    def repo_index_status(self, args: dict[str, Any]) -> dict[str, Any]: ...

    def repo_semantic_search(self, args: dict[str, Any]) -> dict[str, Any]: ...

    def lsp_references(self, args: dict[str, Any]) -> dict[str, Any]: ...

    def lsp_definition(self, args: dict[str, Any]) -> dict[str, Any]: ...

    def lsp_hover(self, args: dict[str, Any]) -> dict[str, Any]: ...

    def lsp_symbols(self, args: dict[str, Any]) -> dict[str, Any]: ...


@dataclass
class HttpInternalToolAdapter:
    base_url: str
    timeout_seconds: float = 5.0
    find_callers_timeout_seconds: float = 120.0
    route_resolve_service: str = "/catalog/resolve_service"
    route_get_log_sources: str = "/catalog/get_log_sources"
    route_query_log_by_trace: str = "/log/query_by_trace_id"
    route_query_log_by_template: str = "/log/query_by_template"
    route_get_trace_chain: str = "/trace/get_chain"
    route_code_search: str = "/code/search"
    route_code_semantic_search: str = "/code/semantic-search"
    route_code_read: str = "/code/read"
    route_code_find_callers: str = "/code/find_callers"
    route_graph_impact: str = "/graph/impact"
    route_graph_context: str = "/graph/context"
    route_graph_query: str = "/graph/query"
    route_graph_cypher: str = "/graph/cypher"
    route_graph_trace: str = "/graph/trace"
    route_graph_list_repos: str = "/graph/list_repos"
    route_graph_detect_changes: str = "/graph/detect_changes"
    route_index_status: str = "/index/get_status"
    route_notify_send: str = "/notify/send"
    route_repo_register: str = "/repos"
    route_repo_sync: str = "/repos/{name}/sync"
    route_repo_list: str = "/repos"
    route_repo_get: str = "/repos/{name}"
    route_repo_unregister: str = "/repos/{name}"
    route_repo_sync_all: str = "/repos/sync-all"
    route_repo_sync_changed: str = "/repos/sync-changed"
    route_repo_index_status: str = "/repos/{name}/index-status"
    route_repo_semantic_search: str = "/code/semantic-search"
    route_lsp_references: str = "/lsp/references"
    route_lsp_definition: str = "/lsp/definition"
    route_lsp_hover: str = "/lsp/hover"
    route_lsp_symbols: str = "/lsp/symbols"
    transport: httpx.BaseTransport | None = None

    def _post(
        self,
        route: str,
        payload: dict[str, Any],
        *,
        timeout_seconds: float | None = None,
    ) -> dict[str, Any]:
        url = f"{self.base_url.rstrip('/')}/{route.lstrip('/')}"
        timeout = self.timeout_seconds if timeout_seconds is None else timeout_seconds
        with httpx.Client(timeout=timeout, transport=self.transport) as client:
            response = client.post(url, json=payload)
            response.raise_for_status()
            data = response.json()
            if not isinstance(data, dict):
                raise RuntimeError(f"unexpected response format: {type(data).__name__}")
            return data

    def _get(self, route: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        url = f"{self.base_url.rstrip('/')}/{route.lstrip('/')}"
        with httpx.Client(timeout=self.timeout_seconds, transport=self.transport) as client:
            response = client.get(url, params=params or {})
            response.raise_for_status()
            data = response.json()
            if not isinstance(data, dict):
                raise RuntimeError(f"unexpected response format: {type(data).__name__}")
            return data

    def _delete(self, route: str) -> dict[str, Any]:
        url = f"{self.base_url.rstrip('/')}/{route.lstrip('/')}"
        with httpx.Client(timeout=self.timeout_seconds, transport=self.transport) as client:
            response = client.delete(url)
            response.raise_for_status()
            data = response.json()
            if not isinstance(data, dict):
                raise RuntimeError(f"unexpected response format: {type(data).__name__}")
            return data

    def resolve_service(
        self, tenant: str, environment: str, service_name: str
    ) -> ServiceCatalogEntry:
        data = self._post(
            self.route_resolve_service,
            {"tenant": tenant, "environment": environment, "service_name": service_name},
        )
        entry_payload = data.get("entry", data)
        return ServiceCatalogEntry.model_validate(entry_payload)

    def get_log_sources(
        self, tenant: str, environment: str, service_name: str
    ) -> list[dict[str, Any]]:
        data = self._post(
            self.route_get_log_sources,
            {"tenant": tenant, "environment": environment, "service_name": service_name},
        )
        raw_sources = data.get("sources", [])
        return [dict(item) for item in raw_sources]

    def query_logs_by_trace_id(
        self, trace_id: str, service_name: str | None = None
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"trace_id": trace_id}
        if service_name:
            payload["service_name"] = service_name
        return self._post(self.route_query_log_by_trace, payload)

    def query_logs_by_template(
        self, template_id: str, service_name: str | None = None
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"template_id": template_id}
        if service_name:
            payload["service_name"] = service_name
        return self._post(self.route_query_log_by_template, payload)

    def get_trace_chain(self, trace_id: str) -> dict[str, Any]:
        return self._post(self.route_get_trace_chain, {"trace_id": trace_id})

    def search_code(self, query: str) -> dict[str, Any]:
        return self._post(self.route_code_search, {"query": query})

    def semantic_search_code(
        self, query: str, repo_name: str | None = None, limit: int = 10
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"query": query, "limit": limit}
        if repo_name:
            payload["repo_name"] = repo_name
        return self._post(self.route_code_semantic_search, payload)

    def read_code(self, path: str, repo: str | None = None) -> dict[str, Any]:
        return self._post(self.route_code_read, {"path": path, **({"repo": repo} if repo else {})})

    def find_callers(self, args: dict[str, Any]) -> dict[str, Any]:
        return self._post(
            self.route_code_find_callers,
            args,
            timeout_seconds=self.find_callers_timeout_seconds,
        )

    def graph_impact(self, args: dict[str, Any]) -> dict[str, Any]:
        return self._post(
            self.route_graph_impact, args, timeout_seconds=self.find_callers_timeout_seconds
        )

    def graph_context(self, args: dict[str, Any]) -> dict[str, Any]:
        return self._post(
            self.route_graph_context, args, timeout_seconds=self.find_callers_timeout_seconds
        )

    def graph_query(self, args: dict[str, Any]) -> dict[str, Any]:
        return self._post(
            self.route_graph_query, args, timeout_seconds=self.find_callers_timeout_seconds
        )

    def graph_cypher(self, args: dict[str, Any]) -> dict[str, Any]:
        return self._post(
            self.route_graph_cypher, args, timeout_seconds=self.find_callers_timeout_seconds
        )

    def graph_trace(self, args: dict[str, Any]) -> dict[str, Any]:
        return self._post(
            self.route_graph_trace, args, timeout_seconds=self.find_callers_timeout_seconds
        )

    def graph_list_repos(self, args: dict[str, Any]) -> dict[str, Any]:
        return self._post(self.route_graph_list_repos, args)

    def graph_detect_changes(self, args: dict[str, Any]) -> dict[str, Any]:
        return self._post(
            self.route_graph_detect_changes,
            args,
            timeout_seconds=self.find_callers_timeout_seconds,
        )

    def get_index_status(self) -> dict[str, Any]:
        return self._post(self.route_index_status, {})

    def send_notification(self, channel: str, message: str) -> dict[str, Any]:
        return self._post(self.route_notify_send, {"channel": channel, "message": message})

    # Repo operations via HTTP
    def repo_register(self, args: dict[str, Any]) -> dict[str, Any]:
        return self._post(self.route_repo_register, args)

    def repo_sync(self, args: dict[str, Any]) -> dict[str, Any]:
        name = str(args.get("name", ""))
        payload: dict[str, Any] = {
            "trigger_index": args.get("trigger_index", True),
            "force_reclone": bool(args.get("force_reclone", False)),
        }
        return self._post(self.route_repo_sync.format(name=name), payload)

    def repo_list(self, args: dict[str, Any]) -> dict[str, Any]:
        return self._get(
            self.route_repo_list, params={k: v for k, v in args.items() if v is not None}
        )

    def repo_get(self, args: dict[str, Any]) -> dict[str, Any]:
        name = str(args.get("name", ""))
        return self._get(self.route_repo_get.format(name=name))

    def repo_unregister(self, args: dict[str, Any]) -> dict[str, Any]:
        name = str(args.get("name", ""))
        return self._delete(self.route_repo_unregister.format(name=name))

    def repo_sync_all(self, args: dict[str, Any]) -> dict[str, Any]:
        trigger = args.get("trigger_index", True)
        return self._post(f"{self.route_repo_sync_all}?trigger_index={str(trigger).lower()}", {})

    def repo_sync_changed(self, args: dict[str, Any]) -> dict[str, Any]:
        trigger = args.get("trigger_index", True)
        return self._post(
            f"{self.route_repo_sync_changed}?trigger_index={str(trigger).lower()}", {}
        )

    def repo_index_status(self, args: dict[str, Any]) -> dict[str, Any]:
        name = str(args.get("name", ""))
        return self._get(self.route_repo_index_status.format(name=name))

    def repo_semantic_search(self, args: dict[str, Any]) -> dict[str, Any]:
        return self._post(self.route_repo_semantic_search, args)

    def lsp_references(self, args: dict[str, Any]) -> dict[str, Any]:
        return self._post(self.route_lsp_references, args)

    def lsp_definition(self, args: dict[str, Any]) -> dict[str, Any]:
        return self._post(self.route_lsp_definition, args)

    def lsp_hover(self, args: dict[str, Any]) -> dict[str, Any]:
        return self._post(self.route_lsp_hover, args)

    def lsp_symbols(self, args: dict[str, Any]) -> dict[str, Any]:
        return self._post(self.route_lsp_symbols, args)
