from __future__ import annotations

from collections.abc import Callable
from typing import Any

from rootseeker.contracts.tool import ToolSpec

__all__ = ["ToolHandler", "ToolRegistry"]

ToolHandler = Callable[[dict[str, Any]], dict[str, Any]]


class ToolRegistry:
    """Registers ToolSpec + synchronous handler for internal MCP tools."""

    def __init__(self) -> None:
        self._specs: dict[str, ToolSpec] = {}
        self._handlers: dict[str, ToolHandler] = {}

    def register(self, spec: ToolSpec, handler: ToolHandler) -> None:
        if spec.name in self._specs:
            raise ValueError(f"Tool already registered: {spec.name}")
        self._specs[spec.name] = spec
        self._handlers[spec.name] = handler

    def register_external(self, spec: ToolSpec) -> None:
        if spec.name in self._specs:
            raise ValueError(f"Tool already registered: {spec.name}")
        self._specs[spec.name] = spec

    def get_spec(self, tool_name: str) -> ToolSpec | None:
        return self._specs.get(tool_name)

    def get_handler(self, tool_name: str) -> ToolHandler | None:
        return self._handlers.get(tool_name)

    def list_specs(self) -> list[ToolSpec]:
        return list(self._specs.values())

    def known_tools(self) -> frozenset[str]:
        return frozenset(self._specs.keys())
