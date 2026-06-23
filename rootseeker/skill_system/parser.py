from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from rootseeker.contracts.skill import SkillSpec

ROOTSEEKER_SKILL_SPEC_FILENAME = "rootseeker-skill.yaml"

__all__ = ["ROOTSEEKER_SKILL_SPEC_FILENAME", "parse_skill_document", "load_skill_from_path"]


def _split_frontmatter(text: str) -> tuple[str, str]:
    raw = text.lstrip("\ufeff")
    lines = raw.splitlines()
    if not lines or lines[0].strip() != "---":
        raise ValueError("SKILL.md must start with YAML frontmatter (---)")
    end = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end = i
            break
    if end is None:
        raise ValueError("SKILL.md frontmatter not closed with ---")
    yaml_text = "\n".join(lines[1:end])
    body = "\n".join(lines[end + 1 :])
    return yaml_text, body


def parse_skill_document(text: str) -> SkillSpec:
    yaml_text, _body = _split_frontmatter(text)
    data = yaml.safe_load(yaml_text)
    if not isinstance(data, dict):
        raise ValueError("SKILL frontmatter must parse to a mapping")
    try:
        return SkillSpec.model_validate(_normalize_skill_dict(data))
    except ValidationError as e:
        raise ValueError(f"Invalid SkillSpec in SKILL.md: {e}") from e


def _normalize_skill_dict(data: dict[str, Any]) -> dict[str, Any]:
    out = dict(data)
    fp = out.pop("flow_plugin_id", None)
    if fp is not None:
        meta = dict(out.get("metadata") or {})
        meta["flow_plugin_id"] = fp
        out["metadata"] = meta
    return out


def _parse_frontmatter(text: str) -> dict[str, Any]:
    yaml_text, _body = _split_frontmatter(text)
    data = yaml.safe_load(yaml_text)
    if not isinstance(data, dict):
        raise ValueError("SKILL frontmatter must parse to a mapping")
    return data


def _parse_rootseeker_skill_spec(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{ROOTSEEKER_SKILL_SPEC_FILENAME} must parse to a mapping")
    return data


def load_skill_from_path(path: Path) -> SkillSpec:
    text = path.read_text(encoding="utf-8")
    sidecar = path.with_name(ROOTSEEKER_SKILL_SPEC_FILENAME)
    if not sidecar.exists():
        return parse_skill_document(text)
    frontmatter = _parse_frontmatter(text)
    data = _parse_rootseeker_skill_spec(sidecar)
    data.setdefault("name", frontmatter.get("name"))
    data.setdefault("description", frontmatter.get("description", ""))
    try:
        return SkillSpec.model_validate(_normalize_skill_dict(data))
    except ValidationError as e:
        raise ValueError(f"Invalid SkillSpec in {ROOTSEEKER_SKILL_SPEC_FILENAME}: {e}") from e
