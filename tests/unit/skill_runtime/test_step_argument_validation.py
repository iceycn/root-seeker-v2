from rootseeker.contracts.tool import ToolSpec
from rootseeker.skill_runtime.step_argument_validation import validate_step_arguments


def test_validate_step_arguments_accepts_skip() -> None:
    spec = ToolSpec(name="code.read", description="", server_name="internal")
    assert validate_step_arguments(arguments={}, tool_spec=spec, skip=True) is None


def test_validate_step_arguments_rejects_missing_required() -> None:
    spec = ToolSpec(
        name="log.query_by_trace_id",
        description="",
        server_name="internal",
        parameters_schema={
            "type": "object",
            "properties": {"trace_id": {"type": "string"}},
            "required": ["trace_id"],
        },
    )
    assert validate_step_arguments(arguments={}, tool_spec=spec, skip=False) is not None


def test_validate_step_arguments_accepts_required_fields() -> None:
    spec = ToolSpec(
        name="log.query_by_trace_id",
        description="",
        server_name="internal",
        parameters_schema={
            "type": "object",
            "properties": {"trace_id": {"type": "string"}},
            "required": ["trace_id"],
        },
    )
    assert (
        validate_step_arguments(arguments={"trace_id": "t1"}, tool_spec=spec, skip=False) is None
    )
