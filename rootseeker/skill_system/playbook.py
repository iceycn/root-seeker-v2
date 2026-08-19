from __future__ import annotations

from typing import Any

from rootseeker.contracts.case import CaseCreateRequest
from rootseeker.contracts.skill import SkillSourceKind, SkillSpec
from rootseeker.skill_system.errors import SkillError
from rootseeker.skill_system.names import normalize_skill_name
from rootseeker.skill_system.overlay import SkillOverlayState, apply_overlay
from rootseeker.skill_system.registry import SkillRegistry

__all__ = ["DEFAULT_PLAYBOOK_NAME", "PlaybookResolver"]

DEFAULT_PLAYBOOK_NAME = "default-log-triage"
_USER_SOURCE_KINDS = {SkillSourceKind.CUSTOM, SkillSourceKind.EXTERNAL}


class PlaybookResolver:
    def __init__(
        self,
        registry: SkillRegistry,
        overlay: SkillOverlayState | None = None,
    ) -> None:
        self.registry = registry
        self._overlay = overlay if overlay is not None else SkillOverlayState()

    def resolve(self, case_request: CaseCreateRequest) -> SkillSpec:
        seen: set[str] = set()
        for name in self._resolve_candidates(case_request):
            if name in seen:
                continue
            seen.add(name)
            spec = self._usable_playbook(name)
            if spec is not None:
                return spec
        raise SkillError("SKILL_DEFAULT_UNAVAILABLE", "no enabled playbook available")

    def set_default(self, name: str) -> SkillOverlayState:
        name = normalize_skill_name(name)
        spec = self.registry.get(name)
        if spec is None or self.effective_role(spec) != "playbook":
            raise SkillError("SKILL_NOT_PLAYBOOK", f"skill is not a playbook: {name}")
        if not self._is_enabled(spec):
            raise SkillError("SKILL_DEFAULT_UNAVAILABLE", f"playbook is disabled: {name}")
        self._overlay.default_playbook = name
        return self._overlay

    def set_enabled(self, name: str, enabled: bool) -> SkillOverlayState:
        name = normalize_skill_name(name)
        spec = self.registry.get(name)
        if spec is None:
            raise SkillError("SKILL_DEFAULT_UNAVAILABLE", f"skill not found: {name}")
        if not enabled and self._is_current_default(name):
            self._require_builtin_fallback(disabled_name=name)
            self._write_enabled(name, False)
            self._overlay.default_playbook = DEFAULT_PLAYBOOK_NAME
            return self._overlay
        self._write_enabled(name, enabled)
        return self._overlay

    def delete_user_skill(self, name: str) -> SkillOverlayState:
        name = normalize_skill_name(name)
        spec = self.registry.get(name)
        if spec is None:
            return self._overlay
        if spec.source_kind not in _USER_SOURCE_KINDS:
            raise SkillError("SKILL_BUILTIN_PROTECTED", f"cannot delete builtin skill: {name}")
        if self._is_current_default(name):
            self._require_builtin_fallback(disabled_name=name)
            self._overlay.default_playbook = DEFAULT_PLAYBOOK_NAME
        self.registry.unregister(name)
        self._overlay.overlays.pop(name, None)
        return self._overlay

    def effective_role(self, spec: SkillSpec) -> str:
        name = normalize_skill_name(spec.name)
        entry = self._overlay.overlays.get(name) or {}
        role = entry.get("role") or spec.metadata.get("role") or "helper"
        return str(role)

    def _resolve_candidates(self, case_request: CaseCreateRequest) -> list[str]:
        names: list[str] = []
        preferred = self._preferred_name(case_request)
        if preferred:
            names.append(preferred)
        default = normalize_skill_name(self._overlay.default_playbook)
        if default:
            names.append(default)
        names.append(DEFAULT_PLAYBOOK_NAME)
        return names

    def _preferred_name(self, case_request: CaseCreateRequest) -> str | None:
        metadata = case_request.metadata or {}
        preferred = metadata.get("preferred_skill") or metadata.get("skill_slug")
        if isinstance(preferred, str) and preferred.strip():
            return normalize_skill_name(preferred)
        selected = metadata.get("selected_skills")
        if isinstance(selected, list) and selected:
            first = selected[0]
            if isinstance(first, str) and first.strip():
                return normalize_skill_name(first)
        return None

    def _usable_playbook(self, name: str) -> SkillSpec | None:
        spec = self.registry.get(name)
        if spec is None:
            return None
        if not self._is_enabled(spec):
            return None
        if self.effective_role(spec) != "playbook":
            return None
        return spec

    def _is_enabled(self, spec: SkillSpec) -> bool:
        name = normalize_skill_name(spec.name)
        entry = self._overlay.overlays.get(name)
        if entry is not None and "enabled" in entry:
            return bool(entry["enabled"])
        return spec.metadata.get("enabled", True) is not False

    def _is_current_default(self, name: str) -> bool:
        return name == normalize_skill_name(self._overlay.default_playbook)

    def _can_fallback_to_builtin(self, *, disabled_name: str) -> bool:
        if normalize_skill_name(disabled_name) == DEFAULT_PLAYBOOK_NAME:
            return False
        spec = self.registry.get(DEFAULT_PLAYBOOK_NAME)
        if spec is None:
            return False
        return self._is_enabled(spec) and self.effective_role(spec) == "playbook"

    def _require_builtin_fallback(self, *, disabled_name: str) -> None:
        if self._can_fallback_to_builtin(disabled_name=disabled_name):
            return
        raise SkillError(
            "SKILL_DEFAULT_REQUIRED",
            "cannot remove the current default playbook without an enabled builtin fallback",
        )

    def _write_enabled(self, name: str, enabled: bool) -> None:
        entry: dict[str, Any] = self._overlay.overlays.setdefault(name, {})
        entry["enabled"] = enabled
        spec = self.registry.get(name)
        if spec is not None:
            self.registry.upsert(apply_overlay(spec, self._overlay))
