from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import Field

from rootseeker.contracts.common import RootSeekerModel, utc_now

__all__ = ["RepositoryRef", "RepoSyncStatus", "RepoSyncState"]


class RepoSyncState(StrEnum):
    """仓库同步状态"""
    PENDING = "pending"          # 待同步
    SYNCING = "syncing"          # 同步中
    INDEXING = "indexing"        # 索引中
    COMPLETED = "completed"      # 已完成
    FAILED = "failed"            # 失败


class RepoSyncStatus(RootSeekerModel):
    """仓库同步状态详情"""
    state: RepoSyncState = RepoSyncState.PENDING
    last_sync_at: datetime | None = None
    last_index_at: datetime | None = None
    error_message: str | None = None
    commit_hash: str | None = None
    files_indexed: int = 0
    checked_at: datetime = Field(default_factory=utc_now)


class RepositoryRef(RootSeekerModel):
    """代码仓库引用"""
    name: str = Field(min_length=1, description="仓库名称，唯一标识")
    url: str | None = Field(default=None, description="Git 仓库 URL")
    default_branch: str | None = Field(default="main", description="默认分支")
    vcs: str = Field(default="git", description="版本控制系统类型")
    local_path: str | None = Field(default=None, description="本地克隆路径")
    sync_status: RepoSyncStatus = Field(default_factory=RepoSyncStatus, description="同步状态")
    metadata: dict[str, Any] = Field(default_factory=dict, description="扩展元数据")
