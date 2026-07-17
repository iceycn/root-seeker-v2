from __future__ import annotations

from unittest.mock import patch

from rootseeker.code_index.git_auth import GitCredentials
from rootseeker.code_index.repo_sync import RepoSyncService
from rootseeker.contracts.repository import RepositoryRef, RepoSyncState


def test_repo_sync_uses_authenticated_https_clone_url() -> None:
    def resolver(repo: RepositoryRef) -> GitCredentials | None:
        assert repo.name == "codeup-repo"
        return GitCredentials(username="clone-user", token="pt-token", provider="yunxiao")

    sync = RepoSyncService(credential_resolver=resolver)
    sync.register(
        RepositoryRef(
            name="codeup-repo",
            url="https://codeup.aliyun.com/org/repo.git",
            metadata={"provider": "yunxiao", "remote_name": "yx-main"},
        )
    )

    with patch.object(sync, "_git_clone", return_value=("abc123", "main")) as clone_mock, patch.object(
        sync, "_get_commit_hash", return_value="abc123"
    ), patch.object(sync, "zoekt_indexer", None), patch.object(sync, "qdrant_indexer", None):
        result = sync.sync("codeup-repo", trigger_index=False)

    assert result.success is True
    clone_mock.assert_called_once()
    clone_url = clone_mock.call_args.args[0]
    assert clone_url.startswith("https://clone-user:pt-token@codeup.aliyun.com/")


def test_repo_sync_pull_refreshes_origin_with_authenticated_url(tmp_path) -> None:
    def resolver(repo: RepositoryRef) -> GitCredentials | None:
        return GitCredentials(username="clone-user", token="new-token", provider="yunxiao")

    local_path = tmp_path / "codeup-repo"
    local_path.mkdir()
    (local_path / ".git").mkdir()

    sync = RepoSyncService(base_path=tmp_path, credential_resolver=resolver)
    sync.register(
        RepositoryRef(
            name="codeup-repo",
            url="https://codeup.aliyun.com/org/repo.git",
            local_path=str(local_path),
            metadata={"provider": "yunxiao", "remote_name": "yx-main"},
        )
    )

    with patch.object(sync, "_is_usable_git_repo", return_value=True), patch.object(
        sync, "_set_origin_url"
    ) as set_origin_mock, patch.object(
        sync, "_run_git_fetch_reset", return_value=None
    ), patch.object(sync, "_get_current_branch", return_value="main"), patch.object(
        sync, "_get_commit_hash", return_value="def456"
    ), patch.object(sync, "zoekt_indexer", None), patch.object(sync, "qdrant_indexer", None):
        result = sync.sync("codeup-repo", trigger_index=False)

    assert result.success is True
    set_origin_mock.assert_called_once()
    origin_url = set_origin_mock.call_args.args[1]
    assert origin_url.startswith("https://clone-user:new-token@codeup.aliyun.com/")


def test_repo_sync_rejects_remote_credentials_for_mismatched_git_host() -> None:
    def resolver(repo: RepositoryRef) -> GitCredentials | None:
        return GitCredentials(username="clone-user", token="pt-token", provider="yunxiao")

    sync = RepoSyncService(credential_resolver=resolver)
    sync.register(
        RepositoryRef(
            name="evil-repo",
            url="https://evil.example.com/org/repo.git",
            metadata={"provider": "yunxiao", "remote_name": "yx-main"},
        )
    )

    result = sync.sync("evil-repo", trigger_index=False)

    assert result.success is False
    assert result.repo.sync_status.state == RepoSyncState.FAILED
    assert "不匹配" in (result.message or "")
    assert "pt-token" not in (result.message or "")
