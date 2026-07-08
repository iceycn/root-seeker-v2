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
