"""Shared repo MCP handlers used by Composite and HTTP internal adapters."""

from __future__ import annotations

from typing import Any

from rootseeker.code_index.repo_sync import RepoSyncService
from rootseeker.contracts.repository import RepositoryRef

__all__ = [
    "repo_register_tool",
    "repo_sync_tool",
    "repo_list_tool",
    "repo_get_tool",
    "repo_unregister_tool",
    "repo_sync_all_tool",
    "repo_sync_changed_tool",
    "repo_index_status_tool",
    "repo_semantic_search_tool",
]


def repo_register_tool(service: RepoSyncService, args: dict[str, Any]) -> dict[str, Any]:
    name = args.get("name")
    if not name:
        return {"ok": False, "error": "name is required"}

    repo = RepositoryRef(
        name=str(name),
        url=args.get("url"),
        default_branch=args.get("branch", "main"),
        local_path=args.get("local_path"),
        metadata=args.get("metadata", {}),
    )
    service.register(repo)
    return {"ok": True, "repo": repo.model_dump(mode="json")}


def repo_sync_tool(service: RepoSyncService, args: dict[str, Any]) -> dict[str, Any]:
    name = args.get("name")
    if not name:
        return {"ok": False, "error": "name is required"}

    trigger_index = bool(args.get("trigger_index", True))
    force_reclone = bool(args.get("force_reclone", False))
    result = service.sync(
        str(name),
        trigger_index=trigger_index,
        force_reclone=force_reclone,
    )

    response: dict[str, Any] = {
        "ok": result.success,
        "repo_name": result.repo.name,
        "message": result.message,
        "state": result.repo.sync_status.state.value,
    }
    if result.zoekt_status:
        response["zoekt_status"] = result.zoekt_status.model_dump(mode="json")
    if result.qdrant_status:
        response["qdrant_status"] = result.qdrant_status.model_dump(mode="json")
    if result.gitnexus_status:
        response["gitnexus_status"] = result.gitnexus_status.model_dump(mode="json")
    return response


def repo_list_tool(service: RepoSyncService, args: dict[str, Any]) -> dict[str, Any]:
    repos = service.list_repos()
    state_filter = args.get("state")
    if state_filter:
        repos = [r for r in repos if r.sync_status.state.value == state_filter]
    return {"ok": True, "repos": [r.model_dump(mode="json") for r in repos], "total": len(repos)}


def repo_get_tool(service: RepoSyncService, args: dict[str, Any]) -> dict[str, Any]:
    name = args.get("name")
    if not name:
        return {"ok": False, "error": "name is required"}

    repo = service.get_repo(str(name))
    if not repo:
        return {"ok": False, "error": f"Repository not found: {name}"}
    return {"ok": True, "repo": repo.model_dump(mode="json")}


def repo_unregister_tool(service: RepoSyncService, args: dict[str, Any]) -> dict[str, Any]:
    name = args.get("name")
    if not name:
        return {"ok": False, "error": "name is required"}

    success = service.unregister(str(name))
    return {
        "ok": success,
        "message": f"Repository {name} unregistered" if success else f"Repository {name} not found",
    }


def repo_sync_all_tool(service: RepoSyncService, args: dict[str, Any]) -> dict[str, Any]:
    trigger_index = args.get("trigger_index", True)
    force_gitnexus = bool(args.get("force_gitnexus", False))
    results = service.sync_all(trigger_index=trigger_index, force_gitnexus=force_gitnexus)
    return {
        "ok": True,
        "total": len(results),
        "results": [
            {
                "repo_name": r.repo.name,
                "success": r.success,
                "message": r.message,
                "state": r.repo.sync_status.state.value,
                "gitnexus_ready": bool(r.gitnexus_status.ready) if r.gitnexus_status else None,
            }
            for r in results
        ],
    }


def repo_sync_changed_tool(service: RepoSyncService, args: dict[str, Any]) -> dict[str, Any]:
    trigger_index = bool(args.get("trigger_index", True))
    payload = service.sync_changed(trigger_index=trigger_index)
    results = payload.get("results") or []
    return {
        "ok": bool(payload.get("ok", False)),
        "checked": list(payload.get("checked") or []),
        "changed": list(payload.get("changed") or []),
        "synced": list(payload.get("synced") or []),
        "skipped": list(payload.get("skipped") or []),
        "failed_checks": list(payload.get("failed_checks") or []),
        "total_changed": len(payload.get("changed") or []),
        "results": [
            {
                "repo_name": r.repo.name,
                "success": r.success,
                "message": r.message,
                "state": r.repo.sync_status.state.value,
                "commit_hash": r.repo.sync_status.commit_hash,
                "zoekt_ready": bool(r.zoekt_status.ready) if r.zoekt_status else None,
                "qdrant_ready": bool(r.qdrant_status.ready) if r.qdrant_status else None,
                "gitnexus_ready": bool(r.gitnexus_status.ready) if r.gitnexus_status else None,
            }
            for r in results
        ],
    }


def repo_index_status_tool(service: RepoSyncService, args: dict[str, Any]) -> dict[str, Any]:
    name = args.get("name")
    if not name:
        return {"ok": False, "error": "name is required"}

    statuses = service.get_index_status(str(name))
    return {
        "ok": True,
        "repo_name": name,
        "indexes": {kind: status.model_dump(mode="json") for kind, status in statuses.items()},
    }


def repo_semantic_search_tool(service: RepoSyncService, args: dict[str, Any]) -> dict[str, Any]:
    query = str(args.get("query", "")).strip()
    if not query:
        return {"ok": False, "error": "query is required", "result": []}
    repo_name = args.get("repo_name")
    limit = int(args.get("limit", 10))
    return service.semantic_search(query=query, repo_name=str(repo_name) if repo_name else None, limit=limit)
