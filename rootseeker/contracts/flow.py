from __future__ import annotations

from typing import Any

from pydantic import Field

from rootseeker.contracts.common import RootSeekerModel

__all__ = ["FlowStepSpec", "FlowSpec"]


class FlowStepSpec(RootSeekerModel):
    """One step in a bundled flow: capability name routed to MCP via plugin wiring."""

    step_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    capability: str = Field(
        min_length=1,
        description="Logical capability id, often maps 1:1 to an MCP tool name",
    )
    inputs: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class FlowSpec(RootSeekerModel):
    flow_id: str = Field(min_length=1)
    plugin_id: str = Field(min_length=1, description="Bundled flow plugin that owns this spec")
    skill_slug: str = Field(min_length=1)
    steps: list[FlowStepSpec] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
