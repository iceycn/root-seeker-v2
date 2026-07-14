"""MCP tool helpers for GitNexus knowledge-graph queries."""

from __future__ import annotations

from typing import Any

from rootseeker.code_index.gitnexus_adapter import GitNexusAdapter

__all__ = [
    "graph_impact_tool",
    "graph_context_tool",
    "graph_query_tool",
    "graph_cypher_tool",
    "graph_trace_tool",
    "graph_list_repos_tool",
    "graph_detect_changes_tool",
]


def graph_impact_tool(adapter: GitNexusAdapter, args: dict[str, Any]) -> dict[str, Any]:
    return adapter.impact(
        str(args.get("symbol") or ""),
        direction=str(args.get("direction") or "upstream"),
        repo=str(args.get("repo") or "") or None,
        file=str(args.get("file") or "") or None,
        uid=str(args.get("uid") or "") or None,
        kind=str(args.get("kind") or "") or None,
    )


def graph_context_tool(adapter: GitNexusAdapter, args: dict[str, Any]) -> dict[str, Any]:
    return adapter.context(
        str(args.get("symbol") or ""),
        repo=str(args.get("repo") or "") or None,
        file=str(args.get("file") or "") or None,
        uid=str(args.get("uid") or "") or None,
    )


def graph_query_tool(adapter: GitNexusAdapter, args: dict[str, Any]) -> dict[str, Any]:
    return adapter.query(
        str(args.get("search_query") or args.get("query") or ""),
        repo=str(args.get("repo") or "") or None,
    )


def graph_cypher_tool(adapter: GitNexusAdapter, args: dict[str, Any]) -> dict[str, Any]:
    return adapter.cypher(
        str(args.get("query") or ""),
        repo=str(args.get("repo") or "") or None,
    )


def graph_trace_tool(adapter: GitNexusAdapter, args: dict[str, Any]) -> dict[str, Any]:
    return adapter.trace(
        str(args.get("source") or args.get("from") or ""),
        str(args.get("target") or args.get("to") or ""),
        repo=str(args.get("repo") or "") or None,
    )


def graph_list_repos_tool(adapter: GitNexusAdapter, args: dict[str, Any]) -> dict[str, Any]:
    limit = args.get("limit")
    offset = args.get("offset")
    return adapter.list_repos(
        limit=int(limit) if limit is not None else None,
        offset=int(offset) if offset is not None else None,
    )


def graph_detect_changes_tool(adapter: GitNexusAdapter, args: dict[str, Any]) -> dict[str, Any]:
    return adapter.detect_changes(repo=str(args.get("repo") or "") or None)
