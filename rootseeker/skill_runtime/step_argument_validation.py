from __future__ import annotations

from typing import Any

from rootseeker.contracts.tool import ToolSpec

__all__ = ["validate_step_arguments"]


def validate_step_arguments(
    *,
    arguments: dict[str, Any],
    tool_spec: ToolSpec,
    skip: bool,
) -> str | None:
    if skip:
        return None
    schema = tool_spec.parameters_schema if isinstance(tool_spec.parameters_schema, dict) else {}
    properties = schema.get("properties")
    required = schema.get("required")
    if not isinstance(properties, dict):
        properties = {}
    if not isinstance(required, list):
        required = []
    if not arguments and required:
        return "empty arguments with required schema fields"
    for field in required:
        if not isinstance(field, str):
            continue
        value = arguments.get(field)
        if value is None or (isinstance(value, str) and not value.strip()):
            return f"missing required field: {field}"
    return None
