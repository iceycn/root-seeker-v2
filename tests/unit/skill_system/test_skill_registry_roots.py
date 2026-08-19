from pathlib import Path

import pytest

from rootseeker.contracts.skill import SkillSourceKind, SkillSpec
from rootseeker.skill_system.overlay import SkillOverlayState, apply_overlay, normalize_overlay_payload
from rootseeker.skill_system.parser import load_skill_from_path
from rootseeker.skill_system.registry import SkillRegistry, build_skill_registry


def _write_skill(root: Path, name: str, *, role: str = "helper") -> None:
    d = root / name
    d.mkdir(parents=True)
    (d / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: d\nmetadata:\n  role: {role}\n---\n# {name}\n",
        encoding="utf-8",
    )


def test_build_skill_registry_scans_three_roots_and_applies_overlay(tmp_path: Path) -> None:
    builtin = tmp_path / "builtin"
    custom = tmp_path / "custom"
    external = tmp_path / "external"
    _write_skill(builtin, "default-log-triage", role="playbook")
    _write_skill(custom, "mine", role="helper")
    _write_skill(external, "installed", role="helper")
    overlay = normalize_overlay_payload(
        {
            "default_playbook": "flows/default-log-triage",
            "overlays": {
                "installed": {"enabled": True, "role": "playbook"},
                "mine": {"enabled": False},
            },
        }
    )
    assert overlay.default_playbook == "default-log-triage"
    registry = build_skill_registry(
        builtin_root=builtin, custom_root=custom, external_root=external, overlay=overlay
    )
    assert registry.get("default-log-triage").source_kind == SkillSourceKind.BUILTIN
    assert registry.get("installed").metadata["role"] == "playbook"
    assert registry.get("mine").metadata.get("enabled") is False


def test_build_skill_registry_skips_custom_and_external_for_builtin_names(
    tmp_path: Path,
) -> None:
    builtin = tmp_path / "builtin"
    custom = tmp_path / "custom"
    external = tmp_path / "external"
    _write_skill(builtin, "default-log-triage", role="playbook")
    _write_skill(custom, "default-log-triage", role="helper")
    _write_skill(external, "default-log-triage", role="helper")

    registry = build_skill_registry(
        builtin_root=builtin, custom_root=custom, external_root=external, overlay=None
    )

    spec = registry.get("default-log-triage")
    assert spec is not None
    assert spec.source_kind == SkillSourceKind.BUILTIN


def test_build_skill_registry_external_upserts_over_custom(tmp_path: Path) -> None:
    builtin = tmp_path / "builtin"
    custom = tmp_path / "custom"
    external = tmp_path / "external"
    builtin.mkdir()
    _write_skill(custom, "shared-one", role="helper")
    _write_skill(external, "shared-one", role="playbook")

    registry = build_skill_registry(
        builtin_root=builtin, custom_root=custom, external_root=external, overlay=None
    )

    spec = registry.get("shared-one")
    assert spec is not None
    assert spec.source_kind == SkillSourceKind.EXTERNAL


def test_skill_registry_indexes_by_normalized_slug() -> None:
    registry = SkillRegistry()
    spec = SkillSpec(name="foo", slug="flows/foo", source_kind=SkillSourceKind.BUILTIN)
    registry.register(spec)
    assert registry.get("foo") is spec
    assert registry.get("flows/foo") is spec


def test_skill_registry_register_rejects_duplicate_normalized_slug() -> None:
    registry = SkillRegistry()
    registry.register(SkillSpec(name="a", slug="flows/foo"))
    with pytest.raises(ValueError, match="Duplicate skill slug"):
        registry.register(SkillSpec(name="b", slug="foo"))
