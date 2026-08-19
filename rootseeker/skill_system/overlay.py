from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from rootseeker.contracts.skill import SkillSpec
from rootseeker.skill_system.names import normalize_skill_name

__all__ = [
    "SkillOverlayState",
    "apply_overlay",
    "normalize_overlay_payload",
]


@dataclass
class SkillOverlayState:
    default_playbook: str = "default-log-triage"
    overlays: dict[str, dict[str, Any]] = field(default_factory=dict)


def normalize_overlay_payload(raw: dict[str, Any] | None) -> SkillOverlayState:
    data = dict(raw or {})
    default = normalize_skill_name(str(data.get("default_playbook") or "default-log-triage"))
    mapped: dict[str, dict[str, Any]] = {}
    for key, value in dict(data.get("overlays") or {}).items():
        mapped[normalize_skill_name(str(key))] = dict(value or {})
    return SkillOverlayState(default_playbook=default, overlays=mapped)


def apply_overlay(spec: SkillSpec, overlay: SkillOverlayState) -> SkillSpec:
    entry = overlay.overlays.get(normalize_skill_name(spec.slug))
    if not entry:
        return spec
    meta = dict(spec.metadata)
    if "enabled" in entry:
        meta["enabled"] = entry["enabled"]
    if "role" in entry:
        meta["role"] = entry["role"]
    return spec.model_copy(update={"metadata": meta})
