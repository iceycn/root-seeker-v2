from __future__ import annotations

from collections.abc import Callable
from typing import Any

from rootseeker.contracts.tool import ToolScope, ToolSpec

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

    def unregister(self, tool_name: str) -> bool:
        if tool_name not in self._specs:
            return False
        del self._specs[tool_name]
        self._handlers.pop(tool_name, None)
        return True

    def unregister_by_server(self, server_name: str) -> list[str]:
        removed: list[str] = []
        for name, spec in list(self._specs.items()):
            if spec.server_name == server_name and spec.scope == ToolScope.EXTERNAL:
                if self.unregister(name):
                    removed.append(name)
        return removed
