from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class AuditCategory(StrEnum):
    TOOL_CALL = "tool_call"
    APPROVAL = "approval"
    STATE_CHANGE = "state_change"
    SECURITY = "security"
    SYSTEM = "system"


class AuditEvent(BaseModel):
    event_id: str = Field(min_length=1)
    category: AuditCategory
    action: str = Field(min_length=1, description="verb, e.g. mcp.invoke, case.transition")
    actor: str = Field(min_length=1, description="user id, system, or service principal")
    target: str = Field(
        min_length=1,
        description="resource id or logical target, e.g. case_id, tool_name",
    )
    trace_id: str | None = None
    request_id: str | None = None
    detail: dict[str, Any] = Field(default_factory=dict)
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
