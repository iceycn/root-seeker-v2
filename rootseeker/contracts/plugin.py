from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import Field

from rootseeker.contracts.common import RootSeekerModel

__all__ = ["PluginKind", "PluginManifest"]


class PluginKind(StrEnum):
    FLOW = "flow"
    CONNECTOR = "connector"
    CHANNEL = "channel"
    POLICY = "policy"


class PluginManifest(RootSeekerModel):
    plugin_id: str = Field(min_length=1)
    kind: PluginKind
    version: str = Field(default="0.1.0", min_length=1)
    display_name: str = ""
    description: str = ""
    enabled_by_default: bool = True
    capabilities: list[str] = Field(default_factory=list)
    mcp_tools: list[str] = Field(default_factory=list, description="Tool names this plugin registers")
    entry_point: str | None = Field(default=None, description="Importable module or package path")
    config_schema: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
