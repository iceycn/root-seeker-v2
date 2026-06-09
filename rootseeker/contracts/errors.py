from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import Field

from rootseeker.contracts.common import RootSeekerModel

__all__ = ["ErrorShape", "FailureEnvelope", "StandardErrorCode"]


class StandardErrorCode(StrEnum):
    VALIDATION_ERROR = "validation_error"
    NOT_FOUND = "not_found"
    CONFLICT = "conflict"
    UNAUTHORIZED = "unauthorized"
    FORBIDDEN = "forbidden"
    INTERNAL = "internal_error"
    TOOL_ERROR = "tool_error"
    TIMEOUT = "timeout"


class ErrorShape(RootSeekerModel):
    code: str = Field(min_length=1)
    message: str = Field(min_length=1)
    details: dict[str, Any] = Field(default_factory=dict)


class FailureEnvelope(RootSeekerModel):
    """Uniform API/tool failure wrapper (T1 common error shape)."""

    ok: Literal[False] = False
    error: ErrorShape
