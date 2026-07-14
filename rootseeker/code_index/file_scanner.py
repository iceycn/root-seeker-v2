from __future__ import annotations

import fnmatch
import hashlib
from dataclasses import dataclass
from pathlib import Path

__all__ = ["CodeFile", "FileScanConfig", "scan_code_files"]


DEFAULT_EXCLUDED_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".idea",
    ".vscode",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "node_modules",
    "dist",
    "build",
    "target",
    "vendor",
    ".venv",
    "venv",
    "env",
    "fuzzdb",
    "zapHomeFiles",
    "static",
    "webjars",
}

DEFAULT_INCLUDED_EXTENSIONS = {
    "",
    ".c",
    ".cc",
    ".cpp",
    ".cs",
    ".go",
    ".h",
    ".hpp",
    ".java",
    ".js",
    ".jsx",
    ".json",
    ".kt",
    ".md",
    ".php",
    ".py",
    ".rb",
    ".rs",
    ".scala",
    ".sh",
    ".sql",
    ".swift",
    ".toml",
    ".ts",
    ".tsx",
    ".xml",
    ".yaml",
    ".yml",
}

LANGUAGE_BY_EXT = {
    ".go": "go",
    ".java": "java",
    ".js": "javascript",
    ".jsx": "javascript",
    ".json": "json",
    ".md": "markdown",
    ".py": "python",
    ".rs": "rust",
    ".sh": "shell",
    ".sql": "sql",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".yaml": "yaml",
    ".yml": "yaml",
}


@dataclass(frozen=True)
class FileScanConfig:
    included_extensions: set[str] | None = None
    excluded_dirs: set[str] | None = None
    excluded_globs: tuple[str, ...] = (
        "*.lock",
        "*.min.js",
        "*.min.css",
        "*.map",
        "messages_*.properties",
        "chunk-*.js",
        "*Top1m*",
        "UserAgents.txt",
    )
    max_file_bytes: int = 512 * 1024


@dataclass(frozen=True)
class CodeFile:
    path: str
    absolute_path: Path
    content: str
    language: str
    sha256: str
    size_bytes: int


def _is_probably_binary(raw: bytes) -> bool:
    if not raw:
        return False
    if b"\x00" in raw[:4096]:
        return True
    text_controls = {7, 8, 9, 10, 12, 13, 27}
    sample = raw[:4096]
    control_count = sum(1 for b in sample if b < 32 and b not in text_controls)
    return control_count / len(sample) > 0.05


def _language_for(path: Path) -> str:
    if path.name.lower() in {"readme", "license", "notice", "dockerfile", "makefile"}:
        return "text"
    return LANGUAGE_BY_EXT.get(path.suffix.lower(), path.suffix.lower().lstrip(".") or "text")


def _excluded_by_glob(rel: str, patterns: tuple[str, ...]) -> bool:
    return any(fnmatch.fnmatch(rel, pat) for pat in patterns)


def scan_code_files(repo_root: Path | str, config: FileScanConfig | None = None) -> list[CodeFile]:
    """Return readable source files under ``repo_root`` with stable relative paths."""
    cfg = config or FileScanConfig()
    root = Path(repo_root).resolve()
    included = cfg.included_extensions or DEFAULT_INCLUDED_EXTENSIONS
    excluded_dirs = cfg.excluded_dirs or DEFAULT_EXCLUDED_DIRS
    files: list[CodeFile] = []

    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel_path = path.relative_to(root)
        rel = rel_path.as_posix()
        if any(part in excluded_dirs for part in rel_path.parts):
            continue
        if path.suffix.lower() not in included:
            continue
        if _excluded_by_glob(rel, cfg.excluded_globs):
            continue
        try:
            size = path.stat().st_size
        except OSError:
            continue
        if size > cfg.max_file_bytes:
            continue
        try:
            raw = path.read_bytes()
        except OSError:
            continue
        if _is_probably_binary(raw):
            continue
        text = raw.decode("utf-8", errors="replace")
        files.append(
            CodeFile(
                path=rel,
                absolute_path=path,
                content=text,
                language=_language_for(path),
                sha256=hashlib.sha256(raw).hexdigest(),
                size_bytes=size,
            )
        )
    return files
