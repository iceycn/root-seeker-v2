"""High-level GitNexus query adapter for MCP / find_callers integration."""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

from rootseeker.code_index.gitnexus_cli import GitNexusCli, GitNexusCliConfig, GitNexusCommandResult

__all__ = ["GitNexusAdapter"]

logger = logging.getLogger(__name__)

_SYMBOL_SPLIT_RE = re.compile(r"[.#:/]")


class GitNexusAdapter:
    """Wrap GitNexus impact/context/query/cypher/list/trace for RootSeeker tools."""

    def __init__(
        self,
        cli: GitNexusCli | None = None,
        config: GitNexusCliConfig | None = None,
        *,
        repo_path_resolver: Any | None = None,
    ) -> None:
        self.config = config or GitNexusCliConfig.from_env()
        self.cli = cli or GitNexusCli(self.config)
        # Optional Callable[[str], Path | None] mapping repo name → local clone path.
        self.repo_path_resolver = repo_path_resolver

    @property
    def enabled(self) -> bool:
        return bool(self.config.enabled and self.cli.available)

    def _cwd_for_repo(self, repo: str | None) -> Path | None:
        if not repo or self.repo_path_resolver is None:
            return None
        try:
            path = self.repo_path_resolver(repo)
        except Exception:  # noqa: BLE001
            return None
        if path is None:
            return None
        resolved = Path(path)
        return resolved if resolved.exists() else None

    def _wrap(self, result: GitNexusCommandResult, **extra: Any) -> dict[str, Any]:
        payload = result.as_dict()
        payload.update(extra)
        if result.data is not None and "result" not in payload:
            payload["result"] = result.data
        return payload

    def list_repos(self, *, limit: int | None = None, offset: int | None = None) -> dict[str, Any]:
        if not self.enabled:
            return {"ok": False, "error": "gitnexus unavailable", "repos": []}
        return self._wrap(self.cli.list_repos(limit=limit, offset=offset))

    def query(self, search_query: str, *, repo: str | None = None) -> dict[str, Any]:
        if not self.enabled:
            return {"ok": False, "error": "gitnexus unavailable", "result": None}
        q = str(search_query or "").strip()
        if not q:
            return {"ok": False, "error": "search_query is required"}
        return self._wrap(
            self.cli.query(q, repo=repo, cwd=self._cwd_for_repo(repo)),
            search_query=q,
            repo=repo,
        )

    def context(
        self,
        symbol: str,
        *,
        repo: str | None = None,
        file: str | None = None,
        uid: str | None = None,
    ) -> dict[str, Any]:
        if not self.enabled:
            return {"ok": False, "error": "gitnexus unavailable", "result": None}
        sym = str(symbol or "").strip()
        if not sym:
            return {"ok": False, "error": "symbol is required"}
        resolved_repo = self._canonical_repo(repo)
        last: dict[str, Any] | None = None
        for candidate in _symbol_candidates(sym):
            result = self._wrap(
                self.cli.context(
                    candidate,
                    repo=resolved_repo,
                    file=file,
                    uid=uid,
                    cwd=self._cwd_for_repo(resolved_repo),
                ),
                symbol=candidate,
                repo=resolved_repo or repo,
            )
            if _repo_missing(result):
                alt = self._canonical_repo(repo, force_refresh=True)
                if alt and alt != resolved_repo:
                    resolved_repo = alt
                    result = self._wrap(
                        self.cli.context(
                            candidate,
                            repo=resolved_repo,
                            file=file,
                            uid=uid,
                            cwd=self._cwd_for_repo(resolved_repo),
                        ),
                        symbol=candidate,
                        repo=resolved_repo,
                    )
            result = self._resolve_ambiguous(
                result,
                symbol=candidate,
                repo=resolved_repo or repo,
                file=file,
                kind="context",
            )
            last = result
            if _graph_hit_usable(result.get("result")):
                return result
        return last or {"ok": False, "error": "symbol is required", "result": None}

    def impact(
        self,
        symbol: str,
        *,
        direction: str = "upstream",
        repo: str | None = None,
        file: str | None = None,
        uid: str | None = None,
        kind: str | None = None,
    ) -> dict[str, Any]:
        if not self.enabled:
            return {"ok": False, "error": "gitnexus unavailable", "result": None}
        sym = str(symbol or "").strip()
        if not sym:
            return {"ok": False, "error": "symbol is required"}
        direction_norm = str(direction or "upstream").strip().lower() or "upstream"
        resolved_repo = self._canonical_repo(repo)
        last: dict[str, Any] | None = None
        for candidate in _symbol_candidates(sym):
            result = self._wrap(
                self.cli.impact(
                    candidate,
                    direction=direction_norm,
                    repo=resolved_repo,
                    file=file,
                    uid=uid,
                    kind=kind,
                    cwd=self._cwd_for_repo(resolved_repo),
                ),
                symbol=candidate,
                direction=direction_norm,
                repo=resolved_repo or repo,
            )
            if _repo_missing(result):
                alt = self._canonical_repo(repo, force_refresh=True)
                if alt and alt != resolved_repo:
                    resolved_repo = alt
                    result = self._wrap(
                        self.cli.impact(
                            candidate,
                            direction=direction_norm,
                            repo=resolved_repo,
                            file=file,
                            uid=uid,
                            kind=kind,
                            cwd=self._cwd_for_repo(resolved_repo),
                        ),
                        symbol=candidate,
                        direction=direction_norm,
                        repo=resolved_repo,
                    )
            result = self._resolve_ambiguous(
                result,
                symbol=candidate,
                repo=resolved_repo or repo,
                file=file,
                kind="impact",
                direction=direction_norm,
            )
            last = result
            if _graph_hit_usable(result.get("result")):
                return result
        return last or {"ok": False, "error": "symbol is required", "result": None}

    def _canonical_repo(self, repo: str | None, *, force_refresh: bool = False) -> str | None:
        """Map service / Zoekt repo labels onto a GitNexus registry name when possible."""
        requested = str(repo or "").strip()
        if not requested:
            return None
        available = self._listed_repo_names(force_refresh=force_refresh)
        if not available:
            return requested
        matched = _match_gitnexus_repo(requested, available)
        return matched or requested

    def _listed_repo_names(self, *, force_refresh: bool = False) -> list[str]:
        cache = getattr(self, "_repo_name_cache", None)
        if isinstance(cache, list) and cache and not force_refresh:
            return cache
        names: list[str] = []
        try:
            payload = self.list_repos()
            result = payload.get("result")
            data = result if isinstance(result, (dict, list)) else payload.get("data")
            names = _extract_repo_names(data if data is not None else payload)
        except Exception:  # noqa: BLE001
            names = []
        self._repo_name_cache = names
        return names

    def _resolve_ambiguous(
        self,
        payload: dict[str, Any],
        *,
        symbol: str,
        repo: str | None,
        file: str | None,
        kind: str,
        direction: str = "upstream",
    ) -> dict[str, Any]:
        """When GitNexus returns multiple symbol hits, prefer concrete impl over interface."""
        data = payload.get("result")
        if not isinstance(data, dict) or str(data.get("status") or "").lower() != "ambiguous":
            return payload
        pick = _pick_ambiguous_candidate(data.get("candidates"), symbol=symbol, file=file)
        if not pick:
            return payload
        uid = str(pick.get("uid") or "").strip() or None
        file_path = str(pick.get("filePath") or pick.get("file") or file or "").strip() or None
        if kind == "impact":
            resolved = self._wrap(
                self.cli.impact(
                    symbol,
                    direction=direction,
                    repo=repo,
                    file=file_path,
                    uid=uid,
                    cwd=self._cwd_for_repo(repo),
                ),
                symbol=symbol,
                direction=direction,
                repo=repo,
                disambiguated_uid=uid,
            )
        else:
            resolved = self._wrap(
                self.cli.context(
                    symbol,
                    repo=repo,
                    file=file_path,
                    uid=uid,
                    cwd=self._cwd_for_repo(repo),
                ),
                symbol=symbol,
                repo=repo,
                disambiguated_uid=uid,
            )
        if resolved.get("ok"):
            return resolved
        return payload

    def trace(
        self,
        source: str,
        target: str,
        *,
        repo: str | None = None,
    ) -> dict[str, Any]:
        if not self.enabled:
            return {"ok": False, "error": "gitnexus unavailable", "result": None}
        src = str(source or "").strip()
        dst = str(target or "").strip()
        if not src or not dst:
            return {"ok": False, "error": "source and target are required"}
        return self._wrap(
            self.cli.trace(src, dst, repo=repo, cwd=self._cwd_for_repo(repo)),
            source=src,
            target=dst,
            repo=repo,
        )

    def cypher(self, query: str, *, repo: str | None = None) -> dict[str, Any]:
        if not self.enabled:
            return {"ok": False, "error": "gitnexus unavailable", "result": None}
        q = str(query or "").strip()
        if not q:
            return {"ok": False, "error": "query is required"}
        return self._wrap(
            self.cli.cypher(q, repo=repo, cwd=self._cwd_for_repo(repo)),
            query=q,
            repo=repo,
        )

    def detect_changes(self, *, repo: str | None = None) -> dict[str, Any]:
        if not self.enabled:
            return {"ok": False, "error": "gitnexus unavailable", "result": None}
        return self._wrap(
            self.cli.detect_changes(repo=repo, cwd=self._cwd_for_repo(repo)),
            repo=repo,
        )

    def callers_for_symbol(
        self,
        symbol: str,
        *,
        repo: str | None = None,
        file: str | None = None,
        max_depth: int = 5,
    ) -> dict[str, Any]:
        """Normalize impact(upstream) + context into find_callers-compatible frames."""
        candidates = _symbol_candidates(symbol)
        last_error: str | None = None
        for candidate in candidates:
            impact_payload = self.impact(
                candidate,
                direction="upstream",
                repo=repo,
                file=file,
            )
            if not impact_payload.get("ok"):
                last_error = str(impact_payload.get("stderr") or impact_payload.get("error") or "")
                continue
            callers = _extract_callers_from_impact(
                impact_payload.get("result"), max_depth=max_depth
            )
            if callers:
                return {
                    "ok": True,
                    "source": "gitnexus",
                    "symbol": candidate,
                    "repo": repo,
                    "static_callers": callers,
                    "raw": impact_payload,
                }
            context_payload = self.context(candidate, repo=repo, file=file)
            callers = _extract_callers_from_context(
                context_payload.get("result"), max_depth=max_depth
            )
            if callers:
                return {
                    "ok": True,
                    "source": "gitnexus",
                    "symbol": candidate,
                    "repo": repo,
                    "static_callers": callers,
                    "raw": {"impact": impact_payload, "context": context_payload},
                }
        return {
            "ok": False,
            "source": "gitnexus",
            "symbol": symbol,
            "repo": repo,
            "static_callers": [],
            "error": last_error or "no callers found in knowledge graph",
        }


def _repo_missing(payload: dict[str, Any]) -> bool:
    blob = " ".join(
        str(part or "")
        for part in (
            payload.get("stderr"),
            payload.get("stdout"),
            payload.get("error"),
            (payload.get("result") or {}).get("error")
            if isinstance(payload.get("result"), dict)
            else "",
        )
    ).lower()
    return "not found" in blob and "available" in blob


def _match_gitnexus_repo(requested: str, available: list[str]) -> str | None:
    req = requested.strip()
    if not req or not available:
        return None
    lowered = {name: name.lower() for name in available}
    req_l = req.lower()
    for name, low in lowered.items():
        if low == req_l:
            return name
    for name, low in lowered.items():
        if low.endswith("__" + req_l) or low.endswith("/" + req_l) or low.endswith("\\" + req_l):
            return name
    # Prefer the shortest name that contains the service token.
    contains = [name for name, low in lowered.items() if req_l in low]
    if contains:
        return sorted(contains, key=len)[0]
    return None


def _extract_repo_names(data: Any) -> list[str]:
    names: list[str] = []

    def add(value: Any) -> None:
        text = str(value or "").strip()
        if text and text not in names:
            names.append(text)

    if isinstance(data, list):
        for item in data:
            if isinstance(item, str):
                add(item)
            elif isinstance(item, dict):
                add(item.get("name") or item.get("repo") or item.get("id") or item.get("label"))
        return names
    if isinstance(data, dict):
        for key in ("repos", "repositories", "items", "result"):
            nested = data.get(key)
            if nested is not None:
                names.extend(_extract_repo_names(nested))
        # Plain text listing fallback
        text = data.get("text")
        if isinstance(text, str):
            for line in text.splitlines():
                stripped = line.strip().lstrip("-*•").strip()
                if stripped and " " not in stripped and len(stripped) < 120:
                    add(stripped)
    return names


def _graph_hit_usable(data: Any) -> bool:
    if not isinstance(data, dict):
        return False
    err = str(data.get("error") or "").lower()
    if "not found" in err:
        return False
    if str(data.get("status") or "").lower() == "ambiguous":
        return False
    if int(data.get("impactedCount") or 0) > 0:
        return True
    if isinstance(data.get("byDepth"), dict) and any(data["byDepth"].values()):
        return True
    if isinstance(data.get("by_depth"), dict) and any(data["by_depth"].values()):
        return True
    # context payloads: require actual relationship / process payload, not bare target
    for key in (
        "incoming",
        "outgoing",
        "processes",
        "process",
        "categories",
        "categorized",
        "refs",
    ):
        value = data.get(key)
        if value:
            return True
    summary = data.get("summary")
    if isinstance(summary, dict) and any(summary.values()):
        return True
    return False


def _pick_ambiguous_candidate(
    candidates: Any,
    *,
    symbol: str,
    file: str | None = None,
) -> dict[str, Any] | None:
    if not isinstance(candidates, list) or not candidates:
        return None
    rows = [c for c in candidates if isinstance(c, dict)]
    if not rows:
        return None
    file_hint = (file or "").replace("\\", "/").lower()
    class_hint = ""
    if "." in symbol:
        class_hint = symbol.rsplit(".", 1)[0].strip().lower()

    def score(row: dict[str, Any]) -> tuple[int, float]:
        path = str(row.get("filePath") or row.get("file") or "").replace("\\", "/").lower()
        name = str(row.get("name") or "").lower()
        uid = str(row.get("uid") or "").lower()
        points = 0
        if file_hint and file_hint in path:
            points += 100
        if "/impl/" in path or "\\impl\\" in path:
            points += 50
        if class_hint and (class_hint in path or class_hint in name or class_hint in uid):
            points += 40
        if "interface" in path or path.endswith(f"i{class_hint}.java"):
            points -= 20
        return (points, float(row.get("score") or 0.0))

    return sorted(rows, key=score, reverse=True)[0]


def _symbol_candidates(symbol: str) -> list[str]:
    value = str(symbol or "").strip()
    if not value:
        return []
    out: list[str] = []
    seen: set[str] = set()

    def add(item: str) -> None:
        cleaned = item.strip()
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            out.append(cleaned)

    add(value)
    if "(" in value:
        add(value.split("(", 1)[0])
    # Class.method → also try method and Class
    parts = [p for p in _SYMBOL_SPLIT_RE.split(value) if p]
    if len(parts) >= 2:
        add(parts[-1])
        add(".".join(parts[-2:]))
        add(parts[-2])
    return out


def _extract_callers_from_impact(data: Any, *, max_depth: int) -> list[dict[str, Any]]:
    if data is None:
        return []
    items: list[Any] = []
    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        for key in ("affected", "nodes", "results", "upstream", "callers", "items", "symbols"):
            value = data.get(key)
            if isinstance(value, list):
                items = value
                break
        by_depth = (
            data.get("byDepth") if isinstance(data.get("byDepth"), dict) else data.get("by_depth")
        )
        if not items and isinstance(by_depth, dict):
            for depth_key, group in by_depth.items():
                if isinstance(group, list):
                    for item in group:
                        if isinstance(item, dict):
                            item = {**item, "depth": item.get("depth", depth_key)}
                            # Normalize GitNexus impact fields for callers.
                            item.setdefault("file", item.get("filePath") or item.get("path"))
                            item.setdefault("path", item.get("filePath") or item.get("file"))
                        items.append(item)
        if not items and isinstance(data.get("text"), str):
            return _parse_text_callers(data["text"], max_depth=max_depth)
    return [_normalize_caller_item(item, default_depth=1) for item in items if item][
        : max(1, max_depth) * 20
    ]


def _extract_callers_from_context(data: Any, *, max_depth: int) -> list[dict[str, Any]]:
    if isinstance(data, str):
        return _parse_text_callers(data, max_depth=max_depth)
    if not isinstance(data, dict):
        return []
    for key in ("incoming", "callers", "references", "refs", "used_by"):
        value = data.get(key)
        if isinstance(value, list) and value:
            return [_normalize_caller_item(item, default_depth=1) for item in value][
                : max(1, max_depth) * 20
            ]
    categorized = data.get("categorized") or data.get("refs")
    if isinstance(categorized, dict):
        for key in ("calls", "callers", "incoming", "references"):
            value = categorized.get(key)
            if isinstance(value, list) and value:
                return [_normalize_caller_item(item, default_depth=1) for item in value][
                    : max(1, max_depth) * 20
                ]
    if isinstance(data.get("text"), str):
        return _parse_text_callers(data["text"], max_depth=max_depth)
    return []


def _normalize_caller_item(item: Any, *, default_depth: int) -> dict[str, Any]:
    if isinstance(item, str):
        class_name, method_name = _split_symbol(item)
        return {
            "repo": None,
            "path": None,
            "line": None,
            "snippet": item,
            "score": 1.0,
            "caller_class": class_name,
            "caller_method": method_name,
            "depth": default_depth,
            "source": "gitnexus",
        }
    if not isinstance(item, dict):
        return {
            "repo": None,
            "path": None,
            "line": None,
            "snippet": str(item),
            "score": 0.5,
            "caller_class": None,
            "caller_method": str(item),
            "depth": default_depth,
            "source": "gitnexus",
        }
    name = (
        item.get("name")
        or item.get("symbol")
        or item.get("qualified_name")
        or item.get("id")
        or item.get("label")
        or ""
    )
    class_name = item.get("class") or item.get("caller_class") or item.get("parent")
    method_name = item.get("method") or item.get("caller_method")
    if not class_name or not method_name:
        split_class, split_method = _split_symbol(str(name))
        class_name = class_name or split_class
        method_name = method_name or split_method
    return {
        "repo": item.get("repo"),
        "path": item.get("file") or item.get("path") or item.get("filepath"),
        "line": item.get("line") or item.get("start_line") or item.get("line_start"),
        "snippet": item.get("snippet") or str(name),
        "score": float(item.get("score") or item.get("confidence") or 1.0),
        "caller_class": class_name,
        "caller_method": method_name,
        "depth": int(item.get("depth") or default_depth),
        "source": "gitnexus",
        "uid": item.get("uid") or item.get("id"),
    }


def _split_symbol(symbol: str) -> tuple[str | None, str]:
    value = symbol.strip()
    if "." in value:
        left, right = value.rsplit(".", 1)
        return left or None, right or value
    return None, value


def _parse_text_callers(text: str, *, max_depth: int) -> list[dict[str, Any]]:
    callers: list[dict[str, Any]] = []
    for line in text.splitlines():
        stripped = line.strip().lstrip("-*•").strip()
        if not stripped or len(stripped) < 3:
            continue
        if any(
            token in stripped.lower() for token in ("upstream", "downstream", "impact", "depth")
        ):
            # Keep symbol-looking lines only.
            if "(" not in stripped and "." not in stripped:
                continue
        class_name, method_name = _split_symbol(stripped.split()[0])
        callers.append(
            {
                "repo": None,
                "path": None,
                "line": None,
                "snippet": stripped,
                "score": 0.7,
                "caller_class": class_name,
                "caller_method": method_name,
                "depth": 1,
                "source": "gitnexus",
            }
        )
        if len(callers) >= max(1, max_depth) * 20:
            break
    return callers
