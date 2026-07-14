"""Tests for local_path resolution and corrupt checkout repair."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from rootseeker.code_index.repo_sync import (
    RepoSyncResult,
    RepoSyncService,
    _is_container_style_repo_path,
)
from rootseeker.contracts.repository import RepositoryRef


def test_is_container_style_repo_path() -> None:
    assert _is_container_style_repo_path("/data/repos/foo")
    assert _is_container_style_repo_path(r"\data\repos\foo")
    assert _is_container_style_repo_path(r"E:\data\repos\foo")
    assert _is_container_style_repo_path("E:/data/repos/foo")
    assert not _is_container_style_repo_path("repos/foo")
    assert not _is_container_style_repo_path(r"E:\CodeProjects\root-seeker-v2\repos\foo")


def test_resolve_local_path_prefers_existing_base_path_dir(tmp_path: Path) -> None:
    service = RepoSyncService(base_path=tmp_path / "repos", enable_zoekt=False, enable_qdrant=False)
    preferred = tmp_path / "repos" / "demo"
    preferred.mkdir(parents=True)
    (preferred / ".git").mkdir()
    repo = RepositoryRef(name="demo", url="https://example.invalid/demo.git", local_path="/data/repos/demo")
    assert service._resolve_local_path(repo) == preferred.absolute()


def test_resolve_local_path_keeps_existing_windows_data_repos(tmp_path: Path) -> None:
    service = RepoSyncService(base_path=tmp_path / "repos", enable_zoekt=False, enable_qdrant=False)
    legacy = tmp_path / "data" / "repos" / "demo"
    legacy.mkdir(parents=True)
    (legacy / ".git").mkdir()
    with patch.object(service, "_is_usable_git_repo", side_effect=lambda p: Path(p).resolve() == legacy.resolve()):
        repo = RepositoryRef(name="demo", url="https://example.invalid/demo.git", local_path=str(legacy))
        assert service._resolve_local_path(repo) == legacy.absolute()


def test_resolve_local_path_maps_missing_container_path_to_base(tmp_path: Path) -> None:
    service = RepoSyncService(base_path=tmp_path / "repos", enable_zoekt=False, enable_qdrant=False)
    repo = RepositoryRef(name="demo", url="https://example.invalid/demo.git", local_path="/data/repos/demo")
    assert service._resolve_local_path(repo) == (tmp_path / "repos" / "demo").absolute()


def test_has_remote_updates_treats_corrupt_checkout_as_needs_sync(tmp_path: Path) -> None:
    service = RepoSyncService(base_path=tmp_path / "repos", enable_zoekt=False, enable_qdrant=False)
    broken = tmp_path / "data" / "repos" / "broken"
    broken.mkdir(parents=True)
    (broken / ".git").mkdir()
    service.register(
        RepositoryRef(
            name="broken",
            url="https://example.invalid/broken.git",
            local_path=str(broken),
        )
    )
    assert service.has_remote_updates("broken") is True


def test_sync_reclones_corrupt_checkout(tmp_path: Path) -> None:
    service = RepoSyncService(base_path=tmp_path / "repos", enable_zoekt=False, enable_qdrant=False)
    broken = tmp_path / "repos" / "broken"
    broken.mkdir(parents=True)
    (broken / ".git").mkdir()
    (broken / "stale.txt").write_text("x", encoding="utf-8")
    service.register(
        RepositoryRef(
            name="broken",
            url="https://example.invalid/broken.git",
            local_path=str(broken),
        )
    )

    with patch.object(service, "_git_clone", return_value=("abc123", "main")) as clone_mock:
        result = service.sync("broken", trigger_index=False)

    assert result.success is True
    clone_mock.assert_called_once()
    assert not (broken / "stale.txt").exists()


def test_sync_changed_ok_despite_failed_checks(tmp_path: Path) -> None:
    service = RepoSyncService(base_path=tmp_path, enable_zoekt=False, enable_qdrant=False)
    service.register(RepositoryRef(name="a", url="https://example.invalid/a.git"))
    service.register(RepositoryRef(name="b", url="https://example.invalid/b.git"))

    def _has_updates(name: str) -> bool:
        if name == "a":
            raise RuntimeError("fetch failed")
        return False

    service.has_remote_updates = _has_updates  # type: ignore[method-assign]
    payload = service.sync_changed(trigger_index=False)
    assert payload["ok"] is True
    assert payload["changed"] == []
    assert len(payload["failed_checks"]) == 1
    assert payload["failed_checks"][0]["repo_name"] == "a"


def test_sync_changed_treats_branchless_remote_as_check_warning(tmp_path: Path) -> None:
    service = RepoSyncService(base_path=tmp_path, enable_zoekt=False, enable_qdrant=False)
    service.register(RepositoryRef(name="empty", url="https://example.invalid/empty.git"))

    service.has_remote_updates = lambda _name: True  # type: ignore[method-assign]

    def _sync(name: str, trigger_index: bool = True, force_reclone: bool = False, *, force_gitnexus: bool = False):
        repo = service.get_repo(name)
        assert repo is not None
        return RepoSyncResult(
            repo=repo,
            success=False,
            message="Git operation failed: fatal: Remote branch main not found in upstream origin",
        )

    service.sync = _sync  # type: ignore[method-assign]
    payload = service.sync_changed(trigger_index=False)
    assert payload["ok"] is True
    assert payload["changed"] == ["empty"]
    assert payload["synced"] == []
    assert payload["results"] == []
    assert len(payload["failed_checks"]) == 1
    assert payload["failed_checks"][0]["repo_name"] == "empty"
