from __future__ import annotations

from pathlib import Path

from rootseeker.contracts.skill import SkillExecutionPlan, SkillKind, SkillSpec
from rootseeker.skill_system.discovery import discover_skill_files
from rootseeker.skill_system.parser import load_skill_from_path

__all__ = [
    "DEFAULT_BUILTIN_SKILL_SLUG",
    "DEFAULT_FLOW_SKILL_SLUG",
    "SkillRegistry",
    "build_registry_from_builtin_skills",
    "get_default_log_triage_skill",
]

DEFAULT_FLOW_SKILL_SLUG = "flows/default-log-triage"
DEFAULT_BUILTIN_SKILL_SLUG = DEFAULT_FLOW_SKILL_SLUG


class SkillRegistry:
    def __init__(self) -> None:
        self._by_slug: dict[str, SkillSpec] = {}
        self._tool_action_index: dict[str, str] = {}

    def register(self, spec: SkillSpec) -> None:
        if spec.slug in self._by_slug:
            raise ValueError(f"Duplicate skill slug: {spec.slug}")
        self._by_slug[spec.slug] = spec
        self._index_bound_tools(spec)

    def upsert(self, spec: SkillSpec) -> None:
        existing = self._by_slug.pop(spec.slug, None)
        if existing is not None:
            for action in existing.bound_tools:
                if self._tool_action_index.get(action) == spec.slug:
                    self._tool_action_index.pop(action, None)
        self._by_slug[spec.slug] = spec
        self._index_bound_tools(spec)

    def unregister(self, slug: str) -> bool:
        spec = self._by_slug.pop(slug, None)
        if spec is None:
            return False
        for action in spec.bound_tools:
            if self._tool_action_index.get(action) == slug:
                self._tool_action_index.pop(action, None)
        return True

    def get(self, slug: str) -> SkillSpec | None:
        return self._by_slug.get(slug)

    def list_skills(self) -> list[SkillSpec]:
        return list(self._by_slug.values())

    def list_by_kind(self, kind: SkillKind) -> list[SkillSpec]:
        return [spec for spec in self._by_slug.values() if spec.skill_kind == kind]

    def resolve_tool_skill(self, action: str) -> SkillSpec | None:
        slug = self._tool_action_index.get(action)
        if slug is None:
            return None
        return self.get(slug)

    def execution_plan(self, slug: str) -> SkillExecutionPlan | None:
        spec = self.get(slug)
        if spec is None:
            return None
        return SkillExecutionPlan(skill_slug=spec.slug, steps=list(spec.steps))

    def _index_bound_tools(self, spec: SkillSpec) -> None:
        if spec.skill_kind not in {SkillKind.TOOL, SkillKind.TOOL_GROUP}:
            return
        for action in spec.bound_tools:
            existing = self._tool_action_index.get(action)
            if existing is not None and existing != spec.slug:
                raise ValueError(
                    f"Tool action {action!r} already bound to skill {existing!r}, "
                    f"cannot bind to {spec.slug!r}"
                )
            self._tool_action_index[action] = spec.slug


def build_registry_from_builtin_skills(builtin_skills_root: Path) -> SkillRegistry:
    registry = SkillRegistry()
    for path in discover_skill_files(builtin_skills_root):
        registry.register(load_skill_from_path(path))
    return registry


def get_default_log_triage_skill(registry: SkillRegistry) -> SkillSpec:
    spec = registry.get(DEFAULT_FLOW_SKILL_SLUG)
    if spec is None:
        raise ValueError(f"Builtin flow skill not found: {DEFAULT_FLOW_SKILL_SLUG}")
    return spec
