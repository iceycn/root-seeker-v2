"""Tests for MCP tool resolution helpers."""

from __future__ import annotations

from rootseeker.contracts.skill import SkillKind, SkillSpec, SkillStepDefinition
from rootseeker.contracts.tool import ToolPermissionLevel, ToolScope, ToolSpec
from rootseeker.mcp_plane.registry import ToolRegistry
from rootseeker.mcp_plane.tool_resolution import (
    list_external_tool_specs,
    resolve_planner_tools,
    skill_allows_external_mcp,
)


def test_skill_allows_external_mcp_from_metadata() -> None:
    skill = SkillSpec(
        name="flow",
        slug="flows/test",
        skill_kind=SkillKind.FLOW,
        metadata={"allow_external_mcp": True},
    )
    assert skill_allows_external_mcp(skill) is True


def test_resolve_planner_tools_includes_external_when_allowed() -> None:
    registry = ToolRegistry()
    registry.register(
        ToolSpec(
            name="incident.normalize",
            description="",
            server_name="internal",
            permission_level=ToolPermissionLevel.READ,
        ),
        lambda _args: {},
    )
    registry.register_external(
        ToolSpec(
            name="ext.server.echo",
            description="echo",
            permission_level=ToolPermissionLevel.READ,
            scope=ToolScope.EXTERNAL,
            server_name="server",
        )
    )
    skill = SkillSpec(
        name="flow",
        slug="flows/test",
        skill_kind=SkillKind.FLOW,
        required_tools=["incident.normalize"],
        metadata={"allow_external_mcp": True},
        steps=[
            SkillStepDefinition(
                step_id="s1",
                name="normalize",
                action="incident.normalize",
            )
        ],
    )
    names = {spec.name for spec in resolve_planner_tools(registry, skill)}
    assert "incident.normalize" in names
    assert "ext.server.echo" in names


def test_list_external_tool_specs() -> None:
    registry = ToolRegistry()
    registry.register_external(
        ToolSpec(
            name="ext.plantuml.generate",
            description="",
            server_name="plantuml",
            permission_level=ToolPermissionLevel.READ,
            scope=ToolScope.EXTERNAL,
        )
    )
    assert len(list_external_tool_specs(registry)) == 1
