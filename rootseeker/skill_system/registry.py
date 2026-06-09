from __future__ import annotations

from pathlib import Path

from rootseeker.contracts.skill import SkillExecutionPlan, SkillSpec
from rootseeker.skill_system.discovery import discover_skill_files
from rootseeker.skill_system.parser import load_skill_from_path

__all__ = [
    "DEFAULT_BUILTIN_SKILL_SLUG",
    "SkillRegistry",
    "build_registry_from_builtin_skills",
    "get_default_log_triage_skill",
]

DEFAULT_BUILTIN_SKILL_SLUG = "base/default-log-triage"


class SkillRegistry:
    def __init__(self) -> None:
        self._by_slug: dict[str, SkillSpec] = {}

    def register(self, spec: SkillSpec) -> None:
        if spec.slug in self._by_slug:
            raise ValueError(f"Duplicate skill slug: {spec.slug}")
        self._by_slug[spec.slug] = spec

    def upsert(self, spec: SkillSpec) -> None:
        self._by_slug[spec.slug] = spec

    def unregister(self, slug: str) -> bool:
        return self._by_slug.pop(slug, None) is not None

    def get(self, slug: str) -> SkillSpec | None:
        return self._by_slug.get(slug)

    def list_skills(self) -> list[SkillSpec]:
        return list(self._by_slug.values())

    def execution_plan(self, slug: str) -> SkillExecutionPlan | None:
        spec = self.get(slug)
        if spec is None:
            return None
        return SkillExecutionPlan(skill_slug=spec.slug, steps=list(spec.steps))


def build_registry_from_builtin_skills(builtin_skills_root: Path) -> SkillRegistry:
    registry = SkillRegistry()
    for path in discover_skill_files(builtin_skills_root):
        registry.register(load_skill_from_path(path))
    return registry


def get_default_log_triage_skill(registry: SkillRegistry) -> SkillSpec:
    spec = registry.get(DEFAULT_BUILTIN_SKILL_SLUG)
    if spec is None:
        raise ValueError(f"Builtin skill not found: {DEFAULT_BUILTIN_SKILL_SLUG}")
    return spec
