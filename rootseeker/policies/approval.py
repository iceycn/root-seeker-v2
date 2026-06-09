from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any, Protocol
from urllib import request as urllib_request
from urllib.error import URLError

from rootseeker.contracts.common import new_id, utc_now
from rootseeker.contracts.tool import ToolCallRequest, ToolSpec

__all__ = [
    "ApprovalEvent",
    "ApprovalEventSink",
    "ApprovalRequest",
    "ApprovalStatus",
    "ApprovalStore",
    "InMemoryApprovalEventSink",
    "WebhookApprovalEventSink",
]


class ApprovalStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


@dataclass(frozen=True)
class ApprovalEvent:
    event_type: str
    approval: ApprovalRequest
    actor: str = "system"
    reason: str = ""
    emitted_at: datetime = field(default_factory=utc_now)

    def to_payload(self) -> dict[str, Any]:
        return {
            "event_type": self.event_type,
            "actor": self.actor,
            "reason": self.reason,
            "emitted_at": self.emitted_at.isoformat(),
            "approval": self.approval.to_payload(),
        }


class ApprovalEventSink(Protocol):
    def emit(self, event: ApprovalEvent) -> None:
        """Publish an approval lifecycle event."""


class InMemoryApprovalEventSink:
    def __init__(self) -> None:
        self.events: list[ApprovalEvent] = []

    def emit(self, event: ApprovalEvent) -> None:
        self.events.append(event)


class WebhookApprovalEventSink:
    def __init__(self, url: str, *, timeout_seconds: float = 5.0) -> None:
        self.url = url
        self.timeout_seconds = timeout_seconds
        self.last_error: str | None = None

    def emit(self, event: ApprovalEvent) -> None:
        body = json.dumps(event.to_payload()).encode("utf-8")
        req = urllib_request.Request(
            self.url,
            data=body,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "rootseeker-approval-workflow/1.0",
            },
            method="POST",
        )
        try:
            with urllib_request.urlopen(req, timeout=self.timeout_seconds) as response:
                response.read()
            self.last_error = None
        except (OSError, URLError) as exc:
            self.last_error = str(exc)


@dataclass
class ApprovalRequest:
    approval_id: str
    case_id: str
    step_id: str
    tool_name: str
    permission_level: str
    reason: str
    status: ApprovalStatus = ApprovalStatus.PENDING
    requested_at: datetime = field(default_factory=utc_now)
    decided_at: datetime | None = None
    decided_by: str | None = None
    decision_reason: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        return {
            "approval_id": self.approval_id,
            "case_id": self.case_id,
            "step_id": self.step_id,
            "tool_name": self.tool_name,
            "permission_level": self.permission_level,
            "reason": self.reason,
            "status": self.status.value,
            "requested_at": self.requested_at.isoformat(),
            "decided_at": self.decided_at.isoformat() if self.decided_at else None,
            "decided_by": self.decided_by,
            "decision_reason": self.decision_reason,
            "metadata": dict(self.metadata),
        }


class ApprovalStore:
    def __init__(self, *, event_sink: ApprovalEventSink | None = None) -> None:
        self._items: dict[str, ApprovalRequest] = {}
        self._event_sink = event_sink
        self.last_event_error: str | None = None

    def create_for_tool(
        self,
        *,
        request: ToolCallRequest,
        spec: ToolSpec,
        reason: str,
    ) -> ApprovalRequest:
        return self.create_manual(
            case_id=request.case_id,
            step_id=request.step_id,
            tool_name=request.tool_name,
            permission_level=spec.permission_level.value,
            reason=reason,
            metadata={"argument_keys": sorted(request.arguments.keys())},
        )

    def create_manual(
        self,
        *,
        case_id: str,
        step_id: str,
        tool_name: str,
        permission_level: str,
        reason: str,
        metadata: dict[str, Any] | None = None,
    ) -> ApprovalRequest:
        approval = ApprovalRequest(
            approval_id=new_id("approval-"),
            case_id=case_id,
            step_id=step_id,
            tool_name=tool_name,
            permission_level=permission_level,
            reason=reason,
            metadata=dict(metadata or {}),
        )
        self._items[approval.approval_id] = approval
        self._emit("approval.requested", approval, reason=reason)
        return approval

    def get(self, approval_id: str) -> ApprovalRequest | None:
        return self._items.get(approval_id)

    def list(self, *, status: ApprovalStatus | str | None = None, limit: int = 200) -> list[ApprovalRequest]:
        items = list(self._items.values())
        if status is not None:
            expected = status if isinstance(status, ApprovalStatus) else ApprovalStatus(str(status))
            items = [item for item in items if item.status == expected]
        items.sort(key=lambda item: item.requested_at, reverse=True)
        return items[: max(0, limit)]

    def approve(self, approval_id: str, *, actor: str = "system", reason: str = "") -> ApprovalRequest:
        approval = self._require(approval_id)
        approval.status = ApprovalStatus.APPROVED
        approval.decided_at = utc_now()
        approval.decided_by = actor
        approval.decision_reason = reason
        self._emit("approval.approved", approval, actor=actor, reason=reason)
        return approval

    def reject(self, approval_id: str, *, actor: str = "system", reason: str = "") -> ApprovalRequest:
        approval = self._require(approval_id)
        approval.status = ApprovalStatus.REJECTED
        approval.decided_at = utc_now()
        approval.decided_by = actor
        approval.decision_reason = reason
        self._emit("approval.rejected", approval, actor=actor, reason=reason)
        return approval

    def is_approved_for(self, approval_id: str, *, request: ToolCallRequest, spec: ToolSpec) -> bool:
        approval = self.get(approval_id)
        if approval is None or approval.status != ApprovalStatus.APPROVED:
            return False
        return (
            approval.case_id == request.case_id
            and approval.step_id == request.step_id
            and approval.tool_name == request.tool_name
            and approval.permission_level == spec.permission_level.value
        )

    def _require(self, approval_id: str) -> ApprovalRequest:
        approval = self.get(approval_id)
        if approval is None:
            raise KeyError(f"approval not found: {approval_id}")
        return approval

    def _emit(
        self,
        event_type: str,
        approval: ApprovalRequest,
        *,
        actor: str = "system",
        reason: str = "",
    ) -> None:
        if self._event_sink is None:
            return
        try:
            self._event_sink.emit(
                ApprovalEvent(event_type=event_type, approval=approval, actor=actor, reason=reason)
            )
            self.last_event_error = None
        except Exception as exc:  # noqa: BLE001
            self.last_event_error = str(exc)
