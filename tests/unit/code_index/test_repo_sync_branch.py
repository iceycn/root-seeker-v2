from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from rootseeker.code_index.repo_sync import RepoSyncService, detect_remote_default_branch, _is_missing_remote_branch_error
from rootseeker.contracts.repository import RepositoryRef


def test_is_missing_remote_branch_error() -> None:
    stderr = "fatal: Remote branch main not found in upstream origin"
    assert _is_missing_remote_branch_error(stderr) is True
    assert _is_missing_remote_branch_error("fatal: couldn't find remote ref main") is True
    assert _is_missing_remote_branch_error("permission denied") is False


def test_detect_remote_default_branch_parses_symref() -> None:
    with patch("rootseeker.code_index.repo_sync.subprocess.run") as run_mock:
        run_mock.return_value.returncode = 0
        run_mock.return_value.stdout = "ref: refs/heads/master\tHEAD\nabc123\tHEAD\n"
        assert detect_remote_default_branch("https://example.invalid/repo.git") == "master"


def test_git_clone_retries_with_detected_default_branch(tmp_path: Path) -> None:
    sync = RepoSyncService()
    repo_path = tmp_path / "repo"
    calls: list[str] = []

    def fake_run_clone(url: str, path: Path, branch: str) -> str | None:
        calls.append(branch)
        if branch == "main":
            return "fatal: couldn't find remote ref main"
        repo_path.mkdir(parents=True)
        (repo_path / ".git").mkdir()
        return None

    with patch.object(sync, "_run_git_clone", side_effect=fake_run_clone), patch(
        "rootseeker.code_index.repo_sync.detect_remote_default_branch",
        return_value="master",
    ), patch.object(sync, "_get_commit_hash", return_value="deadbeef"):
        commit_hash, branch = sync._git_clone("https://example.invalid/repo.git", repo_path, "main")

    assert commit_hash == "deadbeef"
    assert branch == "master"
    assert calls == ["main", "master"]


def test_git_clone_raises_when_default_branch_cannot_be_detected(tmp_path: Path) -> None:
    sync = RepoSyncService()
    repo_path = tmp_path / "repo"

    with patch.object(
        sync,
        "_run_git_clone",
        return_value="fatal: Remote branch main not found in upstream origin",
    ), patch("rootseeker.code_index.repo_sync.detect_remote_default_branch", return_value=None):
        with pytest.raises(Exception):
            sync._git_clone("https://example.invalid/repo.git", repo_path, "main")


def test_git_pull_uses_local_branch_when_configured_branch_missing(tmp_path: Path) -> None:
    sync = RepoSyncService()
    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    (repo_path / ".git").mkdir()

    calls: list[str] = []

    def fake_fetch_reset(path: Path, branch: str) -> str | None:
        calls.append(branch)
        if branch == "main":
            return "fatal: couldn't find remote ref main"
        return None

    with patch.object(sync, "_set_origin_url"), patch.object(
        sync, "_run_git_fetch_reset", side_effect=fake_fetch_reset
    ), patch.object(sync, "_get_current_branch", return_value="master"), patch.object(
        sync, "_get_commit_hash", return_value="deadbeef"
    ):
        commit_hash, branch = sync._git_pull(repo_path, "main", url="https://example.invalid/repo.git")

    assert commit_hash == "deadbeef"
    assert branch == "master"
    assert calls == ["main", "master"]


def test_sync_updates_default_branch_after_clone_fallback() -> None:
    sync = RepoSyncService()
    sync.register(
        RepositoryRef(
            name="codeup-repo",
            url="https://codeup.aliyun.com/org/repo.git",
            default_branch="main",
        )
    )

    with patch.object(sync, "_git_clone", return_value=("abc123", "master")), patch.object(
        sync, "zoekt_indexer", None
    ), patch.object(sync, "qdrant_indexer", None):
        result = sync.sync("codeup-repo", trigger_index=False)

    assert result.success is True
    assert sync.get_repo("codeup-repo").default_branch == "master"
