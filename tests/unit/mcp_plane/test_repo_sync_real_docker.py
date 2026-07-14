"""Real repo.sync / repo.sync_all against Docker-imported project clones.

Uses local clones under ./repos (copied from rootseeker-zoekt:/repos).
Registers with url=None so sync reads local git state (no outbound network).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mcp_servers.internal.handlers import register_internal_tools
from rootseeker.code_index.repo_sync import RepoSyncService
from rootseeker.contracts.repository import RepositoryRef, RepoSyncState
from rootseeker.contracts.tool import ToolCallRequest
from rootseeker.mcp_plane import McpGateway, PolicyGuard, ToolRegistry
from rootseeker.observability.audit import InMemoryAuditLog

ROOT = Path(__file__).resolve().parents[3]
REAL_REPOS = [
    "iceycn__mcp-server-apollo",
    "iceycn__root_seeker",
]


def _repo_dir(name: str) -> Path:
    return ROOT / "repos" / name


def _all_real_repos_available() -> bool:
    return all((_repo_dir(name) / ".git").is_dir() for name in REAL_REPOS)


pytestmark = pytest.mark.skipif(
    not _all_real_repos_available(),
    reason="Docker-imported clones missing under ./repos (copy from rootseeker-zoekt:/repos)",
)


@pytest.fixture
def sync_gateway(tmp_path: Path):
    """Gateway backed by a RepoSyncService pointed at real local clones."""
    # Use a dedicated registry service; point local_path at real clones.
    service = RepoSyncService(
        base_path=tmp_path / "unused-base",
        enable_zoekt=False,
        enable_qdrant=False,
    )

    class Adapter:
        def __init__(self) -> None:
            self.repo_sync_service = service
            self.calls: list[str] = []

        def resolve_service(self, *a, **k):
            raise NotImplementedError

        def get_log_sources(self, *a, **k):
            raise NotImplementedError

        def query_logs_by_trace_id(self, *a, **k):
            raise NotImplementedError

        def query_logs_by_template(self, *a, **k):
            raise NotImplementedError

        def get_trace_chain(self, *a, **k):
            raise NotImplementedError

        def search_code(self, *a, **k):
            raise NotImplementedError

        def semantic_search_code(self, *a, **k):
            raise NotImplementedError

        def read_code(self, *a, **k):
            raise NotImplementedError

        def find_callers(self, *a, **k):
            raise NotImplementedError

        def get_index_status(self, *a, **k):
            raise NotImplementedError

        def send_notification(self, *a, **k):
            raise NotImplementedError

        def repo_register(self, args):
            from rootseeker.code_index.internal_repo_tools import repo_register_tool

            self.calls.append("repo_register")
            return repo_register_tool(service, args)

        def repo_sync(self, args):
            from rootseeker.code_index.internal_repo_tools import repo_sync_tool

            self.calls.append("repo_sync")
            return repo_sync_tool(service, args)

        def repo_list(self, args):
            from rootseeker.code_index.internal_repo_tools import repo_list_tool

            self.calls.append("repo_list")
            return repo_list_tool(service, args)

        def repo_get(self, args):
            from rootseeker.code_index.internal_repo_tools import repo_get_tool

            self.calls.append("repo_get")
            return repo_get_tool(service, args)

        def repo_unregister(self, args):
            from rootseeker.code_index.internal_repo_tools import repo_unregister_tool

            self.calls.append("repo_unregister")
            return repo_unregister_tool(service, args)

        def repo_sync_all(self, args):
            from rootseeker.code_index.internal_repo_tools import repo_sync_all_tool

            self.calls.append("repo_sync_all")
            return repo_sync_all_tool(service, args)

        def repo_index_status(self, args):
            from rootseeker.code_index.internal_repo_tools import repo_index_status_tool

            self.calls.append("repo_index_status")
            return repo_index_status_tool(service, args)

        def repo_semantic_search(self, args):
            from rootseeker.code_index.internal_repo_tools import repo_semantic_search_tool

            self.calls.append("repo_semantic_search")
            return repo_semantic_search_tool(service, args)

        def lsp_references(self, args):
            raise NotImplementedError

        def lsp_definition(self, args):
            raise NotImplementedError

        def lsp_hover(self, args):
            raise NotImplementedError

        def lsp_symbols(self, args):
            raise NotImplementedError

    adapter = Adapter()
    # Register real Docker-imported clones as local-only (no remote pull).
    for name in REAL_REPOS:
        service.register(
            RepositoryRef(
                name=name,
                url=None,
                local_path=str(_repo_dir(name).resolve()),
                default_branch="main",
                metadata={"source": "docker-import", "verify": "real-sync"},
            )
        )

    registry = ToolRegistry()
    register_internal_tools(registry, adapter=adapter)
    gateway = McpGateway(registry, PolicyGuard(deny_write=False), InMemoryAuditLog())
    return gateway, adapter, service


def _invoke(gateway: McpGateway, tool_name: str, arguments: dict):
    return gateway.invoke(
        ToolCallRequest(
            case_id="real-sync",
            step_id="s1",
            skill_name="flows/default-log-triage",
            tool_name=tool_name,
            arguments=arguments,
        ),
        actor="real-sync-test",
    )


def test_repo_sync_real_docker_imported_project(sync_gateway) -> None:
    gateway, adapter, service = sync_gateway
    name = "iceycn__mcp-server-apollo"

    result = _invoke(gateway, "repo.sync", {"name": name, "trigger_index": False})
    assert result.ok, result.error
    assert "repo_sync" in adapter.calls
    content = result.content
    assert content["ok"] is True
    assert content["repo_name"] == name
    assert content["state"] == RepoSyncState.COMPLETED.value
    assert content.get("message")
    # Must have a real commit from the imported clone
    repo = service.get_repo(name)
    assert repo is not None
    assert repo.sync_status.commit_hash
    assert len(repo.sync_status.commit_hash) >= 7


def test_repo_sync_all_real_docker_imported_projects(sync_gateway) -> None:
    gateway, adapter, service = sync_gateway

    result = _invoke(gateway, "repo.sync_all", {"trigger_index": False})
    assert result.ok, result.error
    assert "repo_sync_all" in adapter.calls
    content = result.content
    assert content["ok"] is True
    assert content["total"] == len(REAL_REPOS)
    assert len(content["results"]) == len(REAL_REPOS)
    by_name = {row["repo_name"]: row for row in content["results"]}
    for name in REAL_REPOS:
        assert by_name[name]["success"] is True
        assert by_name[name]["state"] == RepoSyncState.COMPLETED.value
        repo = service.get_repo(name)
        assert repo is not None
        assert repo.sync_status.commit_hash
