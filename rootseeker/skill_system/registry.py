from __future__ import annotations

from pathlib import Path

from rootseeker.contracts.skill import SkillExecutionPlan, SkillKind, SkillSourceKind, SkillSpec
from rootseeker.skill_system.discovery import discover_skill_files
from rootseeker.skill_system.names import normalize_skill_name
from rootseeker.skill_system.overlay import SkillOverlayState, apply_overlay
from rootseeker.skill_system.parser import load_skill_from_path

__all__ = [
    "DEFAULT_BUILTIN_SKILL_SLUG",
    "DEFAULT_FLOW_SKILL_SLUG",
    "SkillRegistry",
    "build_registry_from_builtin_skills",
    "build_skill_registry",
    "get_default_log_triage_skill",
]

DEFAULT_FLOW_SKILL_SLUG = "default-log-triage"
DEFAULT_BUILTIN_SKILL_SLUG = DEFAULT_FLOW_SKILL_SLUG


class SkillRegistry:
    def __init__(self) -> None:
        self._by_slug: dict[str, SkillSpec] = {}
        self._tool_action_index: dict[str, str] = {}

    def register(self, spec: SkillSpec) -> None:
        key = normalize_skill_name(spec.slug)
        if key in self._by_slug:
            raise ValueError(f"Duplicate skill slug: {key}")
        self._by_slug[key] = spec
        self._index_bound_tools(spec, key)

    def upsert(self, spec: SkillSpec) -> None:
        key = normalize_skill_name(spec.slug)
        existing = self._by_slug.pop(key, None)
        if existing is not None:
            for action in existing.bound_tools:
                if self._tool_action_index.get(action) == key:
                    self._tool_action_index.pop(action, None)
        self._by_slug[key] = spec
        self._index_bound_tools(spec, key)

    def unregister(self, slug: str) -> bool:
        key = normalize_skill_name(slug)
        spec = self._by_slug.pop(key, None)
        if spec is None:
            return False
        for action in spec.bound_tools:
            if self._tool_action_index.get(action) == key:
                self._tool_action_index.pop(action, None)
        return True

    def get(self, slug: str) -> SkillSpec | None:
        return self._by_slug.get(normalize_skill_name(slug))

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

    def _index_bound_tools(self, spec: SkillSpec, key: str) -> None:
        if spec.skill_kind not in {SkillKind.TOOL, SkillKind.TOOL_GROUP}:
            return
        for action in spec.bound_tools:
            existing = self._tool_action_index.get(action)
            if existing is not None and existing != key:
                raise ValueError(
                    f"Tool action {action!r} already bound to skill {existing!r}, "
                    f"cannot bind to {key!r}"
                )
            self._tool_action_index[action] = key


def build_skill_registry(
    *,
    builtin_root: Path,
    custom_root: Path,
    external_root: Path,
    overlay: SkillOverlayState | None = None,
) -> SkillRegistry:
    registry = SkillRegistry()
    builtin_names: set[str] = set()

    for path in discover_skill_files(builtin_root):
        spec = load_skill_from_path(path, source_kind=SkillSourceKind.BUILTIN)
        name = normalize_skill_name(spec.slug)
        registry.register(spec)
        builtin_names.add(name)

    for path in discover_skill_files(custom_root):
        spec = load_skill_from_path(path, source_kind=SkillSourceKind.CUSTOM)
        name = normalize_skill_name(spec.slug)
        if name in builtin_names:
            continue
        registry.upsert(spec)

    for path in discover_skill_files(external_root):
        spec = load_skill_from_path(path, source_kind=SkillSourceKind.EXTERNAL)
        name = normalize_skill_name(spec.slug)
        if name in builtin_names:
            continue
        registry.upsert(spec)

    if overlay is not None:
        for spec in registry.list_skills():
            registry.upsert(apply_overlay(spec, overlay))

    return registry


def build_registry_from_builtin_skills(builtin_skills_root: Path) -> SkillRegistry:
    return build_skill_registry(
        builtin_root=builtin_skills_root,
        custom_root=builtin_skills_root.parent / "custom",
        external_root=builtin_skills_root.parent / "external",
        overlay=None,
    )


def get_default_log_triage_skill(registry: SkillRegistry) -> SkillSpec:
    spec = registry.get(DEFAULT_FLOW_SKILL_SLUG)
    if spec is None:
        raise ValueError(f"Builtin flow skill not found: {DEFAULT_FLOW_SKILL_SLUG}")
    return spec
