"""Merge Admin advanced-settings env vars into MCP stdio process env."""

from __future__ import annotations

from typing import Any

__all__ = ["MCP_ENV_SCOPES", "env_from_admin_items", "merge_stdio_env"]

MCP_ENV_SCOPES = frozenset({"mcp", "runtime"})


def env_from_admin_items(items: list[dict[str, Any]] | None) -> dict[str, str]:
    """Pick env vars that MCP subprocesses should inherit.

    Advanced-settings scopes:
    - ``runtime``: shared by Skill and MCP
    - ``mcp``: MCP subprocesses only
    - ``skill``: excluded here
    """
    result: dict[str, str] = {}
    for item in items or []:
        if not isinstance(item, dict):
            continue
        scope = str(item.get("scope") or "runtime").strip().lower() or "runtime"
        if scope not in MCP_ENV_SCOPES:
            continue
        key = str(item.get("key") or "").strip()
        if not key:
            continue
        result[key] = str(item.get("value") or "")
    return result


def merge_stdio_env(
    *,
    extra_env: dict[str, str] | None = None,
    server_env: dict[str, str] | None = None,
) -> dict[str, str]:
    """Process inherits extra (admin) env, then per-server JSON env overrides."""
    merged: dict[str, str] = {}
    for source in (extra_env, server_env):
        if not source:
            continue
        for key, value in source.items():
            name = str(key).strip()
            if not name:
                continue
            merged[name] = str(value)
    return merged
