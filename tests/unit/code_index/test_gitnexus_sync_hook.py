from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from rootseeker.code_index.gitnexus_cli import GitNexusCliConfig, GitNexusCommandResult
from rootseeker.code_index.gitnexus_indexer import GitNexusIndexer
from rootseeker.code_index.repo_sync import RepoSyncService
from rootseeker.contracts.indexing import IndexKind
from rootseeker.contracts.repository import RepositoryRef


def test_gitnexus_indexer_reports_ready_on_success(tmp_path: Path) -> None:
    repo = tmp_path / "demo"
    repo.mkdir()
    (repo / ".gitnexus").mkdir()
    cli = MagicMock()
    cli.available = True
    cli.analyze.return_value = GitNexusCommandResult(
        ok=True,
        exit_code=0,
        stdout="done",
        stderr="",
        command=["gitnexus", "analyze"],
    )
    indexer = GitNexusIndexer(cli=cli, config=GitNexusCliConfig(enabled=True))
    status = indexer.index_repository("demo", repo)
    assert status.kind == IndexKind.GITNEXUS
    assert status.ready is True
    cli.analyze.assert_called_once()


def test_repo_sync_hooks_gitnexus_after_index(tmp_path: Path, monkeypatch) -> None:
    repo_dir = tmp_path / "svc"
    repo_dir.mkdir()
    (repo_dir / ".git").mkdir()
    (repo_dir / "A.java").write_text("class A {}", encoding="utf-8")

    service = RepoSyncService(
        base_path=tmp_path,
        enable_zoekt=False,
        enable_qdrant=False,
        enable_gitnexus=True,
    )
    fake_status = MagicMock()
    fake_status.ready = True
    fake_status.kind = IndexKind.GITNEXUS
    fake_status.detail = {}
    fake_status.model_dump = lambda mode="json": {"ready": True, "kind": "gitnexus"}
    service.gitnexus_indexer = MagicMock()
    service.gitnexus_indexer.index_repository.return_value = fake_status

    monkeypatch.setattr(service, "_get_commit_hash", lambda path: "abc123")
    monkeypatch.setattr(
        service,
        "_is_usable_git_repo",
        lambda path: Path(path).resolve() == repo_dir.resolve(),
    )
    service.register(
        RepositoryRef(name="svc", url=None, local_path=str(repo_dir), default_branch="main")
    )
    result = service.sync("svc", trigger_index=True)
    assert result.success is True
    assert result.gitnexus_status is fake_status
    service.gitnexus_indexer.index_repository.assert_called_once()
