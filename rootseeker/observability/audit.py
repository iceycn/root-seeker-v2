from __future__ import annotations

from rootseeker.contracts.audit import AuditEvent

__all__ = ["InMemoryAuditLog"]


class InMemoryAuditLog:
    """Append-only in-memory audit trail with simple case-scoped queries."""

    def __init__(self) -> None:
        self._events: list[AuditEvent] = []

    def append(self, event: AuditEvent) -> None:
        self._events.append(event)

    def list_events(
        self,
        *,
        case_id: str | None = None,
        limit: int = 500,
    ) -> list[AuditEvent]:
        events = self._events
        if case_id is not None:
            events = [e for e in events if _event_matches_case(e, case_id)]
        if limit < 0:
            return list(events)
        return list(events[-limit:])

    def count(self) -> int:
        return len(self._events)


def _event_matches_case(event: AuditEvent, case_id: str) -> bool:
    if event.target == case_id:
        return True
    detail = event.detail
    return detail.get("case_id") == case_id
