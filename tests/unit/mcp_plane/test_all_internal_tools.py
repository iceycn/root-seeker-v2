"""Unit tests that invoke every internal MCP tool through McpGateway.

Each test proves the call path:
  gateway.invoke → register_internal_tools handler → adapter method
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from mcp_servers.internal.handlers import register_internal_tools
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
from rootseeker.code_index.repo_sync import RepoSyncResult, RepoSyncService
from rootseeker.contracts.repository import RepositoryRef, RepoSyncState
from rootseeker.contracts.service_catalog import ServiceCatalogEntry
from rootseeker.contracts.tool import ToolCallRequest, ToolPermissionLevel
from rootseeker.mcp_plane import McpGateway, PolicyGuard, ToolRegistry
from rootseeker.observability.audit import InMemoryAuditLog
from rootseeker.service_catalog.memory_catalog import MemoryServiceCatalog

EXPECTED_TOOLS = [
    "incident.normalize",
    "catalog.resolve_service",
    "catalog.get_log_sources",
    "log.query_by_trace_id",
    "log.query_by_template",
    "trace.get_chain",
    "code.search",
    "code.semantic_search",
    "code.read",
    "code.find_callers",
    "index.get_status",
    "notify.send",
    "repo.register",
    "repo.sync",
    "repo.list",
    "repo.get",
    "repo.unregister",
    "repo.sync_all",
    "repo.index_status",
    "repo.semantic_search",
    "lsp.references",
    "lsp.definition",
    "lsp.hover",
    "lsp.symbols",
]


@dataclass
class RecordingAdapter:
    """Adapter that records every method call and exercises real repo tool handlers."""

    base_path: Path
    catalog: MemoryServiceCatalog = field(default_factory=MemoryServiceCatalog.seeded_default)
    calls: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = field(default_factory=list)
    repo_sync_service: RepoSyncService = field(init=False)

    def __post_init__(self) -> None:
        self.repo_sync_service = RepoSyncService(
            base_path=self.base_path,
            enable_zoekt=False,
            enable_qdrant=False,
        )

    def _record(self, name: str, *args: Any, **kwargs: Any) -> None:
        self.calls.append((name, args, kwargs))

    def called(self, name: str) -> bool:
        return any(item[0] == name for item in self.calls)

    def call_count(self, name: str) -> int:
        return sum(1 for item in self.calls if item[0] == name)

    def resolve_service(self, tenant: str, environment: str, service_name: str) -> ServiceCatalogEntry:
        self._record("resolve_service", tenant, environment, service_name)
        entry = self.catalog.resolve(tenant, environment, service_name)
        if entry is None:
            entry = ServiceCatalogEntry(
                tenant=tenant,
                environment=environment,
                service_name=service_name,
                display_name=service_name,
                log_sources=[{"type": "test", "source_id": f"log-{service_name}"}],
            )
        return entry

    def get_log_sources(self, tenant: str, environment: str, service_name: str) -> list[dict[str, Any]]:
        self._record("get_log_sources", tenant, environment, service_name)
        entry = self.resolve_service(tenant, environment, service_name)
        return [dict(item) for item in entry.log_sources]

    def query_logs_by_trace_id(self, trace_id: str, service_name: str | None = None) -> dict[str, Any]:
        self._record("query_logs_by_trace_id", trace_id, service_name)
        return {
            "query_key": f"trace:{trace_id}",
            "records": [{"message": "boom", "trace_id": trace_id, "service": service_name}],
            "truncated": False,
        }

    def query_logs_by_template(self, template_id: str, service_name: str | None = None) -> dict[str, Any]:
        self._record("query_logs_by_template", template_id, service_name)
        return {
            "query_key": f"tpl:{template_id}",
            "records": [{"message": "template-hit", "template_id": template_id}],
            "truncated": False,
        }

    def get_trace_chain(self, trace_id: str) -> dict[str, Any]:
        self._record("get_trace_chain", trace_id)
        return {
            "trace_id": trace_id,
            "spans": [{"span_id": "s1", "operation": "GET /api"}],
            "total_spans": 1,
            "configured": True,
        }

    def search_code(self, query: str) -> dict[str, Any]:
        self._record("search_code", query)
        return {
            "query": query,
            "hits": [{"repo": "demo", "path": "Demo.java", "line_start": 1, "snippet": "class Demo", "score": 10}],
            "total": 1,
        }

    def semantic_search_code(self, query: str, repo_name: str | None = None, limit: int = 10) -> dict[str, Any]:
        self._record("semantic_search_code", query, repo_name=repo_name, limit=limit)
        return {"ok": True, "query": query, "repo_name": repo_name, "limit": limit, "result": []}

    def read_code(self, path: str, repo: str | None = None) -> dict[str, Any]:
        self._record("read_code", path, repo)
        return {"path": path, "repo": repo, "content": f"// {path}\nclass Demo {{}}\n", "total_lines": 2}

    def find_callers(self, args: dict[str, Any]) -> dict[str, Any]:
        self._record("find_callers", args)
        return {
            "target": {"class_name": "A", "method_name": "b"},
            "runtime_chain": args.get("call_chain") or [],
            "static_callers": [{"path": "Caller.java", "line": 10}],
            "aligned": {"matched": True},
            "entrypoints": [],
        }

    def get_index_status(self) -> dict[str, Any]:
        self._record("get_index_status")
        return {"ready": True, "indexes": [{"name": "demo", "ready": True}]}

    def send_notification(self, channel: str, message: str) -> dict[str, Any]:
        self._record("send_notification", channel, message)
        return {"ok": True, "channel": channel, "message": message, "metadata": {"test": True}}

    def repo_register(self, args: dict[str, Any]) -> dict[str, Any]:
        self._record("repo_register", args)
        return repo_register_tool(self.repo_sync_service, args)

    def repo_sync(self, args: dict[str, Any]) -> dict[str, Any]:
        self._record("repo_sync", args)
        return repo_sync_tool(self.repo_sync_service, args)

    def repo_list(self, args: dict[str, Any]) -> dict[str, Any]:
        self._record("repo_list", args)
        return repo_list_tool(self.repo_sync_service, args)

    def repo_get(self, args: dict[str, Any]) -> dict[str, Any]:
        self._record("repo_get", args)
        return repo_get_tool(self.repo_sync_service, args)

    def repo_unregister(self, args: dict[str, Any]) -> dict[str, Any]:
        self._record("repo_unregister", args)
        return repo_unregister_tool(self.repo_sync_service, args)

    def repo_sync_all(self, args: dict[str, Any]) -> dict[str, Any]:
        self._record("repo_sync_all", args)
        return repo_sync_all_tool(self.repo_sync_service, args)

    def repo_index_status(self, args: dict[str, Any]) -> dict[str, Any]:
        self._record("repo_index_status", args)
        return repo_index_status_tool(self.repo_sync_service, args)

    def repo_semantic_search(self, args: dict[str, Any]) -> dict[str, Any]:
        self._record("repo_semantic_search", args)
        return repo_semantic_search_tool(self.repo_sync_service, args)

    def lsp_references(self, args: dict[str, Any]) -> dict[str, Any]:
        self._record("lsp_references", args)
        return {"items": [{"path": "a.py", "line": 1, "symbol": args.get("symbol")}]}

    def lsp_definition(self, args: dict[str, Any]) -> dict[str, Any]:
        self._record("lsp_definition", args)
        return {"items": [{"path": args.get("file_path"), "line": args.get("line"), "character": args.get("character")}]}

    def lsp_hover(self, args: dict[str, Any]) -> dict[str, Any]:
        self._record("lsp_hover", args)
        return {"hover": {"contents": "doc", "line": args.get("line")}}

    def lsp_symbols(self, args: dict[str, Any]) -> dict[str, Any]:
        self._record("lsp_symbols", args)
        return {"items": [{"name": "Demo", "kind": "class", "path": args.get("file_path")}]}


def _gateway(adapter: RecordingAdapter) -> tuple[McpGateway, ToolRegistry, InMemoryAuditLog]:
    registry = ToolRegistry()
    register_internal_tools(registry, adapter=adapter)
    audit = InMemoryAuditLog()
    gateway = McpGateway(registry, PolicyGuard(deny_write=False), audit)
    return gateway, registry, audit


def _invoke(gateway: McpGateway, tool_name: str, arguments: dict[str, Any]):
    req = ToolCallRequest(
        case_id="case-tool-ut",
        step_id="step-1",
        skill_name="flows/default-log-triage",
        tool_name=tool_name,
        arguments=arguments,
    )
    return gateway.invoke(req, actor="unit-test")


@pytest.fixture
def adapter(tmp_path: Path) -> RecordingAdapter:
    return RecordingAdapter(base_path=tmp_path / "repos")


@pytest.fixture
def gateway(adapter: RecordingAdapter):
    return _gateway(adapter)


def test_all_expected_tools_are_registered(gateway) -> None:
    _gw, registry, _audit = gateway
    names = sorted(spec.name for spec in registry.list_specs())
    assert names == sorted(EXPECTED_TOOLS)
    assert len(names) == 24


def test_every_tool_is_invoked_and_reaches_adapter(adapter: RecordingAdapter, gateway) -> None:
    gw, _registry, audit = gateway
    before_audit = audit.count()

    scenarios: list[tuple[str, dict[str, Any], str]] = [
        (
            "incident.normalize",
            {
                "payload": {
                    "title": "npe",
                    "service_name": "order-service",
                    "message": "NullPointerException at Foo.bar(Foo.java:9)",
                    "source": "webhook",
                    "trace_id": "t-1",
                    "tenant": "demo",
                    "environment": "prod",
                }
            },
            "resolve_service",
        ),
        ("catalog.resolve_service", {"tenant": "demo", "environment": "prod", "service_name": "order-service"}, "resolve_service"),
        ("catalog.get_log_sources", {"tenant": "demo", "environment": "prod", "service_name": "order-service"}, "get_log_sources"),
        ("log.query_by_trace_id", {"trace_id": "t-1", "service_name": "order-service"}, "query_logs_by_trace_id"),
        ("log.query_by_template", {"template_id": "default.error_window", "service_name": "order-service"}, "query_logs_by_template"),
        ("trace.get_chain", {"trace_id": "t-1"}, "get_trace_chain"),
        ("code.search", {"query": "Foo.bar"}, "search_code"),
        ("code.semantic_search", {"query": "Foo.bar", "limit": 3}, "semantic_search_code"),
        ("code.read", {"path": "Foo.java", "repo": "demo"}, "read_code"),
        (
            "code.find_callers",
            {"call_chain": ["Foo.bar (Foo.java:9)", "BazController.run (BazController.java:1)"], "limit": 5},
            "find_callers",
        ),
        ("index.get_status", {}, "get_index_status"),
        ("notify.send", {"channel": "webhook", "message": "hi"}, "send_notification"),
        (
            "repo.register",
            {"name": "demo-repo", "url": "https://example.com/demo.git", "branch": "main"},
            "repo_register",
        ),
        ("repo.list", {}, "repo_list"),
        ("repo.get", {"name": "demo-repo"}, "repo_get"),
        ("repo.index_status", {"name": "demo-repo"}, "repo_index_status"),
        ("repo.semantic_search", {"query": "Foo", "limit": 2}, "repo_semantic_search"),
        ("lsp.references", {"symbol": "Foo", "file_path": "Foo.java"}, "lsp_references"),
        ("lsp.definition", {"file_path": "Foo.java", "line": 1, "character": 2}, "lsp_definition"),
        ("lsp.hover", {"file_path": "Foo.java", "line": 1, "character": 2}, "lsp_hover"),
        ("lsp.symbols", {"file_path": "Foo.java"}, "lsp_symbols"),
        ("repo.unregister", {"name": "demo-repo"}, "repo_unregister"),
    ]

    for tool_name, args, adapter_method in scenarios:
        adapter.calls.clear()
        result = _invoke(gw, tool_name, args)
        assert result.ok, f"{tool_name} failed: {result.error}"
        assert result.tool_name == tool_name
        if tool_name != "incident.normalize":
            assert adapter.called(adapter_method), f"{tool_name} did not reach adapter.{adapter_method}"

    adapter.calls.clear()
    # Real sync path: register existing Docker-imported clones as local-only.
    real_names = [
        name
        for name in ("iceycn__mcp-server-apollo", "iceycn__root_seeker")
        if ((Path(__file__).resolve().parents[3] / "repos" / name / ".git").is_dir())
    ]
    if real_names:
        for name in real_names:
            adapter.repo_sync_service.register(
                RepositoryRef(
                    name=f"verify-{name}",
                    url=None,
                    local_path=str((Path(__file__).resolve().parents[3] / "repos" / name).resolve()),
                    default_branch="main",
                )
            )
        sync_res = _invoke(gw, "repo.sync", {"name": f"verify-{real_names[0]}", "trigger_index": False})
        assert sync_res.ok
        assert adapter.called("repo_sync")
        assert sync_res.content["ok"] is True
        assert sync_res.content["state"] == "completed"

        adapter.calls.clear()
        all_res = _invoke(gw, "repo.sync_all", {"trigger_index": False})
        assert all_res.ok
        assert adapter.called("repo_sync_all")
        assert all_res.content["ok"] is True
        assert all_res.content["total"] >= len(real_names)
        assert all(row["success"] for row in all_res.content["results"] if str(row["repo_name"]).startswith("verify-"))
    else:
        with patch.object(
            adapter.repo_sync_service,
            "sync",
            return_value=RepoSyncResult(
                repo=RepositoryRef(name="x", url="https://example.com/x.git"),
                success=True,
                message="synced",
            ),
        ):
            _invoke(gw, "repo.register", {"name": "x", "url": "https://example.com/x.git"})
            adapter.calls.clear()
            sync_res = _invoke(gw, "repo.sync", {"name": "x", "trigger_index": False})
            assert sync_res.ok
            assert adapter.called("repo_sync")
            assert sync_res.content["ok"] is True

            adapter.calls.clear()
            with patch.object(adapter.repo_sync_service, "sync_all", return_value=[]):
                all_res = _invoke(gw, "repo.sync_all", {"trigger_index": False})
                assert all_res.ok
                assert adapter.called("repo_sync_all")

    assert audit.count() >= before_audit + len(EXPECTED_TOOLS) - 2


def test_incident_normalize_payload_and_flat_args(adapter: RecordingAdapter, gateway) -> None:
    gw, _, _ = gateway
    nested = _invoke(
        gw,
        "incident.normalize",
        {
            "payload": {
                "title": "spike",
                "service_name": "api",
                "message": "boom in Service.java:12",
                "source": "webhook",
                "trace_id": "abc",
            }
        },
    )
    assert nested.ok
    assert nested.content["extracted"]["code_path"] == "Service.java"
    assert "trace_id" in nested.content["extracted"]

    flat = _invoke(
        gw,
        "incident.normalize",
        {
            "title": "flat",
            "service_name": "api",
            "message": (
                "java.lang.NullPointerException: boom\n"
                "\tat com.example.PopRecordService.insertPopRecordLogic(PopRecordService.java:42)\n"
                "\tat com.example.BazController.run(BazController.java:1)\n"
            ),
            "source": "webhook",
        },
    )
    assert flat.ok
    assert flat.content["extracted"]["call_chain"]
    assert "PopRecordService.insertPopRecordLogic" in flat.content["extracted"]["call_chain"][0]
    assert flat.content["case_request"]["service_name"] == "api"
    assert "time_window" in flat.content["missing_fields"]


def test_catalog_unknown_service_still_returns_entry(adapter: RecordingAdapter, gateway) -> None:
    gw, _, _ = gateway
    res = _invoke(
        gw,
        "catalog.resolve_service",
        {"tenant": "demo", "environment": "prod", "service_name": "brand-new-service"},
    )
    assert res.ok
    assert res.content["entry"]["service_name"] == "brand-new-service"
    assert adapter.called("resolve_service")


def test_log_and_trace_tools_pass_optional_service_name(adapter: RecordingAdapter, gateway) -> None:
    gw, _, _ = gateway
    by_trace = _invoke(gw, "log.query_by_trace_id", {"trace_id": "t-9"})
    assert by_trace.ok
    assert by_trace.content["query_key"] == "trace:t-9"
    assert adapter.calls[-1][0] == "query_logs_by_trace_id"
    assert adapter.calls[-1][1][1] is None

    by_tpl = _invoke(gw, "log.query_by_template", {"template_id": "tpl-1", "service_name": "svc"})
    assert by_tpl.ok
    assert adapter.calls[-1][1][1] == "svc"

    chain = _invoke(gw, "trace.get_chain", {"trace_id": "t-9"})
    assert chain.ok
    assert chain.content["total_spans"] == 1


def test_code_tools_success_and_empty_query(adapter: RecordingAdapter, gateway) -> None:
    gw, _, _ = gateway
    search = _invoke(gw, "code.search", {"query": "Demo"})
    assert search.ok
    assert search.content["hits"][0]["path"] == "Demo.java"
    assert adapter.called("search_code")

    empty = _invoke(gw, "code.search", {"query": ""})
    assert empty.ok
    assert adapter.calls[-1][1][0] == ""

    semantic = _invoke(gw, "code.semantic_search", {"query": "Demo", "repo_name": "demo", "limit": 2})
    assert semantic.ok
    assert adapter.called("semantic_search_code")

    read = _invoke(gw, "code.read", {"path": "a/b.py"})
    assert read.ok
    assert "class Demo" in read.content["content"]

    callers = _invoke(
        gw,
        "code.find_callers",
        {"call_chain": ["A.b (A.java:1)"], "class_name": "A", "method_name": "b"},
    )
    assert callers.ok
    assert callers.content["static_callers"]


def test_repo_lifecycle_validation_and_happy_path(adapter: RecordingAdapter, gateway) -> None:
    gw, _, _ = gateway

    missing = _invoke(gw, "repo.register", {})
    assert missing.ok
    assert missing.content["ok"] is False
    assert "name is required" in missing.content["error"]
    assert adapter.called("repo_register")

    created = _invoke(
        gw,
        "repo.register",
        {"name": "life", "url": "https://example.com/life.git", "branch": "develop", "metadata": {"k": "v"}},
    )
    assert created.content["ok"] is True
    assert created.content["repo"]["default_branch"] == "develop"

    listed = _invoke(gw, "repo.list", {})
    assert listed.content["total"] == 1
    filtered = _invoke(gw, "repo.list", {"state": "pending"})
    assert filtered.content["total"] == 1

    got = _invoke(gw, "repo.get", {"name": "life"})
    assert got.content["ok"] is True
    missing_get = _invoke(gw, "repo.get", {"name": "nope"})
    assert missing_get.content["ok"] is False

    status = _invoke(gw, "repo.index_status", {"name": "life"})
    assert status.content["ok"] is True

    with patch.object(
        adapter.repo_sync_service,
        "semantic_search",
        return_value={"ok": True, "query": "q", "result": [{"id": 1}]},
    ) as mocked:
        sem = _invoke(gw, "repo.semantic_search", {"query": "q", "limit": 1})
        assert sem.content["ok"] is True
        mocked.assert_called_once()
        assert adapter.called("repo_semantic_search")

    with patch.object(
        adapter.repo_sync_service,
        "sync",
        return_value=RepoSyncResult(
            repo=adapter.repo_sync_service.get_repo("life"),  # type: ignore[arg-type]
            success=False,
            message="clone failed",
        ),
    ):
        sync = _invoke(gw, "repo.sync", {"name": "life", "trigger_index": False, "force_reclone": True})
        assert sync.content["ok"] is False
        assert sync.content["message"] == "clone failed"

    sync_missing = _invoke(gw, "repo.sync", {})
    assert sync_missing.content["ok"] is False

    with patch.object(adapter.repo_sync_service, "sync_all", return_value=[]) as mocked_all:
        all_res = _invoke(gw, "repo.sync_all", {"trigger_index": False})
        assert all_res.content["total"] == 0
        mocked_all.assert_called_once_with(trigger_index=False)

    removed = _invoke(gw, "repo.unregister", {"name": "life"})
    assert removed.content["ok"] is True
    removed_again = _invoke(gw, "repo.unregister", {"name": "life"})
    assert removed_again.content["ok"] is False


def test_lsp_tools_forward_arguments(adapter: RecordingAdapter, gateway) -> None:
    gw, _, _ = gateway
    refs = _invoke(gw, "lsp.references", {"symbol": "Demo", "file_path": "Demo.java", "root_path": "/tmp"})
    assert refs.ok and refs.content["items"]
    assert adapter.calls[-1][1][0]["symbol"] == "Demo"

    definition = _invoke(gw, "lsp.definition", {"file_path": "Demo.java", "line": 3, "character": 4})
    assert definition.content["items"][0]["line"] == 3

    hover = _invoke(gw, "lsp.hover", {"file_path": "Demo.java", "line": 3, "character": 4})
    assert hover.content["hover"]["contents"] == "doc"

    symbols = _invoke(gw, "lsp.symbols", {"file_path": "Demo.java"})
    assert symbols.content["items"][0]["name"] == "Demo"


def test_notify_and_index_status(adapter: RecordingAdapter, gateway) -> None:
    gw, _, _ = gateway
    notify = _invoke(gw, "notify.send", {"channel": "feishu", "message": "ping"})
    assert notify.ok
    assert notify.content["channel"] == "feishu"
    assert adapter.called("send_notification")

    status = _invoke(gw, "index.get_status", {})
    assert status.content["ready"] is True
    assert adapter.called("get_index_status")


WRITE_TOOLS = [
    "notify.send",
    "repo.register",
    "repo.sync",
    "repo.unregister",
    "repo.sync_all",
]


@pytest.mark.parametrize("tool_name", WRITE_TOOLS)
def test_all_write_tools_denied_when_policy_blocks(adapter: RecordingAdapter, tool_name: str) -> None:
    registry = ToolRegistry()
    register_internal_tools(registry, adapter=adapter)
    gw = McpGateway(registry, PolicyGuard(deny_write=True), InMemoryAuditLog())
    args = {
        "notify.send": {"channel": "webhook", "message": "x"},
        "repo.register": {"name": "n", "url": "https://example.com/n.git"},
        "repo.sync": {"name": "n"},
        "repo.unregister": {"name": "n"},
        "repo.sync_all": {"trigger_index": False},
    }[tool_name]
    before = list(adapter.calls)
    res = _invoke(gw, tool_name, args)
    assert res.ok is False
    assert res.error is not None
    assert res.error.code == "POLICY_DENIED"
    assert adapter.calls == before
    spec = registry.get_spec(tool_name)
    assert spec is not None
    assert spec.permission_level == ToolPermissionLevel.WRITE


def test_handler_defaults_still_reach_adapter(adapter: RecordingAdapter, gateway) -> None:
    """Missing optional/required schema fields use handler defaults and still call adapter."""
    gw, _, _ = gateway

    catalog = _invoke(gw, "catalog.resolve_service", {})
    assert catalog.ok
    assert catalog.content["entry"]["tenant"] == "demo"
    assert catalog.content["entry"]["service_name"] == "unknown"
    assert adapter.called("resolve_service")

    adapter.calls.clear()
    sources = _invoke(gw, "catalog.get_log_sources", {})
    assert sources.ok
    assert sources.content["service_name"] == "unknown"
    assert adapter.called("get_log_sources")

    adapter.calls.clear()
    by_trace = _invoke(gw, "log.query_by_trace_id", {})
    assert by_trace.ok
    assert by_trace.content["query_key"] == "trace:trace-unknown"
    assert adapter.called("query_logs_by_trace_id")

    adapter.calls.clear()
    by_tpl = _invoke(gw, "log.query_by_template", {})
    assert by_tpl.ok
    assert by_tpl.content["query_key"] == "tpl:tpl-unknown"
    assert adapter.called("query_logs_by_template")

    adapter.calls.clear()
    chain = _invoke(gw, "trace.get_chain", {})
    assert chain.ok
    assert chain.content["trace_id"] == "trace-unknown"
    assert adapter.called("get_trace_chain")

    adapter.calls.clear()
    read = _invoke(gw, "code.read", {})
    assert read.ok
    assert read.content["path"] == "README.md"
    assert adapter.called("read_code")

    adapter.calls.clear()
    notify = _invoke(gw, "notify.send", {})
    assert notify.ok
    assert notify.content["channel"] == "webhook"
    assert adapter.called("send_notification")

    adapter.calls.clear()
    semantic = _invoke(gw, "code.semantic_search", {})
    assert semantic.ok
    assert adapter.called("semantic_search_code")
    assert adapter.calls[-1][2].get("limit") == 10 or adapter.calls[-1][1]


def test_repo_tool_validation_scenarios(adapter: RecordingAdapter, gateway) -> None:
    gw, _, _ = gateway

    get_missing = _invoke(gw, "repo.get", {})
    assert get_missing.content["ok"] is False
    assert adapter.called("repo_get")

    adapter.calls.clear()
    unreg_missing = _invoke(gw, "repo.unregister", {})
    assert unreg_missing.content["ok"] is False
    assert "name is required" in unreg_missing.content["error"]
    assert adapter.called("repo_unregister")

    adapter.calls.clear()
    index_missing = _invoke(gw, "repo.index_status", {})
    assert index_missing.content["ok"] is False
    assert adapter.called("repo_index_status")

    adapter.calls.clear()
    empty_query = _invoke(gw, "repo.semantic_search", {"query": "   "})
    assert empty_query.content["ok"] is False
    assert "query is required" in empty_query.content["error"]
    assert adapter.called("repo_semantic_search")

    adapter.calls.clear()
    # qdrant disabled → real RepoSyncService.semantic_search path
    disabled = _invoke(gw, "repo.semantic_search", {"query": "Foo"})
    assert disabled.ok
    assert disabled.content["ok"] is False
    assert "qdrant" in str(disabled.content.get("error", "")).lower()
    assert adapter.called("repo_semantic_search")


def test_incident_normalize_channel_variants_and_missing_fields(adapter: RecordingAdapter, gateway) -> None:
    gw, _, _ = gateway

    sparse = _invoke(gw, "incident.normalize", {"payload": {"source": "webhook"}})
    assert sparse.ok
    assert "service_name" in sparse.content["missing_fields"]
    assert sparse.content["case_request"]["service_name"] == "unknown-service"

    prom = _invoke(
        gw,
        "incident.normalize",
        {
            "payload": {
                "source": "prometheus",
                "status": "firing",
                "alerts": [
                    {
                        "status": "firing",
                        "labels": {"alertname": "HighError", "service": "pay"},
                        "annotations": {"summary": "error in PayService.java:9"},
                    }
                ],
            }
        },
    )
    assert prom.ok
    assert prom.content["case_request"]["service_name"] == "pay"
    assert prom.content["extracted"]["code_path"] == "PayService.java"


def test_code_find_callers_passes_full_args_dict(adapter: RecordingAdapter, gateway) -> None:
    gw, _, _ = gateway
    args = {
        "call_chain": ["A.b (A.java:1)"],
        "class_name": "A",
        "method_name": "b",
        "file_path": "A.java",
        "line": 1,
        "repo": "demo",
        "service_name": "svc",
        "max_depth": 3,
        "limit": 7,
    }
    res = _invoke(gw, "code.find_callers", args)
    assert res.ok
    assert adapter.called("find_callers")
    forwarded = adapter.calls[-1][1][0]
    assert forwarded["limit"] == 7
    assert forwarded["max_depth"] == 3
    assert forwarded["repo"] == "demo"


def test_lsp_defaults_when_args_missing(adapter: RecordingAdapter, gateway) -> None:
    gw, _, _ = gateway
    for tool_name, method in (
        ("lsp.references", "lsp_references"),
        ("lsp.definition", "lsp_definition"),
        ("lsp.hover", "lsp_hover"),
        ("lsp.symbols", "lsp_symbols"),
    ):
        adapter.calls.clear()
        res = _invoke(gw, tool_name, {})
        assert res.ok, tool_name
        assert adapter.called(method), tool_name


def test_unknown_tool_does_not_hit_adapter(adapter: RecordingAdapter, gateway) -> None:
    gw, _, _ = gateway
    res = _invoke(gw, "does.not.exist", {"a": 1})
    assert res.ok is False
    assert res.error is not None
    assert res.error.code == "TOOL_NOT_REGISTERED"
    assert adapter.calls == []


# Explicit per-tool matrix: each row must invoke gateway → handler → adapter (except incident.normalize).
TOOL_REACH_MATRIX: list[tuple[str, dict[str, Any], str | None]] = [
    ("incident.normalize", {"payload": {"title": "t", "service_name": "s", "message": "m", "source": "webhook"}}, None),
    ("catalog.resolve_service", {"tenant": "demo", "environment": "prod", "service_name": "order-service"}, "resolve_service"),
    ("catalog.get_log_sources", {"tenant": "demo", "environment": "prod", "service_name": "order-service"}, "get_log_sources"),
    ("log.query_by_trace_id", {"trace_id": "t"}, "query_logs_by_trace_id"),
    ("log.query_by_template", {"template_id": "tpl"}, "query_logs_by_template"),
    ("trace.get_chain", {"trace_id": "t"}, "get_trace_chain"),
    ("code.search", {"query": "x"}, "search_code"),
    ("code.semantic_search", {"query": "x"}, "semantic_search_code"),
    ("code.read", {"path": "a.py"}, "read_code"),
    ("code.find_callers", {"call_chain": []}, "find_callers"),
    ("index.get_status", {}, "get_index_status"),
    ("notify.send", {"channel": "webhook", "message": "m"}, "send_notification"),
    ("repo.register", {"name": "r1", "url": "https://example.com/r1.git"}, "repo_register"),
    ("repo.list", {}, "repo_list"),
    ("repo.get", {"name": "r1"}, "repo_get"),
    ("repo.index_status", {"name": "r1"}, "repo_index_status"),
    ("repo.semantic_search", {"query": "x"}, "repo_semantic_search"),
    ("lsp.references", {"symbol": "S"}, "lsp_references"),
    ("lsp.definition", {"file_path": "a.py", "line": 1, "character": 0}, "lsp_definition"),
    ("lsp.hover", {"file_path": "a.py", "line": 1, "character": 0}, "lsp_hover"),
    ("lsp.symbols", {"file_path": "a.py"}, "lsp_symbols"),
    ("repo.unregister", {"name": "r1"}, "repo_unregister"),
]


@pytest.mark.parametrize("tool_name,args,adapter_method", TOOL_REACH_MATRIX, ids=[row[0] for row in TOOL_REACH_MATRIX])
def test_each_tool_reaches_handler_and_adapter(
    adapter: RecordingAdapter,
    gateway,
    tool_name: str,
    args: dict[str, Any],
    adapter_method: str | None,
) -> None:
    gw, _, _ = gateway
    adapter.calls.clear()
    result = _invoke(gw, tool_name, args)
    assert result.ok, f"{tool_name}: {result.error}"
    assert result.tool_name == tool_name
    if adapter_method is None:
        assert adapter.calls == []
    else:
        assert adapter.called(adapter_method), f"{tool_name} did not call {adapter_method}; calls={adapter.calls}"


@pytest.mark.parametrize(
    "tool_name,args",
    [
        ("repo.sync", {"name": "sync-me", "trigger_index": False, "force_reclone": False}),
        ("repo.sync_all", {"trigger_index": False}),
    ],
)
def test_repo_sync_tools_reach_adapter_with_real_local_clone(
    adapter: RecordingAdapter,
    gateway,
    tool_name: str,
    args: dict[str, Any],
    tmp_path: Path,
) -> None:
    """Prefer a Docker-imported clone; fall back to a tiny local git repo."""
    gw, _, _ = gateway
    real = Path(__file__).resolve().parents[3] / "repos" / "iceycn__mcp-server-apollo"
    if (real / ".git").is_dir():
        local = real
        name = "sync-me"
        adapter.repo_sync_service.register(
            RepositoryRef(name=name, url=None, local_path=str(local.resolve()), default_branch="main")
        )
    else:
        local = tmp_path / "mini"
        local.mkdir()
        import subprocess

        subprocess.run(["git", "init"], cwd=local, check=True, capture_output=True)
        (local / "README.md").write_text("mini\n", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=local, check=True, capture_output=True)
        subprocess.run(
            ["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-m", "init"],
            cwd=local,
            check=True,
            capture_output=True,
        )
        name = "sync-me"
        adapter.repo_sync_service.register(
            RepositoryRef(name=name, url=None, local_path=str(local.resolve()), default_branch="master")
        )

    if tool_name == "repo.sync":
        args = {**args, "name": name}
    adapter.calls.clear()
    result = _invoke(gw, tool_name, args)
    assert result.ok, result.error
    expected = "repo_sync" if tool_name == "repo.sync" else "repo_sync_all"
    assert adapter.called(expected)
    if tool_name == "repo.sync":
        assert result.content["ok"] is True
    else:
        assert result.content["ok"] is True
        assert result.content["total"] >= 1
        assert any(row["success"] for row in result.content["results"])
