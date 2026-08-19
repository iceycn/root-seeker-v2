from pathlib import Path

import pytest

from rootseeker.contracts.skill import SkillKind, SkillSourceKind
from rootseeker.skill_system.errors import SkillError
from rootseeker.skill_system.parser import load_skill_from_path


def test_load_standard_skill_without_sidecar(tmp_path: Path) -> None:
    skill_dir = tmp_path / "code-lookup"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        """---
name: code-lookup
description: Search and read code related to an incident.
allowed-tools: code.search code.read code.find_callers
metadata:
  role: helper
  env:
    - ZOEK_URL
  env_optional:
    - ZOEK_URL
---
# Code lookup
Use code.search first.
""",
        encoding="utf-8",
    )
    spec = load_skill_from_path(skill_dir / "SKILL.md", source_kind=SkillSourceKind.CUSTOM)
    assert spec.name == "code-lookup"
    assert spec.slug == "code-lookup"
    assert spec.bound_tools == ["code.search", "code.read", "code.find_callers"]
    assert spec.metadata["role"] == "helper"
    assert spec.metadata["env"] == ["ZOEK_URL"]
    assert spec.source_kind == SkillSourceKind.CUSTOM
    assert spec.steps == []


def test_load_skill_rejects_name_directory_mismatch(tmp_path: Path) -> None:
    skill_dir = tmp_path / "foo"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        "---\nname: bar\ndescription: x\n---\n# x\n",
        encoding="utf-8",
    )
    with pytest.raises(SkillError) as exc:
        load_skill_from_path(skill_dir / "SKILL.md")
    assert exc.value.code == "SKILL_INVALID_PACKAGE"


def test_load_skill_ignores_sidecar_yaml(tmp_path: Path) -> None:
    skill_dir = tmp_path / "play"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        "---\nname: play\ndescription: p\nmetadata:\n  role: playbook\n---\n# p\n",
        encoding="utf-8",
    )
    (skill_dir / "rootseeker-skill.yaml").write_text(
        "slug: ignored\nsteps: [{step_id: a, name: A, action: noop}]\n",
        encoding="utf-8",
    )
    spec = load_skill_from_path(skill_dir / "SKILL.md")
    assert spec.steps == []
    assert spec.slug == "play"


def test_load_skill_kind_from_metadata_role(tmp_path: Path) -> None:
    helper_dir = tmp_path / "code-lookup"
    helper_dir.mkdir()
    (helper_dir / "SKILL.md").write_text(
        "---\nname: code-lookup\ndescription: h\nmetadata:\n  role: helper\n---\n# h\n",
        encoding="utf-8",
    )
    playbook_dir = tmp_path / "default-log-triage"
    playbook_dir.mkdir()
    (playbook_dir / "SKILL.md").write_text(
        "---\nname: default-log-triage\ndescription: p\nmetadata:\n  role: playbook\n---\n# p\n",
        encoding="utf-8",
    )
    helper = load_skill_from_path(helper_dir / "SKILL.md")
    playbook = load_skill_from_path(playbook_dir / "SKILL.md")
    assert helper.skill_kind == SkillKind.TOOL
    assert playbook.skill_kind == SkillKind.FLOW
