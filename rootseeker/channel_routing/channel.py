from __future__ import annotations

from dataclasses import dataclass, field

__all__ = ["ChannelSpec"]


@dataclass
class ChannelSpec:
    channel_id: str
    inbound_enabled: bool = True
    outbound_enabled: bool = True
    capabilities: set[str] = field(default_factory=set)
