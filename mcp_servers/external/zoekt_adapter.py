"""Zoekt Code Search adapter for production code index queries.

This adapter provides real HTTP integration with Zoekt code search backend.
Supports current sourcegraph/zoekt webserver RPC (POST /api/search, POST /api/list)
with fallback to legacy GET for older deployments.

Environment variables:
- ZOEKT_ENDPOINT: Zoekt HTTP API (same as root_seek `zoekt.api_base_url`, e.g. http://127.0.0.1:6070)
- ROOTSEEKER_ZOEKT_ENDPOINT: fallback if ZOEKT_ENDPOINT unset
- ZOEKT_TIMEOUT_SECONDS / ROOTSEEKER_ZOEKT_TIMEOUT_SECONDS: Request timeout (default: 10.0)
"""

from __future__ import annotations

import base64
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

from rootseeker.code_index.search_query import ZOEKT_NOISE_FILTERS

__all__ = ["ZoektCodeAdapter", "ZoektConfig"]


@dataclass
class ZoektConfig:
    """Configuration for Zoekt adapter."""

    endpoint: str = ""
    timeout_seconds: float = 10.0

    @classmethod
    def from_env(cls) -> ZoektConfig:
        """Load configuration from environment variables."""
        endpoint = (os.getenv("ZOEKT_ENDPOINT") or "").strip() or (
            os.getenv("ROOTSEEKER_ZOEKT_ENDPOINT") or ""
        ).strip()
        timeout_raw = os.getenv("ZOEKT_TIMEOUT_SECONDS") or os.getenv(
            "ROOTSEEKER_ZOEKT_TIMEOUT_SECONDS"
        )
        timeout_seconds = float(timeout_raw) if timeout_raw else 10.0
        return cls(
            endpoint=endpoint,
            timeout_seconds=timeout_seconds,
        )

    def is_configured(self) -> bool:
        """Check if endpoint is explicitly configured."""
        return bool(self.endpoint)


def _snippet_from_zoekt_line(cell: Any) -> str:
    """Decode Zoekt RPC line fragments (often base64) to UTF-8 text."""
    if not isinstance(cell, str):
        return str(cell or "")
    raw = cell.strip()
    if not raw:
        return ""
    pad = "=" * ((-len(raw)) % 4)
    try:
        return base64.b64decode(raw + pad).decode("utf-8", errors="replace")
    except Exception:
        return cell


def _prepare_zoekt_query(query: str) -> str:
    cleaned = " ".join((query or "").split())
    if not cleaned:
        return cleaned
    missing = [item for item in ZOEKT_NOISE_FILTERS if item not in cleaned]
    if not missing:
        return cleaned
    return f"{cleaned} {' '.join(missing)}"


def _safe_read_repo_file(repo_root: Path, rel_path: str) -> str | None:
    try:
        root = repo_root.resolve()
        target = (root / rel_path.lstrip("/")).resolve()
        target.relative_to(root)
        return target.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return None


def _container_source_candidates(source: str) -> list[str]:
    raw = (source or "").strip().replace("\\", "/")
    if not raw:
        return []
    candidates = [raw]
    if raw.startswith("/data/repos"):
        candidates.append("/repos" + raw[len("/data/repos") :])
    elif raw.startswith("/repos/"):
        candidates.append("/data/repos" + raw[len("/repos") :])
    # Deduplicate while preserving order.
    seen: set[str] = set()
    ordered: list[str] = []
    for item in candidates:
        if item not in seen:
            seen.add(item)
            ordered.append(item)
    return ordered


def _local_source_candidates(source: str) -> list[Path]:
    paths: list[Path] = []
    for candidate in _container_source_candidates(source):
        paths.append(Path(candidate))
        for prefix in ("/data/repos", "/repos"):
            if candidate.startswith(prefix + "/") or candidate == prefix:
                rel = candidate[len(prefix) :].lstrip("/")
                base = Path(os.getenv("ROOTSEEKER_REPO_BASE_PATH") or "repos")
                paths.append(base / rel if rel else base)
    seen: set[str] = set()
    ordered: list[Path] = []
    for path in paths:
        key = str(path)
        if key not in seen:
            seen.add(key)
            ordered.append(path)
    return ordered


def _docker_read_repo_file(source: str, rel_path: str) -> str | None:
    """Read a file from the Zoekt/repo Docker volume when host paths are unavailable."""
    import shutil
    import subprocess

    if not shutil.which("docker"):
        return None
    container = (os.getenv("ROOTSEEKER_ZOEKT_CONTAINER") or "rootseeker-zoekt").strip()
    safe_rel = rel_path.lstrip("/").replace("\\", "/")
    if not safe_rel or ".." in Path(safe_rel).parts:
        return None
    for root in _container_source_candidates(source):
        if not (root.startswith("/repos") or root.startswith("/data/repos")):
            continue
        target = f"{root.rstrip('/')}/{safe_rel}"
        try:
            completed = subprocess.run(
                ["docker", "exec", container, "cat", target],
                capture_output=True,
                text=True,
                timeout=20,
                check=False,
            )
        except Exception:
            continue
        if completed.returncode == 0:
            return completed.stdout
    return None


def _read_from_source(source: str, rel_path: str) -> str | None:
    for root in _local_source_candidates(source):
        text = _safe_read_repo_file(root, rel_path)
        if text is not None:
            return text
    return _docker_read_repo_file(source, rel_path)


def _normalize_rel_path(rel_path: str) -> str:
    return str(rel_path or "").replace("\\", "/").lstrip("/")


def _path_is_suffix(full: str, needle: str) -> bool:
    full_n = _normalize_rel_path(full)
    needle_n = _normalize_rel_path(needle)
    if not needle_n:
        return False
    return full_n == needle_n or full_n.endswith("/" + needle_n)


def _java_type_path(path: str) -> str:
    normalized = _normalize_rel_path(path)
    marker = "src/main/java/"
    index = normalized.find(marker)
    if index >= 0:
        return normalized[index + len(marker) :]
    return normalized


def _package_overlap_len(full: str, needle: str) -> int:
    full_parts = [part for part in _java_type_path(full).split("/") if part]
    needle_parts = [part for part in _java_type_path(needle).split("/") if part]
    overlap = 0
    for left, right in zip(reversed(full_parts), reversed(needle_parts)):
        if left != right:
            break
        overlap += 1
    return overlap


def _path_matches_request(full: str, needle: str) -> bool:
    if _path_is_suffix(full, needle):
        return True
    if not _java_type_path(full).endswith(".java") or not _java_type_path(needle).endswith(".java"):
        return False
    return _package_overlap_len(full, needle) >= 3


def _repo_names_match(hit_repo: str | None, requested: str | None) -> bool:
    left = str(hit_repo or "").strip().lower()
    right = str(requested or "").strip().lower()
    if not left or not right:
        return False
    return left == right or left.endswith("__" + right) or right.endswith("__" + left) or right in left


def _repo_base_path() -> Path:
    return Path(os.getenv("ROOTSEEKER_REPO_BASE_PATH") or "repos")


def _local_roots_for_repo(repo_name: str | None, source: str) -> list[Path]:
    roots = list(_local_source_candidates(source))
    base = _repo_base_path()
    name = str(repo_name or "").strip()
    if name:
        roots.append(base / name)
        if "__" in name:
            roots.append(base / name.rsplit("__", 1)[-1])
    seen: set[str] = set()
    ordered: list[Path] = []
    for root in roots:
        key = str(root)
        if key not in seen:
            seen.add(key)
            ordered.append(root)
    return ordered


def _prefer_suffix_match(matches: list[Path], needle: str) -> Path | None:
    if not matches:
        return None
    if len(matches) == 1:
        return matches[0]
    needle_n = _normalize_rel_path(needle)
    java_src = [path for path in matches if "/src/main/java/" in path.as_posix()]
    pool = java_src or matches
    exact_suffix = [path for path in pool if _path_matches_request(path.as_posix(), needle_n)]
    pool = exact_suffix or pool
    return sorted(
        pool,
        key=lambda path: (-_package_overlap_len(path.as_posix(), needle_n), len(path.as_posix())),
    )[0]


def _read_text_from_root(root: Path, rel_path: str) -> tuple[str, str] | None:
    needle = _normalize_rel_path(rel_path)
    if not needle:
        return None
    text = _safe_read_repo_file(root, needle)
    if text is not None:
        return text, needle
    name = needle.rsplit("/", 1)[-1]
    if not name or not root.exists() or not root.is_dir():
        return None
    matches: list[Path] = []
    try:
        for candidate in root.rglob(name):
            if not candidate.is_file():
                continue
            rel = candidate.relative_to(root).as_posix()
            if _path_matches_request(rel, needle):
                matches.append(candidate)
    except (OSError, ValueError):
        return None
    chosen = _prefer_suffix_match(matches, needle)
    if chosen is None:
        return None
    try:
        return chosen.read_text(encoding="utf-8", errors="replace"), chosen.relative_to(root).as_posix()
    except OSError:
        return None


def _read_indexed_file(
    *,
    repo_name: str | None,
    source: str,
    rel_path: str,
) -> tuple[str, str] | None:
    for root in _local_roots_for_repo(repo_name, source):
        found = _read_text_from_root(root, rel_path)
        if found is not None:
            return found
    text = _docker_read_repo_file(source, rel_path)
    if text is not None:
        return text, _normalize_rel_path(rel_path)
    return None


def _match_index_repos(requested: str | None, repos: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not requested:
        return list(repos)
    req = requested.strip().lower()
    if not req:
        return list(repos)
    exact = [item for item in repos if str(item.get("name") or "").lower() == req]
    if exact:
        return exact
    suffix: list[dict[str, Any]] = []
    contains: list[dict[str, Any]] = []
    for item in repos:
        name = str(item.get("name") or "").lower()
        if name.endswith("__" + req) or name.endswith("/" + req) or name.endswith("\\" + req):
            suffix.append(item)
        elif req in name:
            contains.append(item)
    if suffix:
        return suffix
    return sorted(contains, key=lambda item: len(str(item.get("name") or "")))


def _sliced_read_result(
    *,
    path: str,
    repo: str | None,
    text: str,
    start_line: int,
    end_line: int | None,
    focus_line: int | None,
    methods: list[Any] | None = None,
) -> dict[str, Any]:
    from rootseeker.analysis.code_slice import slice_source_window

    content, start, end = slice_source_window(
        text,
        start_line=start_line,
        end_line=end_line,
        focus_line=focus_line,
        methods=methods,
    )
    total = len(str(text).splitlines())
    returned = len(content.splitlines()) if content else 0
    return {
        "path": path,
        "repo": repo,
        "content": content,
        "total_lines": total,
        "returned_lines": returned,
        "start_line": start,
        "end_line": end,
    }


@dataclass
class ZoektCodeAdapter:
    """Production adapter for Zoekt code search.

    Implements code search and file reading from Zoekt backend.
    """

    config: ZoektConfig = field(default_factory=ZoektConfig.from_env)
    _client: httpx.Client | None = field(default=None, repr=False)
    _index_list_cache: dict[str, Any] | None = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        if self.config.is_configured():
            self._client = httpx.Client(timeout=self.config.timeout_seconds, trust_env=False)

    def close(self) -> None:
        """Close HTTP client."""
        self._index_list_cache = None
        if self._client:
            self._client.close()
            self._client = None

    def _fetch_index_list_payload(self, *, reuse_cache: bool) -> dict[str, Any] | None:
        """GET/POST /api/list as supported by server version."""
        if not self._client:
            return None
        if reuse_cache and self._index_list_cache is not None:
            return self._index_list_cache
        url = f"{self.config.endpoint.rstrip('/')}/api/list"
        try:
            r = self._client.post(url, json={})
            if r.status_code == 405:
                r = self._client.get(url)
            r.raise_for_status()
            data = r.json()
            self._index_list_cache = data
            return data
        except Exception:
            return None

    def _normalized_repos_from_list(self, data: dict[str, Any]) -> list[dict[str, Any]]:
        repos: list[dict[str, Any]] = []

        lst = data.get("List") or {}
        for ent in lst.get("Repos") or []:
            rm = ent.get("Repository") or {}
            im = ent.get("IndexMetadata") or {}
            repos.append(
                {
                    "name": rm.get("Name", ""),
                    "url": rm.get("URL", ""),
                    "source": (rm.get("Source") or "").strip(),
                    "index_time": im.get("IndexTime", ""),
                    "branches": rm.get("Branches") or [],
                }
            )

        if not repos:
            for repo in data.get("RepoList") or []:
                repos.append(
                    {
                        "name": repo.get("Name", ""),
                        "url": repo.get("URL", ""),
                        "source": "",
                        "index_time": repo.get("IndexTime", ""),
                        "branches": repo.get("Branches") or [],
                    }
                )
        return repos

    def _local_repo_root(self, repo: str | None, path: str | None = None) -> Path | None:
        data = self._fetch_index_list_payload(reuse_cache=True)
        if not data:
            return None
        repos = self._normalized_repos_from_list(data)
        for item in self._iter_repo_candidates(repos, repo):
            src = str(item.get("source") or "")
            name = str(item.get("name") or "") or None
            if path and _read_indexed_file(repo_name=name, source=src, rel_path=path) is None:
                continue
            for root in _local_roots_for_repo(name, src):
                if root.exists():
                    return root
            if src:
                return Path(src)
        return None

    def _source_for_repo(self, repo: str | None, path: str | None = None) -> str | None:
        data = self._fetch_index_list_payload(reuse_cache=True)
        if not data:
            return None
        repos = self._normalized_repos_from_list(data)
        for item in self._iter_repo_candidates(repos, repo):
            src = str(item.get("source") or "")
            name = str(item.get("name") or "") or None
            if path and _read_indexed_file(repo_name=name, source=src, rel_path=path) is None:
                continue
            if src:
                return src
        return None

    def _iter_repo_candidates(
        self,
        repos: list[dict[str, Any]],
        repo: str | None,
    ) -> list[dict[str, Any]]:
        matched = _match_index_repos(repo, repos)
        seen: set[str] = set()
        ordered: list[dict[str, Any]] = []
        for item in [*matched, *repos]:
            key = str(item.get("name") or item.get("source") or id(item))
            if key in seen:
                continue
            seen.add(key)
            ordered.append(item)
        return ordered

    def _read_from_index_list(
        self,
        path: str,
        repo: str | None,
    ) -> tuple[str, str, str | None] | None:
        data = self._fetch_index_list_payload(reuse_cache=True)
        if not data:
            return None
        repos = self._normalized_repos_from_list(data)
        for item in self._iter_repo_candidates(repos, repo):
            src = str(item.get("source") or "")
            name = str(item.get("name") or "") or None
            found = _read_indexed_file(repo_name=name, source=src, rel_path=path)
            if found is None:
                continue
            content, resolved_path = found
            return content, resolved_path, name
        return None

    def _read_from_search_hit(
        self,
        path: str,
        repo: str | None,
    ) -> tuple[str, str, str | None] | None:
        basename = _normalize_rel_path(path).rsplit("/", 1)[-1]
        if not basename:
            return None
        search = self.search_code(f"file:{basename}", num_results=20)
        hits = search.get("hits") if isinstance(search, dict) else None
        if not isinstance(hits, list):
            return None
        ranked: list[dict[str, Any]] = []
        for hit in hits:
            if not isinstance(hit, dict):
                continue
            hit_path = str(hit.get("path") or "")
            if not hit_path:
                continue
            if (
                _path_matches_request(hit_path, path)
                or _path_is_suffix(hit_path, path)
                or hit_path.endswith("/" + basename)
                or hit_path == basename
            ):
                ranked.append(hit)
        if not ranked:
            ranked = [hit for hit in hits if isinstance(hit, dict)]
        ranked.sort(
            key=lambda hit: (
                _package_overlap_len(str(hit.get("path") or ""), path),
                1 if _repo_names_match(str(hit.get("repo") or ""), repo) else 0,
                1 if _path_is_suffix(str(hit.get("path") or ""), path) else 0,
                float(hit.get("score") or 0.0),
            ),
            reverse=True,
        )
        best_overlap = _package_overlap_len(str(ranked[0].get("path") or ""), path) if ranked else 0
        if best_overlap >= 3:
            ranked = [
                hit
                for hit in ranked
                if _package_overlap_len(str(hit.get("path") or ""), path) >= 3
            ]
        for hit in ranked:
            hit_path = str(hit.get("path") or path)
            hit_repo = str(hit.get("repo") or "") or repo
            found = self._read_from_index_list(hit_path, hit_repo)
            if found is not None:
                return found
        return None

    def search_code(
        self,
        query: str,
        num_results: int = 50,
        repo_filter: str | None = None,
    ) -> dict[str, Any]:
        """Search code using Zoekt."""
        if not self._client:
            return self._not_configured_search(query)

        query = _prepare_zoekt_query(query)
        url = f"{self.config.endpoint.rstrip('/')}/api/search"
        payload: dict[str, Any] = {"q": query, "Num": num_results}
        if repo_filter:
            payload["Repository"] = repo_filter

        try:
            response = self._client.post(url, json=payload)
            if response.status_code == 405:
                response = self._client.get(
                    url,
                    params={
                        "q": query,
                        "num": num_results,
                        **({"r": repo_filter} if repo_filter else {}),
                    },
                )
            response.raise_for_status()
            data = response.json()

            return self._transform_search_response(query, data, max_hits=num_results)
        except Exception as e:
            return {
                "query": query,
                "hits": [],
                "total": 0,
                "error": str(e),
            }

    def _transform_search_response(
        self,
        query: str,
        data: dict[str, Any],
        *,
        max_hits: int = 50,
    ) -> dict[str, Any]:
        hits: list[dict[str, Any]] = []
        result = data.get("Result")
        max_hits = max(1, int(max_hits))

        if isinstance(result, dict) and result.get("Files") is not None:
            for file_match in result.get("Files") or []:
                repo = file_match.get("Repository") or file_match.get("Repo") or ""
                file_name = file_match.get("FileName", "")
                for line_match in file_match.get("LineMatches") or []:
                    line_num = line_match.get("LineNumber", 0)
                    line_cell = line_match.get("Line", "")
                    snippet = _snippet_from_zoekt_line(line_cell)
                    hits.append(
                        {
                            "repo": repo,
                            "path": file_name,
                            "line_start": line_num,
                            "line_end": line_num,
                            "snippet": snippet.strip(),
                            "score": float(line_match.get("Score") or 0.0),
                        }
                    )
        elif isinstance(result, list):
            for res in result:
                repo_name = res.get("Repository", "")
                for file_match in res.get("FileMatches") or []:
                    file_name = file_match.get("FileName", "")
                    for line_match in file_match.get("LineMatches") or []:
                        line_num = line_match.get("LineNumber", 0)
                        snippet = line_match.get("Line", "")
                        if isinstance(snippet, str):
                            snippet_try = _snippet_from_zoekt_line(snippet)
                            snippet_use = snippet_try if snippet_try else snippet.strip()
                        else:
                            snippet_use = str(snippet or "")
                        hits.append(
                            {
                                "repo": repo_name,
                                "path": file_name,
                                "line_start": line_num,
                                "line_end": line_num,
                                "snippet": snippet_use,
                                "score": float(line_match.get("Score") or 0.0),
                            }
                        )

        hits.sort(key=lambda item: float(item.get("score") or 0.0), reverse=True)
        truncated = len(hits) > max_hits
        selected = hits[:max_hits]
        payload = {
            "query": query,
            "hits": selected,
            "total": len(hits),
        }
        if truncated:
            payload["truncated"] = True
        return payload

    def _not_configured_search(self, query: str) -> dict[str, Any]:
        return {
            "query": query,
            "hits": [],
            "total": 0,
            "configured": False,
            "error": "Zoekt is not configured: set ZOEKT_ENDPOINT",
        }

    def read_file(
        self,
        path: str,
        repo: str | None = None,
        start_line: int = 1,
        end_line: int | None = None,
        focus_line: int | None = None,
        methods: list[Any] | None = None,
    ) -> dict[str, Any]:
        """Read file: prefer Zoekt legacy HTTP GET /api/file; else local clone path from index list."""
        if not self._client:
            return self._not_configured_read_file(path)

        url = f"{self.config.endpoint.rstrip('/')}/api/file"
        params = {"path": path}
        if repo:
            params["repo"] = repo

        try:
            response = self._client.get(url, params=params)
            if response.status_code == 200:
                return _sliced_read_result(
                    path=path,
                    repo=repo,
                    text=response.text,
                    start_line=start_line,
                    end_line=end_line,
                    focus_line=focus_line,
                    methods=methods,
                )
        except Exception:
            pass

        found = self._read_from_index_list(path, repo) or self._read_from_search_hit(path, repo)
        if found is None:
            return {
                "path": path,
                "repo": repo,
                "content": "",
                "error": "file read via Zoekt /api/file unavailable and no local Source in index list",
            }
        text, resolved_path, resolved_repo = found
        return _sliced_read_result(
            path=resolved_path,
            repo=resolved_repo or repo,
            text=text,
            start_line=start_line,
            end_line=end_line,
            focus_line=focus_line,
            methods=methods,
        )

    def _not_configured_read_file(self, path: str) -> dict[str, Any]:
        return {
            "path": path,
            "repo": None,
            "content": "",
            "total_lines": 0,
            "returned_lines": 0,
            "configured": False,
            "error": "Zoekt is not configured: set ZOEKT_ENDPOINT",
        }

    def get_index_status(self) -> dict[str, Any]:
        """Get index status from Zoekt."""
        if not self._client:
            return self._not_configured_index_status()

        url = f"{self.config.endpoint.rstrip('/')}/api/list"

        try:
            response = self._client.post(url, json={})
            if response.status_code == 405:
                response = self._client.get(url)
            response.raise_for_status()
            data = response.json()
            self._index_list_cache = data

            repos = []
            for r in self._normalized_repos_from_list(data):
                repos.append(
                    {
                        "name": r["name"],
                        "url": r["url"],
                        "index_time": r["index_time"],
                        "branches": r["branches"],
                    }
                )

            return {
                "ready": True,
                "indexes": repos,
                "total": len(repos),
            }
        except Exception as e:
            return {
                "ready": False,
                "indexes": [],
                "total": 0,
                "error": str(e),
            }

    def _not_configured_index_status(self) -> dict[str, Any]:
        return {
            "ready": False,
            "indexes": [],
            "total": 0,
            "configured": False,
            "error": "Zoekt is not configured: set ZOEKT_ENDPOINT",
        }
