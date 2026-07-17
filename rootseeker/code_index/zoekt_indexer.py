from __future__ import annotations

import logging
import os
import subprocess
import time
from pathlib import Path
from shutil import which
from urllib.parse import urlparse, urlunparse

import httpx

from rootseeker.code_index.gitnexus_cli import _rewrite_path_for_sidecar
from rootseeker.contracts.common import utc_now
from rootseeker.contracts.indexing import IndexKind, IndexStatus

__all__ = ["ZoektIndexer", "get_zoekt_status"]

logger = logging.getLogger(__name__)


def _get_default_endpoint() -> str:
    """与 root_seek config.yaml `zoekt.api_base_url` 对齐；支持 ZOEKT_* 与 ROOTSEEKER_ZOEKT_*。"""
    return (
        (os.getenv("ZOEKT_ENDPOINT") or "").strip()
        or (os.getenv("ROOTSEEKER_ZOEKT_ENDPOINT") or "").strip()
        or "http://127.0.0.1:6070"
    )


def _get_default_timeout() -> float:
    raw = os.getenv("ZOEKT_TIMEOUT_SECONDS") or os.getenv("ROOTSEEKER_ZOEKT_TIMEOUT_SECONDS")
    return float(raw) if raw else 30.0


def _get_default_index_timeout() -> float:
    raw = os.getenv("ROOTSEEKER_ZOEKT_INDEX_TIMEOUT_SECONDS") or os.getenv(
        "ZOEKT_INDEX_TIMEOUT_SECONDS"
    )
    return float(raw) if raw else 600.0


def _get_default_index_dir() -> Path:
    return Path(os.getenv("ROOTSEEKER_ZOEKT_INDEX_DIR", "data/zoekt/index"))


def _get_default_index_endpoint() -> str | None:
    explicit = (os.getenv("ROOTSEEKER_ZOEKT_INDEX_ENDPOINT") or "").strip() or (
        os.getenv("ZOEKT_INDEX_ENDPOINT") or ""
    ).strip()
    if explicit:
        return explicit.rstrip("/")
    return None


def _derive_index_endpoint(search_endpoint: str) -> str:
    """Map search :6070 -> index HTTP :6071 on the same host."""
    parsed = urlparse(search_endpoint)
    host = parsed.hostname or "127.0.0.1"
    scheme = parsed.scheme or "http"
    netloc = f"{host}:6071"
    if parsed.username:
        auth = parsed.username
        if parsed.password:
            auth = f"{auth}:{parsed.password}"
        netloc = f"{auth}@{netloc}"
    return urlunparse((scheme, netloc, "", "", "", "")).rstrip("/")


class ZoektIndexer:
    """Zoekt 代码搜索引擎索引器（本机 CLI 或容器内远程 HTTP）。"""

    def __init__(
        self,
        endpoint: str | None = None,
        timeout_seconds: float | None = None,
        index_dir: Path | str | None = None,
        binary: str | None = None,
        index_endpoint: str | None = None,
        path_map: str | None = None,
        index_timeout_seconds: float | None = None,
    ) -> None:
        self.endpoint = (endpoint or _get_default_endpoint()).rstrip("/")
        self.timeout_seconds = (
            timeout_seconds if timeout_seconds is not None else _get_default_timeout()
        )
        self.index_timeout_seconds = (
            index_timeout_seconds
            if index_timeout_seconds is not None
            else _get_default_index_timeout()
        )
        self.index_dir = Path(index_dir) if index_dir is not None else _get_default_index_dir()
        env_binary = (os.getenv("ROOTSEEKER_ZOEKT_INDEX_BINARY") or "").strip() or None
        self.binary = binary if binary is not None else (env_binary or which("zoekt-index"))
        # None = resolve from env / auto-derive; "" = force local CLI mode.
        if index_endpoint is not None:
            self.index_endpoint = index_endpoint.rstrip("/") or None
        else:
            self.index_endpoint = _get_default_index_endpoint()
            if not self.index_endpoint and not self.binary and self.endpoint:
                self.index_endpoint = _derive_index_endpoint(self.endpoint)
        self.path_map = (
            path_map
            if path_map is not None
            else ((os.getenv("ROOTSEEKER_ZOEKT_PATH_MAP") or "").strip() or None)
        )

    def index_repository(
        self,
        repo_name: str,
        repo_url: str,
        branch: str = "main",
        local_path: Path | str | None = None,
    ) -> IndexStatus:
        """Index a checked-out repository via remote HTTP sidecar or local zoekt-index."""
        started = time.monotonic()
        path = Path(local_path) if local_path is not None else None
        if path is None:
            return IndexStatus(
                index_name=repo_name,
                kind=IndexKind.ZOEKT,
                ready=False,
                detail={
                    "error": "local_path is required for zoekt-index",
                    "repo_url": repo_url,
                    "branch": branch,
                },
            )
        if not path.exists():
            return IndexStatus(
                index_name=repo_name,
                kind=IndexKind.ZOEKT,
                ready=False,
                detail={"error": f"local_path does not exist: {path}"},
            )
        if self.index_endpoint:
            return self._index_remote(repo_name, path, started)
        if self.binary:
            return self._index_local(repo_name, path, started)
        return IndexStatus(
            index_name=repo_name,
            kind=IndexKind.ZOEKT,
            ready=False,
            detail={
                "error": "zoekt-index binary not found and no remote index endpoint",
                "hint": (
                    "set ROOTSEEKER_ZOEKT_INDEX_ENDPOINT (e.g. http://127.0.0.1:6071) "
                    "or install zoekt-index locally"
                ),
            },
        )

    def _index_remote(self, repo_name: str, path: Path, started: float) -> IndexStatus:
        assert self.index_endpoint is not None
        mapped = _rewrite_path_for_sidecar(str(path), self.path_map)
        remote_index_dir = (
            os.getenv("ROOTSEEKER_ZOEKT_REMOTE_INDEX_DIR") or ""
        ).strip() or "/data/index"
        try:
            with httpx.Client(timeout=self.index_timeout_seconds, trust_env=False) as client:
                response = client.post(
                    f"{self.index_endpoint}/v1/index",
                    json={
                        "path": mapped,
                        "index_dir": remote_index_dir,
                        "timeout_seconds": self.index_timeout_seconds,
                    },
                )
                try:
                    body = response.json()
                except Exception:
                    body = {"ok": False, "stderr": response.text[:4000]}
                if response.status_code >= 400 or not body.get("ok", False):
                    return IndexStatus(
                        index_name=repo_name,
                        kind=IndexKind.ZOEKT,
                        ready=False,
                        detail={
                            "mode": "remote",
                            "error": body.get("stderr")
                            or body.get("error")
                            or response.text[:4000],
                            "status_code": response.status_code,
                            "local_path": str(path),
                            "mapped_path": mapped,
                            "index_endpoint": self.index_endpoint,
                            "stdout": (body.get("stdout") or "")[-4000:],
                            "stderr": (body.get("stderr") or "")[-4000:],
                        },
                    )
                return IndexStatus(
                    index_name=repo_name,
                    kind=IndexKind.ZOEKT,
                    ready=True,
                    last_full_sync_at=utc_now(),
                    lag_seconds=int(time.monotonic() - started),
                    detail={
                        "mode": "remote",
                        "local_path": str(path),
                        "mapped_path": mapped,
                        "index_endpoint": self.index_endpoint,
                        "index_dir": remote_index_dir,
                        "command": body.get("command"),
                        "stdout": (body.get("stdout") or "")[-4000:],
                        "stderr": (body.get("stderr") or "")[-4000:],
                    },
                )
        except httpx.HTTPError as e:
            logger.error("Zoekt remote index failed for %s: %s", repo_name, e)
            return IndexStatus(
                index_name=repo_name,
                kind=IndexKind.ZOEKT,
                ready=False,
                detail={
                    "mode": "remote",
                    "error": str(e),
                    "local_path": str(path),
                    "mapped_path": mapped,
                    "index_endpoint": self.index_endpoint,
                },
            )

    def _index_local(self, repo_name: str, path: Path, started: float) -> IndexStatus:
        assert self.binary is not None
        try:
            self.index_dir.mkdir(parents=True, exist_ok=True)
            cmd = [self.binary, "-index", str(self.index_dir), str(path)]
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.index_timeout_seconds,
                check=True,
            )
            return IndexStatus(
                index_name=repo_name,
                kind=IndexKind.ZOEKT,
                ready=True,
                last_full_sync_at=utc_now(),
                lag_seconds=int(time.monotonic() - started),
                detail={
                    "mode": "local",
                    "command": cmd,
                    "local_path": str(path),
                    "index_dir": str(self.index_dir),
                    "stdout": result.stdout[-4000:],
                    "stderr": result.stderr[-4000:],
                },
            )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
            logger.error("Zoekt index failed for %s: %s", repo_name, e)
            return IndexStatus(
                index_name=repo_name,
                kind=IndexKind.ZOEKT,
                ready=False,
                detail={
                    "mode": "local",
                    "error": str(e),
                    "stdout": getattr(e, "stdout", "") or "",
                    "stderr": getattr(e, "stderr", "") or "",
                    "index_dir": str(self.index_dir),
                },
            )

    def search(
        self,
        query: str,
        repo_name: str | None = None,
        limit: int = 50,
    ) -> dict:
        """
        搜索代码

        Args:
            query: 搜索查询
            repo_name: 限定仓库名（可选）
            limit: 结果数量限制

        Returns:
            搜索结果字典
        """
        try:
            with httpx.Client(timeout=self.timeout_seconds, trust_env=False) as client:
                payload = {"q": query, "Num": limit}
                if repo_name:
                    payload["Repository"] = repo_name
                response = client.post(f"{self.endpoint}/api/search", json=payload)
                if response.status_code == 405:
                    params = {"q": query, "num": limit}
                    if repo_name:
                        params["r"] = repo_name
                    response = client.get(f"{self.endpoint}/api/search", params=params)
                response.raise_for_status()
                return response.json()
        except httpx.HTTPError as e:
            logger.error(f"Zoekt search failed: {e}")
            return {"error": str(e), "hits": []}

    def get_status(self, repo_name: str | None = None) -> IndexStatus:
        """获取索引状态"""
        try:
            with httpx.Client(timeout=self.timeout_seconds, trust_env=False) as client:
                response = client.post(f"{self.endpoint}/api/list", json={})
                if response.status_code == 405:
                    response = client.get(f"{self.endpoint}/api/list")
                response.raise_for_status()
                data = response.json()

            # 检查指定仓库是否在索引列表中
            if repo_name:
                found = repo_name in self._repo_names_from_list(data)
                return IndexStatus(
                    index_name=repo_name,
                    kind=IndexKind.ZOEKT,
                    ready=found,
                    detail=data,
                )

            return IndexStatus(
                index_name="zoekt-all",
                kind=IndexKind.ZOEKT,
                ready=True,
                detail=data,
            )
        except httpx.HTTPError as e:
            logger.error(f"Zoekt status check failed: {e}")
            return IndexStatus(
                index_name=repo_name or "zoekt-default",
                kind=IndexKind.ZOEKT,
                ready=False,
                detail={"error": str(e)},
            )

    def _repo_names_from_list(self, data: dict) -> set[str]:
        names: set[str] = set()
        lst = data.get("List") or {}
        for ent in lst.get("Repos") or []:
            repo = ent.get("Repository") or {}
            name = repo.get("Name")
            if name:
                names.add(str(name))
            source = repo.get("Source")
            if source:
                names.add(Path(str(source)).name)
        for repo in data.get("RepoList") or []:
            name = repo.get("Name")
            if name:
                names.add(str(name))
        return names


def get_zoekt_status(index_name: str = "zoekt-default") -> IndexStatus:
    """向后兼容的状态查询函数"""
    indexer = ZoektIndexer()
    return indexer.get_status(index_name)
