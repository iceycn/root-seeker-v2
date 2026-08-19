from pathlib import Path

import pytest

from rootseeker.contracts.case import CaseCreateRequest
from rootseeker.skill_system.errors import SkillError
from rootseeker.skill_system.overlay import SkillOverlayState, normalize_overlay_payload
from rootseeker.skill_system.playbook import PlaybookResolver
from rootseeker.skill_system.registry import SkillRegistry, build_skill_registry


def _write_skill(root: Path, name: str, *, role: str = "helper") -> None:
    d = root / name
    d.mkdir(parents=True)
    (d / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: d\nmetadata:\n  role: {role}\n---\n# {name}\n",
        encoding="utf-8",
    )


def _plain_request(**metadata: object) -> CaseCreateRequest:
    return CaseCreateRequest(
        title="t",
        symptom="s",
        service_name="svc",
        source="webhook",
        metadata=dict(metadata),
    )


@pytest.fixture
def skill_roots(tmp_path: Path) -> dict[str, Path]:
    builtin = tmp_path / "builtin"
    custom = tmp_path / "custom"
    external = tmp_path / "external"
    _write_skill(builtin, "default-log-triage", role="playbook")
    _write_skill(builtin, "code-lookup", role="helper")
    _write_skill(external, "my-db-triage", role="playbook")
    return {"builtin": builtin, "custom": custom, "external": external}


@pytest.fixture
def overlay() -> SkillOverlayState:
    return normalize_overlay_payload({})


@pytest.fixture
def registry(skill_roots: dict[str, Path], overlay: SkillOverlayState) -> SkillRegistry:
    return build_skill_registry(
        builtin_root=skill_roots["builtin"],
        custom_root=skill_roots["custom"],
        external_root=skill_roots["external"],
        overlay=overlay,
    )


@pytest.fixture
def resolver(registry: SkillRegistry, overlay: SkillOverlayState) -> PlaybookResolver:
    return PlaybookResolver(registry, overlay=overlay)


def test_set_default_rejects_helper(resolver: PlaybookResolver) -> None:
    with pytest.raises(SkillError) as exc:
        resolver.set_default("code-lookup")
    assert exc.value.code == "SKILL_NOT_PLAYBOOK"


def test_delete_builtin_rejected(resolver: PlaybookResolver) -> None:
    with pytest.raises(SkillError) as exc:
        resolver.delete_user_skill("default-log-triage")
    assert exc.value.code == "SKILL_BUILTIN_PROTECTED"


def test_disable_current_default_falls_back_to_builtin(resolver: PlaybookResolver) -> None:
    overlay = resolver.set_default("my-db-triage")
    overlay = resolver.set_enabled("my-db-triage", False)
    assert overlay.default_playbook == "default-log-triage"


def test_resolve_preferred_skill(resolver: PlaybookResolver) -> None:
    spec = resolver.resolve(
        CaseCreateRequest(
            title="t",
            symptom="s",
            service_name="svc",
            source="webhook",
            metadata={"preferred_skill": "my-db-triage"},
        )
    )
    assert spec.name == "my-db-triage"


def test_resolve_normalizes_preferred_skill(resolver: PlaybookResolver) -> None:
    spec = resolver.resolve(_plain_request(preferred_skill="flows/my-db-triage"))
    assert spec.name == "my-db-triage"


def test_resolve_normalizes_skill_slug(resolver: PlaybookResolver) -> None:
    spec = resolver.resolve(_plain_request(skill_slug="flows/my-db-triage"))
    assert spec.name == "my-db-triage"


def test_resolve_normalizes_selected_skills(resolver: PlaybookResolver) -> None:
    spec = resolver.resolve(_plain_request(selected_skills=["flows/my-db-triage"]))
    assert spec.name == "my-db-triage"


def test_set_default_is_held_and_used_by_later_resolve(resolver: PlaybookResolver) -> None:
    overlay = resolver.set_default("my-db-triage")
    assert overlay.default_playbook == "my-db-triage"
    spec = resolver.resolve(_plain_request())
    assert spec.name == "my-db-triage"


def test_set_default_rejects_disabled_playbook(resolver: PlaybookResolver) -> None:
    resolver.set_enabled("my-db-triage", False)
    with pytest.raises(SkillError) as exc:
        resolver.set_default("my-db-triage")
    assert exc.value.code == "SKILL_DEFAULT_UNAVAILABLE"


def test_disable_current_default_without_builtin_fallback_rejected(
    resolver: PlaybookResolver,
) -> None:
    resolver.set_default("my-db-triage")
    resolver.set_enabled("default-log-triage", False)
    with pytest.raises(SkillError) as exc:
        resolver.set_enabled("my-db-triage", False)
    assert exc.value.code == "SKILL_DEFAULT_REQUIRED"
    spec = resolver.resolve(_plain_request())
    assert spec.name == "my-db-triage"


def test_delete_current_default_falls_back_to_builtin(resolver: PlaybookResolver) -> None:
    resolver.set_default("my-db-triage")
    overlay = resolver.delete_user_skill("my-db-triage")
    assert overlay.default_playbook == "default-log-triage"
    assert resolver.registry.get("my-db-triage") is None


def test_delete_current_default_without_builtin_fallback_rejected(
    resolver: PlaybookResolver,
) -> None:
    resolver.set_default("my-db-triage")
    resolver.set_enabled("default-log-triage", False)
    with pytest.raises(SkillError) as exc:
        resolver.delete_user_skill("my-db-triage")
    assert exc.value.code == "SKILL_DEFAULT_REQUIRED"
    assert resolver.registry.get("my-db-triage") is not None


def test_resolve_falls_back_to_builtin_playbook(resolver: PlaybookResolver) -> None:
    spec = resolver.resolve(_plain_request())
    assert spec.name == "default-log-triage"


def test_resolve_unavailable_when_no_enabled_playbook(
    skill_roots: dict[str, Path],
) -> None:
    overlay = normalize_overlay_payload(
        {
            "default_playbook": "default-log-triage",
            "overlays": {
                "default-log-triage": {"enabled": False},
                "my-db-triage": {"enabled": False},
            },
        }
    )
    registry = build_skill_registry(
        builtin_root=skill_roots["builtin"],
        custom_root=skill_roots["custom"],
        external_root=skill_roots["external"],
        overlay=overlay,
    )
    resolver = PlaybookResolver(registry, overlay=overlay)
    with pytest.raises(SkillError) as exc:
        resolver.resolve(_plain_request())
    assert exc.value.code == "SKILL_DEFAULT_UNAVAILABLE"


def test_overlay_role_promotes_helper_to_playbook(
    skill_roots: dict[str, Path],
) -> None:
    overlay = normalize_overlay_payload(
        {
            "overlays": {"code-lookup": {"role": "playbook"}},
        }
    )
    registry = build_skill_registry(
        builtin_root=skill_roots["builtin"],
        custom_root=skill_roots["custom"],
        external_root=skill_roots["external"],
        overlay=overlay,
    )
    resolver = PlaybookResolver(registry, overlay=overlay)
    updated = resolver.set_default("code-lookup")
    assert updated.default_playbook == "code-lookup"
    spec = resolver.resolve(_plain_request())
    assert spec.name == "code-lookup"
