import pytest
from rootseeker.skill_system.errors import SkillError
from rootseeker.skill_system.names import normalize_skill_name, validate_skill_name


def test_normalize_strips_legacy_flow_prefix() -> None:
    assert normalize_skill_name("flows/default-log-triage") == "default-log-triage"
    assert normalize_skill_name("tools/code-lookup") == "code-lookup"
    assert normalize_skill_name("default-log-triage") == "default-log-triage"


def test_validate_skill_name_rejects_uppercase_and_spaces() -> None:
    with pytest.raises(SkillError) as exc:
        validate_skill_name("Code lookup")
    assert exc.value.code == "SKILL_INVALID_PACKAGE"
