from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class ToolPermissionLevel(StrEnum):
    READ = "read"
    WRITE = "write"
    ADMIN = "admin"


class ToolScope(StrEnum):
    INTERNAL = "internal"
    EXTERNAL = "external"


class ToolSpec(BaseModel):
    name: str = Field(min_length=1)
    description: str = ""
    permission_level: ToolPermissionLevel = ToolPermissionLevel.READ
    scope: ToolScope = ToolScope.INTERNAL
    parameters_schema: dict[str, Any] = Field(default_factory=dict)
    server_name: str = Field(min_length=1)
    tags: list[str] = Field(default_factory=list)


class ToolCallRequest(BaseModel):
    case_id: str = Field(min_length=1)
    step_id: str = Field(min_length=1)
    skill_name: str = Field(min_length=1)
    tool_name: str = Field(min_length=1)
    arguments: dict[str, Any] = Field(default_factory=dict)
    requested_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ToolError(BaseModel):
    code: str = Field(min_length=1)
    message: str = Field(min_length=1)
    details: dict[str, Any] = Field(default_factory=dict)
    retryable: bool = False


class ToolCallResult(BaseModel):
    ok: bool
    tool_name: str = Field(min_length=1)
    content: dict[str, Any] = Field(default_factory=dict)
    error: ToolError | None = None
    latency_ms: int = Field(default=0, ge=0)
    finished_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
