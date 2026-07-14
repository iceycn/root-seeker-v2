"""Unit tests for RepoSyncService.sync_changed and force_gitnexus."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from rootseeker.code_index.repo_sync import RepoSyncResult, RepoSyncService
from rootseeker.contracts.indexing import IndexKind, IndexStatus
from rootseeker.contracts.repository import RepositoryRef


def test_sync_changed_skips_unchanged_and_forces_gitnexus(tmp_path: Path) -> None:
    service = RepoSyncService(
        base_path=tmp_path,
        enable_zoekt=False,
        enable_qdrant=False,
        enable_gitnexus=True,
    )
    changed = RepositoryRef(name="changed-repo", url="https://example.com/a.git")
    stable = RepositoryRef(name="stable-repo", url="https://example.com/b.git")
    service.register(changed)
    service.register(stable)

    gitnexus = MagicMock()
    gitnexus.index_repository.return_value = IndexStatus(
        index_name="changed-repo",
        kind=IndexKind.GITNEXUS,
        ready=True,
    )
    service.gitnexus_indexer = gitnexus

    def _has_updates(name: str) -> bool:
        return name == "changed-repo"

    def _sync(name: str, trigger_index: bool = True, force_reclone: bool = False, *, force_gitnexus: bool = False):
        assert name == "changed-repo"
        assert trigger_index is True
        assert force_gitnexus is True
        status = service.gitnexus_indexer.index_repository(
            repo_name=name,
            local_path=tmp_path / name,
            force=True if force_gitnexus else None,
        )
        repo = service.get_repo(name)
        assert repo is not None
        return RepoSyncResult(repo=repo, success=True, message="ok", gitnexus_status=status)

    service.has_remote_updates = _has_updates  # type: ignore[method-assign]
    service.sync = _sync  # type: ignore[method-assign]

    payload = service.sync_changed(trigger_index=True)
    assert payload["checked"] == ["changed-repo", "stable-repo"] or set(payload["checked"]) == {
        "changed-repo",
        "stable-repo",
    }
    assert payload["changed"] == ["changed-repo"]
    assert payload["skipped"] == ["stable-repo"]
    assert payload["synced"] == ["changed-repo"]
    assert payload["ok"] is True
    gitnexus.index_repository.assert_called_once()
    assert gitnexus.index_repository.call_args.kwargs.get("force") is True


def test_sync_passes_force_gitnexus_to_indexer(tmp_path: Path) -> None:
    service = RepoSyncService(
        base_path=tmp_path,
        enable_zoekt=False,
        enable_qdrant=False,
        enable_gitnexus=True,
    )
    local = tmp_path / "local-only"
    local.mkdir()
    (local / ".git").mkdir()
    repo = RepositoryRef(name="local-only", url=None, local_path=str(local))
    service.register(repo)

    gitnexus = MagicMock()
    gitnexus.index_repository.return_value = IndexStatus(
        index_name="local-only",
        kind=IndexKind.GITNEXUS,
        ready=True,
    )
    service.gitnexus_indexer = gitnexus
    service._get_commit_hash = lambda _path: "abc123"  # type: ignore[method-assign]
    service._is_usable_git_repo = lambda _path: True  # type: ignore[method-assign]

    result = service.sync("local-only", trigger_index=True, force_gitnexus=True)
    assert result.success is True
    gitnexus.index_repository.assert_called_once()
    assert gitnexus.index_repository.call_args.kwargs.get("force") is True
