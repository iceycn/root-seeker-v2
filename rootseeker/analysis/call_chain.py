from __future__ import annotations

import re
from collections.abc import Iterable

__all__ = ["extract_call_chain_summary", "extract_exception_summary", "merge_call_chain_summaries"]

_JAVA_FRAME_RE = re.compile(
    r"^\s*at\s+(?P<qualified>[\w.$]+)\.(?P<method>[\w$<>]+)\((?P<location>[^)]+)\)\s*$"
)
_JAVA_EXCEPTION_RE = re.compile(r"^[\w$.]+(?:Exception|Error)\b")

_FRAMEWORK_PREFIXES = (
    "org.springframework.",
    "org.apache.catalina.",
    "org.apache.coyote.",
    "org.apache.tomcat.",
    "javax.servlet.",
    "java.lang.reflect.",
    "sun.reflect.",
    "com.sun.proxy.",
    "org.mybatis.",
    "org.apache.ibatis.",
    "org.apache.skywalking.",
    "jdk.internal.",
    "java.util.concurrent.",
    "java.lang.Thread.",
    "com.mysql.cj.",
    "com.zaxxer.hikari.",
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


def _is_framework_frame(qualified: str, method: str) -> bool:
    target = f"{qualified}.{method}"
    if any(target.startswith(prefix) for prefix in _FRAMEWORK_PREFIXES):
        return True
    if method == "doFilter" and _short_class_name(qualified).endswith("Filter"):
        return True
    return any(marker in target for marker in _FRAMEWORK_MARKERS)


def _short_class_name(qualified: str) -> str:
    return qualified.rsplit(".", 1)[-1]


def extract_call_chain_summary(text: str, *, max_frames: int = 12) -> list[str]:
    """Extract application call-chain frames from Java stack traces."""
    if not text:
        return []

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
        if len(frames) >= max_frames:
            break

    return frames


def extract_exception_summary(text: str, *, max_chars: int = 500) -> str:
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
    return candidates[0][:max_chars] if candidates else ""


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
