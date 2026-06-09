from pathlib import Path

from rootseeker.skill_system import (
    DEFAULT_BUILTIN_SKILL_SLUG,
    build_registry_from_builtin_skills,
    get_default_log_triage_skill,
    parse_skill_document,
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def test_discover_and_load_builtin_default_log_triage() -> None:
    root = _repo_root()
    registry = build_registry_from_builtin_skills(root / "skills" / "builtin")
    spec = get_default_log_triage_skill(registry)
    assert spec.slug == DEFAULT_BUILTIN_SKILL_SLUG
    assert spec.source_kind.value == "builtin"
    assert spec.metadata.get("flow_plugin_id") == "builtin.default_log_triage_flow"
    assert any(s.action == "catalog.resolve_service" for s in spec.steps)


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
    assert len(spec.steps) == 1
