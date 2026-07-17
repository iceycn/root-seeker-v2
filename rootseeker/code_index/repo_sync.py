from __future__ import annotations

import logging
import os
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

from rootseeker.code_index.chunker import chunk_code_files
from rootseeker.code_index.file_scanner import scan_code_files
from rootseeker.code_index.git_auth import (
    GitCredentials,
    assert_git_url_allowed_for_provider,
    build_authenticated_git_url,
    mask_git_url,
    sanitize_git_error_message,
)
from rootseeker.code_index.gitnexus_cli import GitNexusCliConfig
from rootseeker.code_index.gitnexus_indexer import GitNexusIndexer
from rootseeker.code_index.qdrant_indexer import QdrantIndexer
from rootseeker.code_index.zoekt_indexer import ZoektIndexer
from rootseeker.contracts.common import utc_now
from rootseeker.contracts.indexing import IndexKind, IndexStatus
from rootseeker.contracts.repository import RepositoryRef, RepoSyncState
from rootseeker.infra_core.http_client import resolve_http_proxy

__all__ = ["RepoSyncService", "RepoSyncResult"]

logger = logging.getLogger(__name__)


def _git_subprocess_env() -> dict[str, str]:
    env = os.environ.copy()
    proxy = resolve_http_proxy()
    if proxy:
        env["HTTP_PROXY"] = proxy
        env["HTTPS_PROXY"] = proxy
        env["http_proxy"] = proxy
        env["https_proxy"] = proxy
    return env


def _run_git(
    args: list[str], *, cwd: str | None = None, check: bool = False
) -> subprocess.CompletedProcess[str]:
    """Run a git command with UTF-8 decoding (Windows GBK-safe)."""
    return subprocess.run(
        args,
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=check,
        env=_git_subprocess_env(),
    )


def _get_default_base_path() -> Path:
    """从环境变量获取默认基础路径"""
    base_path = os.getenv("ROOTSEEKER_REPO_BASE_PATH", "repos")
    return Path(base_path)


def detect_remote_default_branch(url: str) -> str | None:
    """通过 git ls-remote 解析远端默认分支。"""
    result = _run_git(["git", "ls-remote", "--symref", url, "HEAD"], check=False)
    if result.returncode != 0:
        return None
    for line in result.stdout.splitlines():
        if line.startswith("ref: refs/heads/"):
            return line.split("refs/heads/", 1)[1].split("\t", 1)[0].strip() or None
    return None


def _is_missing_remote_branch_error(stderr: str) -> bool:
    lowered = stderr.lower()
    if "remote branch" in lowered and "not found" in lowered:
        return True
    if "couldn't find remote ref" in lowered:
        return True
    if "not found in upstream origin" in lowered:
        return True
    return False


def _is_container_style_repo_path(value: str) -> bool:
    """Detect Docker-style ``/data/repos/...`` paths (incl. Windows ``\\data\\repos``)."""
    norm = (value or "").replace("\\", "/").lower()
    while "//" in norm:
        norm = norm.replace("//", "/")
    # Strip Windows drive prefix: e:/data/repos/foo -> /data/repos/foo
    if len(norm) >= 3 and norm[1] == ":" and norm[2] == "/":
        norm = norm[2:]
    return norm == "/data/repos" or norm.startswith("/data/repos/")


class RepoSyncResult:
    """同步结果"""

    def __init__(
        self,
        repo: RepositoryRef,
        success: bool,
        message: str = "",
        zoekt_status: IndexStatus | None = None,
        qdrant_status: IndexStatus | None = None,
        gitnexus_status: IndexStatus | None = None,
    ) -> None:
        self.repo = repo
        self.success = success
        self.message = message
        self.zoekt_status = zoekt_status
        self.qdrant_status = qdrant_status
        self.gitnexus_status = gitnexus_status


class RepoSyncService:
    """仓库同步服务 - 支持 Git clone/pull 和代码索引"""

    def __init__(
        self,
        base_path: Path | str | None = None,
        zoekt_endpoint: str | None = None,
        qdrant_endpoint: str | None = None,
        qdrant_collection_name: str | None = None,
        qdrant_api_key: str | None = None,
        zoekt_timeout_seconds: float | None = None,
        qdrant_timeout_seconds: float | None = None,
        enable_zoekt: bool | None = None,
        enable_qdrant: bool | None = None,
        enable_gitnexus: bool | None = None,
        gitnexus_config: GitNexusCliConfig | None = None,
        credential_resolver: Callable[[RepositoryRef], GitCredentials | None] | None = None,
    ) -> None:
        """
        初始化仓库同步服务

        Args:
            base_path: 仓库克隆的基础路径（默认从环境变量读取）
            zoekt_endpoint: Zoekt 服务端点（未传则用 ZOEKT_ENDPOINT / ROOTSEEKER_ZOEKT_*，对齐 root_seek）
            qdrant_endpoint: Qdrant 服务端点（未传则用 QDRANT_* / ROOTSEEKER_QDRANT_*）
            qdrant_collection_name: 向量集合名（默认与 root_seek `qdrant.collection` 一致 code_chunks）
            qdrant_api_key: Qdrant API Key（云实例需要；对应 root_seek `qdrant.api_key`）
            zoekt_timeout_seconds / qdrant_timeout_seconds: 请求超时秒数
            enable_zoekt: 是否启用 Zoekt 索引（默认从环境变量读取）
            enable_qdrant: 是否启用 Qdrant 索引（默认从环境变量读取）
            enable_gitnexus: 是否启用 GitNexus 知识图谱索引
        """
        self._repos: dict[str, RepositoryRef] = {}
        self.base_path = Path(base_path) if base_path is not None else _get_default_base_path()
        self.base_path.mkdir(parents=True, exist_ok=True)

        self.enable_zoekt = (
            enable_zoekt
            if enable_zoekt is not None
            else os.getenv("ROOTSEEKER_REPO_ENABLE_ZOEKT", "true").lower() == "true"
        )
        self.enable_qdrant = (
            enable_qdrant
            if enable_qdrant is not None
            else os.getenv("ROOTSEEKER_REPO_ENABLE_QDRANT", "true").lower() == "true"
        )
        self.enable_gitnexus = (
            enable_gitnexus
            if enable_gitnexus is not None
            else os.getenv("ROOTSEEKER_REPO_ENABLE_GITNEXUS", "true").lower() == "true"
        )

        self.zoekt_indexer = (
            ZoektIndexer(endpoint=zoekt_endpoint, timeout_seconds=zoekt_timeout_seconds)
            if self.enable_zoekt
            else None
        )
        self.qdrant_indexer = (
            QdrantIndexer(
                endpoint=qdrant_endpoint,
                collection_name=qdrant_collection_name,
                timeout_seconds=qdrant_timeout_seconds,
                api_key=qdrant_api_key,
            )
            if self.enable_qdrant
            else None
        )
        gitnexus_cfg = gitnexus_config or GitNexusCliConfig.from_env()
        if enable_gitnexus is not None:
            gitnexus_cfg.enabled = bool(enable_gitnexus)
        self.gitnexus_indexer = (
            GitNexusIndexer(config=gitnexus_cfg) if self.enable_gitnexus else None
        )
        self.credential_resolver = credential_resolver

    def register(self, repo: RepositoryRef) -> None:
        """注册仓库"""
        repo.local_path = str(self._resolve_local_path(repo))
        self._repos[repo.name] = repo
        logger.info(f"Registered repository: {repo.name}")

    def _resolve_local_path(self, repo: RepositoryRef) -> Path:
        """Resolve on-disk clone path for the current host.

        Admin configs often store Docker paths like ``/data/repos/<name>``. On Windows
        hybrid hosts those become ``E:\\data\\repos\\...``. Prefer ``base_path / name``
        whenever that directory exists (including via junction to legacy clones).

        Return an absolute path that does **not** follow junctions/symlinks, so Zoekt /
        GitNexus path maps keyed on the project ``repos`` directory still match.
        """
        preferred = (self.base_path / repo.name).absolute()
        configured = (repo.local_path or "").strip()
        if preferred.exists():
            return preferred
        if configured:
            configured_path = Path(configured)
            configured_abs = configured_path.absolute()
            try:
                if configured_path.exists() and preferred.resolve() == configured_path.resolve():
                    return preferred
            except OSError:
                pass
            if self._is_usable_git_repo(configured_path):
                # Prefer the project base path form when it is the same checkout.
                try:
                    if preferred.exists() or preferred.parent.exists():
                        if configured_path.resolve() == preferred.resolve():
                            return preferred
                except OSError:
                    pass
                return configured_abs
            # Keep broken checkouts so sync can force-reclone in place.
            if configured_path.exists() and (configured_path / ".git").exists():
                try:
                    if configured_path.resolve() == preferred.resolve():
                        return preferred
                except OSError:
                    pass
                return configured_abs
            if _is_container_style_repo_path(configured):
                return preferred
            return configured_abs if configured_path.is_absolute() else preferred
        return preferred

    def _remove_checkout(self, path: Path) -> None:
        """Remove a local checkout, clearing Windows read-only bits when needed."""
        if not path.exists():
            return

        def _onexc(func: Any, p: str, exc: BaseException) -> None:  # noqa: ANN401
            try:
                Path(p).chmod(0o700)
            except OSError:
                pass
            try:
                func(p)
            except OSError as retry_exc:
                raise retry_exc from exc

        shutil.rmtree(path, onexc=_onexc)

    def _is_usable_git_repo(self, path: Path) -> bool:
        """True when path is a git work tree with a resolvable HEAD commit."""
        if not path.exists() or not (path / ".git").exists():
            return False
        result = _run_git(["git", "rev-parse", "HEAD"], cwd=str(path), check=False)
        return result.returncode == 0 and bool((result.stdout or "").strip())

    def unregister(self, repo_name: str) -> bool:
        """注销仓库"""
        if repo_name in self._repos:
            del self._repos[repo_name]
            logger.info(f"Unregistered repository: {repo_name}")
            return True
        return False

    def get_repo(self, repo_name: str) -> RepositoryRef | None:
        """获取仓库信息"""
        return self._repos.get(repo_name)

    def list_repos(self) -> list[RepositoryRef]:
        """列出所有仓库"""
        return list(self._repos.values())

    def sync(
        self,
        repo_name: str,
        trigger_index: bool = True,
        force_reclone: bool = False,
        *,
        force_gitnexus: bool = False,
    ) -> RepoSyncResult:
        """
        同步仓库（Git clone 或 pull）

        Args:
            repo_name: 仓库名称
            trigger_index: 是否触发索引
            force_reclone: 是否删除本地目录后重新 clone
            force_gitnexus: 是否对 GitNexus 使用 analyze --force 强制重建知识图谱

        Returns:
            RepoSyncResult: 同步结果
        """
        repo = self._repos.get(repo_name)
        if not repo:
            return RepoSyncResult(
                repo=RepositoryRef(name=repo_name),
                success=False,
                message=f"Repository not found: {repo_name}",
            )

        local_path = self._resolve_local_path(repo)
        if force_reclone and local_path.exists():
            self._remove_checkout(local_path)
            repo.sync_status.error_message = None
        # Corrupt/empty clones (`.git` present but no HEAD) must be re-cloned.
        if (
            not force_reclone
            and local_path.exists()
            and (local_path / ".git").exists()
            and not self._is_usable_git_repo(local_path)
        ):
            logger.warning("Removing unusable git checkout before reclone: %s", local_path)
            self._remove_checkout(local_path)
        is_local_repo = self._is_usable_git_repo(local_path)
        if not repo.url and not is_local_repo:
            return RepoSyncResult(
                repo=repo,
                success=False,
                message="Repository URL is required for sync unless local_path points to a git repository",
            )

        # 更新状态为同步中
        repo.sync_status.state = RepoSyncState.SYNCING
        repo.sync_status.error_message = None

        try:
            branch = repo.default_branch or "main"

            if is_local_repo and not repo.url:
                commit_hash = self._get_commit_hash(local_path)
            elif is_local_repo:
                clone_url = self._authenticated_git_url(repo) if repo.url else None
                local_branch = self._get_current_branch(local_path)
                if local_branch:
                    branch = local_branch
                commit_hash, branch = self._git_pull(local_path, branch, url=clone_url)
                repo.default_branch = branch
            else:
                # 执行 git clone
                clone_url = self._authenticated_git_url(repo)
                commit_hash, branch = self._git_clone(clone_url, local_path, branch)
                repo.default_branch = branch

            # 更新同步状态
            repo.sync_status.state = (
                RepoSyncState.INDEXING if trigger_index else RepoSyncState.COMPLETED
            )
            repo.sync_status.last_sync_at = utc_now()
            repo.sync_status.commit_hash = commit_hash
            repo.local_path = str(local_path)

            logger.info(f"Synced repository {repo_name} at commit {commit_hash}")

            # 触发索引：Zoekt（词法）+ Qdrant（语义）+ GitNexus（结构图）
            zoekt_status = None
            qdrant_status = None
            gitnexus_status = None

            if trigger_index:
                files = scan_code_files(local_path)
                chunks = chunk_code_files(repo_name, files)
                if self.zoekt_indexer:
                    zoekt_status = self.zoekt_indexer.index_repository(
                        repo_name=repo_name,
                        repo_url=repo.url,
                        branch=branch,
                        local_path=local_path,
                    )
                    logger.info(f"Zoekt index status for {repo_name}: {zoekt_status.ready}")

                if self.qdrant_indexer:
                    qdrant_status = self.qdrant_indexer.index_chunks(
                        repo_name=repo_name, chunks=chunks
                    )
                    logger.info(f"Qdrant index status for {repo_name}: {qdrant_status.ready}")

                if self.gitnexus_indexer:
                    gitnexus_status = self.gitnexus_indexer.index_repository(
                        repo_name=repo_name,
                        local_path=local_path,
                        force=True if force_gitnexus else None,
                    )
                    logger.info(f"GitNexus index status for {repo_name}: {gitnexus_status.ready}")

                repo.sync_status.files_indexed = len(files)
                # GitNexus 失败不阻断 Zoekt/Qdrant 成功路径；仅 zoekt/qdrant 计入硬失败。
                hard_statuses = [s for s in (zoekt_status, qdrant_status) if s is not None]
                soft_errors: list[str] = []
                if gitnexus_status is not None and not gitnexus_status.ready:
                    soft_errors.append(
                        str(gitnexus_status.detail.get("error", "gitnexus not ready"))
                    )
                if any(not status.ready for status in hard_statuses):
                    repo.sync_status.state = RepoSyncState.FAILED
                    repo.sync_status.error_message = "; ".join(
                        str(status.detail.get("error", f"{status.kind.value} not ready"))
                        for status in hard_statuses
                        if not status.ready
                    )
                else:
                    repo.sync_status.state = RepoSyncState.COMPLETED
                    repo.sync_status.error_message = "; ".join(soft_errors) if soft_errors else None
                repo.sync_status.last_index_at = utc_now()

            return RepoSyncResult(
                repo=repo,
                success=repo.sync_status.state == RepoSyncState.COMPLETED,
                message=repo.sync_status.error_message or f"Synced and indexed at {commit_hash}",
                zoekt_status=zoekt_status,
                qdrant_status=qdrant_status,
                gitnexus_status=gitnexus_status,
            )

        except ValueError as e:
            error_msg = sanitize_git_error_message(str(e))
            repo.sync_status.state = RepoSyncState.FAILED
            repo.sync_status.error_message = error_msg
            logger.error(f"Sync failed for {repo_name}: {error_msg}")
            return RepoSyncResult(repo=repo, success=False, message=error_msg)
        except subprocess.CalledProcessError as e:
            raw_error = e.stderr or e.stdout or "git command failed"
            error_msg = sanitize_git_error_message(f"Git operation failed: {raw_error}")
            repo.sync_status.state = RepoSyncState.FAILED
            repo.sync_status.error_message = error_msg
            logger.error(f"Sync failed for {repo_name}: {error_msg}")

            return RepoSyncResult(
                repo=repo,
                success=False,
                message=error_msg,
            )
        except Exception as e:
            error_msg = sanitize_git_error_message(f"Unexpected error: {e}")
            repo.sync_status.state = RepoSyncState.FAILED
            repo.sync_status.error_message = error_msg
            logger.error(f"Sync failed for {repo_name}: {error_msg}")

            return RepoSyncResult(
                repo=repo,
                success=False,
                message=error_msg,
            )

    def sync_all(
        self, trigger_index: bool = True, *, force_gitnexus: bool = False
    ) -> list[RepoSyncResult]:
        """同步所有仓库"""
        results = []
        for repo_name in list(self._repos.keys()):
            results.append(
                self.sync(repo_name, trigger_index=trigger_index, force_gitnexus=force_gitnexus)
            )
        return results

    def has_remote_updates(self, repo_name: str) -> bool:
        """Fetch remote and compare local HEAD with origin/<branch>."""
        repo = self._repos.get(repo_name)
        if not repo:
            raise KeyError(f"Repository not found: {repo_name}")
        local_path = self._resolve_local_path(repo)
        repo.local_path = str(local_path)
        if not self._is_usable_git_repo(local_path):
            # Missing or corrupt checkout — treat as needing sync/reclone.
            return bool(repo.url)
        if not repo.url:
            return False

        clone_url = self._authenticated_git_url(repo)
        self._set_origin_url(local_path, clone_url)
        branch = self._get_current_branch(local_path) or repo.default_branch or "main"
        fetch = _run_git(["git", "fetch", "origin", branch], cwd=str(local_path), check=False)
        if fetch.returncode != 0:
            # Missing remote branch: try default detection once.
            if _is_missing_remote_branch_error(fetch.stderr or fetch.stdout or ""):
                detected = detect_remote_default_branch(clone_url)
                if detected and detected != branch:
                    branch = detected
                    fetch = _run_git(
                        ["git", "fetch", "origin", branch], cwd=str(local_path), check=False
                    )
            if fetch.returncode != 0:
                detail = fetch.stderr or fetch.stdout or "git fetch failed"
                raise subprocess.CalledProcessError(
                    returncode=fetch.returncode,
                    cmd=["git", "fetch", "origin", branch],
                    stderr=detail,
                )

        local_hash = self._get_commit_hash(local_path)
        remote_hash = self._remote_commit_hash(local_path, branch)
        return bool(remote_hash) and remote_hash != local_hash

    def sync_changed(self, trigger_index: bool = True) -> dict[str, Any]:
        """Sync only repositories whose remote commit differs from local HEAD.

        Changed repos are pulled and re-indexed with GitNexus ``analyze --force``.
        """
        checked: list[str] = []
        changed: list[str] = []
        skipped: list[str] = []
        failed_checks: list[dict[str, str]] = []
        results: list[RepoSyncResult] = []

        for repo_name in list(self._repos.keys()):
            checked.append(repo_name)
            try:
                needs_sync = self.has_remote_updates(repo_name)
            except Exception as exc:  # noqa: BLE001
                failed_checks.append(
                    {"repo_name": repo_name, "error": sanitize_git_error_message(str(exc))}
                )
                logger.warning("has_remote_updates failed for %s: %s", repo_name, exc)
                continue
            if not needs_sync:
                skipped.append(repo_name)
                continue
            changed.append(repo_name)
            result = self.sync(repo_name, trigger_index=trigger_index, force_gitnexus=True)
            # Empty / branchless remotes are configuration problems, not transient sync
            # failures — surface them as check warnings so the cron job can still succeed.
            if (not result.success) and _is_missing_remote_branch_error(result.message or ""):
                failed_checks.append(
                    {
                        "repo_name": repo_name,
                        "error": sanitize_git_error_message(
                            result.message or "remote branch missing"
                        ),
                    }
                )
                logger.warning(
                    "sync skipped for branchless remote %s: %s",
                    repo_name,
                    result.message,
                )
                continue
            results.append(result)

        synced = [r.repo.name for r in results if r.success]
        sync_failed = [r.repo.name for r in results if not r.success]
        # Check failures are warnings; job hard-fails only when an attempted sync fails.
        ok = not sync_failed
        return {
            "checked": checked,
            "changed": changed,
            "synced": synced,
            "skipped": skipped,
            "failed_checks": failed_checks,
            "results": results,
            "ok": ok,
            "total_changed": len(changed),
        }

    def _remote_commit_hash(self, path: Path, branch: str) -> str | None:
        result = _run_git(["git", "rev-parse", f"origin/{branch}"], cwd=str(path), check=False)
        if result.returncode != 0:
            return None
        return (result.stdout or "").strip() or None

    def _resolve_git_credentials(self, repo: RepositoryRef) -> GitCredentials | None:
        metadata = dict(repo.metadata or {})
        token = str(metadata.get("git_token") or "").strip()
        username = str(metadata.get("git_username") or "").strip()
        provider = str(metadata.get("provider") or "custom")
        if token:
            return GitCredentials(username=username, token=token, provider=provider)
        if self.credential_resolver is not None:
            return self.credential_resolver(repo)
        return None

    def _authenticated_git_url(self, repo: RepositoryRef) -> str:
        url = str(repo.url or "")
        if not url or url.startswith("git@"):
            return url
        if not url.startswith("http://") and not url.startswith("https://"):
            return url
        credentials = self._resolve_git_credentials(repo)
        if credentials is None:
            return url
        assert_git_url_allowed_for_provider(url, credentials.provider)
        return build_authenticated_git_url(
            url,
            provider=credentials.provider,
            username=credentials.username,
            token=credentials.token,
        )

    def _get_current_branch(self, path: Path) -> str | None:
        result = _run_git(["git", "branch", "--show-current"], cwd=str(path), check=False)
        if result.returncode != 0:
            return None
        branch = (result.stdout or "").strip()
        return branch or None

    def _git_pull(self, path: Path, branch: str, *, url: str | None = None) -> tuple[str, str]:
        """执行 git pull，若指定分支不存在则自动探测并重试。"""
        logger.info(f"Pulling updates in {path} (branch={branch})")
        if url:
            self._set_origin_url(path, url)

        error = self._run_git_fetch_reset(path, branch)
        if error is None:
            return self._get_commit_hash(path), branch

        if _is_missing_remote_branch_error(error):
            detected = self._get_current_branch(path)
            if not detected and url:
                detected = detect_remote_default_branch(url)
            if detected and detected != branch:
                logger.info(f"Remote branch {branch} missing, retrying pull with {detected}")
                retry_error = self._run_git_fetch_reset(path, detected)
                if retry_error is None:
                    return self._get_commit_hash(path), detected

        raise subprocess.CalledProcessError(
            returncode=1,
            cmd=["git", "fetch", "origin", branch],
            stderr=error,
        )

    def _set_origin_url(self, path: Path, url: str) -> None:
        """Refresh origin so incremental sync uses the latest HTTPS credentials."""
        result = _run_git(["git", "remote", "set-url", "origin", url], cwd=str(path), check=False)
        if result.returncode == 0:
            return
        # Fresh clones should already have origin; add it when missing.
        add = _run_git(["git", "remote", "add", "origin", url], cwd=str(path), check=False)
        if add.returncode != 0:
            detail = add.stderr or result.stderr or "failed to set origin url"
            raise subprocess.CalledProcessError(
                returncode=add.returncode or result.returncode or 1,
                cmd=["git", "remote", "set-url", "origin", url],
                stderr=detail,
            )

    def _run_git_fetch_reset(self, path: Path, branch: str) -> str | None:
        fetch = _run_git(["git", "fetch", "origin", branch], cwd=str(path), check=False)
        if fetch.returncode != 0:
            return (
                fetch.stderr
                or fetch.stdout
                or f"git fetch failed with exit code {fetch.returncode}"
            )

        reset = _run_git(["git", "reset", "--hard", f"origin/{branch}"], cwd=str(path), check=False)
        if reset.returncode != 0:
            return (
                reset.stderr
                or reset.stdout
                or f"git reset failed with exit code {reset.returncode}"
            )
        return None

    def _git_clone(self, url: str, path: Path, branch: str) -> tuple[str, str]:
        """执行 git clone，若指定分支不存在则自动探测远端默认分支并重试。"""
        logger.info(f"Cloning {mask_git_url(url)} to {path} (branch={branch})")

        error = self._run_git_clone(url, path, branch)
        if error is None:
            return self._get_commit_hash(path), branch

        if _is_missing_remote_branch_error(error):
            candidates: list[str] = []
            detected = detect_remote_default_branch(url)
            for candidate in (detected, "master", "develop", "release"):
                if candidate and candidate != branch and candidate not in candidates:
                    candidates.append(candidate)
            for candidate in candidates:
                logger.info(f"Remote branch {branch} missing, retrying clone with {candidate}")
                if path.exists():
                    self._remove_checkout(path)
                retry_error = self._run_git_clone(url, path, candidate)
                if retry_error is None:
                    return self._get_commit_hash(path), candidate
                if not _is_missing_remote_branch_error(retry_error):
                    error = retry_error
                    break
                error = retry_error

        raise subprocess.CalledProcessError(
            returncode=1,
            cmd=["git", "clone", "--branch", branch, url, str(path)],
            stderr=error,
        )

    def _run_git_clone(self, url: str, path: Path, branch: str) -> str | None:
        result = _run_git(
            ["git", "clone", "--branch", branch, "--single-branch", url, str(path)], check=False
        )
        if result.returncode == 0:
            return None
        return (
            result.stderr or result.stdout or f"git clone failed with exit code {result.returncode}"
        )

    def _get_commit_hash(self, path: Path) -> str:
        """获取当前 commit hash"""
        result = _run_git(["git", "rev-parse", "HEAD"], cwd=str(path), check=True)
        return result.stdout.strip()

    def get_index_status(self, repo_name: str) -> dict[str, IndexStatus]:
        """获取仓库索引状态"""
        result = {}

        if self.zoekt_indexer:
            result["zoekt"] = self.zoekt_indexer.get_status(repo_name)

        if self.qdrant_indexer:
            result["qdrant"] = self.qdrant_indexer.get_status(repo_name)
        elif repo_name:
            result["qdrant"] = IndexStatus(
                index_name=repo_name,
                kind=IndexKind.QDRANT,
                ready=False,
                detail={"error": "qdrant indexer disabled"},
            )

        if self.gitnexus_indexer:
            repo = self._repos.get(repo_name)
            local_path = None
            if repo:
                local_path = str(self._resolve_local_path(repo))
            elif repo_name:
                local_path = str(self.base_path / repo_name)
            result["gitnexus"] = self.gitnexus_indexer.get_status(repo_name, local_path=local_path)
        elif repo_name:
            result["gitnexus"] = IndexStatus(
                index_name=repo_name,
                kind=IndexKind.GITNEXUS,
                ready=False,
                detail={"error": "gitnexus indexer disabled"},
            )

        return result

    def semantic_search(
        self,
        query: str,
        repo_name: str | None = None,
        limit: int = 10,
    ) -> dict:
        if not self.qdrant_indexer:
            return {"ok": False, "error": "qdrant indexer disabled", "result": []}
        result = self.qdrant_indexer.search_similar_text(query, repo_name=repo_name, limit=limit)
        return {
            "ok": "error" not in result,
            "query": query,
            "repo_name": repo_name,
            "limit": limit,
            **result,
        }
