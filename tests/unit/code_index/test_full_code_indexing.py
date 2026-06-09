from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from rootseeker.code_index.chunker import chunk_code_files
from rootseeker.code_index.embedding import HashEmbeddingProvider
from rootseeker.code_index.file_scanner import scan_code_files
from rootseeker.code_index.qdrant_indexer import QdrantIndexer
from rootseeker.code_index.repo_sync import RepoSyncService
from rootseeker.code_index.zoekt_indexer import ZoektIndexer
from rootseeker.contracts.repository import RepositoryRef, RepoSyncState


def test_scan_chunk_and_hash_embedding(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".git").mkdir()
    (repo / "src").mkdir()
    (repo / "src" / "app.py").write_text("def hello():\n    return 'world'\n", encoding="utf-8")
    (repo / "src" / "app.bin").write_bytes(b"\x00\x01")

    files = scan_code_files(repo)
    assert [f.path for f in files] == ["src/app.py"]

    chunks = chunk_code_files("repo", files)
    assert len(chunks) == 1
    assert chunks[0].path == "src/app.py"

    emb = HashEmbeddingProvider(dimension=32)
    vec = emb.embed_query(chunks[0].content)
    assert len(vec) == 32
    assert any(v != 0 for v in vec)


def test_qdrant_index_chunks_uses_stable_uuid_and_payload() -> None:
    provider = HashEmbeddingProvider(dimension=8)
    indexer = QdrantIndexer(endpoint="http://qdrant:6333", embedding_provider=provider)

    with patch.object(indexer, "ensure_collection", return_value=True), patch.object(
        indexer, "delete_repo", return_value=True
    ), patch("httpx.Client") as mock_client:
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_context = MagicMock()
        mock_context.__enter__ = MagicMock(return_value=mock_context)
        mock_context.__exit__ = MagicMock(return_value=False)
        mock_context.put.return_value = mock_response
        mock_client.return_value = mock_context

        files = [{"path": "a.py", "content": "def a(): pass", "language": "python"}]
        status = indexer.index_code_files("repo", files, [[0.1] * 8])

        assert status.ready
        payload = mock_context.put.call_args.kwargs["json"]
        assert payload["points"][0]["id"].count("-") == 4
        assert payload["points"][0]["payload"]["repo"] == "repo"


def test_zoekt_index_repository_runs_cli(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    index_dir = tmp_path / "index"
    indexer = ZoektIndexer(endpoint="http://zoekt:6070", index_dir=index_dir, binary="/bin/zoekt-index")

    with patch("subprocess.run") as run:
        run.return_value = MagicMock(stdout="ok", stderr="")
        status = indexer.index_repository("repo", "file://repo", local_path=repo)

    assert status.ready
    cmd = run.call_args.args[0]
    assert cmd[:3] == ["/bin/zoekt-index", "-index", str(index_dir)]
    assert cmd[-1] == str(repo)


def test_repo_sync_service_indexes_local_repo(tmp_path: Path) -> None:
    service = RepoSyncService(base_path=tmp_path / "repos", enable_zoekt=False, enable_qdrant=False)
    service.register(RepositoryRef(name="repo", url="https://example.invalid/repo.git", default_branch="main"))

    local = tmp_path / "repos" / "repo"
    local.mkdir(parents=True)
    (local / ".git").mkdir()
    (local / "README.md").write_text("hello readme\n", encoding="utf-8")

    with patch.object(service, "_git_pull", return_value="abc123"):
        result = service.sync("repo", trigger_index=True)

    assert result.success
    assert result.repo.sync_status.state == RepoSyncState.COMPLETED
    assert result.repo.sync_status.commit_hash == "abc123"
