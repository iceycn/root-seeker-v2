from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

__all__ = [
    "analyze_call_chain",
    "align_runtime_static_chain",
    "build_caller_search_query",
    "parse_call_chain_frame",
]

_FRAME_SUMMARY_RE = re.compile(
    r"^(?P<class_name>[\w$]+)\.(?P<method_name>[\w$<>]+)\s+\((?P<file_path>[^:]+):(?P<line>\d+)\)\s*$"
)
_JAVA_FILE_CLASS_RE = re.compile(r"/([\w$]+)\.java$|^(?:[\w$]+/)?([\w$]+)\.java$")
_HTTP_MAPPING_RE = re.compile(
    r"@(?:(?:Get|Post|Put|Delete|Patch|Request)Mapping)\s*\(([^)]*)\)",
    re.MULTILINE,
)
_HTTP_PATH_RE = re.compile(r'(?:value|path)\s*=\s*["\']([^"\']+)["\']')
_JAVA_METHOD_DEF_RE = re.compile(
    r"(?:public|protected|private|static|\s)+[\w<>\[\],\s.?]+\s+(?P<method>[\w$]+)\s*\([^;]*\)\s*(?:throws[\w\s,]+)?\s*\{"
)


def parse_call_chain_frame(frame: str) -> dict[str, Any] | None:
    """Parse a call-chain summary frame into structured fields."""
    value = str(frame or "").strip()
    if not value:
        return None
    match = _FRAME_SUMMARY_RE.match(value)
    if match is None:
        return None
    return {
        "class_name": match.group("class_name"),
        "method_name": match.group("method_name"),
        "file_path": match.group("file_path"),
        "line": int(match.group("line")),
        "summary": value,
    }


def build_caller_search_query(
    *,
    class_name: str | None = None,
    method_name: str,
    repo: str | None = None,
) -> str:
    """Build a Zoekt query to find call sites of a method."""
    method = str(method_name or "").strip()
    if not method:
        return ""
    parts: list[str] = []
    if repo:
        parts.append(f"repo:{repo}")
    if class_name:
        parts.append(str(class_name))
    parts.append(f"{method}(")
    return " ".join(parts)


def align_runtime_static_chain(
    runtime_chain: list[str],
    static_frames: list[dict[str, Any]],
) -> dict[str, Any]:
    """Align runtime stack frames with statically discovered caller frames."""
    runtime_parsed = [parse_call_chain_frame(item) for item in runtime_chain]
    runtime_parsed = [item for item in runtime_parsed if item is not None]

    static_summaries = [
        f"{item.get('caller_class')}.{item.get('caller_method')}"
        for item in static_frames
        if item.get("caller_class") and item.get("caller_method")
    ]

    aligned: list[str] = []
    matched_indices: list[int] = []
    for runtime_frame in runtime_parsed:
        signature = f"{runtime_frame['class_name']}.{runtime_frame['method_name']}"
        aligned.append(signature)
        for static_index, static_frame in enumerate(static_frames):
            static_signature = (
                f"{static_frame.get('caller_class')}.{static_frame.get('caller_method')}"
            )
            if static_signature == signature and static_index not in matched_indices:
                matched_indices.append(static_index)
                break

    entry_frame = runtime_parsed[-1] if runtime_parsed else None
    fault_frame = runtime_parsed[0] if runtime_parsed else None
    return {
        "matched": len(matched_indices) > 0 or bool(runtime_parsed),
        "runtime_chain": [f"{f['class_name']}.{f['method_name']}" for f in runtime_parsed],
        "static_chain": static_summaries,
        "aligned_path": aligned,
        "fault_method": (
            f"{fault_frame['class_name']}.{fault_frame['method_name']}" if fault_frame else None
        ),
        "entry_method": (
            f"{entry_frame['class_name']}.{entry_frame['method_name']}" if entry_frame else None
        ),
    }


def analyze_call_chain(
    call_chain: list[str],
    *,
    search_code: Callable[..., dict[str, Any]],
    read_code: Callable[..., dict[str, Any]] | None = None,
    repo: str | None = None,
    service_name: str | None = None,
    max_depth: int = 5,
    limit_per_query: int = 30,
    graph_callers: Callable[..., dict[str, Any]] | None = None,
    prefer_graph: bool = True,
) -> dict[str, Any]:
    """Trace callers across indexed repositories.

    Prefer knowledge-graph callers (GitNexus) when available, then fall back to
    Zoekt text-search heuristics.
    """
    frames = [str(item).strip() for item in call_chain if str(item).strip()]
    parsed_frames = [parse_call_chain_frame(item) for item in frames]
    parsed_frames = [item for item in parsed_frames if item is not None]

    if not parsed_frames:
        return {
            "target": None,
            "runtime_chain": frames,
            "static_callers": [],
            "aligned": align_runtime_static_chain(frames, []),
            "entrypoints": [],
            "queries": [],
            "source": None,
            "notes": "未提供可解析的 call_chain 帧。",
        }

    repo_hint = (repo or service_name or "").strip() or None
    target = parsed_frames[0]
    graph_meta: dict[str, Any] | None = None

    if prefer_graph and graph_callers is not None:
        symbol = f"{target['class_name']}.{target['method_name']}"
        try:
            graph_result = graph_callers(
                symbol,
                repo=repo_hint,
                file=str(target.get("file_path") or "") or None,
                max_depth=max_depth,
            )
        except Exception as exc:  # noqa: BLE001
            graph_result = {"ok": False, "error": str(exc), "static_callers": []}
        if isinstance(graph_result, dict) and graph_result.get("ok"):
            static_callers = list(graph_result.get("static_callers") or [])
            if static_callers:
                for caller in static_callers:
                    if isinstance(caller, dict):
                        caller.setdefault("source", "gitnexus")
                aligned = align_runtime_static_chain(frames, static_callers)
                entrypoints = _detect_entrypoints(parsed_frames, read_code=read_code)
                return {
                    "target": target,
                    "runtime_chain": frames,
                    "static_callers": static_callers[:limit_per_query],
                    "aligned": aligned,
                    "entrypoints": entrypoints,
                    "queries": [],
                    "repo_hint": repo_hint,
                    "source": "gitnexus",
                    "graph": {
                        "symbol": graph_result.get("symbol") or symbol,
                        "raw_ok": True,
                    },
                    "notes": (
                        "基于 GitNexus 知识图谱的跨仓库 caller 追踪；失败时才会回退 Zoekt 启发式。"
                    ),
                }
        graph_meta = {
            "attempted": True,
            "ok": bool(isinstance(graph_result, dict) and graph_result.get("ok")),
            "error": (graph_result or {}).get("error") if isinstance(graph_result, dict) else None,
        }

    zoekt_result = _analyze_call_chain_zoekt(
        frames=frames,
        parsed_frames=parsed_frames,
        target=target,
        repo_hint=repo_hint,
        search_code=search_code,
        read_code=read_code,
        max_depth=max_depth,
        limit_per_query=limit_per_query,
    )
    if graph_meta is not None:
        zoekt_result["graph"] = graph_meta
        zoekt_result["notes"] = "GitNexus 无可用 caller，已回退 Zoekt 文本搜索启发式；" + str(
            zoekt_result.get("notes") or ""
        )
    return zoekt_result


def _analyze_call_chain_zoekt(
    *,
    frames: list[str],
    parsed_frames: list[dict[str, Any]],
    target: dict[str, Any],
    repo_hint: str | None,
    search_code: Callable[..., dict[str, Any]],
    read_code: Callable[..., dict[str, Any]] | None,
    max_depth: int,
    limit_per_query: int,
) -> dict[str, Any]:
    """Trace callers across indexed repositories using Zoekt heuristics."""
    static_callers: list[dict[str, Any]] = []
    queries: list[str] = []
    seen_signatures: set[str] = set()

    depth_limit = max(1, min(max_depth, len(parsed_frames)))
    for depth, callee_frame in enumerate(parsed_frames[:depth_limit]):
        callee_method = str(callee_frame["method_name"])
        callee_class = str(callee_frame["class_name"])
        query = build_caller_search_query(
            class_name=None,
            method_name=callee_method,
            repo=repo_hint,
        )
        if not query:
            continue
        queries.append(query)
        search_result = search_code(query, limit_per_query, repo_hint)
        hits = search_result.get("hits") if isinstance(search_result, dict) else []
        if not isinstance(hits, list):
            hits = []

        expected_caller = parsed_frames[depth + 1] if depth + 1 < len(parsed_frames) else None
        for hit in hits:
            if not isinstance(hit, dict):
                continue
            caller = _caller_from_hit(
                hit,
                callee_method=callee_method,
                callee_class=callee_class,
                read_code=read_code,
            )
            if caller is None:
                continue
            signature = (
                f"{caller['repo']}:{caller['caller_class']}.{caller['caller_method']}"
                f"->{callee_class}.{callee_method}"
            )
            if signature in seen_signatures:
                continue
            seen_signatures.add(signature)
            caller["depth"] = depth + 1
            caller["callee_class"] = callee_class
            caller["callee_method"] = callee_method
            caller["runtime_match"] = _matches_expected_caller(caller, expected_caller)
            caller.setdefault("source", "zoekt")
            static_callers.append(caller)

    static_callers.sort(
        key=lambda item: (
            0 if item.get("runtime_match") else 1,
            -float(item.get("score") or 0.0),
            int(item.get("depth") or 99),
        )
    )

    aligned = align_runtime_static_chain(frames, static_callers)
    entrypoints = _detect_entrypoints(parsed_frames, read_code=read_code)

    return {
        "target": target,
        "runtime_chain": frames,
        "static_callers": static_callers[:limit_per_query],
        "aligned": aligned,
        "entrypoints": entrypoints,
        "queries": queries,
        "repo_hint": repo_hint,
        "source": "zoekt",
        "notes": (
            "基于 Zoekt 文本搜索的跨仓库 caller 追踪；"
            "runtime_match=true 表示与日志 call_chain 下一帧一致。"
        ),
    }


def _matches_expected_caller(
    caller: dict[str, Any],
    expected: dict[str, Any] | None,
) -> bool:
    if expected is None:
        return False
    return str(caller.get("caller_class") or "") == str(expected.get("class_name") or "") and str(
        caller.get("caller_method") or ""
    ) == str(expected.get("method_name") or "")


def _caller_from_hit(
    hit: dict[str, Any],
    *,
    callee_method: str,
    callee_class: str,
    read_code: Callable[..., dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    snippet = str(hit.get("snippet") or "")
    path = str(hit.get("path") or "")
    if not snippet or not path:
        return None
    if _looks_like_definition(snippet, callee_method):
        return None
    if callee_method not in snippet:
        return None

    caller_class = _class_name_from_path(path)
    line = hit.get("line_start")
    repo = hit.get("repo")
    caller_method = _caller_method_from_snippet(snippet, path, line, callee_method=callee_method)
    if not caller_method and read_code is not None:
        caller_method = _enclosing_method_from_context(read_code, path, repo, line)
    if not caller_class or not caller_method:
        return None
    if caller_class == callee_class and caller_method == callee_method:
        return None

    return {
        "repo": hit.get("repo"),
        "path": path,
        "line": hit.get("line_start"),
        "snippet": snippet.strip(),
        "score": hit.get("score", 0.0),
        "caller_class": caller_class,
        "caller_method": caller_method,
    }


def _looks_like_definition(snippet: str, method_name: str) -> bool:
    stripped = snippet.strip()
    if not stripped:
        return False
    if re.search(
        rf"\b(?:public|protected|private|static)\b.*\b{re.escape(method_name)}\s*\(", stripped
    ):
        return True
    if re.search(r"\b(?:class|interface|enum)\s+\w+", stripped):
        return True
    return False


def _class_name_from_path(path: str) -> str | None:
    normalized = path.replace("\\", "/")
    match = _JAVA_FILE_CLASS_RE.search(normalized)
    if match is None:
        stem = normalized.rsplit("/", 1)[-1]
        if "." in stem:
            return stem.rsplit(".", 1)[0]
        return stem or None
    return match.group(1) or match.group(2)


def _caller_method_from_snippet(
    snippet: str,
    path: str,
    line: Any,
    *,
    callee_method: str | None = None,
) -> str | None:
    for match in _JAVA_METHOD_DEF_RE.finditer(snippet):
        method = match.group("method")
        if method not in {"if", "for", "while", "switch", "catch", "new"}:
            return method

    file_class = _class_name_from_path(path)
    if file_class:
        guessed = _guess_method_from_filename(file_class, snippet)
        if guessed and guessed != callee_method:
            return guessed
    return None


def _enclosing_method_from_context(
    read_code: Callable[..., dict[str, Any]],
    path: str,
    repo: Any,
    line: Any,
) -> str | None:
    line_no = int(line or 1)
    start = max(1, line_no - 60)
    try:
        payload = read_code(path, repo, start_line=start, end_line=line_no)
    except TypeError:
        payload = read_code(path, repo)
    if not isinstance(payload, dict):
        return None
    content = str(payload.get("content") or "")
    if not content:
        return None

    for raw in reversed(content.splitlines()):
        match = _JAVA_METHOD_DEF_RE.search(raw)
        if match is not None:
            candidate = match.group("method")
            if candidate not in {"if", "for", "while", "switch", "catch", "new"}:
                return candidate
    return None


def _guess_method_from_filename(class_name: str, snippet: str) -> str | None:
    # If snippet is `foo.bar(callee)` we cannot know caller method without file context.
    # Use a lightweight heuristic: method names often appear before the callee call on same line.
    tokens = re.findall(r"\b([A-Za-z_][\w$]*)\s*\(", snippet)
    for token in reversed(tokens):
        if token not in {"if", "for", "while", "switch", "catch", "new", class_name}:
            return token
    return None


def _detect_entrypoints(
    parsed_frames: list[dict[str, Any]],
    *,
    read_code: Callable[..., dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    if not parsed_frames:
        return []

    entrypoints: list[dict[str, Any]] = []
    seen: set[str] = set()
    for frame in reversed(parsed_frames):
        class_name = str(frame.get("class_name") or "")
        method_name = str(frame.get("method_name") or "")
        if not class_name.endswith("Controller"):
            continue
        signature = f"{class_name}.{method_name}"
        if signature in seen:
            continue
        seen.add(signature)
        entry: dict[str, Any] = {
            "type": "http",
            "class_name": class_name,
            "method_name": method_name,
            "file_path": frame.get("file_path"),
            "line": frame.get("line"),
            "mapping": None,
        }
        if read_code is not None:
            mapping = _read_http_mapping(
                read_code,
                file_path=str(frame.get("file_path") or ""),
                method_name=method_name,
                line=int(frame.get("line") or 0),
            )
            if mapping:
                entry["mapping"] = mapping
        entrypoints.append(entry)
    return entrypoints


def _read_http_mapping(
    read_code: Callable[..., dict[str, Any]],
    *,
    file_path: str,
    method_name: str,
    line: int,
) -> str | None:
    if not file_path:
        return None
    start = max(1, line - 80)
    end = max(start, line + 5)
    try:
        payload = read_code(file_path, None, start_line=start, end_line=end)
    except TypeError:
        payload = read_code(file_path)
    if not isinstance(payload, dict):
        payload = read_code(file_path)
    content = str(payload.get("content") or "") if isinstance(payload, dict) else ""
    if not content:
        return None

    method_line = 0
    lines = content.splitlines()
    for index, raw in enumerate(lines, start=start):
        if re.search(rf"\b{re.escape(method_name)}\s*\(", raw):
            method_line = index
            break
    if method_line <= 0:
        method_line = line

    window_start = max(start, method_line - 30)
    window = "\n".join(
        line_text
        for line_no, line_text in enumerate(lines, start=start)
        if window_start <= line_no <= method_line
    )
    mappings = list(_HTTP_MAPPING_RE.finditer(window))
    if not mappings:
        return None
    last = mappings[-1].group(1)
    path_match = _HTTP_PATH_RE.search(last)
    if path_match:
        return path_match.group(1)
    compact = " ".join(last.split())
    return compact or None
