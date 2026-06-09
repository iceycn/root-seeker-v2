from __future__ import annotations

from pydantic import Field

from rootseeker.contracts.common import RootSeekerModel
from rootseeker.contracts.plugin import PluginKind

__all__ = ["RegisteredCapability"]


class RegisteredCapability(RootSeekerModel):
    capability_id: str = Field(min_length=1)
    plugin_id: str = Field(min_length=1)
    kind: PluginKind
    is_mcp_tool: bool = Field(
        default=False,
        description="True when this id is an MCP tool name exposed by the plugin",
    )
