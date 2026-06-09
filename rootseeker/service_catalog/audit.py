from __future__ import annotations

from rootseeker.contracts.audit import AuditCategory, AuditEvent
from rootseeker.contracts.common import new_id

__all__ = ["build_catalog_audit_event"]


def build_catalog_audit_event(
    *,
    case_id: str,
    actor: str,
    service_name: str,
    tenant: str,
    environment: str,
) -> AuditEvent:
    return AuditEvent(
        event_id=new_id("audit-"),
        category=AuditCategory.TOOL_CALL,
        action="catalog.resolve_service",
        actor=actor,
        target=service_name,
        detail={
            "case_id": case_id,
            "tenant": tenant,
            "environment": environment,
            "service_name": service_name,
        },
    )
