"""Code chunking for vector indexing.

Primary unit follows the old root_seeker idea: prefer method/class symbol spans.
Oversized symbols are subdivided with the existing max_lines/overlap window *inside*
that symbol — there is no separate whole-file line-window fallback path.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from rootseeker.code_index.file_scanner import CodeFile

__all__ = [
    "CodeChunk",
    "ChunkConfig",
    "SymbolSpan",
    "chunk_code_file",
    "chunk_code_files",
    "extract_symbol_spans",
]


@dataclass(frozen=True)
class ChunkConfig:
    max_lines: int = 120
    overlap_lines: int = 20
    min_chars: int = 1


@dataclass(frozen=True)
class SymbolSpan:
    """Inclusive 1-based line range for a named code symbol."""

    name: str
    kind: str  # method | class | function
    start_line: int
    end_line: int


@dataclass(frozen=True)
class CodeChunk:
    repo: str
    path: str
    language: str
    start_line: int
    end_line: int
    content: str
    sha256: str
    symbol: str | None = None
    symbol_kind: str | None = None

    @property
    def stable_key(self) -> str:
        symbol = self.symbol or ""
        return (
            f"{self.repo}:{self.path}:{self.start_line}:{self.end_line}:"
            f"{symbol}:{self.sha256}"
        )


_JAVA_TYPE_START = re.compile(
    r"^\s*(?:(?:public|protected|private|static|final|abstract|sealed|non-sealed|strictfp)\s+)*"
    r"(?:class|interface|enum|record)\s+(?P<name>[A-Za-z_][\w$]*)\b"
)
_JAVA_METHOD_START = re.compile(
    r"^\s*(?:(?:public|protected|private|static|final|native|synchronized|abstract|default|strictfp)\s+)+"
    r"(?:<[^>]+>\s*)?"
    r"(?:[\w.$\[\]]+)\s+(?P<name>[A-Za-z_][\w$]*)\s*\("
)
_JAVA_CTOR_START = re.compile(
    r"^\s*(?:(?:public|protected|private)\s+)+(?P<name>[A-Za-z_][\w$]*)\s*\("
)
_PY_DEF = re.compile(r"^(?P<indent>\s*)(?:async\s+)?def\s+(?P<name>[A-Za-z_][\w]*)\s*\(")
_PY_CLASS = re.compile(r"^(?P<indent>\s*)class\s+(?P<name>[A-Za-z_][\w]*)\s*[:(]")
_JS_FUNC = re.compile(
    r"^\s*(?:export\s+)?(?:async\s+)?function\s+(?P<name>[A-Za-z_$][\w$]*)\s*\("
)
_JS_CLASS = re.compile(r"^\s*(?:export\s+)?class\s+(?P<name>[A-Za-z_$][\w$]*)\b")
_JS_METHOD = re.compile(
    r"^\s*(?:async\s+)?(?P<name>[A-Za-z_$][\w$]*)\s*\([^;]*\)\s*\{"
)
_GO_FUNC = re.compile(
    r"^func\s+(?:\([^)]+\)\s+)?(?P<name>[A-Za-z_][\w]*)\s*\("
)


def chunk_code_file(repo_name: str, code_file: CodeFile, config: ChunkConfig | None = None) -> list[CodeChunk]:
    cfg = config or ChunkConfig()
    lines = code_file.content.splitlines()
    if not lines:
        return []

    spans = extract_symbol_spans(lines, code_file.language)
    if not spans:
        # No named symbols: index the whole file as one logical unit, windowing only
        # when it exceeds max_lines (same subdivider used for oversized methods).
        return _window_range(
            repo_name=repo_name,
            code_file=code_file,
            lines=lines,
            start_line=1,
            end_line=len(lines),
            symbol=None,
            symbol_kind=None,
            config=cfg,
        )

    chunks: list[CodeChunk] = []
    covered = [False] * (len(lines) + 1)
    for span in spans:
        for line_no in range(span.start_line, span.end_line + 1):
            if 1 <= line_no <= len(lines):
                covered[line_no] = True
        chunks.extend(
            _window_range(
                repo_name=repo_name,
                code_file=code_file,
                lines=lines,
                start_line=span.start_line,
                end_line=span.end_line,
                symbol=span.name,
                symbol_kind=span.kind,
                config=cfg,
            )
        )

    # Keep preamble / gaps between symbols as anonymous units (imports, fields, etc.).
    gap_start: int | None = None
    for line_no in range(1, len(lines) + 1):
        if covered[line_no]:
            if gap_start is not None:
                chunks.extend(
                    _window_range(
                        repo_name=repo_name,
                        code_file=code_file,
                        lines=lines,
                        start_line=gap_start,
                        end_line=line_no - 1,
                        symbol=None,
                        symbol_kind=None,
                        config=cfg,
                    )
                )
                gap_start = None
            continue
        if gap_start is None:
            gap_start = line_no
    if gap_start is not None:
        chunks.extend(
            _window_range(
                repo_name=repo_name,
                code_file=code_file,
                lines=lines,
                start_line=gap_start,
                end_line=len(lines),
                symbol=None,
                symbol_kind=None,
                config=cfg,
            )
        )

    chunks.sort(key=lambda item: (item.start_line, item.end_line, item.symbol or ""))
    return chunks


def chunk_code_files(repo_name: str, files: list[CodeFile], config: ChunkConfig | None = None) -> list[CodeChunk]:
    chunks: list[CodeChunk] = []
    for code_file in files:
        chunks.extend(chunk_code_file(repo_name, code_file, config=config))
    return chunks


def extract_symbol_spans(lines: list[str], language: str) -> list[SymbolSpan]:
    lang = (language or "").strip().lower()
    if lang in {"java"}:
        return _extract_java_spans(lines)
    if lang in {"python", "py"}:
        return _extract_python_spans(lines)
    if lang in {"javascript", "js", "typescript", "ts", "tsx", "jsx"}:
        return _extract_brace_spans(lines, language=lang)
    if lang in {"go"}:
        return _extract_go_spans(lines)
    return []


def _window_range(
    *,
    repo_name: str,
    code_file: CodeFile,
    lines: list[str],
    start_line: int,
    end_line: int,
    symbol: str | None,
    symbol_kind: str | None,
    config: ChunkConfig,
) -> list[CodeChunk]:
    if end_line < start_line:
        return []
    segment = lines[start_line - 1 : end_line]
    if not segment:
        return []

    max_lines = max(1, config.max_lines)
    overlap = max(0, min(config.overlap_lines, max_lines - 1))
    step = max(1, max_lines - overlap)
    chunks: list[CodeChunk] = []
    offset = 0
    while offset < len(segment):
        piece_end = min(len(segment), offset + max_lines)
        content = "\n".join(segment[offset:piece_end]).strip()
        if len(content) >= config.min_chars:
            abs_start = start_line + offset
            abs_end = start_line + piece_end - 1
            chunks.append(
                CodeChunk(
                    repo=repo_name,
                    path=code_file.path,
                    language=code_file.language,
                    start_line=abs_start,
                    end_line=abs_end,
                    content=content,
                    sha256=code_file.sha256,
                    symbol=symbol,
                    symbol_kind=symbol_kind,
                )
            )
        if piece_end >= len(segment):
            break
        offset += step
    return chunks


def _extract_python_spans(lines: list[str]) -> list[SymbolSpan]:
    starts: list[tuple[int, int, str, str]] = []  # line, indent, name, kind
    for idx, line in enumerate(lines):
        if line.strip().startswith("#"):
            continue
        class_match = _PY_CLASS.match(line)
        if class_match:
            starts.append((idx + 1, len(class_match.group("indent")), class_match.group("name"), "class"))
            continue
        def_match = _PY_DEF.match(line)
        if def_match:
            starts.append((idx + 1, len(def_match.group("indent")), def_match.group("name"), "function"))

    spans: list[SymbolSpan] = []
    for i, (start_line, indent, name, kind) in enumerate(starts):
        end_line = len(lines)
        for next_start, next_indent, _n, _k in starts[i + 1 :]:
            if next_indent <= indent:
                end_line = next_start - 1
                break
        end_line = _trim_trailing_blank(lines, start_line, end_line)
        spans.append(SymbolSpan(name=name, kind=kind, start_line=start_line, end_line=end_line))
    return spans


def _extract_java_spans(lines: list[str]) -> list[SymbolSpan]:
    spans: list[SymbolSpan] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        type_match = _JAVA_TYPE_START.match(line)
        method_match = _JAVA_METHOD_START.match(line)
        ctor_match = None if method_match else _JAVA_CTOR_START.match(line)
        match = type_match or method_match or ctor_match
        if match is None or "{" not in line and not _header_continues_to_brace(lines, i):
            i += 1
            continue
        kind = "class" if type_match else "method"
        name = match.group("name")
        brace_line = i if "{" in line else _find_opening_brace(lines, i)
        if brace_line is None:
            i += 1
            continue
        end_idx = _match_brace_block(lines, brace_line)
        if end_idx is None:
            i += 1
            continue
        spans.append(
            SymbolSpan(
                name=name,
                kind=kind,
                start_line=i + 1,
                end_line=end_idx + 1,
            )
        )
        # Do not skip nested methods inside a class: continue scanning from next line
        # after the header so nested method_declaration-like spans are collected.
        # For methods/ctors, jump past the body to avoid overlapping fragments.
        if kind == "method":
            i = end_idx + 1
        else:
            i += 1
    return _dedupe_spans(spans)


def _extract_brace_spans(lines: list[str], *, language: str) -> list[SymbolSpan]:
    spans: list[SymbolSpan] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        class_match = _JS_CLASS.match(line)
        func_match = _JS_FUNC.match(line)
        method_match = None
        if class_match is None and func_match is None and "{" in line:
            method_match = _JS_METHOD.match(line)
            if method_match and method_match.group("name") in {
                "if",
                "for",
                "while",
                "switch",
                "catch",
                "function",
            }:
                method_match = None
        match = class_match or func_match or method_match
        if match is None:
            i += 1
            continue
        kind = "class" if class_match else ("function" if func_match else "method")
        brace_line = i if "{" in line else _find_opening_brace(lines, i)
        if brace_line is None:
            i += 1
            continue
        end_idx = _match_brace_block(lines, brace_line)
        if end_idx is None:
            i += 1
            continue
        spans.append(
            SymbolSpan(
                name=match.group("name"),
                kind=kind,
                start_line=i + 1,
                end_line=end_idx + 1,
            )
        )
        if kind != "class":
            i = end_idx + 1
        else:
            i += 1
    _ = language
    return _dedupe_spans(spans)


def _extract_go_spans(lines: list[str]) -> list[SymbolSpan]:
    spans: list[SymbolSpan] = []
    i = 0
    while i < len(lines):
        match = _GO_FUNC.match(lines[i])
        if match is None:
            i += 1
            continue
        brace_line = i if "{" in lines[i] else _find_opening_brace(lines, i)
        if brace_line is None:
            i += 1
            continue
        end_idx = _match_brace_block(lines, brace_line)
        if end_idx is None:
            i += 1
            continue
        spans.append(
            SymbolSpan(
                name=match.group("name"),
                kind="function",
                start_line=i + 1,
                end_line=end_idx + 1,
            )
        )
        i = end_idx + 1
    return spans


def _header_continues_to_brace(lines: list[str], start: int) -> bool:
    return _find_opening_brace(lines, start) is not None


def _find_opening_brace(lines: list[str], start: int) -> int | None:
    for idx in range(start, min(len(lines), start + 12)):
        if "{" in lines[idx]:
            return idx
        stripped = lines[idx].strip()
        if idx > start and stripped and not stripped.endswith(",") and not stripped.endswith("("):
            # Stop if the signature clearly ended without a body.
            if stripped.endswith(";") or stripped.startswith("@"):
                return None
    return None


def _match_brace_block(lines: list[str], brace_line: int) -> int | None:
    depth = 0
    started = False
    for idx in range(brace_line, len(lines)):
        for ch in lines[idx]:
            if ch == "{":
                depth += 1
                started = True
            elif ch == "}":
                depth -= 1
                if started and depth == 0:
                    return idx
    return None


def _trim_trailing_blank(lines: list[str], start_line: int, end_line: int) -> int:
    end = end_line
    while end > start_line and not lines[end - 1].strip():
        end -= 1
    return end


def _dedupe_spans(spans: list[SymbolSpan]) -> list[SymbolSpan]:
    """Prefer tighter method spans over a containing class when ranges collide entirely."""
    if not spans:
        return []
    ordered = sorted(spans, key=lambda s: (s.start_line, -(s.end_line - s.start_line), s.name))
    kept: list[SymbolSpan] = []
    for span in ordered:
        duplicate = False
        for existing in kept:
            if (
                existing.start_line == span.start_line
                and existing.end_line == span.end_line
                and existing.name == span.name
            ):
                duplicate = True
                break
        if not duplicate:
            kept.append(span)
    return sorted(kept, key=lambda s: (s.start_line, s.end_line, s.name))
