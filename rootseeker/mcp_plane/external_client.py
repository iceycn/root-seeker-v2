from __future__ import annotations

from collections.abc import Callable
from typing import Any

from rootseeker.contracts.tool import ToolSpec

__all__ = ["ExternalInvoker", "McpExternalClient"]

ExternalInvoker = Callable[[str, dict[str, Any]], dict[str, Any]]


class McpExternalClient:
    def __init__(self) -> None:
        self._invokers: dict[str, ExternalInvoker] = {}

    def register_server(self, server_name: str, invoker: ExternalInvoker) -> None:
        self._invokers[server_name] = invoker

    def invoke(self, spec: ToolSpec, arguments: dict[str, Any]) -> dict[str, Any]:
        invoker = self._invokers.get(spec.server_name)
        if invoker is None:
            raise RuntimeError(f"external server not configured: {spec.server_name}")
        return invoker(spec.name, dict(arguments))
