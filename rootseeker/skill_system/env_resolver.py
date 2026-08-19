from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from rootseeker.skill_system.errors import SkillError


@dataclass(frozen=True)
class SkillEnvResolution:
    mcp_extra: dict[str, str]
    substitutions: dict[str, str]
    missing: list[str]


def substitute_non_secret(text: str, substitutions: dict[str, str]) -> str:
    for key, value in substitutions.items():
        text = text.replace("${" + key + "}", value)
    return text


def _resolve_key(
    key: str,
    process_env: dict[str, str],
    runtime_items: dict[str, dict[str, Any]],
    skill_items: dict[str, dict[str, Any]],
) -> tuple[str | None, bool]:
    value = process_env.get(key)
    is_secret = False

    if key in runtime_items:
        value = runtime_items[key]["value"]
        is_secret = bool(runtime_items[key].get("secret"))

    if key in skill_items:
        value = skill_items[key]["value"]
        is_secret = bool(skill_items[key].get("secret"))

    return value, is_secret


def resolve_skill_env(
    *,
    declared_keys: list[str],
    optional_keys: list[str],
    process_env: dict[str, str],
    admin_items: list[dict[str, Any]],
    require: bool = True,
) -> SkillEnvResolution:
    runtime_items: dict[str, dict[str, Any]] = {}
    skill_items: dict[str, dict[str, Any]] = {}

    for item in admin_items:
        key = item.get("key") or ""
        if not key:
            continue
        scope = item.get("scope", "runtime")
        if scope == "mcp":
            continue
        if scope == "skill":
            skill_items[key] = item
        else:
            runtime_items[key] = item

    mcp_extra: dict[str, str] = {}
    substitutions: dict[str, str] = {}

    for key in declared_keys:
        value, is_secret = _resolve_key(key, process_env, runtime_items, skill_items)
        if value is not None:
            mcp_extra[key] = value
            if not is_secret:
                substitutions[key] = value

    for key in optional_keys:
        if key in mcp_extra:
            continue
        value, is_secret = _resolve_key(key, process_env, runtime_items, skill_items)
        if value is not None:
            mcp_extra[key] = value
            if not is_secret:
                substitutions[key] = value

    optional_set = set(optional_keys)
    missing = [
        key for key in declared_keys if key not in mcp_extra and key not in optional_set
    ]

    if missing and require:
        raise SkillError(
            "SKILL_ENV_MISSING",
            f"Missing required env keys: {', '.join(missing)}",
        )

    return SkillEnvResolution(
        mcp_extra=mcp_extra,
        substitutions=substitutions,
        missing=missing,
    )
