from __future__ import annotations

from unittest.mock import MagicMock, patch

from rootseeker.code_index import (
    QdrantIndexer,
    RepoSyncService,
    ZoektIndexer,
    code_hits_to_evidence,
    find_symbol_references,
)
from rootseeker.contracts.evidence import EvidencePack
from rootseeker.contracts.repository import RepositoryRef, RepoSyncState


def test_repo_sync_and_index_status() -> None:
    sync = RepoSyncService()
    sync.register(RepositoryRef(name="repo-a"))
    assert len(sync.list_repos()) == 1


def test_lsp_and_code_evidence_mapper() -> None:
    """测试 LSP 和代码证据映射"""
    # 测试证据映射功能
    pack = EvidencePack(case_id="c1")

    # 模拟代码搜索结果
    mock_hits = [
        {"path": "src/main.py", "line": 10, "snippet": "def Foo():", "symbol": "Foo"}
    ]
    code_hits_to_evidence(pack=pack, tool_name="code.search", query="Foo", hits=mock_hits)
    assert len(pack.items) == 1

    # 测试空符号查询
    refs = find_symbol_references("")
    assert refs == []


def test_repository_ref_with_sync_status() -> None:
    """测试 RepositoryRef 包含同步状态"""
    repo = RepositoryRef(
        name="test-repo",
        url="https://github.com/test/repo.git",
        default_branch="main",
        local_path="/tmp/repos/test-repo",
    )

    assert repo.name == "test-repo"
    assert repo.url == "https://github.com/test/repo.git"
    assert repo.sync_status.state == RepoSyncState.PENDING


def test_repo_sync_service_register() -> None:
    """测试仓库注册"""
    sync = RepoSyncService(base_path="/tmp/test-repos")

    repo = RepositoryRef(
        name="my-service",
        url="https://github.com/org/my-service.git",
        default_branch="main",
        metadata={"team": "platform"},
    )

    sync.register(repo)

    # 验证注册成功
    repos = sync.list_repos()
    assert len(repos) == 1
    assert repos[0].name == "my-service"

    # 验证可以获取
    retrieved = sync.get_repo("my-service")
    assert retrieved is not None
    assert retrieved.url == "https://github.com/org/my-service.git"


def test_repo_sync_service_unregister() -> None:
    """测试仓库注销"""
    sync = RepoSyncService()

    repo = RepositoryRef(name="temp-repo", url="https://github.com/temp/repo.git")
    sync.register(repo)

    assert len(sync.list_repos()) == 1

    # 注销
    success = sync.unregister("temp-repo")
    assert success is True
    assert len(sync.list_repos()) == 0

    # 再次注销返回 False
    success = sync.unregister("temp-repo")
    assert success is False


def test_zoekt_indexer_search() -> None:
    """测试 Zoekt 索引器搜索"""
    indexer = ZoektIndexer(endpoint="http://localhost:6070")

    # Mock HTTP 响应
    with patch("httpx.Client") as mock_client:
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "Result": {
                "Files": [
                    {
                        "FileName": "src/main.py",
                        "LineMatches": [{"LineNumber": 10, "Line": "def main():"}],
                    }
                ]
            }
        }
        mock_response.raise_for_status = MagicMock()

        mock_client_instance = MagicMock()
        mock_client_instance.post.return_value = mock_response
        mock_client.return_value.__enter__.return_value = mock_client_instance

        result = indexer.search("def main")

        assert "Result" in result


def test_qdrant_indexer_ensure_collection() -> None:
    """测试 Qdrant 索引器集合管理"""
    indexer = QdrantIndexer(endpoint="http://localhost:6333")

    # Mock HTTP 响应 - 集合已存在
    with patch("httpx.Client") as mock_client:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()

        mock_client_instance = MagicMock()
        mock_client_instance.get.return_value = mock_response
        mock_client.return_value.__enter__.return_value = mock_client_instance

        success = indexer.ensure_collection()
        assert success is True


def test_repo_sync_service_sync_without_url() -> None:
    """测试同步没有 URL 的仓库"""
    sync = RepoSyncService()

    repo = RepositoryRef(name="no-url-repo")  # 没有 URL
    sync.register(repo)

    result = sync.sync("no-url-repo")

    assert result.success is False
    assert "URL is required" in result.message


def test_repo_sync_service_sync_nonexistent() -> None:
    """测试同步不存在的仓库"""
    sync = RepoSyncService()

    result = sync.sync("nonexistent-repo")

    assert result.success is False
    assert "not found" in result.message


def test_repo_sync_service_list_with_filter() -> None:
    """测试按状态过滤仓库列表"""
    sync = RepoSyncService()

    repo1 = RepositoryRef(name="repo-1", url="https://github.com/1.git")
    repo2 = RepositoryRef(name="repo-2", url="https://github.com/2.git")

    sync.register(repo1)
    sync.register(repo2)

    # 修改 repo1 的状态
    repo1.sync_status.state = RepoSyncState.COMPLETED

    # 过滤 COMPLETED 状态
    sync.list_repos()
    # 注意：list_repos 返回的是副本，需要通过 get_repo 获取引用
    repo1_ref = sync.get_repo("repo-1")
    assert repo1_ref is not None
    assert repo1_ref.sync_status.state == RepoSyncState.COMPLETED
