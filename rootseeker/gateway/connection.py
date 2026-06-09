from __future__ import annotations

from dataclasses import dataclass, field

from rootseeker.contracts.common import new_id, utc_now
from rootseeker.gateway.protocol import GatewayEventFrame

__all__ = ["GatewayConnection"]


@dataclass
class GatewayConnection:
    client_id: str = field(default_factory=lambda: new_id("gw-client-"))
    connected_at: str = field(default_factory=lambda: utc_now().isoformat())
    capabilities: set[str] = field(default_factory=set)
    subscriptions: set[str] = field(default_factory=set)
    inbox: list[GatewayEventFrame] = field(default_factory=list)

    def can(self, capability: str) -> bool:
        return capability in self.capabilities
