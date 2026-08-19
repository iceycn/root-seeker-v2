"""Gateway business methods for skill operations."""

from __future__ import annotations

from typing import Any

from rootseeker.bootstrap import DevRuntime
from rootseeker.contracts.skill import SkillSourceKind
from rootseeker.skill_system.errors import SkillError
from rootseeker.skill_system.installer import install_from_source
from rootseeker.skill_system.names import normalize_skill_name
from rootseeker.skill_system.overlay import SkillOverlayState
from rootseeker.skill_system.playbook import PlaybookResolver

__all__ = ["register_skill_methods"]


def _resolver(runtime: DevRuntime) -> PlaybookResolver:
    overlay = runtime.skill_overlay
    if overlay is None:
        overlay = SkillOverlayState()
        runtime.skill_overlay = overlay
    return PlaybookResolver(runtime.skill_registry, overlay=overlay)


def _skill_name(params: dict[str, Any]) -> str:
    return normalize_skill_name(str(params.get("name") or params.get("slug") or ""))


def _install_name_sets(runtime: DevRuntime) -> tuple[set[str], set[str]]:
    builtin_names: set[str] = set()
    existing_names: set[str] = set()
    for spec in runtime.skill_registry.list_skills():
        name = normalize_skill_name(spec.name)
        existing_names.add(name)
        if spec.source_kind == SkillSourceKind.BUILTIN:
            builtin_names.add(name)
    return builtin_names, existing_names


def _skill_error(exc: SkillError) -> dict[str, Any]:
    return {"ok": False, "code": exc.code, "message": str(exc), "error": str(exc)}


def register_skill_methods(registry: Any, runtime: DevRuntime) -> None:
    """Register skill.* gateway methods.

    Methods:
    - skill.list: List all available skills
    - skill.get: Get skill by slug/name
    - skill.install: Install from local path, zip, or git URL
    - skill.set_default: Set the default playbook
    - skill.set_role: Overlay-only playbook/helper role
    - skill.enable / skill.disable: Overlay enabled flag
    """

    def skill_list(params: dict[str, Any]) -> dict[str, Any]:
        tags = params.get("tags")
        resolver = _resolver(runtime)
        items = [resolver.public_item(spec) for spec in runtime.skill_registry.list_skills()]
        if tags:
            tag_set = set(tags) if isinstance(tags, list) else {tags}
            items = [item for item in items if tag_set & set(item.get("tags", []))]
        return {"items": items, "total": len(items)}

    def skill_get(params: dict[str, Any]) -> dict[str, Any]:
        name = _skill_name(params)
        if not name:
            return {"error": "slug is required", "found": False}
        skill = runtime.skill_registry.get(name)
        if skill is None:
            return {"error": f"skill not found: {name}", "found": False}
        return {"found": True, "skill": _resolver(runtime).public_item(skill)}

    def skill_install(params: dict[str, Any]) -> dict[str, Any]:
        source = str(params.get("source") or "").strip()
        if not source:
            return {"ok": False, "code": "SKILL_INVALID_PACKAGE", "message": "source is required"}
        overwrite = bool(params.get("overwrite", False))
        only_name = params.get("only_name")
        only = str(only_name).strip() if isinstance(only_name, str) and only_name.strip() else None
        builtin_names, existing_names = _install_name_sets(runtime)
        external_root = runtime.skill_external_root or (runtime.repo_root / "skills" / "external")
        try:
            names = install_from_source(
                source,
                external_root=external_root,
                builtin_names=builtin_names,
                existing_names=existing_names,
                overwrite=overwrite,
                only_name=only,
            )
        except SkillError as exc:
            return _skill_error(exc)
        runtime.reload_skill_registry()
        resolver = _resolver(runtime)
        items = [
            resolver.public_item(spec)
            for spec in runtime.skill_registry.list_skills()
            if spec.name in names
        ]
        return {"ok": True, "installed": names, "items": items}

    def skill_set_default(params: dict[str, Any]) -> dict[str, Any]:
        name = _skill_name(params)
        if not name:
            return {"ok": False, "code": "SKILL_INVALID_PACKAGE", "message": "slug is required"}
        try:
            overlay = _resolver(runtime).set_default(name)
        except SkillError as exc:
            return _skill_error(exc)
        runtime.skill_overlay = overlay
        runtime.persist_skill_overlay()
        return {"ok": True, "default_playbook": overlay.default_playbook}

    def skill_set_role(params: dict[str, Any]) -> dict[str, Any]:
        name = _skill_name(params)
        if not name:
            return {"ok": False, "code": "SKILL_INVALID_PACKAGE", "message": "slug is required"}
        role = str(params.get("role") or "").strip()
        try:
            overlay = _resolver(runtime).set_role(name, role)
        except SkillError as exc:
            return _skill_error(exc)
        runtime.skill_overlay = overlay
        runtime.persist_skill_overlay()
        return {"ok": True, "name": name, "role": role}

    def skill_enable(params: dict[str, Any]) -> dict[str, Any]:
        name = _skill_name(params)
        if not name:
            return {"ok": False, "code": "SKILL_INVALID_PACKAGE", "message": "slug is required"}
        try:
            overlay = _resolver(runtime).set_enabled(name, True)
        except SkillError as exc:
            return _skill_error(exc)
        runtime.skill_overlay = overlay
        runtime.persist_skill_overlay()
        return {"ok": True, "name": name, "enabled": True}

    def skill_disable(params: dict[str, Any]) -> dict[str, Any]:
        name = _skill_name(params)
        if not name:
            return {"ok": False, "code": "SKILL_INVALID_PACKAGE", "message": "slug is required"}
        try:
            overlay = _resolver(runtime).set_enabled(name, False)
        except SkillError as exc:
            return _skill_error(exc)
        runtime.skill_overlay = overlay
        runtime.persist_skill_overlay()
        return {"ok": True, "name": name, "enabled": False}

    registry.register("skill.list", skill_list)
    registry.register("skill.get", skill_get)
    registry.register("skill.install", skill_install)
    registry.register("skill.set_default", skill_set_default)
    registry.register("skill.set_role", skill_set_role)
    registry.register("skill.enable", skill_enable)
    registry.register("skill.disable", skill_disable)
