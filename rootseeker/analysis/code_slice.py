from __future__ import annotations

import re
from typing import Any

__all__ = [
    "DEFAULT_MAX_CODE_READ_LINES",
    "chain_methods_for_path",
    "fault_line_for_path",
    "slice_source_window",
]

DEFAULT_MAX_CODE_READ_LINES = 400

_METHOD_START_RE = re.compile(
    r"^\s*(?:(?:public|protected|private|static|final|synchronized|native|default|abstract)\s+)+"
    r".+\([^;]*\)\s*\{?\s*$"
)
_CONTROL_START_RE = re.compile(r"^\s*(if|for|while|switch|catch|else)\b")
_SKIP_LEADING = {
    "if",
    "for",
    "while",
    "switch",
    "catch",
    "else",
    "return",
    "throw",
    "new",
    "this",
    "super",
    "try",
    "do",
    "case",
    "assert",
    "goto",
}


def fault_line_for_path(path: str, call_chain: list[str]) -> int | None:
    """Pick the first call-chain line that belongs to this source file."""
    methods = chain_methods_for_path(path, call_chain)
    for item in methods:
        line = int(item.get("line") or 0)
        if line > 0:
            return line
    return None


def chain_methods_for_path(path: str, call_chain: list[str]) -> list[dict[str, Any]]:
    """Return this file's call-chain methods in stack order, de-duplicated."""
    from rootseeker.analysis.find_callers import parse_call_chain_frame

    needle = _file_needle(path)
    if not needle:
        return []
    found: list[dict[str, Any]] = []
    seen: set[str] = set()
    for frame in call_chain or []:
        parsed = parse_call_chain_frame(str(frame))
        if parsed is None:
            continue
        file_name = _file_needle(str(parsed.get("file_path") or ""))
        if not file_name or not _same_source_file(needle, file_name):
            continue
        name = str(parsed.get("method_name") or "").strip()
        if not name or name in {"<init>", "<clinit>"} or name in seen:
            continue
        seen.add(name)
        line = int(parsed.get("line") or 0)
        found.append({"name": name, "line": line or None})
    return found


def slice_source_window(
    text: str,
    *,
    start_line: int = 1,
    end_line: int | None = None,
    focus_line: int | None = None,
    methods: list[Any] | None = None,
    max_lines: int = DEFAULT_MAX_CODE_READ_LINES,
) -> tuple[str, int, int]:
    """Return only the requested methods, or a window around the fault line."""
    lines = str(text or "").splitlines()
    total = len(lines)
    if total == 0:
        return "", 1, 1

    explicit_end = end_line is not None and int(end_line) > 0
    start = max(1, int(start_line or 1))
    end = min(total, int(end_line)) if explicit_end else total

    if explicit_end and start_line > 1:
        start, end = _clamp_window(start, end, total, max_lines, focus_line)
        return _join(lines, start, end), start, end

    named = _extract_named_methods(lines, methods)
    if named is not None:
        return named

    if focus_line:
        focus = max(1, min(int(focus_line), total))
        method_start = _java_method_start(lines, focus)
        method_end = _java_method_end(lines, method_start or focus)
        if method_start and method_end:
            start, end = method_start, method_end
        else:
            start = max(1, focus - 160)
            end = min(total, focus + 40)
        start, end = _clamp_window(start, end, total, max_lines, focus)
        return _join(lines, start, end), start, end

    if total > max_lines and not explicit_end:
        return _join(lines, 1, max_lines), 1, max_lines
    return _join(lines, 1, total), 1, total


def _file_needle(path: str) -> str:
    return str(path or "").replace("\\", "/").rsplit("/", 1)[-1].lower()


def _same_source_file(needle: str, file_name: str) -> bool:
    return file_name == needle or needle.endswith(file_name) or file_name.endswith(needle)


def _normalize_methods(methods: list[Any] | None) -> list[dict[str, Any]]:
    specs: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in methods or []:
        name = ""
        line: int | None = None
        if isinstance(item, str):
            name = item.strip()
        elif isinstance(item, dict):
            name = str(item.get("name") or item.get("method_name") or "").strip()
            raw_line = item.get("line")
            line = int(raw_line) if raw_line else None
        if not name or name in {"<init>", "<clinit>"} or name in seen:
            continue
        seen.add(name)
        specs.append({"name": name, "line": line})
    return specs


def _extract_named_methods(
    lines: list[str], methods: list[Any] | None
) -> tuple[str, int, int] | None:
    specs = _normalize_methods(methods)
    if not specs:
        return None
    spans: list[tuple[int, int]] = []
    for spec in specs:
        span = _java_named_method_span(lines, spec["name"], spec.get("line"))
        if span is not None:
            spans.append(span)
    if not spans:
        return None
    merged = _merge_spans(spans)
    parts = [_join(lines, start, end) for start, end in merged]
    return "\n\n".join(parts), merged[0][0], merged[-1][1]


def _merge_spans(spans: list[tuple[int, int]]) -> list[tuple[int, int]]:
    ordered = sorted(spans, key=lambda item: (item[0], item[1]))
    merged: list[tuple[int, int]] = [ordered[0]]
    for start, end in ordered[1:]:
        prev_start, prev_end = merged[-1]
        if start <= prev_end + 1:
            merged[-1] = (prev_start, max(prev_end, end))
        else:
            merged.append((start, end))
    return merged


def _join(lines: list[str], start: int, end: int) -> str:
    return "\n".join(lines[start - 1 : end])


def _clamp_window(
    start: int,
    end: int,
    total: int,
    max_lines: int,
    focus_line: int | None,
) -> tuple[int, int]:
    start = max(1, start)
    end = min(total, max(start, end))
    if end - start + 1 <= max_lines:
        return start, end
    focus = focus_line or end
    focus = max(start, min(focus, end))
    new_start = max(start, focus - max_lines + 60)
    new_end = min(end, new_start + max_lines - 1)
    if new_end - new_start + 1 < max_lines:
        new_start = max(start, new_end - max_lines + 1)
    return new_start, new_end


def _java_method_start(lines: list[str], focus: int) -> int | None:
    for index in range(focus - 1, -1, -1):
        stripped = lines[index].strip()
        if not stripped or _CONTROL_START_RE.match(stripped):
            continue
        if _METHOD_START_RE.match(lines[index]):
            return index + 1
    return None


def _java_named_method_span(
    lines: list[str], name: str, line: int | None
) -> tuple[int, int] | None:
    pattern = re.compile(
        r"^\s*(?:(?:public|protected|private|static|final|synchronized|native|default|abstract)\s+)*"
        rf".+?\s+{re.escape(name)}\s*\("
    )
    candidates: list[int] = []
    for index, text in enumerate(lines):
        stripped = text.strip()
        if not stripped or stripped.endswith(";"):
            continue
        lead = stripped.split()[0]
        if lead in _SKIP_LEADING:
            continue
        if not pattern.match(text):
            continue
        candidates.append(index + 1)
    if not candidates:
        return None
    focus = int(line) if line else 0
    if focus > 0:
        at_or_before = [item for item in candidates if item <= focus]
        start = at_or_before[-1] if at_or_before else min(
            candidates, key=lambda item: abs(item - focus)
        )
    else:
        start = candidates[0]
    return start, _java_method_end(lines, start)


def _java_method_end(lines: list[str], start: int) -> int:
    depth = 0
    started = False
    for index in range(max(0, start - 1), len(lines)):
        for char in lines[index]:
            if char == "{":
                depth += 1
                started = True
            elif char == "}":
                depth -= 1
                if started and depth == 0:
                    return index + 1
    return len(lines)
