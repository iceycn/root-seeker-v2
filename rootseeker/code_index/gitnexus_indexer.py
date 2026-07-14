"""GitNexus repository indexer hooked from RepoSyncService."""

from __future__ import annotations

import logging
import time
from pathlib import Path

from rootseeker.code_index.gitnexus_cli import GitNexusCli, GitNexusCliConfig
from rootseeker.contracts.common import utc_now
from rootseeker.contracts.indexing import IndexKind, IndexStatus

__all__ = ["GitNexusIndexer"]

logger = logging.getLogger(__name__)


class GitNexusIndexer:
    """Run ``gitnexus analyze`` against a local clone and report IndexStatus."""

    def __init__(
        self,
        cli: GitNexusCli | None = None,
        config: GitNexusCliConfig | None = None,
    ) -> None:
        self.config = config or GitNexusCliConfig.from_env()
        self.cli = cli or GitNexusCli(self.config)

    def index_repository(
        self,
        repo_name: str,
        local_path: Path | str,
        *,
        force: bool | None = None,
    ) -> IndexStatus:
        started = time.monotonic()
        path = Path(local_path)
        if not self.config.enabled:
            return IndexStatus(
                index_name=repo_name,
                kind=IndexKind.GITNEXUS,
                ready=False,
                detail={"error": "gitnexus indexing disabled", "skipped": True},
            )
        if not path.exists():
            return IndexStatus(
                index_name=repo_name,
                kind=IndexKind.GITNEXUS,
                ready=False,
                detail={"error": f"local_path does not exist: {path}"},
            )
        if not self.cli.available:
            return IndexStatus(
                index_name=repo_name,
                kind=IndexKind.GITNEXUS,
                ready=False,
                detail={
                    "error": "gitnexus CLI/HTTP not available",
                    "hint": "Install Node.js + `npm i -g gitnexus`, or set ROOTSEEKER_GITNEXUS_ENDPOINT",
                },
            )

        result = self.cli.analyze(path, force=force)
        elapsed_ms = int((time.monotonic() - started) * 1000)
        graph_dir = path / ".gitnexus"
        ready = result.ok and (graph_dir.exists() or result.ok)
        detail: dict = {
            "elapsed_ms": elapsed_ms,
            "local_path": str(path),
            "graph_dir": str(graph_dir),
            "graph_dir_exists": graph_dir.exists(),
            "command": result.command,
            "exit_code": result.exit_code,
        }
        if result.stderr:
            detail["stderr_tail"] = result.stderr[-2000:]
        if result.stdout:
            detail["stdout_tail"] = result.stdout[-2000:]
        if not result.ok:
            detail["error"] = (result.stderr or result.stdout or "gitnexus analyze failed")[:1000]
            logger.warning("GitNexus analyze failed for %s: %s", repo_name, detail.get("error"))
        else:
            logger.info("GitNexus analyze ready for %s in %sms", repo_name, elapsed_ms)

        return IndexStatus(
            index_name=repo_name,
            kind=IndexKind.GITNEXUS,
            ready=ready and result.ok,
            last_full_sync_at=utc_now() if result.ok else None,
            detail=detail,
        )

    def get_status(self, repo_name: str, local_path: Path | str | None = None) -> IndexStatus:
        path = Path(local_path) if local_path else None
        if path is None:
            return IndexStatus(
                index_name=repo_name,
                kind=IndexKind.GITNEXUS,
                ready=False,
                detail={"error": "local_path required for gitnexus status"},
            )
        graph_dir = path / ".gitnexus"
        if not graph_dir.exists():
            return IndexStatus(
                index_name=repo_name,
                kind=IndexKind.GITNEXUS,
                ready=False,
                detail={"graph_dir": str(graph_dir), "graph_dir_exists": False},
            )
        status = self.cli.status(cwd=path, repo=repo_name)
        return IndexStatus(
            index_name=repo_name,
            kind=IndexKind.GITNEXUS,
            ready=status.ok or graph_dir.exists(),
            detail={
                "graph_dir": str(graph_dir),
                "graph_dir_exists": True,
                "cli": status.as_dict(),
            },
        )
