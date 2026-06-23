from pathlib import Path

from rootseeker.skill_system import (
    DEFAULT_BUILTIN_SKILL_SLUG,
    build_registry_from_builtin_skills,
    get_default_log_triage_skill,
    parse_skill_document,
)
from rootseeker.skill_system.parser import ROOTSEEKER_SKILL_SPEC_FILENAME, load_skill_from_path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def test_discover_and_load_builtin_default_log_triage() -> None:
    root = _repo_root()
    registry = build_registry_from_builtin_skills(root / "skills" / "builtin")
    spec = get_default_log_triage_skill(registry)
    assert spec.slug == DEFAULT_BUILTIN_SKILL_SLUG
    assert spec.source_kind.value == "builtin"
    assert spec.metadata.get("flow_plugin_id") == "builtin.default_log_triage_flow"
    assert spec.steps[0].action == "incident.normalize"
    assert any(s.action == "catalog.resolve_service" for s in spec.steps)
    assert any(s.action == "repo.list" for s in spec.steps)


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


def test_load_standard_skill_with_rootseeker_sidecar(tmp_path: Path) -> None:
    skill_dir = tmp_path / "x"
    skill_dir.mkdir()
    skill_path = skill_dir / "SKILL.md"
    skill_path.write_text(
        """---
name: X
description: Standard Codex-style frontmatter
---
# X
""",
        encoding="utf-8",
    )
    (skill_dir / ROOTSEEKER_SKILL_SPEC_FILENAME).write_text(
        """slug: test/x
version: 0.0.1
source_kind: builtin
steps:
  - step_id: a
    name: A
    action: noop
""",
        encoding="utf-8",
    )

    spec = load_skill_from_path(skill_path)
    assert spec.name == "X"
    assert spec.description == "Standard Codex-style frontmatter"
    assert spec.slug == "test/x"
    assert len(spec.steps) == 1
