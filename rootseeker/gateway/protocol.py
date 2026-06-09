from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import Field

from rootseeker.contracts.common import RootSeekerModel, new_id, utc_now

__all__ = [
    "GatewayEventFrame",
    "GatewayFrameType",
    "GatewayRequestFrame",
    "GatewayResponseFrame",
]


class GatewayFrameType(StrEnum):
    REQUEST = "request"
    RESPONSE = "response"
    EVENT = "event"
    CONNECTED = "connected"
    PING = "ping"
    PONG = "pong"
    SUBSCRIBE = "subscribe"
    SUBSCRIBED = "subscribed"
    UNSUBSCRIBE = "unsubscribe"
    UNSUBSCRIBED = "unsubscribed"


class GatewayRequestFrame(RootSeekerModel):
    frame_type: GatewayFrameType = GatewayFrameType.REQUEST
    request_id: str = Field(default_factory=lambda: new_id("gw-req-"))
    method: str = Field(min_length=1)
    params: dict[str, Any] = Field(default_factory=dict)
    client_id: str | None = None
    protocol_version: str = "1.0"


class GatewayResponseFrame(RootSeekerModel):
    frame_type: GatewayFrameType = GatewayFrameType.RESPONSE
    request_id: str = Field(min_length=1)
    ok: bool = True
    result: dict[str, Any] = Field(default_factory=dict)
    error: dict[str, Any] | None = None
    protocol_version: str = "1.0"


class GatewayEventFrame(RootSeekerModel):
    frame_type: GatewayFrameType = GatewayFrameType.EVENT
    event_id: str = Field(default_factory=lambda: new_id("gw-evt-"))
    topic: str = Field(min_length=1)
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)
    protocol_version: str = "1.0"
