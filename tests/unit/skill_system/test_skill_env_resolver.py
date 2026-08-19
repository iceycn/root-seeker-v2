import pytest
from rootseeker.skill_system.env_resolver import resolve_skill_env
from rootseeker.skill_system.errors import SkillError


def test_priority_skill_overrides_runtime_and_process() -> None:
    result = resolve_skill_env(
        declared_keys=["FOO"],
        optional_keys=[],
        process_env={"FOO": "proc"},
        admin_items=[
            {"key": "FOO", "value": "runtime", "scope": "runtime", "secret": False},
            {"key": "FOO", "value": "skill", "scope": "skill", "secret": False},
        ],
    )
    assert result.mcp_extra["FOO"] == "skill"
    assert result.substitutions["FOO"] == "skill"


def test_secret_not_in_substitutions() -> None:
    result = resolve_skill_env(
        declared_keys=["TOKEN"],
        optional_keys=[],
        process_env={},
        admin_items=[{"key": "TOKEN", "value": "s3cret", "scope": "skill", "secret": True}],
    )
    assert result.mcp_extra["TOKEN"] == "s3cret"
    assert "TOKEN" not in result.substitutions


def test_undeclared_skill_scope_not_included() -> None:
    result = resolve_skill_env(
        declared_keys=[],
        optional_keys=[],
        process_env={},
        admin_items=[{"key": "SKILL_ONLY", "value": "x", "scope": "skill"}],
    )
    assert result.mcp_extra == {}


def test_missing_required_raises() -> None:
    with pytest.raises(SkillError) as exc:
        resolve_skill_env(
            declared_keys=["NEED"],
            optional_keys=[],
            process_env={},
            admin_items=[],
        )
    assert exc.value.code == "SKILL_ENV_MISSING"


def test_overlapping_declared_optional_missing_does_not_raise() -> None:
    result = resolve_skill_env(
        declared_keys=["OVERLAP"],
        optional_keys=["OVERLAP"],
        process_env={},
        admin_items=[],
    )
    assert "OVERLAP" not in result.missing
    assert result.mcp_extra == {}


def test_mcp_scope_item_is_ignored() -> None:
    result = resolve_skill_env(
        declared_keys=[],
        optional_keys=["FOO"],
        process_env={},
        admin_items=[{"key": "FOO", "value": "from-mcp", "scope": "mcp", "secret": False}],
    )
    assert result.mcp_extra == {}
    assert "FOO" not in result.substitutions


def test_require_false_records_missing_without_raising() -> None:
    result = resolve_skill_env(
        declared_keys=["NEED"],
        optional_keys=[],
        process_env={},
        admin_items=[],
        require=False,
    )
    assert result.missing == ["NEED"]
    assert result.mcp_extra == {}
