from pathlib import Path

from rootseeker.contracts.skill import SkillKind
from rootseeker.skill_system import (
    DEFAULT_BUILTIN_SKILL_SLUG,
    build_registry_from_builtin_skills,
    get_default_log_triage_skill,
    parse_skill_document,
)
from rootseeker.skill_system.registry import DEFAULT_FLOW_SKILL_SLUG, build_skill_registry


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def test_discover_and_load_builtin_default_log_triage() -> None:
    root = _repo_root()
    registry = build_registry_from_builtin_skills(root / "skills" / "builtin")
    spec = get_default_log_triage_skill(registry)
    assert spec.slug == DEFAULT_BUILTIN_SKILL_SLUG
    assert spec.name == "default-log-triage"
    assert spec.source_kind.value == "builtin"
    assert spec.metadata.get("role") == "playbook"
    assert spec.steps == []
    assert "incident.normalize" in spec.bound_tools
    sidecar = root / "skills" / "builtin" / "default-log-triage" / "rootseeker-skill.yaml"
    assert not sidecar.exists()


def test_builtin_default_playbook_is_standard_package() -> None:
    root = Path(__file__).resolve().parents[3]
    registry = build_skill_registry(
        builtin_root=root / "skills" / "builtin",
        custom_root=root / "skills" / "custom",
        external_root=root / "skills" / "external",
        overlay=None,
    )
    spec = registry.get("default-log-triage")
    assert spec.name == "default-log-triage"
    assert spec.metadata.get("role") == "playbook"
    assert "incident.normalize" in spec.bound_tools
    assert spec.steps == []
    assert not (root / "skills" / "builtin" / "default-log-triage" / "rootseeker-skill.yaml").exists()
    assert DEFAULT_FLOW_SKILL_SLUG == "default-log-triage"


def test_builtin_helper_is_tool_and_playbook_is_flow() -> None:
    root = _repo_root()
    registry = build_skill_registry(
        builtin_root=root / "skills" / "builtin",
        custom_root=root / "skills" / "custom",
        external_root=root / "skills" / "external",
        overlay=None,
    )
    helper = registry.get("code-lookup")
    playbook = registry.get("default-log-triage")
    assert helper.skill_kind == SkillKind.TOOL
    assert playbook.skill_kind == SkillKind.FLOW


def test_parse_skill_document_minimal() -> None:
    text = """---
name: X
slug: test/x
version: 0.0.1
source_kind: builtin
steps:
  - step_id: a
    name: A
    action: noop
---
# Body
hello
"""
    spec = parse_skill_document(text)
    assert spec.slug == "test/x"
