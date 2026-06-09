from __future__ import annotations

from collections.abc import Callable
from typing import Any

from rootseeker.gateway.errors import GatewayMethodNotFoundError

__all__ = ["GatewayMethod", "GatewayMethodRegistry"]

GatewayMethod = Callable[[dict[str, Any]], dict[str, Any]]


class GatewayMethodRegistry:
    def __init__(self) -> None:
        self._methods: dict[str, GatewayMethod] = {}

    def register(self, method: str, handler: GatewayMethod) -> None:
        self._methods[method] = handler

    def invoke(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        handler = self._methods.get(method)
        if handler is None:
            raise GatewayMethodNotFoundError(f"gateway method not found: {method}")
        return handler(dict(params))

    def list_methods(self) -> list[str]:
        return sorted(self._methods.keys())
