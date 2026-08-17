"""Gateway system methods."""

from __future__ import annotations

from typing import Any

from rootseeker.bootstrap import DevRuntime

__all__ = ["register_system_methods"]


def register_system_methods(registry: Any, runtime: DevRuntime) -> None:
    def list_presence(_params: dict[str, Any]) -> dict[str, Any]:
        nodes = runtime.presence_registry.list_nodes()
        return {
            "items": [
                {
                    "node_id": node.node_id,
                    "role": node.role,
                    "last_seen_at": node.last_seen_at.isoformat(),
                    "metadata": dict(node.metadata),
                }
                for node in nodes
            ],
            "total": len(nodes),
        }

    registry.register("system.list_presence", list_presence)
