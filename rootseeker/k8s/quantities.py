"""Parse and format Kubernetes resource quantities."""

from __future__ import annotations

import re

__all__ = ["format_bytes", "format_cores", "parse_bytes", "parse_cpu_cores"]

_NUMBER = re.compile(r"^([0-9]*\.?[0-9]+)([A-Za-z]*)$")

_CPU_SCALE = {
    "n": 1e-9,
    "u": 1e-6,
    "m": 1e-3,
    "": 1.0,
    "k": 1e3,
    "M": 1e6,
    "G": 1e9,
}

_BYTE_SCALE = {
    "": 1.0,
    "Ki": 1024.0,
    "Mi": 1024.0**2,
    "Gi": 1024.0**3,
    "Ti": 1024.0**4,
    "Pi": 1024.0**5,
    "Ei": 1024.0**6,
    "k": 1000.0,
    "K": 1000.0,
    "M": 1000.0**2,
    "G": 1000.0**3,
    "T": 1000.0**4,
    "P": 1000.0**5,
    "E": 1000.0**6,
    "m": 0.001,
}


def parse_cpu_cores(raw: object) -> float | None:
    """Convert a Kubernetes CPU quantity to cores."""
    if raw is None or isinstance(raw, bool) or raw == "":
        return None
    if isinstance(raw, (int, float)):
        return float(raw)
    match = _NUMBER.fullmatch(str(raw).strip())
    if match is None:
        return None
    scale = _CPU_SCALE.get(match.group(2))
    if scale is None:
        return None
    return float(match.group(1)) * scale


def parse_bytes(raw: object) -> int | None:
    """Convert a Kubernetes memory/storage quantity to bytes."""
    if raw is None or isinstance(raw, bool) or raw == "":
        return None
    if isinstance(raw, int):
        return raw
    if isinstance(raw, float):
        return int(raw)
    match = _NUMBER.fullmatch(str(raw).strip())
    if match is None:
        return None
    scale = _BYTE_SCALE.get(match.group(2))
    if scale is None:
        return None
    return int(float(match.group(1)) * scale)


def format_cores(value: float | None) -> str:
    if value is None:
        return "未知"
    if abs(value) < 1:
        return f"{value * 1000:.0f}m"
    return f"{value:.2f}"


def format_bytes(value: int | float | None) -> str:
    if value is None:
        return "未知"
    size = float(value)
    for unit in ("B", "Ki", "Mi", "Gi", "Ti"):
        if size < 1024 or unit == "Ti":
            if unit == "B":
                return f"{int(size)}B"
            return f"{size:.1f}{unit}"
        size /= 1024
    return f"{int(value)}B"
