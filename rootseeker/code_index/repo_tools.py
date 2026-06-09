from __future__ import annotations

import logging
from typing import Any

from rootseeker.code_index.repo_sync import RepoSyncService
from rootseeker.contracts.repository import RepositoryRef

logger = logging.getLogger(__name__)

__all__ = ["create_repo_handlers"]

# 全局 RepoSyncService 实例
_repo_sync_service: RepoSyncService | None = None


def get_repo_sync_service() -> RepoSyncService:
    """获取全局 RepoSyncService 实例"""
    global _repo_sync_service
    if _repo_sync_service is None:
        _repo_sync_service = RepoSyncService()
    return _repo_sync_service


def set_repo_sync_service(service: RepoSyncService) -> None:
    """设置全局 RepoSyncService 实例"""
    global _repo_sync_service
    _repo_sync_service = service


def create_repo_handlers(sync_service: RepoSyncService | None = None) -> dict[str, Any]:
    """
    创建 repo MCP 工具处理器

    返回一个字典：{tool_name: handler_function}
    """
    service = sync_service or get_repo_sync_service()

    def repo_register(args: dict[str, Any]) -> dict[str, Any]:
        """
        注册仓库

        Args:
            name: 仓库名称
            url: Git 仓库 URL
            branch: 默认分支（可选，默认 main）
            metadata: 扩展元数据（可选）
        """
        name = args.get("name")
        if not name:
            return {"ok": False, "error": "name is required"}

        repo = RepositoryRef(
            name=str(name),
            url=args.get("url"),
            default_branch=args.get("branch", "main"),
            metadata=args.get("metadata", {}),
        )

        service.register(repo)

        return {
            "ok": True,
            "repo": repo.model_dump(mode="json"),
        }

    def repo_sync(args: dict[str, Any]) -> dict[str, Any]:
        """
        同步仓库

        Args:
            name: 仓库名称
            trigger_index: 是否触发索引（可选，默认 True）
        """
        name = args.get("name")
        if not name:
            return {"ok": False, "error": "name is required"}

        trigger_index = args.get("trigger_index", True)
        result = service.sync(str(name), trigger_index=trigger_index)

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

        return response

    def repo_list(args: dict[str, Any]) -> dict[str, Any]:
        """
        列出所有仓库

        Args:
            state: 过滤状态（可选）
        """
        repos = service.list_repos()

        # 按状态过滤
        state_filter = args.get("state")
        if state_filter:
            repos = [r for r in repos if r.sync_status.state.value == state_filter]

        return {
            "ok": True,
            "repos": [r.model_dump(mode="json") for r in repos],
            "total": len(repos),
        }

    def repo_get(args: dict[str, Any]) -> dict[str, Any]:
        """
        获取仓库详情

        Args:
            name: 仓库名称
        """
        name = args.get("name")
        if not name:
            return {"ok": False, "error": "name is required"}

        repo = service.get_repo(str(name))
        if not repo:
            return {"ok": False, "error": f"Repository not found: {name}"}

        return {
            "ok": True,
            "repo": repo.model_dump(mode="json"),
        }

    def repo_unregister(args: dict[str, Any]) -> dict[str, Any]:
        """
        注销仓库

        Args:
            name: 仓库名称
        """
        name = args.get("name")
        if not name:
            return {"ok": False, "error": "name is required"}

        success = service.unregister(str(name))

        return {
            "ok": success,
            "message": f"Repository {name} unregistered" if success else f"Repository {name} not found",
        }

    def repo_sync_all(args: dict[str, Any]) -> dict[str, Any]:
        """
        同步所有仓库

        Args:
            trigger_index: 是否触发索引（可选，默认 True）
        """
        trigger_index = args.get("trigger_index", True)
        results = service.sync_all(trigger_index=trigger_index)

        return {
            "ok": True,
            "total": len(results),
            "results": [
                {
                    "repo_name": r.repo.name,
                    "success": r.success,
                    "message": r.message,
                }
                for r in results
            ],
        }

    def repo_index_status(args: dict[str, Any]) -> dict[str, Any]:
        """
        获取仓库索引状态

        Args:
            name: 仓库名称
        """
        name = args.get("name")
        if not name:
            return {"ok": False, "error": "name is required"}

        statuses = service.get_index_status(str(name))

        return {
            "ok": True,
            "repo_name": name,
            "indexes": {
                kind: status.model_dump(mode="json")
                for kind, status in statuses.items()
            },
        }

    def repo_semantic_search(args: dict[str, Any]) -> dict[str, Any]:
        query = str(args.get("query", "")).strip()
        if not query:
            return {"ok": False, "error": "query is required", "result": []}
        repo_name = args.get("repo_name")
        return service.semantic_search(
            query=query,
            repo_name=str(repo_name) if repo_name else None,
            limit=int(args.get("limit", 10)),
        )

    return {
        "repo.register": repo_register,
        "repo.sync": repo_sync,
        "repo.list": repo_list,
        "repo.get": repo_get,
        "repo.unregister": repo_unregister,
        "repo.sync_all": repo_sync_all,
        "repo.index_status": repo_index_status,
        "repo.semantic_search": repo_semantic_search,
    }
