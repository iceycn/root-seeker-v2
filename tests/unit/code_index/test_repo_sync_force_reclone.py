from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from rootseeker.code_index.internal_repo_tools import repo_sync_tool
from rootseeker.code_index.repo_sync import RepoSyncService
from rootseeker.contracts.repository import RepositoryRef


def test_repo_sync_tool_passes_force_reclone(tmp_path: Path) -> None:
    sync = RepoSyncService(base_path=tmp_path)
    sync.register(
        RepositoryRef(
            name="demo-repo",
            url="https://example.invalid/demo.git",
            local_path=str(tmp_path / "demo-repo"),
        )
    )
    local_path = tmp_path / "demo-repo"
    local_path.mkdir()
    (local_path / "stale.txt").write_text("broken", encoding="utf-8")

    with patch.object(sync, "_git_clone", return_value=("abc123", "main")) as clone_mock, patch.object(
        sync, "_get_commit_hash", return_value="abc123"
    ), patch.object(sync, "zoekt_indexer", None), patch.object(sync, "qdrant_indexer", None):
        result = repo_sync_tool(
            sync,
            {"name": "demo-repo", "trigger_index": False, "force_reclone": True},
        )

    assert result["ok"] is True
    clone_mock.assert_called_once()
    assert not (tmp_path / "demo-repo" / "stale.txt").exists()
