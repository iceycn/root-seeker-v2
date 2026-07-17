from __future__ import annotations

from typing import Any

from rootseeker.contracts.audit import AuditCategory, AuditEvent
from rootseeker.contracts.common import new_id

__all__ = ["build_agent_event"]


def build_agent_event(
    *, action: str, actor: str, target: str, detail: dict[str, Any]
) -> AuditEvent:
    return AuditEvent(
        event_id=new_id("agent-evt-"),
        category=AuditCategory.SYSTEM,
        action=action,
        actor=actor,
        target=target,
        detail=dict(detail),
    )
