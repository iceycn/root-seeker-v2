from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from rootseeker.contracts.plugin import PluginManifest

__all__ = ["load_manifest_from_path", "manifest_from_dict"]


def _normalize_keys(raw: dict[str, Any]) -> dict[str, Any]:
    data = dict(raw)
    if "plugin_id" not in data and "id" in data:
        data["plugin_id"] = data.pop("id")
    if "display_name" not in data and "name" in data:
        data["display_name"] = data.pop("name")
    if "entry_point" not in data and "entrypoint" in data:
        data["entry_point"] = data.pop("entrypoint")
    return data


def manifest_from_dict(raw: dict[str, Any]) -> PluginManifest:
    try:
        return PluginManifest.model_validate(_normalize_keys(raw))
    except ValidationError as e:
        raise ValueError(f"Invalid plugin manifest: {e}") from e


def load_manifest_from_path(path: Path) -> PluginManifest:
    text = path.read_text(encoding="utf-8")
    data = yaml.safe_load(text)
    if not isinstance(data, dict):
        raise ValueError(f"Plugin manifest must be a mapping: {path}")
    return manifest_from_dict(data)
