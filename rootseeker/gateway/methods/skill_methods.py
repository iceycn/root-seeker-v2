"""Gateway business methods for skill operations."""

from __future__ import annotations

from typing import Any

from rootseeker.bootstrap import DevRuntime

__all__ = ["register_skill_methods"]


def register_skill_methods(registry: Any, runtime: DevRuntime) -> None:
    """Register skill.* gateway methods.

    Methods:
    - skill.list: List all available skills
    - skill.get: Get skill by slug
    """

    def skill_list(params: dict[str, Any]) -> dict[str, Any]:
        """List all available skills.

        Params:
            tags: Optional tag filter
        """
        tags = params.get("tags")
        skills = runtime.skill_registry.list_skills()

        items = [
            {
                "slug": s.slug,
                "name": s.name,
                "version": s.version,
                "source_kind": s.source_kind.value,
                "tags": list(s.tags) if s.tags else [],
            }
            for s in skills
        ]

        if tags:
            tag_set = set(tags) if isinstance(tags, list) else {tags}
            items = [i for i in items if tag_set & set(i.get("tags", []))]

        return {
            "items": items,
            "total": len(items),
        }

    def skill_get(params: dict[str, Any]) -> dict[str, Any]:
        """Get skill by slug.

        Params:
            slug: Skill slug
        """
        slug = str(params.get("slug", ""))
        if not slug:
            return {"error": "slug is required", "found": False}

        skill = runtime.skill_registry.get(slug)
        if skill is None:
            return {"error": f"skill not found: {slug}", "found": False}

        return {
            "found": True,
            "skill": {
                "slug": skill.slug,
                "name": skill.name,
                "version": skill.version,
                "source_kind": skill.source_kind.value,
                "tags": list(skill.tags) if skill.tags else [],
                "triggers": list(skill.triggers) if skill.triggers else [],
                "required_tools": list(skill.required_tools) if skill.required_tools else [],
                "steps": [s.model_dump(mode="json") for s in skill.steps] if skill.steps else [],
            },
        }

    registry.register("skill.list", skill_list)
    registry.register("skill.get", skill_get)
