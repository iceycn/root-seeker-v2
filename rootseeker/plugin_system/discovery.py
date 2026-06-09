from __future__ import annotations

from pathlib import Path

__all__ = ["discover_bundled_plugin_manifests", "DEFAULT_MANIFEST_NAME"]


DEFAULT_MANIFEST_NAME = "plugin.yaml"


def discover_bundled_plugin_manifests(builtin_root: Path) -> list[Path]:
    """Return sorted paths to ``plugin.yaml`` under ``builtin_root/<plugin>/``."""
    if not builtin_root.is_dir():
        return []
    out: list[Path] = []
    for child in sorted(builtin_root.iterdir()):
        if not child.is_dir():
            continue
        candidate = child / DEFAULT_MANIFEST_NAME
        if candidate.is_file():
            out.append(candidate)
    return out
