from __future__ import annotations

import re
from collections.abc import Iterable

from rootseeker.analysis.log_text import unwrap_embedded_log_text

__all__ = [
    "extract_call_chain_summary",
    "extract_code_path",
    "extract_exception_summary",
    "merge_call_chain_summaries",
]

_JAVA_FRAME_RE = re.compile(
    r"^\s*at\s+(?P<qualified>[\w.$]+)\.(?P<method>[\w$<>]+)\((?P<location>[^)]+)\)\s*$"
)
_JAVA_EXCEPTION_RE = re.compile(r"^[\w$.]+(?:Exception|Error)\b")
_CODE_PATH_RE = re.compile(
    r"([A-Za-z0-9_./-]+\.(?:java|kt|py|go|ts|tsx|js|jsx|cs|rb|php|scala|rs|cpp|c|h))(?::\d+)?"
)
_CAUSED_BY_SPLIT_RE = re.compile(r"(?=Caused by:)")

_FRAMEWORK_PREFIXES = (
    "org.springframework.",
    "org.apache.catalina.",
    "org.apache.coyote.",
    "org.apache.tomcat.",
    "javax.servlet.",
    "java.lang.",
    "sun.reflect.",
    "com.sun.proxy.",
    "org.mybatis.",
    "org.apache.ibatis.",
    "org.apache.skywalking.",
    "jdk.internal.",
    "java.util.concurrent.",
    "java.util.Base64",
    "java.lang.Thread.",
    "com.mysql.cj.",
    "com.zaxxer.hikari.",
    "com.github.pagehelper.",
    "net.coolcollege.platform.",
    "net.coolcollege.starter.",
)

_FRAMEWORK_MARKERS = (
    "CGLIB",
    "FastClassBySpringCGLIB",
    "$$Enhancer",
    "MethodProxy",
    "DelegatingMethodAccessorImpl",
    "NativeMethodAccessorImpl",
    "GeneratedMethodAccessor",
    "InstMethodsInter",
    "auxiliary$",
    "original$",
    "accessor$",
    "ProxyPreparedStatement",
    "HikariProxy",
)

_SKIP_CODE_PATH_FILES = {
    "base64.java",
    "throwable.java",
    "exception.java",
    "thread.java",
    "class.java",
    "objects.java",
    "long.java",
    "integer.java",
    "string.java",
    "boolean.java",
    "double.java",
    "float.java",
}

_SKIP_CODE_PATH_MARKERS = (
    "springframework",
    "mybatis",
    "apache.catalina",
    "apache.tomcat",
    "apache.coyote",
    "hikari",
    "mysql.cj",
    "pagehelper",
)


def _is_framework_frame(qualified: str, method: str) -> bool:
    target = f"{qualified}.{method}"
    if any(target.startswith(prefix) for prefix in _FRAMEWORK_PREFIXES):
        return True
    if method == "doFilter" and _short_class_name(qualified).endswith("Filter"):
        return True
    return any(marker in target for marker in _FRAMEWORK_MARKERS)


def _short_class_name(qualified: str) -> str:
    return qualified.rsplit(".", 1)[-1]


def _frames_from_text(text: str) -> list[str]:
    frames: list[str] = []
    seen: set[str] = set()
    for raw_line in text.splitlines():
        match = _JAVA_FRAME_RE.match(raw_line)
        if match is None:
            continue
        qualified = match.group("qualified")
        method = match.group("method")
        location = match.group("location")
        if _is_framework_frame(qualified, method):
            continue
        short_class = _short_class_name(qualified)
        frame = f"{short_class}.{method} ({location})"
        if frame in seen:
            continue
        seen.add(frame)
        frames.append(frame)
    return frames


def extract_call_chain_summary(text: str, *, max_frames: int = 12) -> list[str]:
    """Extract application call-chain frames from Java stack traces.

    Innermost Caused-by application frames come first so callers / graph tools
    target the fault method instead of the outer wrapper.
    """
    text = unwrap_embedded_log_text(text)
    if not text:
        return []

    blocks = [part for part in _CAUSED_BY_SPLIT_RE.split(text) if part.strip()]
    ordered_blocks = list(reversed(blocks)) if len(blocks) > 1 else blocks

    frames: list[str] = []
    seen: set[str] = set()
    for block in ordered_blocks:
        for frame in _frames_from_text(block):
            if frame in seen:
                continue
            seen.add(frame)
            frames.append(frame)
            if len(frames) >= max_frames:
                return frames
    return frames


def _file_from_frame(frame: str) -> str | None:
    if "(" not in frame or ")" not in frame:
        return None
    location = frame.rsplit("(", 1)[-1].rstrip(")")
    path = location.split(":", 1)[0].strip()
    if not path or path in {"Unknown Source", "Native Method"} or path.startswith("<"):
        return None
    return path


def _is_noise_code_path(path: str) -> bool:
    normalized = path.replace("\\", "/").lower()
    name = normalized.rsplit("/", 1)[-1]
    stem, sep, ext = name.rpartition(".")
    if sep and ext in {"c", "h"} and (len(stem) <= 2 or "/" not in normalized):
        return True
    if name in _SKIP_CODE_PATH_FILES:
        return True
    if name.endswith("exception.java") or name.endswith("error.java"):
        return True
    return any(marker in normalized for marker in _SKIP_CODE_PATH_MARKERS)


def extract_code_path(text: str) -> str | None:
    """Best-effort source file for the fault, skipping logger abbreviations."""
    text = unwrap_embedded_log_text(text)
    for frame in extract_call_chain_summary(text):
        path = _file_from_frame(frame)
        if path and not _is_noise_code_path(path):
            return path
    for match in _CODE_PATH_RE.findall(str(text or "")):
        if not _is_noise_code_path(match):
            return match
    return None


def extract_exception_summary(text: str, *, max_chars: int = 500) -> str:
    text = unwrap_embedded_log_text(text)
    candidates: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("at "):
            continue
        if line.startswith("[") and "]" in line:
            continue
        if line.startswith("Caused by:"):
            line = line.removeprefix("Caused by:").strip()
        if _JAVA_EXCEPTION_RE.match(line):
            candidates.append(line)
    if not candidates:
        return ""
    # Innermost Caused-by is the fault; the first match is often a wrapper.
    return candidates[-1][:max_chars]


def merge_call_chain_summaries(*groups: Iterable[str], max_frames: int = 12) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()
    for group in groups:
        for item in group:
            value = str(item).strip()
            if not value or value in seen:
                continue
            seen.add(value)
            merged.append(value)
            if len(merged) >= max_frames:
                return merged
    return merged
