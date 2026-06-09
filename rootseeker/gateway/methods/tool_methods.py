"""Gateway business methods for tool operations."""

from __future__ import annotations

from typing import Any

from rootseeker.bootstrap import DevRuntime
from rootseeker.contracts.tool import ToolCallRequest

__all__ = ["register_tool_methods"]


def register_tool_methods(registry: Any, runtime: DevRuntime) -> None:
    """Register tool.* gateway methods.

    Methods:
    - tool.invoke: Invoke an MCP tool
    - tool.list: List available tools
    """

    def tool_invoke(params: dict[str, Any]) -> dict[str, Any]:
        """Invoke an MCP tool.

        Params:
            tool_name: Tool name to invoke
            arguments: Tool arguments
            case_id: Optional case ID
            step_id: Optional step ID
        """
        tool_name = str(params.get("tool_name", ""))
        if not tool_name:
            return {"error": "tool_name is required", "ok": False}

        arguments = dict(params.get("arguments", {}))
        case_id = str(params.get("case_id", "gateway-case"))
        step_id = str(params.get("step_id", "gateway-step"))

        req = ToolCallRequest(
            case_id=case_id,
            step_id=step_id,
            skill_name="gateway",
            tool_name=tool_name,
            arguments=arguments,
        )

        result = runtime.gateway.invoke(req, plugin_id="gateway", actor="gateway-method")

        return {
            "ok": result.ok,
            "tool_name": tool_name,
            "content": result.content,
            "error": result.error,
        }

    def tool_list(params: dict[str, Any]) -> dict[str, Any]:
        """List available tools.

        Params:
            tags: Optional tag filter
        """
        tags = params.get("tags")
        specs = runtime.tool_registry.list_specs()

        items = [
            {
                "name": s.name,
                "description": s.description,
                "server_name": s.server_name,
                "scope": s.scope.value,
                "tags": list(s.tags) if s.tags else [],
            }
            for s in specs
        ]

        if tags:
            tag_set = set(tags) if isinstance(tags, list) else {tags}
            items = [i for i in items if tag_set & set(i.get("tags", []))]

        return {
            "items": items,
            "total": len(items),
        }

    registry.register("tool.invoke", tool_invoke)
    registry.register("tool.list", tool_list)
