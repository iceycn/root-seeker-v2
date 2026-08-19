"""Resolve which MCP tools are available to skills and the agent planner."""

from __future__ import annotations

from rootseeker.contracts.skill import SkillSpec
from rootseeker.contracts.tool import ToolPermissionLevel, ToolScope, ToolSpec
from rootseeker.mcp_plane.registry import ToolRegistry

__all__ = [
    "list_external_tool_specs",
    "resolve_planner_tools",
    "skill_allows_external_mcp",
]


def skill_allows_external_mcp(skill: SkillSpec | None) -> bool:
    if skill is None:
        return False
    if bool(skill.metadata.get("allow_external_mcp")):
        return True
    return "mcp" in {str(tag).strip().lower() for tag in skill.tags}


def list_external_tool_specs(registry: ToolRegistry) -> list[ToolSpec]:
    return [
        spec
        for spec in registry.list_specs()
        if spec.scope == ToolScope.EXTERNAL
    ]


def resolve_planner_tools(
    registry: ToolRegistry,
    skill: SkillSpec | None,
    *,
    allow_write_tools: bool = False,
) -> list[ToolSpec]:
    if skill is None:
        specs = list(registry.list_specs())
    elif skill_allows_external_mcp(skill):
        internal_names = _internal_tool_names_for_skill(skill)
        specs = [
            spec
            for spec in registry.list_specs()
            if spec.scope == ToolScope.EXTERNAL or spec.name in internal_names
        ]
    else:
        internal_names = _internal_tool_names_for_skill(skill)
        specs = [
            spec
            for spec in registry.list_specs()
            if spec.scope != ToolScope.EXTERNAL and spec.name in internal_names
        ]
        if not specs:
            specs = [
                spec
                for spec in registry.list_specs()
                if spec.scope != ToolScope.EXTERNAL
            ]
    if allow_write_tools:
        return specs
    return [spec for spec in specs if spec.permission_level == ToolPermissionLevel.READ]


def _internal_tool_names_for_skill(skill: SkillSpec) -> set[str]:
    names = {str(name).strip() for name in skill.required_tools if str(name).strip()}
    names.update(str(step.action).strip() for step in skill.steps if str(step.action).strip())
    names.update(str(name).strip() for name in skill.bound_tools if str(name).strip())
    return names
