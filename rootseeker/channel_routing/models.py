from __future__ import annotations

from typing import Any

from pydantic import Field

from rootseeker.contracts.common import RootSeekerModel

__all__ = [
    "ChannelMessage",
    "NormalizedInboundMessage",
    "OutboundTarget",
    "ResolvedRoute",
]


class ChannelMessage(RootSeekerModel):
    channel: str = Field(min_length=1)
    payload: dict[str, Any] = Field(default_factory=dict)
    headers: dict[str, str] = Field(default_factory=dict)
    remote_ip: str | None = None


class NormalizedInboundMessage(RootSeekerModel):
    channel: str = Field(min_length=1)
    tenant: str = "demo"
    environment: str = "prod"
    service_name: str = Field(min_length=1)
    severity: str = "warning"
    team: str = "unknown"
    title: str = Field(min_length=1)
    symptom: str = Field(min_length=1)
    trace_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ResolvedRoute(RootSeekerModel):
    channel: str = Field(min_length=1)
    tenant: str = Field(min_length=1)
    team: str = Field(min_length=1)
    priority: str = "normal"
    labels: dict[str, str] = Field(default_factory=dict)


class OutboundTarget(RootSeekerModel):
    channel: str = Field(min_length=1)
    endpoint: str = Field(min_length=1)
    team: str = Field(min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)
